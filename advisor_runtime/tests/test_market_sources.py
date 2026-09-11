"""Deterministic tests for market labeling and coverage warnings."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


RUNTIME_DIR = Path(__file__).resolve().parents[1]
TEST_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

import advisor  # noqa: E402
import market_sources  # noqa: E402
from test_advisor_v2 import fixture_live_context, fixture_snapshot  # noqa: E402


class MarketLabelTests(unittest.TestCase):
    def _provider_summary(self, lines, fair_line, stat="receiving_yards"):
        payload = {
            "data": [{
                "players": {"player": {"name": "Test Player"}},
                "odds": {"prop": {
                    "periodID": "game",
                    "betTypeID": "ou",
                    "sideID": "over",
                    "playerID": "player",
                    "statID": stat,
                    "fairOverUnder": fair_line,
                    "byBookmaker": {
                        f"book-{index}": {"overUnder": line}
                        for index, line in enumerate(lines)
                    },
                }},
            }],
        }
        with (
            mock.patch.object(market_sources, "load_secrets", return_value={
                "SPORTSGAMEODDS_API_KEY": "fixture",
            }),
            mock.patch.object(market_sources, "_cache_read", return_value=payload),
            mock.patch.object(market_sources.requests, "get", side_effect=AssertionError(
                "market regression tests must not use network"
            )),
        ):
            result = market_sources.sports_game_odds([{"name": "Test Player"}])
        return result["players"]["test player"][market_sources.SPORTS_GAME_ODDS_STATS[stat]]

    def test_provider_fair_line_requires_inclusive_book_range_at_any_book_count(self):
        for lines in ([60.5], [58.5, 59.5, 60.5], [58.5, 59.5, 59.5, 60.5]):
            low, high = min(lines), max(lines)
            for fair_line, accepted in (
                (low - 0.001, False),
                (low, True),
                ((low + high) / 2, True),
                (high, True),
                (high + 0.001, False),
            ):
                with self.subTest(lines=lines, fair_line=fair_line):
                    summary = self._provider_summary(lines, fair_line)
                    self.assertEqual(summary["range"], [low, high])
                    self.assertEqual(summary["book_count"], len(lines))
                    self.assertEqual(summary["fair_line"], fair_line)
                    self.assertEqual(summary["consensus_line"], summary["book_consensus_line"])
                    self.assertEqual(
                        summary["projection_line"],
                        fair_line if accepted else summary["consensus_line"],
                    )
                    self.assertEqual(
                        summary["projection_line_method"],
                        "provider_fair_line_within_book_range" if accepted else
                        "robust_book_median; provider_fair_line_rejected",
                    )

    def test_above_book_fair_lines_from_september_11_use_book_median(self):
        cases = (
            ("London 18:04", "receiving_yards", [58.5, 61.5, 59.5], 63.5, 59.5),
            ("London 18:21", "receiving_yards", [58.5, 61.5, 59.5, 58.5], 64.5, 59.0),
            ("Lawrence 18:21", "passing_yards", [232.5, 236.5, 234.5, 239.5], 245.0, 235.5),
        )
        for observation, stat, lines, fair_line, median in cases:
            for ordered_lines in (lines, list(reversed(lines))):
                with self.subTest(observation=observation, lines=ordered_lines):
                    summary = self._provider_summary(ordered_lines, fair_line, stat)
                    self.assertEqual(summary["range"], [min(lines), max(lines)])
                    self.assertEqual(summary["book_count"], len(lines))
                    self.assertEqual(summary["excluded_outliers"], [])
                    self.assertEqual(summary["consensus_line"], median)
                    self.assertEqual(summary["projection_line"], median)
                    self.assertEqual(
                        summary["projection_line_method"],
                        "robust_book_median; provider_fair_line_rejected",
                    )

    def test_projection_oracle_cannot_enable_legacy_market_paths(self):
        engine = advisor.load_engine(quick=False)
        self.assertTrue(engine.QUICK)
        self.assertEqual(engine.BP_API_KEY, "")
        self.assertEqual(engine.BP_KEY, {})
        self.assertEqual(
            engine.check_receptions(),
            {"legacy_market_probe": "disabled"},
        )
        self.assertTrue(engine.src_underdog().empty)

    def test_underdog_adapter_is_hard_disabled(self):
        with mock.patch.object(
            market_sources.requests,
            "get",
            side_effect=AssertionError("disabled adapter must not use network"),
        ):
            result = market_sources.underdog(
                [{"name": "Tee Higgins", "position": "WR"}]
            )
        self.assertEqual(result["status"], "manual_browser_on_request")
        self.assertEqual(result["players"], {})

    def test_book_consensus_never_changes_to_unlisted_provider_line(self):
        summary = market_sources._book_summary(
            [
                {"book": "A", "line": 4.5, "updated_at": "1"},
                {"book": "B", "line": 4.5, "updated_at": "1"},
                {"book": "C", "line": 4.5, "updated_at": "1"},
            ],
            "fixture",
        )
        self.assertEqual(summary["consensus_line"], 4.5)
        self.assertEqual(summary["book_consensus_line"], 4.5)
        self.assertEqual(summary["projection_line"], 4.5)

    def test_projection_update_labels_fair_line_separately(self):
        player = {
            "live_week_projection": 12.0,
            "live_projection_stats": {"rec": 4.0},
        }
        sportsbook = {
            "rec": {
                "consensus_line": 4.5,
                "book_consensus_line": 4.5,
                "projection_line": 5.0,
                "projection_line_method": "provider_fair_line",
                "book_count": 3,
                "range": [4.5, 4.5],
            }
        }
        update = market_sources.market_projection_update(player, sportsbook)
        replacement = update["replacements"][0]
        self.assertEqual(replacement["market"], 5.0)
        self.assertEqual(replacement["book_consensus"], 4.5)
        self.assertEqual(replacement["market_method"], "provider_fair_line")

    def test_comparison_warns_when_only_one_player_has_props(self):
        snapshot = fixture_snapshot()
        market = {
            "source_status": {
                "sports_game_odds": "live",
                "pickem_boards": "manual_browser_on_request",
                "the_odds_api": "not_requested",
            },
            "players": {
                "Travis Etienne": {
                    "sportsbooks": None,
                    "projection_update": None,
                },
                "Tee Higgins": {
                    "sportsbooks": {"rec": {"consensus_line": 4.5}},
                    "projection_update": None,
                },
            },
        }
        with mock.patch.object(advisor, "focused_market_packet", return_value=market):
            packet = advisor.build_packet(
                "Compare Travis Etienne and Tee Higgins",
                snapshot,
                live_context=fixture_live_context(snapshot),
                include_market=True,
            )
        self.assertTrue(
            any("asymmetric" in warning.lower() for warning in packet["warnings"])
        )


if __name__ == "__main__":
    unittest.main()
