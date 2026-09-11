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


if __name__ == "__main__":
    unittest.main()
