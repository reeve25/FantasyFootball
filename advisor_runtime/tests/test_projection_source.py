"""T4: the projection-source switch. See STATUS.md's T4 Decision Log entry
for why this is a snapshot-substitution helper reusing evaluate_trade's own
independent_projection_checks mechanism, rather than a parameter threaded
through _projection_for_week/optimize_lineup/_roster_average/
_legalize_roster/evaluate_trade.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parents[1]
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import advisor  # noqa: E402


def player_with_sources(**by_source):
    return {
        "name": "Test Player",
        "weekly_points": {"1": 99.0},  # existing default average; never read once a source is selected
        "weekly_points_by_source": by_source,
    }


class SelectProjectionSourceTests(unittest.TestCase):
    def test_rejects_unknown_source(self):
        with self.assertRaises(ValueError):
            advisor.select_projection_source({"players": {}}, "nonsense")

    def test_selects_each_real_source_without_touching_the_default_average(self):
        snapshot = {
            "players": {
                "p1": player_with_sources(
                    sleeper_projection_feed={"1": 9.0},
                    espn={"1": 11.0},
                    market_anchor={"1": 8.5},
                    market_anchor_blend={"1": 8.7},
                )
            }
        }
        original = copy.deepcopy(snapshot)
        for source, expected in (
            ("sleeper", 9.0), ("espn", 11.0),
            ("market_anchor", 8.5), ("blend", 8.7),
        ):
            with self.subTest(source=source):
                result = advisor.select_projection_source(snapshot, source)
                self.assertEqual(result["players"]["p1"]["weekly_points"], {"1": expected})
        # The input snapshot is never mutated by any of the four selections.
        self.assertEqual(snapshot, original)

    def test_missing_source_yields_empty_weekly_points_not_a_fallback(self):
        snapshot = {"players": {"p1": player_with_sources()}}
        result = advisor.select_projection_source(snapshot, "market_anchor")
        self.assertEqual(result["players"]["p1"]["weekly_points"], {})
        points, source = advisor._projection_for_week(result["players"]["p1"], 1)
        self.assertIsNone(points)
        self.assertEqual(source, "missing")

    def test_other_player_fields_are_preserved(self):
        snapshot = {"players": {"p1": player_with_sources(espn={"1": 11.0})}}
        result = advisor.select_projection_source(snapshot, "espn")
        self.assertEqual(result["players"]["p1"]["name"], "Test Player")

    def test_non_player_snapshot_fields_pass_through(self):
        snapshot = {"players": {}, "league": {"current_week": 3}}
        result = advisor.select_projection_source(snapshot, "sleeper")
        self.assertEqual(result["league"], {"current_week": 3})


if __name__ == "__main__":
    unittest.main()
