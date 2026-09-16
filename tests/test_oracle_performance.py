"""Offline regression tests for bounded acquisition and equivalent lineup math."""
import importlib.util
import os
from pathlib import Path
import pickle
import tempfile
import threading
import time
import unittest
from unittest import mock


ENGINE = Path(__file__).resolve().parents[1] / "advisor_runtime" / "engine" / "ff_v6_3.py"
spec = importlib.util.spec_from_file_location("oracle_performance", ENGINE)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class OraclePerformanceTests(unittest.TestCase):
    def test_roster_only_math_matches_full_board_with_flex_and_waivers(self):
        val, mat = {}, {}
        for i in range(240):
            pos = ["QB", "RB", "WR", "TE"][i % 4]
            name = f"Player {i}"
            val[str(i)] = (float(i % 29), pos, name)
            mat[engine.norm(name, pos)] = {w: float((i * w) % 29) for w in (1, 2, 3)}
        roster = [str(i) for i in range(16)] + ["unmodeled"]
        pool = {"QB": [(10, "Available QB", {1: 9, 2: 12, 3: 15})]}
        for week in (1, 2, 3):
            full = {pid: (mat[engine.norm(name, pos)][week], pos, name)
                    for pid, (_, pos, name) in val.items()}
            full["__FA_QB"] = (pool["QB"][0][2][week], "QB", "Available QB")
            expected = engine.best8(roster + ["__FA_QB"], full)
            self.assertEqual(engine._pg_week(roster, val, mat, {}, pool, week), expected)
        before = engine._pg_week(roster, val, mat, {}, None, 1)
        mat[engine.norm("Player 0", "QB")][1] = 200.0
        after = engine._pg_week(roster, val, mat, {}, None, 1)
        self.assertGreater(after, before)

    def test_cost_does_not_grow_with_unrelated_players(self):
        class RosterLookupOnly(dict):
            def items(self):
                raise AssertionError("lineup scoring scanned the entire league player board")

        val = RosterLookupOnly({"q": (20.0, "QB", "Roster Quarterback")})
        result = engine._pg_week(["q"], val, {engine.norm("Roster Quarterback", "QB"): {1: 20}}, {}, None, 1)
        self.assertEqual(result, 20.0)

    def test_weekly_requests_are_parallel_bounded_and_ordered(self):
        lock = threading.Lock()
        counters = {"active": 0, "peak": 0}

        def response(url, **kwargs):
            self.assertEqual(kwargs["timeout"], engine.WEEKLY_REQUEST_TIMEOUT)
            with lock:
                counters["active"] += 1
                counters["peak"] = max(counters["peak"], counters["active"])
            time.sleep(0.015)
            with lock:
                counters["active"] -= 1
            return mock.Mock(json=lambda: [{"week": int(url)}], raise_for_status=lambda: None)

        with mock.patch.object(engine.requests, "get", side_effect=response):
            result = engine._weekly_payloads(range(1, 10), str, {}, "Fixture")
        self.assertEqual([week for week, payload in result], list(range(1, 10)))
        self.assertGreater(counters["peak"], 1)
        self.assertLessEqual(counters["peak"], 4)

    def test_failed_force_refresh_preserves_bytes_and_timestamp(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(engine, "CACHE", directory):
            path = Path(directory) / "weekly.pkl"
            path.write_bytes(pickle.dumps({"previous": "complete"}))
            stamp = time.time() - 86400
            os.utime(path, (stamp, stamp))
            previous_bytes = path.read_bytes()
            with mock.patch.object(engine, "src_weekly", side_effect=RuntimeError("upstream timeout")):
                with self.assertRaises(RuntimeError):
                    engine.weekly_cached(force=True)
            self.assertEqual(path.read_bytes(), previous_bytes)
            self.assertAlmostEqual(path.stat().st_mtime, stamp, places=3)
            self.assertGreater(engine.cache_info("weekly")["age_hours"], 23.99)

    def test_successful_cache_read_does_not_reset_fetch_time(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(engine, "CACHE", directory):
            engine._cached("sample", lambda: {"value": 7}, 60)
            stamp = (Path(directory) / "sample.pkl").stat().st_mtime
            value = engine._cached("sample", lambda: self.fail("cache should have been read"), 60)
            self.assertEqual(value, {"value": 7})
            self.assertEqual((Path(directory) / "sample.pkl").stat().st_mtime, stamp)
            self.assertFalse(list(Path(directory).glob("*.tmp")))

    def test_partial_or_error_weekly_payload_is_not_cached(self):
        def response(url, **kwargs):
            if url == "2":
                raise engine.requests.Timeout("fixture timeout")
            return mock.Mock(json=lambda: [{"week": int(url)}], raise_for_status=lambda: None)

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(engine, "CACHE", directory):
            with mock.patch.object(engine.requests, "get", side_effect=response):
                with self.assertRaisesRegex(RuntimeError, "week 2: Timeout"):
                    engine._cached("partial", lambda: engine._weekly_payloads([1, 2, 3], str, {}, "Fixture"), 3600)
            self.assertFalse((Path(directory) / "partial.pkl").exists())


if __name__ == "__main__":
    unittest.main()
