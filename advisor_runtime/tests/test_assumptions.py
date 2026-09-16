import copy
import json
import tempfile
import unittest
from pathlib import Path

from advisor_runtime.assumptions import REGISTRY_SCHEMA, apply, load_registry, validate_registry


def assumption(**changes):
    item = dict(player="12522", week_range=[2, 6], stat_affected="fantasy_points",
                delta=2., confidence=.5, rationale="Offline test evidence",
                source="fixture:role", half_life_weeks=2.)
    item.update(changes)
    return item


class AssumptionTests(unittest.TestCase):
    def blend(self, items, base=20., week=2, **changes):
        options = dict(player="12522", week=week, priced_in_guard=lambda a, w: False)
        options.update(changes)
        return apply({"anchor_fp": base, "fp_variance": 4.}, items, **options)

    def test_positive_and_negative_cap(self):
        for sign in (1, -1):
            row = self.blend([assumption(delta=sign * 100, confidence=1)])
            self.assertAlmostEqual(row["adjusted_fp"], 20 + sign * 3)
            self.assertTrue(row["cap_applied"])

    def test_gross_cap_and_attribution_reconcile(self):
        row = self.blend([assumption(delta=10, confidence=1),
                          assumption(delta=-8, confidence=1, source="fixture:other")])
        effects = [e["applied_fp_delta"] for e in row["attribution"]]
        self.assertAlmostEqual(sum(abs(d) for d in effects), 3.)
        self.assertAlmostEqual(sum(effects), row["adjusted_fp"] - 20)
        self.assertAlmostEqual(row["adjusted_fp"], 20 + 1/3)

    def test_half_life_and_range(self):
        item = assumption()
        for week, delta in ((1, 0), (2, 1), (4, .5), (6, .25), (7, 0)):
            self.assertAlmostEqual(self.blend([item], week=week)["adjustment_fp"], delta)
        self.assertEqual(self.blend([item], player="other")["adjustment_fp"], 0)

    def test_guard_true_false_unknown_and_absent(self):
        for guard, status, delta in ((lambda a, w: True, "already_priced", 0),
                                     (lambda a, w: False, "applied", 1),
                                     (lambda a, w: None, "pricing_unknown", 0),
                                     (None, "pricing_unknown", 0)):
            row = self.blend([assumption()], priced_in_guard=guard)
            self.assertEqual(row["attribution"][0]["status"], status)
            self.assertEqual(row["adjustment_fp"], delta)

    def test_guard_errors_are_not_silently_unpriced(self):
        with self.assertRaises(ValueError):
            self.blend([assumption()], priced_in_guard=lambda a, w: "false")
        def broken(a, w):
            raise RuntimeError("failed evidence lookup")
        with self.assertRaises(RuntimeError):
            self.blend([assumption()], priced_in_guard=broken)

    def test_stat_units_and_negative_scoring(self):
        row = self.blend([assumption(stat_affected="pass_yd", delta=25),
                          assumption(stat_affected="pass_int", delta=1)],
                         scoring={"pass_yd": .04, "pass_int": -1})
        self.assertAlmostEqual(row["adjustment_fp"], 0.)
        with self.assertRaises(ValueError):
            self.blend([assumption(stat_affected="rec")])

    def test_availability_weight_decay_and_basis_guard(self):
        item = assumption(type="injury", stat_affected="p_active", delta=-.2)
        row = self.blend([item], anchor_is_conditional=True)
        self.assertAlmostEqual(row["adjusted_fp"], 18.)
        self.assertAlmostEqual(self.blend([item], week=4, anchor_is_conditional=True)["adjusted_fp"], 19.)
        self.assertEqual(self.blend([item])["attribution"][0]["status"], "availability_basis_unknown")
        row = self.blend([assumption(type="workload", stat_affected="p_active", delta=-1, confidence=1)],
                         anchor_is_conditional=True)
        self.assertEqual(row["adjusted_fp"], 17.)  # still capped; not an injury-status override

    def test_zero_negative_missing_anchors(self):
        self.assertEqual(self.blend([assumption()], base=0)["adjusted_fp"], 0.)
        self.assertAlmostEqual(self.blend([assumption(delta=-10)], base=-10)["adjusted_fp"], -11.5)
        missing = self.blend([assumption()], base=None)
        self.assertIsNone(missing["adjusted_fp"])
        self.assertEqual(missing["attribution"][0]["status"], "missing_anchor")

    def test_registry_rejects_invalid_input(self):
        cases = [dict(confidence=True), dict(confidence=1.1), dict(delta=float("nan")),
                 dict(delta=float("inf")), dict(half_life_weeks=0), dict(week_range=[4, 2]),
                 dict(week_range=[True, 2]), dict(week_range=[1, 19]), dict(source=" "),
                 dict(player=12522), dict(typo=1), dict(type="unknown"),
                 dict(stat_affected="p_active"),
                 dict(type="injury", stat_affected="p_active", delta=.1)]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_registry([assumption(**changes)])
        with self.assertRaises(ValueError): validate_registry([assumption(), assumption()])
        with self.assertRaises(ValueError): validate_registry({})
        bad = assumption(); del bad["confidence"]
        with self.assertRaises(ValueError): validate_registry([bad])

    def test_json_registry_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "registry.json"
            path.write_text(json.dumps([assumption()]), encoding="utf-8")
            self.assertEqual(load_registry(path), [assumption()])
        self.assertEqual(json.loads(json.dumps(REGISTRY_SCHEMA))["type"], "array")

    def test_inputs_unchanged_and_weights_not_in_output(self):
        items = [assumption()]; original = copy.deepcopy(items)
        def mutating_guard(item, week):
            item["delta"] = 1000
            return False
        row = self.blend(items, priced_in_guard=mutating_guard)
        self.assertEqual(items, original)
        self.assertEqual(row["adjustment_fp"], 1.)
        self.assertNotIn('"confidence"', json.dumps(row))
        self.assertIsNone(row["variance"])
        self.assertEqual(self.blend([])["variance"], 4.)
