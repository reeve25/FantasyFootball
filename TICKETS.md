# TICKETS.md — self-contained, one agent session each.
# Agent instructions (paste at top of every session, any tool):
# "Read ADVISOR_SPEC.md and SESSION_LOG.md. You are working ticket T<n> only.
#  Do not expand scope. Run the acceptance check before finishing. Follow the
#  session-end protocol in ADVISOR_SPEC.md section 8."

## T1 — Spec bootstrap (human or 1 prompt)
Create this file structure at repo root: ADVISOR_SPEC.md, TICKETS.md, SESSION_LOG.md.
Fill section 4 of the spec from the engine summary. Nothing else.
Acceptance: files exist, committed.

## T2 — Market-anchored projection converter  [CORE]
Build `advisor_runtime/market_anchor.py`: from an SGO snapshot (lines + BOTH prices)
reconstruct market-implied fantasy points per player-week under the league's scoring
rules. De-vig prices to implied probabilities; derive implied stat value from line +
juice (e.g., a yardage prop at 74.5 -110/-110 vs 74.5 -130/+110 implies different
means). Handle missing props via team-total share fallbacks. Output rows keyed
(player_id, week): {anchor_fp, implied_stats, source_ts, confidence}.
Acceptance: hand-verify 3 players for one settled week against final box scores
distribution shape (not exact points — check the anchor is within ~1 FP of the
consensus close). Unit test included.

## T3 — Assumption registry + conservative blender  [CORE]
Build `advisor_runtime/assumptions.py`: JSON schema per spec section 2; apply()
blends anchor + weighted deltas with the 15% cap; half-life decay for time-sensitive
assumptions; games-played probability support (injury/workload type). No web research
inside this module — assumptions are INPUTS, curated by the advisor conversation.
Acceptance: unit tests covering cap, decay, double-count guard hook (interface for T6).

## T4 — Wire projections into evaluator  [CORE]
Add projection source switch: sleeper | espn | market_anchor | blend (default).
Rerun the Walker<->London example end-to-end. Report: weekly PPG delta, playoff-week
delta, bye effects, and WHICH assumptions moved the number and by how much.
Acceptance: same-shape output as the existing tested run + an assumptions-attribution
block. Compare blend vs Sleeper-only side by side.

## T5 — Backtest harness  [CORE — this is the "accuracy" answer]
Build `advisor_runtime/backtest.py`: score any stored projection snapshot vs actual
results; MAE per source (anchor / Sleeper / ESPN / blend); per-assumption-type error
breakdown once 4+ weeks of data exist. Run on all historical snapshots available now.
Acceptance: produces a report file for at least one completed week; numbers sanity-checked.

## T6 — Delta table  [leverage, already designed]
Per-book line + price movement vs baseline snapshot, projection movement alongside.
Feed the anti-double-count guard from T3: flag assumptions whose news is already
priced into line movement.
Acceptance: flags reproduce 2 known examples (e.g., a post-injury line crash).

## T7 — Conversational routing
Parse "Kenneth Walker for Drake London?" -> identify operation, trigger targeted
evidence refresh (stale-projection logic already exists), run T4, format decision
report. Report template: market anchor -> assumption list w/ confidence -> weekly +
playoff PPG impact -> "what would change this decision" thresholds.
Acceptance: the Walker<->London conversation runs from one user message with no
assistant intermediation.

## T8 — Risk-aware decision layer (later-season)
Championship probability, variance-seeking vs floor-seeking by team state.
Acceptance: deferred until T5 has 4+ weeks of scored data.

# Session budget rule: if a ticket is not done in one session, STOP, log exact
# state in SESSION_LOG.md, and split the remainder into T<n>a/T<n>b next session.
# Never leave uncommitted work.
