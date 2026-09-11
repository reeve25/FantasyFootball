"""Offline regressions for evidence freshness, timing and trade claims."""
import datetime as dt
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from advisor_runtime import advisor as a


class EvidenceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 9, 10, 23, tzinfo=dt.timezone.utc)
        self.clock = mock.patch.object(a, "utc_now", return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def snapshot(self):
        stamp = self.now.isoformat()
        return {
            "schema_version": 2, "generated_at_utc": stamp,
            "engine": {"source_cache_fetched_at_utc": {"sleeper_projection_feed": stamp, "espn": stamp}},
            "league": {"current_week": 1, "season_end_week": 3, "starter_slots": ["WR"],
                       "roster_positions": ["WR", "BN"], "live_refreshed_at_utc": stamp},
            "players": {
                "a": {"pid": "a", "name": "Alpha", "pos": "WR", "weekly_points": {"1": 30, "2": 10, "3": 10},
                      "weekly_points_by_source": {source: {"1": 30, "2": 10, "3": 10} for source in ("espn", "sleeper_projection_feed")}},
                "b": {"pid": "b", "name": "Beta", "pos": "WR", "weekly_points": {"1": 10, "2": 12, "3": 12},
                      "weekly_points_by_source": {source: {"1": 10, "2": 12, "3": 12} for source in ("espn", "sleeper_projection_feed")}},
            },
            "rosters": [{"roster_id": 9, "player_ids": ["a"]}, {"roster_id": 4, "player_ids": ["b"]}],
        }

    def terms(self):
        return {"terms_explicit": True, "perspective_rid": 9, "other_rid": 4,
                "give_ids": ["a"], "get_ids": ["b"], "give": ["Alpha"], "get": ["Beta"]}

    def test_new_snapshot_does_not_freshen_old_sources(self):
        snapshot = self.snapshot()
        snapshot["engine"]["source_cache_fetched_at_utc"]["espn"] = (self.now - dt.timedelta(days=2)).isoformat()
        freshness = a.evidence_freshness(snapshot)
        self.assertFalse(freshness["all_projection_sources_fresh"])
        self.assertEqual(freshness["projection_sources"]["espn"]["status"], "stale")

    def test_unknown_source_and_offline_ownership_are_unverified(self):
        snapshot = self.snapshot()
        snapshot["engine"] = {}
        snapshot["league"].pop("live_refreshed_at_utc")
        freshness = a.evidence_freshness(snapshot)
        self.assertFalse(freshness["all_projection_sources_fresh"])
        self.assertEqual(freshness["rosters"]["status"], "unverified")

    def test_incomplete_ros_is_not_divided_by_missing_weeks(self):
        summary = a._ros_summary({"weekly_points": {"1": 17}}, list(range(1, 18)))
        self.assertIsNone(summary["projection_pg"])
        self.assertEqual(summary["projection_state"], "partial_weekly")
        self.assertEqual(summary["projection_horizon"]["known_week_mean_pg"], 17)
        self.assertEqual(summary["projection_horizon"]["projected_weeks"], 1)

    def test_known_zero_and_bye_remain_distinct_from_missing(self):
        summary = a._ros_summary({"weekly_points": {"1": 10, "3": 0}, "bye_weeks": [2]}, [1, 2, 3])
        self.assertTrue(summary["projection_horizon"]["complete"])
        self.assertEqual(summary["projection_pg"], 5)

    def test_loading_legacy_snapshot_repairs_false_ros(self):
        snapshot = self.snapshot()
        snapshot["players"]["a"]["weekly_points"] = {"1": 10}
        snapshot["players"]["a"]["projection_pg"] = 3.333
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            with mock.patch.object(a, "SNAPSHOT_PATH", path):
                loaded = a.load_snapshot()
        self.assertIsNone(loaded["players"]["a"]["projection_pg"])

    def test_live_null_injury_clears_old_out_and_unknown_points_do_not_halve(self):
        snapshot = self.snapshot()
        snapshot["players"]["a"]["injury_status"] = "Out"
        live = {"week": 1, "refreshed_at_utc": self.now.isoformat(),
                "player_metadata_by_id": {"a": {"injury_status": None, "team": "NEW"}},
                "projection_by_player": {"a": {"points": None}}}
        player = a._sync_live(snapshot, live)["players"]["a"]
        self.assertIsNone(player["injury_status"])
        self.assertEqual(player["team"], "NEW")
        self.assertEqual(player["weekly_points"]["1"], 30)

    def test_unknown_timing_starts_next_week_and_excludes_played_advantage(self):
        snapshot, terms = self.snapshot(), self.terms()
        terms.update(a.trade_horizon(snapshot, terms))
        result = a.evaluate_trade(snapshot, terms)
        self.assertEqual(result["weeks"], [2, 3])
        self.assertEqual(result["perspective_delta_pg"], 2)

    def test_past_game_excludes_current_week_even_if_requested(self):
        snapshot = self.snapshot()
        for player in snapshot["players"].values():
            player["game_date"] = (self.now + dt.timedelta(days=3)).isoformat()
        snapshot["players"]["a"]["game_date"] = (self.now - dt.timedelta(hours=2)).isoformat()
        self.assertEqual(a.trade_horizon(snapshot, {**self.terms(), "effective_week": 1})["effective_week"], 2)

    def test_all_games_future_allow_current_week(self):
        snapshot = self.snapshot()
        for player in snapshot["players"].values():
            player["game_date"] = (self.now + dt.timedelta(days=3)).isoformat()
        self.assertEqual(a.trade_horizon(snapshot, self.terms())["effective_week"], 1)

    def test_projection_gains_cannot_become_actionable_without_market_value(self):
        result = {"perspective_delta_pg": 2, "counterparty_delta_pg": 1,
                  "independent_projection_checks": {source: {"perspective_delta_pg": 2, "counterparty_delta_pg": 1} for source in ("espn", "sleeper_projection_feed")}}
        validation = a._trade_validation(self.snapshot(), result)
        self.assertTrue(validation["projection_edge_supported"])
        self.assertFalse(validation["actionable"])
        self.assertIsNone(validation["acceptance_probability"])

    def test_counterparty_loss_and_single_source_block_winning_claim(self):
        result = {"perspective_delta_pg": 2, "counterparty_delta_pg": -1,
                  "independent_projection_checks": {"espn": {"perspective_delta_pg": 2, "counterparty_delta_pg": -1}}}
        validation = a._trade_validation(self.snapshot(), result)
        self.assertIn("counterparty_projected_loss", validation["reason_codes"])
        self.assertIn("fewer_than_two_complete_projection_sources", validation["reason_codes"])
        self.assertFalse(validation["projection_edge_supported"])


if __name__ == "__main__":
    unittest.main()
