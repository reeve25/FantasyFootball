"""T5: offline tests for the backtest harness. No test in this file makes a
network request -- fetch_realized_stats's own network call is mocked at
sleeper_live._get_json; run_backtest/score_event_player tests inject a fake
realized_fetcher directly instead.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from advisor_runtime import backtest


FETCHED_AT = "2026-09-11T12:00:00.000000+00:00"  # well before kickoff
KICKOFF = "2026-09-14T17:00:00.000Z"


def event_metadata(kickoff=KICKOFF):
    return {
        "sport_id": "FOOTBALL", "league_id": "NFL", "season_week": "Week 3",
        "status": {"startsAt": kickoff}, "teams": {},
    }


def line_row(side, price, **changes):
    row = dict(
        row_type="line", source="SportsGameOdds", event_id="evt1",
        player_id="TEST_TE_1_NFL", book="b", market="rec_yd", line=50.5,
        side=side, price=price, fetched_at_utc=FETCHED_AT,
        player_name="Test TE", event_metadata=event_metadata(),
    )
    row.update(changes)
    return row


def projection_row(points, week=3, **changes):
    row = dict(
        row_type="projection", source="engine_projection", player_id="999",
        player_name="Test TE", week=week, points=points, stats={},
        fetched_at_utc=FETCHED_AT,
    )
    row.update(changes)
    return row


def write_snapshot(directory: Path, name: str, rows: list[dict]) -> Path:
    path = directory / name
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return path


ENGINE_PLAYERS = [{"pid": "999", "name": "Test TE", "pos": "TE"}]
SCORING = {"rec_yd": 0.1}


class ScanPreKickoffEventsTests(unittest.TestCase):
    def test_finds_a_pre_kickoff_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_snapshot(Path(tmp), "a.jsonl", [line_row("over", -110)])
            events = backtest.scan_pre_kickoff_events(Path(tmp))
            self.assertEqual(events["evt1"]["season_week"], 3)
            self.assertEqual(events["evt1"]["snapshot_path"], path)

    def test_excludes_rows_fetched_at_or_after_kickoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            late = dict(line_row("over", -110), fetched_at_utc="2026-09-15T00:00:00+00:00")
            write_snapshot(Path(tmp), "a.jsonl", [late])
            self.assertEqual(backtest.scan_pre_kickoff_events(Path(tmp)), {})

    def test_excludes_rows_without_t2c_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_format = dict(line_row("over", -110))
            old_format.pop("event_metadata")
            old_format.pop("player_name")
            write_snapshot(Path(tmp), "a.jsonl", [old_format])
            self.assertEqual(backtest.scan_pre_kickoff_events(Path(tmp)), {})

    def test_keeps_the_earliest_qualifying_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            earlier = dict(line_row("over", -110), fetched_at_utc="2026-09-10T00:00:00+00:00")
            later = dict(line_row("over", -110), fetched_at_utc="2026-09-11T00:00:00+00:00")
            write_snapshot(Path(tmp), "a-later.jsonl", [later])
            write_snapshot(Path(tmp), "b-earlier.jsonl", [earlier])
            events = backtest.scan_pre_kickoff_events(Path(tmp))
            self.assertEqual(events["evt1"]["snapshot_fetched_at"], "2026-09-10T00:00:00+00:00")


class EventPlayersTests(unittest.TestCase):
    def test_resolves_provider_name_to_sleeper_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_snapshot(Path(tmp), "a.jsonl", [line_row("over", -110), line_row("under", -110)])
            event_info = {"snapshot_path": path, "season_week": 3}
            players = backtest.event_players("evt1", event_info, ENGINE_PLAYERS)
            self.assertEqual(players, [{"pid": "999", "name": "Test TE", "pos": "TE"}])

    def test_unresolvable_provider_name_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = line_row("over", -110, player_name="Totally Unknown Player")
            path = write_snapshot(Path(tmp), "a.jsonl", [row])
            event_info = {"snapshot_path": path, "season_week": 3}
            self.assertEqual(backtest.event_players("evt1", event_info, ENGINE_PLAYERS), [])


class HistoricalSleeperProjectionTests(unittest.TestCase):
    def test_reads_the_stored_projection_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_snapshot(Path(tmp), "a.jsonl", [projection_row(8.0)])
            self.assertEqual(backtest.historical_sleeper_projection(path, "999", 3), 8.0)

    def test_none_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_snapshot(Path(tmp), "a.jsonl", [])
            self.assertIsNone(backtest.historical_sleeper_projection(path, "999", 3))


class ScoreEventPlayerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = write_snapshot(
            Path(self.tmp.name), "a.jsonl",
            [line_row("over", -110), line_row("under", -110), projection_row(8.0)],
        )
        self.event_info = {"snapshot_path": self.path, "season_week": 3, "event_id": "evt1"}
        self.player = {"pid": "999", "name": "Test TE", "pos": "TE"}

    def test_scores_anchored_and_consensus_counterfactual_against_the_same_outcome(self):
        realized = {"999": {"played": True, "stats": {"rec_yd": 60.0}}}
        record = backtest.score_event_player(
            "evt1", self.event_info, self.player, scoring=SCORING, realized=realized,
        )
        self.assertEqual(record["realized_fp"], 6.0)  # 60.0 * 0.1
        self.assertAlmostEqual(record["anchored"]["market_anchor"], 5.05)  # 50.5 * 0.1
        self.assertAlmostEqual(record["anchored"]["market_anchor_blend"], 5.05)
        self.assertEqual(record["anchored"]["sleeper_projection_feed"], 8.0)
        self.assertAlmostEqual(record["anchored"]["error"]["market_anchor"], 0.95)
        self.assertAlmostEqual(record["anchored"]["error"]["sleeper_projection_feed"], 2.0)
        self.assertEqual(record["consensus_counterfactual"]["market_anchor_blend"], 8.0)
        self.assertAlmostEqual(record["consensus_counterfactual"]["error"]["market_anchor_blend"], 2.0)

    def test_none_when_player_did_not_play(self):
        realized = {"999": {"played": False, "stats": {}}}
        self.assertIsNone(
            backtest.score_event_player("evt1", self.event_info, self.player, scoring=SCORING, realized=realized)
        )

    def test_none_when_player_absent_from_realized_stats(self):
        self.assertIsNone(
            backtest.score_event_player("evt1", self.event_info, self.player, scoring=SCORING, realized={})
        )


class SummarizeTests(unittest.TestCase):
    def test_aggregates_mae_and_anchored_vs_consensus_diff(self):
        records = [
            {
                "anchored": {"error": {"market_anchor": 1.0, "market_anchor_blend": 1.0, "sleeper_projection_feed": 3.0}},
                "consensus_counterfactual": {"error": {"market_anchor_blend": 3.0}},
            },
            {
                "anchored": {"error": {"market_anchor": 2.0, "market_anchor_blend": 2.0, "sleeper_projection_feed": 4.0}},
                "consensus_counterfactual": {"error": {"market_anchor_blend": 4.0}},
            },
        ]
        summary = backtest.summarize(records)
        self.assertEqual(summary["mae_by_source"]["market_anchor"], 1.5)
        self.assertEqual(summary["mae_by_source"]["market_anchor_blend"], 1.5)
        self.assertEqual(summary["mae_by_source"]["sleeper_projection_feed"], 3.5)
        diff = summary["anchored_vs_consensus_counterfactual"]
        self.assertEqual(diff["anchored_blend_mae"], 1.5)
        self.assertEqual(diff["consensus_only_blend_mae"], 3.5)
        self.assertEqual(diff["anchored_minus_consensus_mae"], -2.0)

    def test_missing_values_are_excluded_not_zero_filled(self):
        records = [{
            "anchored": {"error": {"market_anchor": None, "market_anchor_blend": 1.0, "sleeper_projection_feed": None}},
            "consensus_counterfactual": {"error": {"market_anchor_blend": None}},
        }]
        summary = backtest.summarize(records)
        self.assertIsNone(summary["mae_by_source"]["market_anchor"])
        self.assertEqual(summary["n_by_source"]["market_anchor"], 0)
        self.assertEqual(summary["anchored_vs_consensus_counterfactual"]["n"], 0)


class RunBacktestTests(unittest.TestCase):
    def test_no_eligible_weeks_when_history_is_empty(self):
        with tempfile.TemporaryDirectory() as history, tempfile.TemporaryDirectory() as out:
            result = backtest.run_backtest(
                history_dir=Path(history), engine_players=ENGINE_PLAYERS, scoring=SCORING,
                season="2026", out_dir=Path(out),
            )
            self.assertEqual(result["status"], "no_eligible_weeks")
            self.assertEqual(result["player_weeks_scored"], 0)
            self.assertTrue((Path(out) / f"{result['run_id']}.json").exists())

    def test_no_eligible_weeks_when_nobody_has_played_yet(self):
        with tempfile.TemporaryDirectory() as history, tempfile.TemporaryDirectory() as out:
            write_snapshot(Path(history), "a.jsonl", [line_row("over", -110), line_row("under", -110)])
            result = backtest.run_backtest(
                history_dir=Path(history), engine_players=ENGINE_PLAYERS, scoring=SCORING,
                season="2026", out_dir=Path(out),
                realized_fetcher=lambda season, week: {"999": {"played": False, "stats": {}}},
            )
            self.assertEqual(result["status"], "no_eligible_weeks")
            self.assertEqual(result["candidate_events"], 1)

    def test_scores_a_real_eligible_week_end_to_end_and_writes_files(self):
        with tempfile.TemporaryDirectory() as history, tempfile.TemporaryDirectory() as out:
            write_snapshot(
                Path(history), "a.jsonl",
                [line_row("over", -110), line_row("under", -110), projection_row(8.0)],
            )
            result = backtest.run_backtest(
                history_dir=Path(history), engine_players=ENGINE_PLAYERS, scoring=SCORING,
                season="2026", out_dir=Path(out),
                realized_fetcher=lambda season, week: {"999": {"played": True, "stats": {"rec_yd": 60.0}}},
            )
            self.assertEqual(result["status"], "scored")
            self.assertEqual(result["player_weeks_scored"], 1)
            self.assertEqual(result["records"][0]["pid"], "999")

            run_path = Path(out) / f"{result['run_id']}.json"
            self.assertTrue(run_path.exists())
            summary = json.loads((Path(out) / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["latest"]["run_id"], result["run_id"])
            self.assertEqual(len(summary["runs"]), 1)

    def test_second_run_appends_to_the_rolling_summary(self):
        with tempfile.TemporaryDirectory() as history, tempfile.TemporaryDirectory() as out:
            for _ in range(2):
                backtest.run_backtest(
                    history_dir=Path(history), engine_players=ENGINE_PLAYERS, scoring=SCORING,
                    season="2026", out_dir=Path(out),
                )
            summary = json.loads((Path(out) / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(len(summary["runs"]), 2)

    def test_write_false_produces_no_files(self):
        with tempfile.TemporaryDirectory() as history, tempfile.TemporaryDirectory() as out:
            backtest.run_backtest(
                history_dir=Path(history), engine_players=ENGINE_PLAYERS, scoring=SCORING,
                season="2026", out_dir=Path(out), write=False,
            )
            self.assertEqual(list(Path(out).glob("*")), [])


class FetchRealizedStatsTests(unittest.TestCase):
    def test_parses_played_and_numeric_stats_only(self):
        fixture = [
            {"player_id": "999", "stats": {"gp": 1.0, "rec_yd": 60.0, "note": "x"}},
            {"player_id": "1000", "stats": {"gp": 0.0}},
            {"player_id": None, "stats": {"gp": 1.0}},
        ]
        with mock.patch.object(backtest.sleeper_live, "_get_json", return_value=fixture):
            result = backtest.fetch_realized_stats("2026", 3)
        self.assertEqual(result["999"], {"played": True, "stats": {"gp": 1.0, "rec_yd": 60.0}})
        self.assertEqual(result["1000"]["played"], False)
        self.assertNotIn(None, result)


if __name__ == "__main__":
    unittest.main()
