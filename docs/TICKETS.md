# TICKETS.md -- self-contained, one agent session each.
# Agent instructions (paste at top of every session, any tool):
# "Read BRIEF.md, docs/FORECASTING.md and docs/TICKETS.md. You are working
#  ticket T<n> only. Do not expand scope. Run the acceptance check before
#  finishing -- with code, not a gap-analysis table (see docs/TRAPS.md's
#  Ticket workflow section). Then commit and add a dated STATUS.md entry:
#  what shipped, the acceptance check's actual result, any blockers, and the
#  exact next prompt if the ticket isn't done. A session only counts once all
#  three (check run, commit, STATUS.md entry) are true."
#
# Build order: T2 -> T3 -> T4 -> T5 is the core smart-prediction loop; T6-T8
# are leverage, built on top. Do not reorder without a dated note in
# STATUS.md. T1 (spec bootstrap: create this file structure) is complete and
# deleted from this list.

## T2 — Market-anchored projection converter  [CORE; split T2a/T2b/T2d/T2e]

T2a (2026-09-12): conditional offline converter implemented; eight new unit
tests pass through `ff.py selftest`. See docs/MARKET_ANCHOR.md for assumptions
and supported inputs. T2 remains incomplete until T2b passes.

T2d (2026-09-12): sourced and wired the rec_yd/rush_yd SD that T4 exposed as
missing, via `market_anchor.YARDAGE_SD_DEFAULTS` (provisional per-position
defaults, applied one layer up in `market_anchor_projection.py`, not inside
`convert_snapshot` itself). Real, non-null per-player projections now flow
for QB/RB/WR. Two things found and explicitly deferred, not fixed here: the
`rec_td`/`rush_td` vs. aggregate `td` market-name mismatch (narrowed
`REQUIRED_STATS_BY_POSITION` to core yardage stats only as a workaround),
and market_anchor/blend only ever covering whatever week a single fetch's
snapshot has lines for, never a full ROS range (so `evaluate_trade`'s
multi-week rollup still comes back null even though the per-week anchor
does not). Still provisional, not T2b-validated. See STATUS.md's 2026-09-12
T2d entry and docs/T2_ACCEPTANCE.json's `t2d_check`.

T2e (2026-09-13): parsed SportsGameOdds's aggregate anytime-TD market into
an expected-TDs value and added it to the anchor as an OPTIONAL stat (new
`convert_snapshot` parameter, backward compatible) -- present when the
market is posted and the league's rush_td/rec_td coefficients agree,
gracefully degraded to yardage-only (never null, never fabricated)
otherwise. Found along the way: the market is genuinely one-sided (no book
ever prices the "under" side) and, in live data, posts at a 1.5 ("2+ TDs")
threshold rather than the ticket's assumed 0.5 ("anytime") -- both changed
the conversion design; see STATUS.md's 2026-09-13 T2e entry for the full
reasoning. All 6 real players in the acceptance run moved from 33%-56% to
54%-88% of the default projection. `rec`/secondary rushing volume and T2b
validation remain open. See docs/T2_ACCEPTANCE.json's `t2e_check`.

T2c (2026-09-12): user-authorized prerequisite before T2b, completed. New line
rows retain provider player names and event time/week/team/status metadata
additively. Existing snapshots untouched. Run selftests and a real fresh-write
metadata check before committing as "T2c". This sequencing explicitly overrides
the one-ticket session default for the user's T2c-then-T2b request.

T2b: obtain verified identity/event metadata, team-total allocations and
closing-reference/final-box-score evidence for three players in one settled
week; run the original numerical acceptance below and refine the converter
if needed. Existing history alone does not establish these references.
T2b is deferred by the user's 2026-09-12 instruction; T3 may proceed without
weakening or substituting T2b validation. Do not treat the synthetic tests as empirical
validation or the conditional stat variance as calibrated forecast variance.

Build `advisor_runtime/market_anchor.py`: from an SGO snapshot (lines + BOTH
prices, see docs/MARKET_HISTORY.md) reconstruct market-implied fantasy points
per player-week under the league's scoring rules. De-vig prices to implied
probabilities; derive implied stat value from line + juice (e.g., a yardage
prop at 74.5 -110/-110 vs 74.5 -130/+110 implies different means). Handle
missing props via team-total share fallbacks. Output rows keyed
(player_id, week): {anchor_fp, implied_stats, source_ts, confidence}.
Note: the snapshot store keys line rows by the SportsGameOdds playerID, not
the engine's Sleeper pid -- join via `market_sources.resolve_provider_name`
the same way `market_sources.sports_game_odds` does at read time (see
docs/TRAPS.md's id-namespace entry). Do not invent a third ID.
Acceptance: hand-verify 3 players for one settled week against final box
scores distribution shape (not exact points -- check the anchor is within
~1 FP of the consensus close). Unit test included.

## T3 — Assumption registry + conservative blender  [CORE]
Implemented 2026-09-12; see docs/ASSUMPTIONS.md for the registry and guard
contract. Acceptance results and conservative decisions are in STATUS.md.

Build `advisor_runtime/assumptions.py`: JSON schema per docs/FORECASTING.md;
apply() blends anchor + weighted deltas with the 15% cap; half-life decay for
time-sensitive assumptions; games-played probability support (injury/workload
type). No web research inside this module -- assumptions are INPUTS, curated
by the advisor conversation.
Acceptance: unit tests covering cap, decay, double-count guard hook
(interface for T6).

## T4 — Wire projections into evaluator  [CORE; complete 2026-09-12]

Implemented as `ff.py trade --projection-source {sleeper,espn,market_anchor,
blend}`. See docs/PROJECTION_SOURCE.md for the mechanism and verified
results; acceptance results and the mechanism decision are in STATUS.md.
Default (flag omitted) is unchanged existing behavior, not "blend" -- the
ticket's "(default)" below is superseded, per this session's explicit rule
that existing evaluator/trade math must not change when the switch is
disabled; logged in STATUS.md's Decision Log rather than silently applied.

Add a projection source switch: sleeper | espn | market_anchor | blend
(default). Rerun the Walker<->London example (see STATUS.md's 2026-09-11
entry) end-to-end. Report: weekly PPG delta, playoff-week delta, bye effects,
and which assumptions moved the number and by how much.
Likely integration point: `advisor_runtime/advisor.py`'s
`_projection_for_week()` reads `player["weekly_points"]`, which `_sync_live()`
already blends from `player["weekly_points_by_source"]` (currently
`sleeper_projection_feed` + `espn`); a `market_anchor` source most likely adds
a third key to that same per-player map. `evaluate_trade()` (also in
advisor.py) is the trade-lineup-math consumer to rerun for the acceptance
check. UNCERTAIN: whether the source switch should be a `CONFIG` flag, a
per-request argument threaded through `build_packet`, or something else --
confirm during this ticket, don't guess further here.
Acceptance: same-shape output as the existing tested run + an
assumptions-attribution block. Compare blend vs. Sleeper-only side by side.

## T5 — Backtest harness  [CORE — this is the "accuracy" answer]
Build `advisor_runtime/backtest.py`: score any stored projection snapshot vs
actual results; MAE per source (anchor / Sleeper / ESPN / blend);
per-assumption-type error breakdown once 4+ weeks of data exist. Run on all
historical snapshots available now (`advisor_runtime/data/market_history/
sports_game_odds/*.jsonl`, plus whatever the engine already stores as
`weekly_points`/`weekly_points_by_source` for realized weeks).
UNCERTAIN: where realized/actual weekly stat lines come from for scoring --
no existing module in advisor_runtime fetches final box scores today.
Confirm the source during this ticket rather than assuming Sleeper's stats
endpoint covers it.
Acceptance: produces a report file for at least one completed week; numbers
sanity-checked.

## T6 — Delta table  [leverage, already designed]
Per-book line + price movement vs. baseline snapshot, projection movement
alongside. Feed the anti-double-count guard from T3: flag assumptions whose
news is already priced into line movement. Builds on
`advisor_runtime/data/market_history/sports_game_odds/` (append-only,
row_type "line"/"projection" -- see docs/MARKET_HISTORY.md); this is
explicitly the "next task" that prior market-history writer sessions
deferred, not something to fold into T2/T3.
Acceptance: flags reproduce 2 known examples (e.g., a post-injury line
crash).

## T7 — Conversational routing
Parse "Kenneth Walker for Drake London?" -> identify operation, trigger
targeted evidence refresh (stale-projection logic already exists as
`evidence_freshness()` and `CONFIG["snapshot_ttl_minutes"]` in
advisor_runtime/advisor.py, surfaced today via `ff.py refresh --rebuild`),
run T4, format decision report. Report template: market anchor -> assumption
list w/ confidence -> weekly + playoff PPG impact -> "what would change this
decision" thresholds.
Acceptance: the Walker<->London conversation runs from one user message with
no assistant intermediation.

## T8 — Risk-aware decision layer (later-season)
Championship probability, variance-seeking vs. floor-seeking by team state.
Acceptance: deferred until T5 has 4+ weeks of scored data.

# Session budget rule: if a ticket is not done in one session, STOP, log
# exact state in STATUS.md (done / blockers / exact next prompt), and split
# the remainder into T<n>a/T<n>b next session. Never leave uncommitted work.
