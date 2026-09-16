"""Offline checks for request bounds, source age, scoring and selective reads."""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import requests

from advisor_runtime import sleeper_live as live


class RequestCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patcher = mock.patch.object(live, "CACHE_DIR", Path(self.directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_short_timeout_and_cache_preserve_original_observation(self):
        response = mock.Mock()
        response.json.return_value = {"week": 4}
        session = mock.Mock()
        session.get.return_value = response
        first, second = {}, {}
        with mock.patch.object(live, "_session", return_value=session):
            self.assertEqual(live._get_json("https://example.test/state", provenance=first, source="state"), {"week": 4})
            self.assertEqual(live._get_json("https://example.test/state", provenance=second, source="state"), {"week": 4})
        session.get.assert_called_once_with("https://example.test/state", timeout=(3.05, 8.0))
        self.assertEqual(first["state"]["fetched_at_utc"], second["state"]["fetched_at_utc"])
        self.assertEqual(second["state"]["cache"], "local_60s")
        response.close.assert_called_once()

    def test_expired_cache_never_becomes_silent_live_fallback(self):
        response = mock.Mock()
        response.json.return_value = {"week": 4}
        session = mock.Mock()
        session.get.return_value = response
        with mock.patch.object(live, "_session", return_value=session):
            live._get_json("https://example.test/state")
            path = next(live.CACHE_DIR.glob("*.json"))
            envelope = json.loads(path.read_text())
            envelope["fetched_at"] = time.time() - 61
            path.write_text(json.dumps(envelope))
            session.get.side_effect = requests.Timeout("timeout")
            with self.assertRaises(requests.Timeout):
                live._get_json("https://example.test/state")

    def test_retry_after_cannot_trigger_automatic_retries(self):
        session = live._session()
        retry = session.get_adapter("https://").max_retries
        self.assertEqual(retry.total, 0)


class LiveContextTests(unittest.TestCase):
    players = {
        "qb": {"name": "Quarter Back", "pos": "QB", "status": "Active"},
        "rb": {"name": "Running Back", "pos": "RB", "injury_status": "OUT"},
    }

    def fake_get(self, url, **kwargs):
        if self.barrier is not None and url.rsplit("/", 1)[-1] in {"nfl", "league1", "rosters", "users"}:
            self.barrier.wait(timeout=2)
        self.urls.append(url)
        provenance = kwargs.get("provenance")
        if provenance is not None:
            provenance[kwargs["source"]] = {
                "fetched_at_utc": "2026-09-10T00:00:00+00:00", "cache": "network", "age_seconds": 0,
            }
        if "transactions/" in url:
            return []
        if "projections/nfl/" in url:
            if self.projection_error:
                raise requests.Timeout("projection timeout")
            return [
                {"player_id": "qb", "stats": {"pass_yd": 250}, "player": {"position": "QB", "team": "ABC"}},
                {"player_id": "rb", "stats": {"pts_ppr": 16}, "player": {"position": "RB", "injury_status": None, "status": "Active"}},
            ]
        if "/matchups/" in url:
            return []
        if url.endswith("/state/nfl"):
            return {"week": 4, "season": "2026"}
        if url.endswith("/league/league1"):
            return {"season": "2026", "roster_positions": ["QB", "RB", "BN"], "scoring_settings": {"pass_yd": 0.04, "rush_yd": 0.1}}
        if url.endswith("/rosters"):
            return [{"roster_id": 9, "owner_id": "user", "players": ["qb", "rb"], "starters": ["qb", "rb"]}]
        if url.endswith("/users"):
            return [{"user_id": "user", "display_name": "Reeve"}]
        raise AssertionError(url)

    def setUp(self):
        self.urls = []
        self.barrier = None
        self.projection_error = False

    def context(self, **kwargs):
        with mock.patch.object(live, "_get_json", side_effect=self.fake_get):
            return live.fetch_live_context("league1", 9, self.players, **kwargs)

    def test_independent_facts_run_concurrently_and_skip_transactions(self):
        self.barrier = threading.Barrier(4)
        context = self.context()
        self.assertEqual(len(self.urls), 6)
        self.assertFalse(any("transactions/" in url for url in self.urls))
        self.assertEqual(context["source_provenance"]["rosters"]["age_seconds"], 0)

    def test_transactions_are_only_fetched_on_request(self):
        context = self.context(include_transactions=True)
        self.assertEqual(sum("transactions/" in url for url in self.urls), 3)
        self.assertTrue(context["transactions_requested"])

    def test_missing_scoring_components_remain_null_with_live_metadata(self):
        context = self.context()
        self.assertEqual(context["current_lineup"][0]["points"], 10)
        self.assertIsNone(context["current_lineup"][1]["points"])
        self.assertIsNone(context["current_lineup_total"])
        self.assertEqual(context["current_lineup_known_subtotal"], 10)
        self.assertIn("injury_status", context["player_metadata_by_id"]["rb"])
        self.assertIsNone(context["player_metadata_by_id"]["rb"]["injury_status"])

    def test_optional_projection_failure_preserves_current_ownership(self):
        self.projection_error = True
        context = self.context()
        self.assertEqual(context["owner_by_player"], {"qb": 9, "rb": 9})
        self.assertIsNone(context["current_lineup_total"])
        self.assertTrue(context["runtime_warnings"])

    def test_no_ppr_or_nonfinite_fallback(self):
        self.assertIsNone(live._score({"pts_ppr": 20}, {"rec": 0.5}))
        self.assertIsNone(live._score({"rush_yd": float("nan")}, {"rush_yd": 0.1}))
        self.assertEqual(live._score({"rush_yd": 0}, {"rush_yd": 0.1}), 0)


if __name__ == "__main__":
    unittest.main()
