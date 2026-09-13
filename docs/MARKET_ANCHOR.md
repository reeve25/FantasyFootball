# Market anchor converter (T2a)

`advisor_runtime/market_anchor.py` is an offline internal module. Production
advice still uses the existing sources; evaluator integration belongs to T4.
Run regression checks through `python ff.py selftest`.

`convert_snapshot` accepts one snapshot's decoded rows, provider-ID-to-name
metadata, event-ID-to-week metadata, engine players (`pid`, `name`), explicit
linear scoring coefficients and a complete required-stat list per player.
It returns a `rows` dictionary keyed by `(Sleeper pid, week)` and diagnostics.
Historical files lack provider names and event weeks: callers must recover
these from verified matching provider metadata. Never decode a name from an ID
or infer the game week from the snapshot's projection rows.

Both American prices are converted to probabilities and normalized by their
sum. Over and under must share event, player, book, market, line and fetch.
Missing prices, unmatched sides and unsupported integer push thresholds are
rejected. Books receive equal weight; their distributions form a mixture.

A single threshold and two prices identify only one distribution quantile.
Yardage uses a normal location approximation with an explicit caller-supplied
SD for each player/week/stat. Counts use a Poisson model. These are modeling
assumptions, not uniquely reconstructed market distributions. Normal yardage
can have a negative tail; it is an approximation requiring empirical review.
For 74.5 yards at -110/-110, the mean is 74.5. At -130/+110, the no-vig over
probability is 273/503 and the mean increases by SD times the normal quantile.
For 0.5 touchdowns at balanced prices, a Poisson mean is ln(2), not 0.5.

Fallbacks are explicit `(pid, week, stat)` entries containing `team_stat_mean`,
`share`, `source_ts`, and `rationale`. Their product fills only missing props.
A team points total alone does not identify passing yards, receptions, or a
player's touchdown share: callers must supply and document that conversion.
This module neither fetches team totals nor invents allocations. An absent
component makes `anchor_fp` null, preserving any known implied stats.

Scoring is supplied using engine stat keys. Do not pass an entire Sleeper
settings object as the required-stat list: explicitly enumerate components,
including negative scoring such as interceptions and lost fumbles. Aggregate
`td` is usable only with an appropriate common rush/receiving TD coefficient.
Combined yardage and touchdown components cannot overlap their parts.
Nonlinear bonuses and position-dependent scoring need a separate adapter;
they are not supported by this linear converter.

Per-stat variance is reported. Fantasy-point variance is unknown because
cross-stat covariance is not identified. `confidence` is a categorical
evidence label; it is not a calibrated probability or a T3 blend weight.
`source_ts` is the oldest contributing ISO UTC source timestamp; all contributing
timestamps are retained. Snapshot times remain fetch times, never verified
book publication times. Callers must use normalized ISO UTC timestamps.

T2b must validate three real players in one settled week against independently
sourced consensus closing projections (within approximately one FP), with
final box scores used to inspect plausible distribution shape. Synthetic math
checks do not satisfy this requirement. No accuracy claim is supported yet.

T2d (2026-09-12) added `YARDAGE_SD_DEFAULTS`/`default_yardage_sd(position,
stat)` to this module: provisional per-position weekly yardage SDs, sourced
from the engine's own backtested `SIGMA_POS` (fantasy-point SD) divided by
each stat's scoring weight for primary stats, and separately-reasoned
constants for secondary ones. `convert_snapshot` itself is unchanged --
still no default, still requires an explicit `yardage_sd` dict, still nulls
a component with none. The default table is a caller-side convenience (used
by `market_anchor_projection.compute_projection_sources`), never per-player,
and does not satisfy T2b -- see STATUS.md's T2d entry for full sourcing and
why cross-book line dispersion and alt-line quantile fitting were checked
and rejected as sources first.

T2e (2026-09-13) added `touchdown_distribution(line, price)` and an
`optional_stats` parameter to `convert_snapshot` (default `None`, fully
backward compatible). The SportsGameOdds "touchdowns" (anytime-TD) market is
genuinely one-sided -- its paired `under` oddID exists in the raw payload
but never carries a real bookmaker price -- so `touchdown_distribution` uses
the single posted price's `implied_probability` directly (no de-vig
partner) under a Poisson touchdown-count assumption, solved via
`_poisson_mean_for_threshold` (the same general root-finder
`stat_distribution`'s own Poisson branch now shares, refactored out rather
than duplicated). Real live data posts this market at a 1.5 ("2+ TDs")
threshold, not the anytime (0.5, "1+") case a naive `-ln(1-P)` closed form
would assume -- the general solve handles either. `optional_stats` differs
from `required_stats`: an optional stat's absence never nulls `anchor_fp`
or joins `missing_stats`; it's tracked in a new `optional_missing` list and
the row's `confidence` becomes `"yardage_only"` instead. See STATUS.md's
T2e entry for the full Decision Log, including how the TD scoring
coefficient is resolved from real league config with an explicit
degrade-if-mismatched rule (`market_anchor_projection.
resolve_touchdown_scoring`).
