import math
import unittest

from advisor_runtime.market_anchor import (
    YARDAGE_SD_DEFAULTS,
    convert_snapshot,
    default_yardage_sd,
    stat_distribution,
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
                       scoring={"rec_yd": .1}, required_stats={"12522": ["rec_yd"]},
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
        row = self.convert(scoring={"rec_yd": .1, "rec": 1},
                           required_stats={"12522": ["rec_yd", "rec"]})["rows"]["12522", 1]
        self.assertIsNone(row["anchor_fp"])
        self.assertEqual(row["missing_stats"], ["rec"])
