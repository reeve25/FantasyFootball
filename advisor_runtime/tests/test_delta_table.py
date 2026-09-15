"""T6: offline tests for the delta table and its anti-double-count guard.
No test in this file makes a network request."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from advisor_runtime import delta_table as dt


def event_metadata(week="Week 1"):
    return {"season_week": week, "status": {"startsAt": "2026-09-14T17:00:00Z"}}


def line_row(book, market, side, line, price, *, event_id="e1", player_id="SGO1",
             fetched_at="T0", week="Week 1", player_name="Test Player"):
    return {
        "row_type": "line", "source": "SportsGameOdds", "event_id": event_id,
        "player_id": player_id, "book": book, "market": market, "side": side,
        "line": line, "price": price, "fetched_at_utc": fetched_at,
        "player_name": player_name, "event_metadata": event_metadata(week),
    }


def projection_row(points, *, player_id="999", week=1, fetched_at="T0", player_name="Test Player"):
    return {
        "row_type": "projection", "source": "engine_projection", "player_id": player_id,
        "player_name": player_name, "week": week, "points": points, "stats": {},
        "fetched_at_utc": fetched_at,
    }


class ComputeLineDeltasTests(unittest.TestCase):
    def test_matching_key_produces_line_and_price_move(self):
        baseline = [line_row("fanduel", "rec_yd", "over", 24.5, 230, fetched_at="T0")]
        current = [line_row("fanduel", "rec_yd", "over", 10.5, -115, fetched_at="T1")]
        deltas = dt.compute_line_deltas(baseline, current)
        self.assertEqual(len(deltas), 1)
        row = deltas[0]
        self.assertEqual(row["row_type"], "delta")
        self.assertEqual(row["delta_kind"], "line")
        self.assertAlmostEqual(row["line_move"], -14.0)
        self.assertAlmostEqual(row["price_move"], -345.0)
        self.assertEqual(row["season_week"], 1)

    def test_key_only_in_one_snapshot_is_skipped_not_zero_filled(self):
        baseline = [line_row("fanduel", "rec_yd", "over", 24.5, 230)]
        current = [line_row("draftkings", "rec_yd", "over", 10.5, -115)]
        self.assertEqual(dt.compute_line_deltas(baseline, current), [])

    def test_stable_line_reports_zero_move(self):
        baseline = [line_row("fanduel", "rec", "over", 1.5, 140, fetched_at="T0")]
        current = [line_row("fanduel", "rec", "over", 1.5, 155, fetched_at="T1")]
        row = dt.compute_line_deltas(baseline, current)[0]
        self.assertEqual(row["line_move"], 0.0)
        self.assertAlmostEqual(row["price_move"], 15.0)

    def test_week_mismatch_between_snapshots_leaves_season_week_none(self):
        baseline = [line_row("fanduel", "rec_yd", "over", 24.5, 230, week="Week 1")]
        current = [line_row("fanduel", "rec_yd", "over", 10.5, -115, week="Week 2")]
        row = dt.compute_line_deltas(baseline, current)[0]
        self.assertIsNone(row["season_week"])

    def test_non_line_rows_are_ignored(self):
        baseline = [projection_row(5.0)]
        current = [projection_row(6.0)]
        self.assertEqual(dt.compute_line_deltas(baseline, current), [])


class ComputeProjectionDeltasTests(unittest.TestCase):
    def test_matching_player_week_produces_points_move(self):
        baseline = [projection_row(3.074, fetched_at="T0")]
        current = [projection_row(3.068, fetched_at="T1")]
        row = dt.compute_projection_deltas(baseline, current)[0]
        self.assertEqual(row["delta_kind"], "projection")
        self.assertAlmostEqual(row["points_move"], -0.006)

    def test_missing_baseline_projection_is_skipped(self):
        current = [projection_row(3.215)]
        self.assertEqual(dt.compute_projection_deltas([], current), [])


class ComputeDeltasTests(unittest.TestCase):
    def test_combines_both_kinds(self):
        baseline = [line_row("fanduel", "rec_yd", "over", 24.5, 230), projection_row(3.0)]
        current = [line_row("fanduel", "rec_yd", "over", 10.5, -115), projection_row(3.2)]
        kinds = {row["delta_kind"] for row in dt.compute_deltas(baseline, current)}
        self.assertEqual(kinds, {"line", "projection"})


class WriteDeltaSnapshotTests(unittest.TestCase):
    def test_writes_a_new_file_and_never_touches_the_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline_path = tmp_path / "baseline.jsonl"
            current_path = tmp_path / "current.jsonl"
            baseline_path.write_text(json.dumps(line_row("fanduel", "rec_yd", "over", 24.5, 230)) + "\n")
            current_path.write_text(json.dumps(line_row("fanduel", "rec_yd", "over", 10.5, -115)) + "\n")
            baseline_before = baseline_path.read_text()
            current_before = current_path.read_text()

            result = dt.write_delta_snapshot(baseline_path, current_path, out_dir=tmp_path)

            self.assertEqual(result["status"], "written")
            self.assertEqual(result["rows"], 1)
            self.assertEqual(result["line_deltas"], 1)
            self.assertEqual(baseline_path.read_text(), baseline_before)
            self.assertEqual(current_path.read_text(), current_before)
            written = Path(result["path"])
            self.assertTrue(written.exists())
            row = json.loads(written.read_text().splitlines()[0])
            self.assertEqual(row["row_type"], "delta")
            self.assertEqual(row["baseline_snapshot_path"], str(baseline_path))

    def test_second_call_creates_a_distinct_file_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline_path = tmp_path / "baseline.jsonl"
            current_path = tmp_path / "current.jsonl"
            baseline_path.write_text(json.dumps(line_row("fanduel", "rec_yd", "over", 24.5, 230)) + "\n")
            current_path.write_text(json.dumps(line_row("fanduel", "rec_yd", "over", 10.5, -115)) + "\n")
            first = dt.write_delta_snapshot(baseline_path, current_path, out_dir=tmp_path)
            second = dt.write_delta_snapshot(baseline_path, current_path, out_dir=tmp_path)
            self.assertNotEqual(first["path"], second["path"])


ENGINE_PLAYERS = [{"pid": "8117", "name": "Jalen Tolbert", "pos": "WR"}]


class BuildPricedInGuardTests(unittest.TestCase):
    def test_real_price_drop_flags_a_matching_negative_assumption_priced_in(self):
        baseline = [line_row("betmgm", "rec_yd", "over", 24.5, 230.0, player_id="JALEN_TOLBERT_1_NFL", player_name="Jalen Tolbert")]
        current = [line_row("betmgm", "rec_yd", "over", 10.5, -115.0, player_id="JALEN_TOLBERT_1_NFL", player_name="Jalen Tolbert")]
        deltas = dt.compute_line_deltas(baseline, current)
        guard = dt.build_priced_in_guard(deltas, ENGINE_PLAYERS)
        assumption = {
            "player": "8117", "week_range": [1, 1], "stat_affected": "rec_yd",
            "delta": -14.0, "confidence": 0.6, "rationale": "test", "source": "test",
            "half_life_weeks": 4.0,
        }
        self.assertTrue(guard(assumption, 1))

    def test_stable_line_does_not_flag_a_related_assumption(self):
        baseline = [line_row("fanduel", "rec", "over", 1.5, 140.0, player_id="JALEN_TOLBERT_1_NFL", player_name="Jalen Tolbert")]
        current = [line_row("fanduel", "rec", "over", 1.5, 155.0, player_id="JALEN_TOLBERT_1_NFL", player_name="Jalen Tolbert")]
        deltas = dt.compute_line_deltas(baseline, current)
        guard = dt.build_priced_in_guard(deltas, ENGINE_PLAYERS)
        assumption = {
            "player": "8117", "week_range": [1, 1], "stat_affected": "rec",
            "delta": -1.0, "confidence": 0.5, "rationale": "test", "source": "test",
            "half_life_weeks": 4.0,
        }
        self.assertIs(guard(assumption, 1), False)

    def test_opposite_direction_move_is_not_treated_as_priced_in(self):
        baseline = [line_row("betmgm", "rec_yd", "over", 10.5, -115.0, player_id="JALEN_TOLBERT_1_NFL", player_name="Jalen Tolbert")]
        current = [line_row("betmgm", "rec_yd", "over", 24.5, 230.0, player_id="JALEN_TOLBERT_1_NFL", player_name="Jalen Tolbert")]
        deltas = dt.compute_line_deltas(baseline, current)
        guard = dt.build_priced_in_guard(deltas, ENGINE_PLAYERS)
        assumption = {
            "player": "8117", "week_range": [1, 1], "stat_affected": "rec_yd",
            "delta": -14.0, "confidence": 0.6, "rationale": "test", "source": "test",
            "half_life_weeks": 4.0,
        }
        self.assertIs(guard(assumption, 1), False)

    def test_below_threshold_move_is_not_flagged(self):
        baseline = [line_row("fanduel", "rec_yd", "over", 24.5, -110.0, player_id="JALEN_TOLBERT_1_NFL", player_name="Jalen Tolbert")]
        current = [line_row("fanduel", "rec_yd", "over", 23.5, -110.0, player_id="JALEN_TOLBERT_1_NFL", player_name="Jalen Tolbert")]
        deltas = dt.compute_line_deltas(baseline, current)
        guard = dt.build_priced_in_guard(deltas, ENGINE_PLAYERS, line_move_threshold=3.0)
        assumption = {
            "player": "8117", "week_range": [1, 1], "stat_affected": "rec_yd",
            "delta": -5.0, "confidence": 0.6, "rationale": "test", "source": "test",
            "half_life_weeks": 4.0,
        }
        self.assertIs(guard(assumption, 1), False)

    def test_non_market_stat_is_always_unknown(self):
        guard = dt.build_priced_in_guard([], ENGINE_PLAYERS)
        for stat in ("fantasy_points", "p_active"):
            assumption = {
                "player": "8117", "week_range": [1, 1], "stat_affected": stat,
                "delta": -1.0 if stat == "p_active" else -2.0, "confidence": 0.5,
                "rationale": "test", "source": "test", "half_life_weeks": 4.0,
            }
            if stat == "p_active":
                assumption["type"] = "injury"
            self.assertIsNone(guard(assumption, 1))

    def test_unresolvable_player_identity_is_unknown(self):
        baseline = [line_row("betmgm", "rec_yd", "over", 24.5, 230.0, player_id="JALEN_TOLBERT_1_NFL")]
        current = [line_row("betmgm", "rec_yd", "over", 10.5, -115.0, player_id="JALEN_TOLBERT_1_NFL")]
        deltas = dt.compute_line_deltas(baseline, current)
        guard = dt.build_priced_in_guard(deltas, [{"pid": "1", "name": "Nobody Else", "pos": "WR"}])
        assumption = {
            "player": "1", "week_range": [1, 1], "stat_affected": "rec_yd",
            "delta": -14.0, "confidence": 0.6, "rationale": "test", "source": "test",
            "half_life_weeks": 4.0,
        }
        self.assertIsNone(guard(assumption, 1))

    def test_wrong_week_is_unknown_not_a_guess(self):
        baseline = [line_row("betmgm", "rec_yd", "over", 24.5, 230.0, player_id="JALEN_TOLBERT_1_NFL", player_name="Jalen Tolbert", week="Week 1")]
        current = [line_row("betmgm", "rec_yd", "over", 10.5, -115.0, player_id="JALEN_TOLBERT_1_NFL", player_name="Jalen Tolbert", week="Week 1")]
        deltas = dt.compute_line_deltas(baseline, current)
        guard = dt.build_priced_in_guard(deltas, ENGINE_PLAYERS)
        assumption = {
            "player": "8117", "week_range": [2, 2], "stat_affected": "rec_yd",
            "delta": -14.0, "confidence": 0.6, "rationale": "test", "source": "test",
            "half_life_weeks": 4.0,
        }
        self.assertIsNone(guard(assumption, 2))


if __name__ == "__main__":
    unittest.main()
