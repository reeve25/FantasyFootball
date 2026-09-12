import math
import unittest

from advisor_runtime.market_anchor_projection import (
    REQUIRED_STATS_BY_POSITION,
    build_identity_inputs,
    compute_projection_sources,
    inject_projection_sources,
    required_stats_for,
)


def line_row(**changes):
    row = dict(
        row_type="line", event_id="e1", player_id="SGO1", book="b",
        market="rec_td", line=0.5, price=-110, side="over",
        fetched_at_utc="2026-09-01T00:00:00Z", player_name="Cam Ward",
        event_metadata={"season_week": "Week 3"},
    )
    row.update(changes)
    return row


class BuildIdentityInputsTests(unittest.TestCase):
    def test_parses_provider_name_and_season_week(self):
        names, weeks = build_identity_inputs([line_row(), line_row(side="under")])
        self.assertEqual(names, {"SGO1": "Cam Ward"})
        self.assertEqual(weeks, {"e1": 3})

    def test_ignores_rows_missing_name_or_week(self):
        names, weeks = build_identity_inputs(
            [line_row(player_name=None, event_metadata={})]
        )
        self.assertEqual(names, {})
        self.assertEqual(weeks, {})

    def test_ignores_projection_rows(self):
        names, weeks = build_identity_inputs(
            [{"row_type": "projection", "player_id": "1", "player_name": "X"}]
        )
        self.assertEqual(names, {})
        self.assertEqual(weeks, {})

    def test_pre_t2c_rows_without_metadata_are_excluded_not_guessed(self):
        old_format_row = {
            "row_type": "line", "event_id": "e1", "player_id": "SGO1",
            "book": "b", "market": "rec_td", "line": 0.5, "price": -110,
            "side": "over", "fetched_at_utc": "2026-09-01T00:00:00Z",
        }
        names, weeks = build_identity_inputs([old_format_row])
        self.assertEqual((names, weeks), ({}, {}))


class RequiredStatsForTests(unittest.TestCase):
    def test_covers_only_positions_the_linear_model_supports(self):
        self.assertEqual(set(REQUIRED_STATS_BY_POSITION), {"QB", "RB", "WR", "TE"})

    def test_excludes_unsupported_positions(self):
        players = [
            {"pid": "1", "pos": "RB"}, {"pid": "2", "pos": "K"}, {"pid": "3", "pos": "DEF"},
        ]
        stats = required_stats_for(players)
        self.assertEqual(set(stats), {"1"})
        self.assertIn("rush_yd", stats["1"])


def te_rows():
    """rec_yd/rec/rec_td cover TE's full required-stats list exactly.

    rec/rec_td use a 0.5 threshold (not a realistic posted line, but a valid
    half-integer count market) so both reuse market_anchor's own
    hand-verified closed form: P(Poisson(mu) > 0) = 0.5 at balanced odds
    implies mu = ln(2), the same constant test_market_anchor.py verifies.
    """
    rows = []
    for market, line in (("rec_yd", 74.5), ("rec", 0.5), ("rec_td", 0.5)):
        for side in ("over", "under"):
            rows.append(line_row(market=market, line=line, side=side))
    return rows


TE_SCORING = {"rec_yd": .1, "rec": 1.0, "rec_td": 6.0}
TE_SD = {("12522", 3, "rec_yd"): 30}
# 74.5 yards at -110/-110: no-vig mean is exactly the line. 0.5 receptions
# and 0.5 TDs at -110/-110: Poisson mean ln(2) each (hand-verified constant
# shared with test_market_anchor.py's own TD case).
TE_EXPECTED_ANCHOR = 74.5 * .1 + math.log(2) * 1.0 + math.log(2) * 6.0


class ComputeProjectionSourcesTests(unittest.TestCase):
    def test_full_position_coverage_and_blend_matches_anchor_with_empty_registry(self):
        players = [{"pid": "12522", "name": "Cam Ward", "pos": "TE"}]
        result = compute_projection_sources(
            te_rows(), players=players, scoring=TE_SCORING, yardage_sd=TE_SD,
        )
        anchor = result["sources"]["12522"]["market_anchor"]["3"]
        blend = result["sources"]["12522"]["market_anchor_blend"]["3"]
        self.assertAlmostEqual(anchor, TE_EXPECTED_ANCHOR)
        self.assertEqual(anchor, blend)  # nothing curated to blend with yet
        self.assertEqual(result["diagnostics"], [])
        entry = result["attribution"]["12522"]["3"]
        self.assertAlmostEqual(entry["anchor_fp"], TE_EXPECTED_ANCHOR)
        self.assertAlmostEqual(entry["adjusted_fp"], TE_EXPECTED_ANCHOR)
        self.assertEqual(entry["attribution"], [])  # present even when empty

    def test_missing_yardage_sd_leaves_anchor_null_not_guessed(self):
        players = [{"pid": "1", "name": "Cam Ward", "pos": "TE"}]
        result = compute_projection_sources(
            te_rows(), players=players, scoring=TE_SCORING,
        )  # no yardage_sd supplied
        self.assertEqual(result["sources"]["1"]["market_anchor"], {})
        self.assertEqual(result["sources"]["1"]["market_anchor_blend"], {})
        self.assertIsNone(result["attribution"]["1"]["3"]["anchor_fp"])

    def test_unsupported_position_player_is_excluded_before_conversion(self):
        rows = [line_row(), line_row(side="under")]
        players = [{"pid": "1", "name": "Cam Ward", "pos": "K"}]
        result = compute_projection_sources(rows, players=players, scoring={})
        self.assertEqual(result["sources"], {})

    def test_curated_assumption_moves_the_blend_away_from_the_anchor(self):
        players = [{"pid": "12522", "name": "Cam Ward", "pos": "TE"}]
        registry = [{
            "player": "12522", "week_range": [3, 3], "stat_affected": "fantasy_points",
            "delta": 1.0, "confidence": 1.0, "rationale": "fixture", "source": "fixture",
            "half_life_weeks": 4.0,
        }]
        result = compute_projection_sources(
            te_rows(), players=players, scoring=TE_SCORING, yardage_sd=TE_SD,
            assumption_registry=registry, priced_in_guard=lambda a, w: False,
        )
        anchor = result["sources"]["12522"]["market_anchor"]["3"]
        blend = result["sources"]["12522"]["market_anchor_blend"]["3"]
        self.assertGreater(blend, anchor)


class InjectProjectionSourcesTests(unittest.TestCase):
    def test_adds_keys_without_mutating_input_or_dropping_other_players(self):
        players_by_id = {
            "1": {"name": "A", "weekly_points_by_source": {"espn": {"1": 5.0}}},
            "2": {"name": "B"},
        }
        sources = {"1": {"market_anchor": {"1": 9.0}, "market_anchor_blend": {"1": 9.5}}}
        updated = inject_projection_sources(players_by_id, sources)
        self.assertEqual(
            updated["1"]["weekly_points_by_source"],
            {"espn": {"1": 5.0}, "market_anchor": {"1": 9.0}, "market_anchor_blend": {"1": 9.5}},
        )
        self.assertEqual(updated["2"], {"name": "B"})
        # Input untouched.
        self.assertEqual(players_by_id["1"]["weekly_points_by_source"], {"espn": {"1": 5.0}})
        self.assertNotIn("weekly_points_by_source", players_by_id["2"])

    def test_empty_source_points_are_not_injected(self):
        players_by_id = {"1": {"name": "A"}}
        sources = {"1": {"market_anchor": {}, "market_anchor_blend": {}}}
        updated = inject_projection_sources(players_by_id, sources)
        self.assertEqual(updated["1"].get("weekly_points_by_source", {}), {})


if __name__ == "__main__":
    unittest.main()
