import math
import unittest

from advisor_runtime.market_anchor import (
    YARDAGE_SD_DEFAULTS,
    convert_snapshot,
    default_yardage_sd,
    stat_distribution,
    touchdown_distribution,
)


class DefaultYardageSdTests(unittest.TestCase):
    def test_covers_every_primary_and_secondary_stat_t2d_needs(self):
        expected = {
            ("QB", "pass_yd"), ("QB", "rush_yd"),
            ("RB", "rush_yd"), ("RB", "rec_yd"),
            ("WR", "rec_yd"), ("WR", "rush_yd"),
            ("TE", "rec_yd"),
        }
        self.assertEqual(set(YARDAGE_SD_DEFAULTS), expected)

    def test_all_values_positive_and_finite(self):
        for value in YARDAGE_SD_DEFAULTS.values():
            self.assertGreater(value, 0)
            self.assertTrue(math.isfinite(value))

    def test_primary_defaults_match_sigma_pos_divided_by_scoring_weight(self):
        # Hand-verify against the engine's own backtested SIGMA_POS
        # (advisor_runtime/engine/ff_v6_3.py) and real league scoring
        # weights, per the sourcing documented in market_anchor.py.
        cases = (("QB", "pass_yd", 3.02, .04), ("RB", "rush_yd", 3.85, .1),
                 ("WR", "rec_yd", 3.20, .1), ("TE", "rec_yd", 2.27, .1))
        for pos, stat, sigma, weight in cases:
            with self.subTest(pos=pos, stat=stat):
                self.assertAlmostEqual(default_yardage_sd(pos, stat), sigma / weight)

    def test_unknown_position_or_stat_returns_none_not_a_guess(self):
        self.assertIsNone(default_yardage_sd("K", "kick_pts"))
        self.assertIsNone(default_yardage_sd("QB", "rec_yd"))
        self.assertIsNone(default_yardage_sd("nonsense", "rush_yd"))


class MarketAnchorTests(unittest.TestCase):
    def convert(self, rows=None, **changes):
        options = dict(provider_names={"SGO": "Cameron Ward"}, event_weeks={"e": 1},
                       players=[{"pid": "12522", "name": "Cam Ward"}],
                       scoring={"rec_yd": .1, "pass_td": 4.0}, required_stats={"12522": ["rec_yd"]},
                       yardage_sd={("12522", 1, "rec_yd"): 30})
        options.update(changes)
        return convert_snapshot(self.rows() if rows is None else rows, **options)

    def rows(self):
        return [dict(row_type="line", player_id="SGO", event_id="e", book="b",
                     market="rec_yd", line=74.5, price=-110, side=side,
                     fetched_at_utc="2026-09-01T00:00:00Z") for side in ("over", "under")]

    def test_hand_calculations(self):
        self.assertAlmostEqual(stat_distribution(74.5, -110, -110, sd=30)["mean"], 74.5)
        tilted = stat_distribution(74.5, -130, 110, sd=30)
        self.assertAlmostEqual(tilted["p_over"], 273/503)
        self.assertGreater(tilted["mean"], 74.5)
        # P(Poisson(mu)>0.5)=0.5 -> mu=ln(2), not 0.5 TD.
        self.assertAlmostEqual(stat_distribution(.5, -110, -110)["mean"], math.log(2))

    def test_identity_and_scoring(self):
        row = self.convert()["rows"]["12522", 1]
        self.assertAlmostEqual(row["anchor_fp"], 7.45)
        self.assertEqual(row["confidence"], "conditional_market")
        self.assertEqual(self.convert(provider_names={})["rows"], {})

    def test_missing_side_and_mismatched_line(self):
        for rows in (self.rows()[:1], [self.rows()[0], dict(self.rows()[1], line=75.5)]):
            self.assertIsNone(self.convert(rows)["rows"]["12522", 1]["anchor_fp"])

    def test_missing_sd_and_invalid_price(self):
        self.assertIsNone(self.convert(yardage_sd={})["rows"]["12522", 1]["anchor_fp"])
        rows = self.rows(); rows[0]["price"] = float("nan")
        self.assertIsNone(self.convert(rows)["rows"]["12522", 1]["anchor_fp"])

    def test_documented_fallback(self):
        fallback = {("12522", 1, "rec_yd"): dict(team_stat_mean=250, share=.3,
                    source_ts="2026-08-31T00:00:00Z", rationale="Explicit team yardage allocation")}
        row = self.convert([], fallbacks=fallback)["rows"]["12522", 1]
        self.assertEqual(row["anchor_fp"], 7.5)
        self.assertEqual(row["confidence"], "fallback")

    def test_reject_mixed_snapshots_and_overlap(self):
        rows = self.rows(); rows[1]["fetched_at_utc"] = "2026-09-02T00:00:00Z"
        with self.assertRaises(ValueError): self.convert(rows)
        with self.assertRaises(ValueError):
            self.convert(required_stats={"12522": ["rush_rec_yd", "rec_yd"]})

    def test_reject_pushes_and_bad_odds(self):
        for line, over in ((74, -110), (74.5, 0), (74.5, float("inf"))):
            with self.assertRaises(ValueError): stat_distribution(line, over, -110, sd=30)

    def test_missing_component_is_not_zero(self):
        row = self.convert(scoring={"rec_yd": .1, "rec": 1, "pass_td": 4.0},
                           required_stats={"12522": ["rec_yd", "rec"]})["rows"]["12522", 1]
        self.assertIsNone(row["anchor_fp"])
        self.assertEqual(row["missing_stats"], ["rec"])


class TouchdownDistributionTests(unittest.TestCase):
    def test_anytime_line_matches_the_closed_form(self):
        # At line 0.5 ("anytime", 1+ TDs) with a price whose raw implied
        # probability is exactly 0.5 (+100, a fair coin -- no vig to net out
        # for a single one-sided price), the solve must match the textbook
        # closed form: P(Poisson(mu)>0)=0.5 -> mu=ln(2).
        self.assertAlmostEqual(touchdown_distribution(.5, 100)["mean"], math.log(2), places=6)

    def test_real_two_plus_line_needs_the_general_solve_not_the_closed_form(self):
        # Real live data (2026-09-12) posts a 1.5 ("2+ TDs") line, not 0.5.
        # The closed form -ln(1-P) would badly understate this.
        row = touchdown_distribution(1.5, 750)  # Breece Hall, draftkings, observed live
        naive_closed_form = -math.log(1 - 100 / (100 + 750))
        self.assertGreater(row["mean"], naive_closed_form * 1.5)
        self.assertAlmostEqual(row["mean"], 0.58, places=1)

    def test_higher_price_implies_fewer_expected_touchdowns(self):
        longshot = touchdown_distribution(1.5, 4500)
        favorite = touchdown_distribution(1.5, 750)
        self.assertLess(longshot["mean"], favorite["mean"])

    def test_uses_the_posted_price_directly_no_devig_partner(self):
        row = touchdown_distribution(.5, 200)
        self.assertAlmostEqual(row["p_over"], 100 / 300)
        self.assertEqual(row["model"], "poisson_one_sided")

    def test_rejects_pushes_and_bad_odds(self):
        for line, price in ((1, 200), (1.5, 0), (1.5, float("nan"))):
            with self.assertRaises(ValueError):
                touchdown_distribution(line, price)


class ConvertSnapshotOptionalTdTests(unittest.TestCase):
    def td_row(self, line=1.5, price=750, player_id="SGO", event_id="e"):
        return dict(row_type="line", player_id=player_id, event_id=event_id, book="b",
                    market="td", line=line, price=price, side="over",
                    fetched_at_utc="2026-09-01T00:00:00Z")

    def yardage_rows(self, player_id="SGO", event_id="e"):
        return [dict(row_type="line", player_id=player_id, event_id=event_id, book="b",
                     market="rec_yd", line=74.5, price=-110, side=side,
                     fetched_at_utc="2026-09-01T00:00:00Z") for side in ("over", "under")]

    def convert(self, rows, **changes):
        options = dict(provider_names={"SGO": "Cameron Ward"}, event_weeks={"e": 1},
                       players=[{"pid": "12522", "name": "Cam Ward"}],
                       scoring={"rec_yd": .1, "td": 6.0, "pass_td": 4.0},
                       required_stats={"12522": ["rec_yd"]},
                       optional_stats={"12522": ["td"]},
                       yardage_sd={("12522", 1, "rec_yd"): 30})
        options.update(changes)
        return convert_snapshot(rows, **options)

    def test_td_present_contributes_and_marks_complete(self):
        row = self.convert(self.yardage_rows() + [self.td_row()])["rows"]["12522", 1]
        expected_td_fp = touchdown_distribution(1.5, 750)["mean"] * 6.0
        self.assertAlmostEqual(row["anchor_fp"], 74.5 * .1 + expected_td_fp)
        self.assertEqual(row["confidence"], "conditional_market")
        self.assertEqual(row["optional_missing"], [])
        self.assertIn("td", row["implied_stats"])

    def test_td_absent_degrades_to_yardage_only_never_null(self):
        row = self.convert(self.yardage_rows())["rows"]["12522", 1]
        self.assertAlmostEqual(row["anchor_fp"], 74.5 * .1)
        self.assertEqual(row["confidence"], "yardage_only")
        self.assertEqual(row["optional_missing"], ["td"])
        self.assertEqual(row["missing_stats"], [])  # never counted as a required gap

    def test_td_never_falls_back_to_a_team_share(self):
        fallback = {("12522", 1, "td"): dict(team_stat_mean=3, share=.3,
                    source_ts="2026-08-31T00:00:00Z", rationale="should never be used")}
        row = self.convert(self.yardage_rows(), fallbacks=fallback)["rows"]["12522", 1]
        self.assertEqual(row["optional_missing"], ["td"])
        self.assertNotIn("td", row["implied_stats"])

    def test_required_missing_still_nulls_anchor_even_with_td_present(self):
        row = self.convert([self.td_row()])["rows"]["12522", 1]
        self.assertIsNone(row["anchor_fp"])
        self.assertEqual(row["missing_stats"], ["rec_yd"])
        self.assertEqual(row["confidence"], "incomplete")

    def test_required_and_optional_cannot_overlap(self):
        with self.assertRaises(ValueError):
            self.convert(self.yardage_rows(), required_stats={"12522": ["rec_yd", "td"]},
                        optional_stats={"12522": ["td"]})

    def test_duplicate_optional_stats_rejected(self):
        with self.assertRaises(ValueError):
            self.convert(self.yardage_rows(), optional_stats={"12522": ["td", "td"]})

    def test_backward_compatible_default_has_no_optional_stats(self):
        row = convert_snapshot(
            self.yardage_rows(), provider_names={"SGO": "Cameron Ward"}, event_weeks={"e": 1},
            players=[{"pid": "12522", "name": "Cam Ward"}], scoring={"rec_yd": .1, "pass_td": 4.0},
            required_stats={"12522": ["rec_yd"]}, yardage_sd={("12522", 1, "rec_yd"): 30},
        )["rows"]["12522", 1]
        self.assertEqual(row["optional_missing"], [])
        self.assertEqual(row["confidence"], "conditional_market")
