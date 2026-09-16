"""Integration routing and complete self-test discovery, without network access."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ff_entrypoint_extra", ROOT / "ff.py")
ff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ff)


class EntrypointIntegrationTests(unittest.TestCase):
    def test_backtest_require_scored_is_a_non_vacuous_acceptance_gate(self):
        from advisor_runtime import advisor as a
        from advisor_runtime import backtest
        from advisor_runtime import sleeper_live

        cases = (
            ({"status": "no_eligible_weeks", "player_weeks_scored": 0}, 3, False),
            ({"status": "scored", "player_weeks_scored": 1}, 0, True),
        )
        for result, expected_code, expected_passed in cases:
            with self.subTest(status=result["status"]), tempfile.TemporaryDirectory() as directory:
                checkpoint = Path(directory) / "evidence.json"
                with (
                    mock.patch.dict(os.environ, {"FF_CHECKPOINT": str(checkpoint)}),
                    mock.patch.object(
                        sleeper_live,
                        "fetch_live_context",
                        return_value={"season": "2026", "scoring_settings": {"rec": 1.0}},
                    ),
                    mock.patch.object(
                        a,
                        "ensure_snapshot",
                        return_value={"players": {"p1": {"pid": "p1"}}},
                    ),
                    mock.patch.object(backtest, "run_backtest", return_value=dict(result)),
                ):
                    code = ff.worker(
                        ff.parser().parse_args(["backtest", "--require-scored"])
                    )

                saved = json.loads(checkpoint.read_text(encoding="utf-8"))
                self.assertEqual(code, expected_code)
                self.assertEqual(saved["acceptance"]["passed"], expected_passed)
                self.assertEqual(
                    saved["acceptance"]["requirement"],
                    "status=scored and player_weeks_scored>0",
                )

        with mock.patch.object(ff, "worker", return_value=3):
            self.assertEqual(
                ff.main(["--_worker", "backtest", "--require-scored"]),
                3,
            )

    def test_market_refresh_implies_market_and_forwards_cache_bypass(self):
        from advisor_runtime import advisor as a
        from advisor_runtime import market_sources
        player = {"name": "Drake London"}
        snapshot = {"players": {"player": player}, "rosters": [], "league": {}}
        for flag, force_refresh in (("--market", False), ("--market-refresh", True)):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory:
                checkpoint = Path(directory) / "evidence.json"
                with (
                    mock.patch.dict(os.environ, {"FF_CHECKPOINT": str(checkpoint)}),
                    mock.patch.object(a, "load_snapshot", return_value=snapshot),
                    mock.patch.object(a, "_sync_live", return_value=snapshot),
                    mock.patch.object(a, "build_packet", return_value={"status": "ok"}),
                    mock.patch.object(a, "match_players", return_value=[player]),
                    mock.patch.object(a, "focused_expert_packet"),
                    mock.patch.dict(a.CONFIG),
                    mock.patch.object(market_sources, "focused_market_packet", return_value={
                        "line_snapshot": {"status": "written"},
                    }) as fetch,
                ):
                    ff.worker(ff.parser().parse_args([
                        "packet", "Show sportsbook lines for Drake London", "--offline", flag,
                    ]))
                fetch.assert_called_once_with(
                    [player], deep=False, force_refresh=force_refresh, projection_universe=[player]
                )
                self.assertEqual(
                    json.loads(checkpoint.read_text())["market_evidence"]["line_snapshot"],
                    {"status": "written"},
                )

    def test_market_refresh_snapshots_projections_for_full_player_universe(self):
        from advisor_runtime import advisor as a
        from advisor_runtime import market_sources
        player = {"name": "Drake London"}
        bench = {"name": "Bench Guy"}
        snapshot = {"players": {"player": player, "bench": bench}, "rosters": [], "league": {}}
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "evidence.json"
            with (
                mock.patch.dict(os.environ, {"FF_CHECKPOINT": str(checkpoint)}),
                mock.patch.object(a, "load_snapshot", return_value=snapshot),
                mock.patch.object(a, "_sync_live", return_value=snapshot),
                mock.patch.object(a, "build_packet", return_value={"status": "ok"}),
                mock.patch.object(a, "match_players", return_value=[player]),
                mock.patch.object(a, "focused_expert_packet"),
                mock.patch.dict(a.CONFIG),
                mock.patch.object(market_sources, "focused_market_packet", return_value={
                    "line_snapshot": {"status": "written"},
                }) as fetch,
            ):
                ff.worker(ff.parser().parse_args([
                    "packet", "Show sportsbook lines for Drake London", "--offline", "--market",
                ]))
            self.assertEqual(fetch.call_args.args, ([player],))
            self.assertEqual(
                {p["name"] for p in fetch.call_args.kwargs["projection_universe"]},
                {"Drake London", "Bench Guy"},
            )

    def test_market_status_is_honest_when_no_player_is_named(self):
        from advisor_runtime import advisor as a
        from advisor_runtime import market_sources
        snapshot = {"players": {}, "rosters": [], "league": {}}
        for command, question in (
            ("lineup", "Show my exact submitted lineup projected total"),
            ("rankings", "Rank every team in league"),
        ):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                checkpoint = Path(directory) / "evidence.json"
                with (
                    mock.patch.dict(os.environ, {"FF_CHECKPOINT": str(checkpoint)}),
                    mock.patch.object(a, "load_snapshot", return_value=snapshot),
                    mock.patch.object(a, "_sync_live", return_value=snapshot),
                    mock.patch.object(a, "build_packet", return_value={"status": "ok"}),
                    mock.patch.object(a, "match_players", return_value=[]),
                    mock.patch.object(a, "focused_expert_packet"),
                    mock.patch.dict(a.CONFIG),
                    mock.patch.object(market_sources, "focused_market_packet") as fetch,
                ):
                    ff.worker(ff.parser().parse_args([command, "--offline", "--market"]))
                fetch.assert_not_called()
                status = json.loads(checkpoint.read_text())["market_status"]
                self.assertNotEqual(status, "not_requested; use --market when it can change this decision")
                self.assertIn("requested but skipped", status)
                self.assertIn(command, status)

    def test_lost_book_coverage_warning_is_surfaced_in_the_saved_packet(self):
        from advisor_runtime import advisor as a
        from advisor_runtime import market_sources
        player = {"name": "Drake London"}
        snapshot = {"players": {"player": player}, "rosters": [], "league": {}}
        coverage_warning = (
            "Lost sportsbook coverage: Drake London had posted lines in the "
            "previous market-history snapshot and has none in this fetch."
        )
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "evidence.json"
            with (
                mock.patch.dict(os.environ, {"FF_CHECKPOINT": str(checkpoint)}),
                mock.patch.object(a, "load_snapshot", return_value=snapshot),
                mock.patch.object(a, "_sync_live", return_value=snapshot),
                mock.patch.object(a, "build_packet", return_value={"status": "ok", "warnings": ["unrelated"]}),
                mock.patch.object(a, "match_players", return_value=[player]),
                mock.patch.object(a, "focused_expert_packet"),
                mock.patch.dict(a.CONFIG),
                mock.patch.object(market_sources, "focused_market_packet", return_value={
                    "line_snapshot": {"status": "written"},
                    "coverage_warnings": [coverage_warning],
                }),
            ):
                ff.worker(ff.parser().parse_args([
                    "packet", "Show sportsbook lines for Drake London", "--offline", "--market",
                ]))
            saved = json.loads(checkpoint.read_text())
            self.assertEqual(saved["warnings"][0], coverage_warning)
            self.assertIn("unrelated", saved["warnings"])

    def test_selftest_runs_both_directories_and_preserves_failure(self):
        results = [subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0)]
        with mock.patch.object(ff.subprocess, "run", side_effect=results) as run:
            self.assertEqual(ff.main(["selftest"]), 1)
        self.assertEqual([call.args[0][-2] for call in run.call_args_list], ["advisor_runtime/tests", "tests"])
        self.assertLessEqual(run.call_args_list[1].kwargs["timeout"], run.call_args_list[0].kwargs["timeout"])

    def test_missing_snapshot_does_not_crash_before_live_or_offline_packet(self):
        from advisor_runtime import advisor as a
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "evidence.json"
            with (
                mock.patch.dict(os.environ, {"FF_CHECKPOINT": str(checkpoint)}),
                mock.patch.object(a, "load_snapshot", side_effect=FileNotFoundError()),
                mock.patch.object(a, "build_packet", return_value={"status": "usable_partial"}),
                mock.patch.object(a, "focused_expert_packet"),
                mock.patch.dict(a.CONFIG),
            ):
                ff.worker(ff.parser().parse_args(["packet", "Compare players", "--offline"]))
            self.assertEqual(json.loads(checkpoint.read_text())["status"], "usable_partial")

    def test_packet_transaction_intent_requests_transaction_reads(self):
        from advisor_runtime import advisor as a
        from advisor_runtime import sleeper_live
        snapshot = {"players": {}, "rosters": [], "league": {}}
        with tempfile.TemporaryDirectory() as directory:
            with (
                mock.patch.dict(os.environ, {"FF_CHECKPOINT": str(Path(directory) / "evidence.json")}),
                mock.patch.object(a, "load_snapshot", return_value=snapshot),
                mock.patch.object(a, "build_packet", return_value={"status": "ok"}),
                mock.patch.object(a, "focused_expert_packet"),
                mock.patch.dict(a.CONFIG),
                mock.patch.object(sleeper_live, "fetch_live_context", return_value=None) as fetch,
            ):
                ff.worker(ff.parser().parse_args(["packet", "Show recent completed trades and transactions"]))
            self.assertTrue(fetch.call_args.kwargs["include_transactions"])


    def test_packet_conversational_trade_resolves_terms_and_decision_report(self):
        from advisor_runtime import advisor as a
        give_player = {"pid": "p1", "name": "Drake London", "pos": "WR", "owner_roster_id": 9}
        get_player = {"pid": "p2", "name": "Kenneth Walker", "pos": "RB", "owner_roster_id": 1}
        snapshot = {
            "players": {"p1": give_player, "p2": get_player},
            "rosters": [
                {"roster_id": 9, "manager": "Reeve", "player_ids": ["p1"]},
                {"roster_id": 1, "manager": "Other", "player_ids": ["p2"]},
            ],
            "league": {"starter_slots": ["WR", "RB"], "current_week": 1},
        }
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "evidence.json"
            fake_trade_math = {
                "perspective_delta_pg": 0.75,
                "perspective_playoff_delta_pg": -0.1,
                "min_ppg_shift_to_flip": 0.75,
                "counterparty_delta_pg": -2.0,
            }
            with (
                mock.patch.dict(os.environ, {"FF_CHECKPOINT": str(checkpoint)}),
                mock.patch.object(a, "load_snapshot", return_value=snapshot),
                mock.patch.object(a, "_sync_live", return_value=snapshot),
                mock.patch.object(a, "focused_expert_packet"),
                mock.patch.dict(a.CONFIG),
                mock.patch.object(a, "evaluate_trade", return_value=fake_trade_math),
            ):
                ff.worker(ff.parser().parse_args(["packet", "Kenneth Walker for Drake London?", "--offline"]))
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            self.assertEqual(saved["decision_type"], "explicit_trade")
            self.assertEqual(saved["min_ppg_shift_to_flip"], 0.75)
            self.assertEqual(saved["assumption_list"], [])
            self.assertIn("decision_report", saved)
            self.assertEqual(saved["decision_report"]["min_ppg_shift_to_flip"], 0.75)
            self.assertEqual(saved["decision_report"]["weekly_ppg_impact"], 0.75)


if __name__ == "__main__":
    unittest.main()
