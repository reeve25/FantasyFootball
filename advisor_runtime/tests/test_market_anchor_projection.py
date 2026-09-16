import math
import unittest

from advisor_runtime.market_anchor import touchdown_distribution
from advisor_runtime.market_anchor_projection import (
    REQUIRED_STATS_BY_POSITION,
    build_identity_inputs,
    compute_projection_sources,
    inject_projection_sources,
    optional_stats_for,
    required_stats_for,
    resolve_touchdown_scoring,
)


def line_row(**changes):
    row = dict(
        row_type="line", event_id="e1", player_id="SGO1", book="b",
        market="rec_yd", line=74.5, price=-110, side="over",
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


class ResolveTouchdownScoringTests(unittest.TestCase):
    def test_usable_when_rush_and_rec_td_agree(self):
        resolved, usable = resolve_touchdown_scoring({"rush_td": 6.0, "rec_td": 6.0})
        self.assertTrue(usable)
        self.assertEqual(resolved["td"], 6.0)

    def test_unusable_when_they_disagree(self):
        resolved, usable = resolve_touchdown_scoring({"rush_td": 6.0, "rec_td": 5.0})
        self.assertFalse(usable)
        self.assertNotIn("td", resolved)

    def test_unusable_when_either_is_absent(self):
        for scoring in ({"rec_td": 6.0}, {"rush_td": 6.0}, {}):
            with self.subTest(scoring=scoring):
                _, usable = resolve_touchdown_scoring(scoring)
                self.assertFalse(usable)

    def test_never_mutates_the_input(self):
        original = {"rush_td": 6.0, "rec_td": 6.0}
        copy_before = dict(original)
        resolve_touchdown_scoring(original)
        self.assertEqual(original, copy_before)


class OptionalStatsForTests(unittest.TestCase):
    def test_every_supported_position_gets_td_when_usable(self):
        players = [{"pid": "1", "pos": "QB"}, {"pid": "2", "pos": "RB"},
                   {"pid": "3", "pos": "WR"}, {"pid": "4", "pos": "TE"}]
        stats = optional_stats_for(players, td_usable=True)
        self.assertEqual(stats, {"1": ["td"], "2": ["td"], "3": ["td"], "4": ["td"]})

    def test_empty_when_not_usable(self):
        players = [{"pid": "1", "pos": "QB"}]
        self.assertEqual(optional_stats_for(players, td_usable=False), {})

    def test_excludes_unsupported_positions(self):
        players = [{"pid": "1", "pos": "K"}]
        self.assertEqual(optional_stats_for(players, td_usable=True), {})


def te_rows():
    """rec_yd alone covers TE's (T2d-narrowed) full required-stats list."""
    return [
        line_row(market="rec_yd", line=74.5, side=side)
        for side in ("over", "under")
    ]


def td_row(line=1.5, price=750, player_id="SGO1", event_id="e1"):
    return dict(
        row_type="line", event_id=event_id, player_id=player_id, book="b",
        market="td", line=line, price=price, side="over",
        fetched_at_utc="2026-09-01T00:00:00Z", player_name="Cam Ward",
        event_metadata={"season_week": "Week 3"},
    )


TE_SCORING = {"rec_yd": .1}
TE_SD = {("12522", 3, "rec_yd"): 30}
# 74.5 yards at -110/-110: no-vig mean is exactly the line.
TE_EXPECTED_ANCHOR = 74.5 * .1
TE_SCORING_WITH_TD = {"rec_yd": .1, "rush_td": 6.0, "rec_td": 6.0}


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

    def test_missing_yardage_sd_leaves_anchor_null_not_guessed_when_defaults_disabled(self):
        players = [{"pid": "1", "name": "Cam Ward", "pos": "TE"}]
        result = compute_projection_sources(
            te_rows(), players=players, scoring=TE_SCORING,
            use_default_yardage_sd=False,
        )  # no yardage_sd supplied, defaults explicitly off (T2a/T2c behavior)
        self.assertEqual(result["sources"]["1"]["market_anchor"], {})
        self.assertEqual(result["sources"]["1"]["market_anchor_blend"], {})
        self.assertIsNone(result["attribution"]["1"]["3"]["anchor_fp"])
        self.assertEqual(result["provisional_sd_stats"], [])

    def test_t2d_position_default_fills_in_automatically_by_default(self):
        """T2d: a real player with no explicit SD now gets a non-null anchor."""
        players = [{"pid": "1", "name": "Cam Ward", "pos": "TE"}]
        result = compute_projection_sources(
            te_rows(), players=players, scoring=TE_SCORING,
        )  # no yardage_sd supplied; use_default_yardage_sd defaults True
        self.assertAlmostEqual(result["sources"]["1"]["market_anchor"]["3"], TE_EXPECTED_ANCHOR)
        self.assertEqual(result["provisional_sd_stats"], ["rec_yd"])
        self.assertEqual(result["attribution"]["1"]["3"]["provisional_sd_stats"], ["rec_yd"])

    def test_explicit_yardage_sd_overrides_the_position_default(self):
        # Unbalanced rec_yd price so the mean actually depends on SD (a
        # balanced -110/-110 line implies the same mean at any SD).
        rows = te_rows()
        for row in rows:
            if row["market"] == "rec_yd":
                row["price"] = -130 if row["side"] == "over" else 110
        players = [{"pid": "12522", "name": "Cam Ward", "pos": "TE"}]
        default_result = compute_projection_sources(rows, players=players, scoring=TE_SCORING)
        overridden = compute_projection_sources(
            rows, players=players, scoring=TE_SCORING,
            yardage_sd={("12522", 3, "rec_yd"): 5.0},
        )
        self.assertNotAlmostEqual(
            default_result["sources"]["12522"]["market_anchor"]["3"],
            overridden["sources"]["12522"]["market_anchor"]["3"],
        )
        # Week 3 specifically was overridden, so its own attribution entry
        # is clean even though the global default table still covers rec_yd
        # for every other week.
        self.assertEqual(overridden["attribution"]["12522"]["3"]["provisional_sd_stats"], [])
        self.assertEqual(overridden["provisional_sd_stats"], ["rec_yd"])

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

    def test_t2e_td_present_adds_a_nonzero_component_and_marks_complete(self):
        players = [{"pid": "12522", "name": "Cam Ward", "pos": "TE"}]
        result = compute_projection_sources(
            te_rows() + [td_row()], players=players, scoring=TE_SCORING_WITH_TD, yardage_sd=TE_SD,
        )
        anchor = result["sources"]["12522"]["market_anchor"]["3"]
        expected_td_fp = touchdown_distribution(1.5, 750)["mean"] * 6.0
        self.assertAlmostEqual(anchor, TE_EXPECTED_ANCHOR + expected_td_fp)
        entry = result["attribution"]["12522"]["3"]
        self.assertEqual(entry["confidence"], "conditional_market")
        self.assertEqual(entry["optional_missing"], [])
        self.assertTrue(result["td_scoring_usable"])

    def test_t2e_td_absent_degrades_to_yardage_only_not_null(self):
        players = [{"pid": "12522", "name": "Cam Ward", "pos": "TE"}]
        result = compute_projection_sources(
            te_rows(), players=players, scoring=TE_SCORING_WITH_TD, yardage_sd=TE_SD,
        )
        anchor = result["sources"]["12522"]["market_anchor"]["3"]
        self.assertAlmostEqual(anchor, TE_EXPECTED_ANCHOR)
        entry = result["attribution"]["12522"]["3"]
        self.assertEqual(entry["confidence"], "yardage_only")
        self.assertEqual(entry["optional_missing"], ["td"])
        self.assertTrue(result["td_scoring_usable"])

    def test_t2e_mismatched_league_td_scoring_never_attempts_td(self):
        players = [{"pid": "12522", "name": "Cam Ward", "pos": "TE"}]
        mismatched = {"rec_yd": .1, "rush_td": 6.0, "rec_td": 5.0}
        result = compute_projection_sources(
            te_rows() + [td_row()], players=players, scoring=mismatched, yardage_sd=TE_SD,
        )
        anchor = result["sources"]["12522"]["market_anchor"]["3"]
        self.assertAlmostEqual(anchor, TE_EXPECTED_ANCHOR)  # td row present but never priced
        self.assertFalse(result["td_scoring_usable"])
        self.assertEqual(result["attribution"]["12522"]["3"]["optional_missing"], [])

    def test_t2e_td_never_falls_back_and_default_behavior_unchanged(self):
        # No rush_td/rec_td at all in scoring (T2d-era caller): td_scoring_usable
        # is False and behavior is byte-for-byte the pre-T2e result.
        players = [{"pid": "12522", "name": "Cam Ward", "pos": "TE"}]
        result = compute_projection_sources(
            te_rows() + [td_row()], players=players, scoring=TE_SCORING, yardage_sd=TE_SD,
        )
        self.assertAlmostEqual(result["sources"]["12522"]["market_anchor"]["3"], TE_EXPECTED_ANCHOR)
        self.assertFalse(result["td_scoring_usable"])


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
