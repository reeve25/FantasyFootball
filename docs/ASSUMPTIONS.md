# T3 assumption registry and blender

`advisor_runtime/assumptions.py` is an offline internal module. Curated inputs
are validated by `validate_registry` or loaded with `load_registry(path)`.
`REGISTRY_SCHEMA` exports a JSON-serializable JSON Schema; runtime validation
also rejects nonfinite numbers, whitespace-only text, reversed ranges and exact
duplicate entries. There are no new dependencies or network operations.

The registry is an array of objects with these required fields:

| Field | Meaning |
| --- | --- |
| `player` | Existing Sleeper ID string, not a display name or new ID |
| `week_range` | Inclusive `[first, last]`, weeks 1 through 18 of one season |
| `stat_affected` | Engine stat key, `fantasy_points`, or `p_active` |
| `delta` | Change in stat units, FP units, or availability weight respectively |
| `confidence` | Required internal weight in [0, 1]; not a calibrated probability |
| `rationale`, `source` | Nonempty curated explanation and evidence reference |
| `half_life_weeks` | Positive finite half life; decay begins at the first week |

Optional `type` is `stat` (default), `injury`, or `workload`. For `p_active`,
type must be injury/workload and delta must lie in [-1, 0]: delta = -0.2 means
an internal active weight of 0.8 relative to a fully active baseline. These are
model inputs, never calibrated claims about a player's likelihood of playing.
Separate weekly entries may encode varying availability scenarios. Callers
must keep registries season-scoped; this module does not guess a season.

`apply(anchor, registry, player=pid, week=week, scoring=coefficients,
priced_in_guard=callback, anchor_is_conditional=False)` accepts a T2 anchor row.
Each applicable ordinary delta is converted to FP with explicit linear league
scoring, then multiplied by its internal weight and
`2 ** (-(week - first_week) / half_life_weeks)`. No scoring defaults are assumed.
An availability delta uses `anchor_fp * delta` and the same weighting/decay,
only when the caller explicitly declares a conditional-on-playing anchor.
Otherwise it is suppressed to avoid discounting risk already in the baseline.

The guard receives a copied assumption and target week. `True` means already
priced (suppress), `False` means checked and unpriced (allow), and `None` means
unknown (suppress). With no hook, applicable assumptions are suppressed. Errors
propagate; invalid return types are rejected. This is the T6 interface only;
T3 does not implement line movement detection. Until T6 exists, callers can
supply a guard based on documented manual evidence. Never use a blanket False
in production merely to enable adjustments.

The sum of absolute weighted FP effects is capped at 15% of the absolute
anchor, proportionally scaling all effects. This stronger gross cap also
limits the net adjustment and prevents offsetting assumptions from hiding
large individual changes. It applies to decreases, increases and availability
effects together. There is no exceptional-evidence override until a policy is
defined. Zero anchors receive no adjustment; missing anchors remain null.
This cap is not a substitute for live eligibility or injury-status handling.

Output includes adjusted mean, cap status, and per-assumption source/rationale,
suppression status, requested FP change and applied FP change. Attribution
reconciles to the total adjustment. Numeric confidence/availability weights are
not echoed. Inputs are unchanged. If any nonzero adjustment is requested,
variance becomes unknown rather than inventing an uncertainty model; otherwise
the anchor's variance is retained. No distribution-calibration claim is made.

Run acceptance through `python ff.py selftest`: test_assumptions covers cap,
decay, the double-count hook, availability, missing data, stat units, validation,
JSON loading and input immutability. Evaluator wiring is reserved for T4.
