# Market-anchored forecasting method

This describes the prediction method the market-anchored projection work
(docs/TICKETS.md T2-T5) implements: how a projection is derived from
sportsbook evidence, how explicit assumptions adjust it, and how accuracy is
measured afterward. It is an engineering/architecture spec for that pipeline,
not advice-session instructions -- BRIEF.md still governs how an assistant
talks to Reeve, and BRIEF.md wins wherever the two disagree (see the logged
conflict in STATUS.md's 2026-09-12 entry: this method's per-assumption
confidence values sit in tension with BRIEF.md's rule against inventing
calibrated confidence percentages; that tension is not resolved here).

Migrated from ADVISOR_SPEC.md sections 2-3, which is deleted; this file is
now the source of truth for the method itself.

## Prediction philosophy (the "smart" method)

The market (Vegas player props + team totals, de-vigged) is the single
hardest-to-beat baseline for weekly player production. The goal is not to
out-guess it with hot takes, but to beat consensus through structure:

1. **ANCHOR**: derive market-implied fantasy points per player-week from the
   engine's own SportsGameOdds snapshots. The snapshot store already keeps
   both sides of each line and each side's price (see docs/MARKET_HISTORY.md),
   which is enough to de-vig and reconstruct implied stat distributions. This
   is the baseline projection.
2. **ADJUST** with explicit, registered assumptions only. Each assumption is:
   `{player, week_range, stat_affected, delta, confidence 0-1, rationale,
   source, half_life_weeks}`. Examples: QB situation -> target share +
   efficiency; injury history -> a weekly P(active) distribution
   (workload/injury risk registered as a games-played probability, not a
   hunch); coaching/pace -> team-total share.
3. **BLEND** conservatively: `adjusted = anchor + SUM(confidence_i * delta_i)`,
   with a hard cap (total adjustment <= 15% of anchor unless evidence is
   exceptional). Anti-double-count rule: if the delta table (T6) shows a
   line already moved on a news item, the market has priced it -- do not
   adjust again for it. See docs/TRAPS.md's Forecasting section.
4. **OUTPUT** a distribution (mean + variance), not a point. Variance drives
   floor/ceiling and risk-aware trade logic (e.g., a championship-window team
   may want more variance, not less).
5. **EVALUATE** on weekly legal-lineup PPG with byes/FLEX/replacements (the
   evaluator already exists in the engine), playoff weeks reported
   separately -- the same standard BRIEF.md and docs/TRADES.md already hold
   ordinary trade advice to.

## Accuracy is measurable -- and it gets measured

Every stored projection snapshot is scored against actuals after the week.
Track: MAE of the blend vs. (a) the raw market anchor, (b) the Sleeper
projection, (c) ESPN. Per-assumption-type hit rate (do QB-situation
adjustments actually beat the market?). This backtest loop (T5) is what
makes the method genuinely smarter over time instead of just louder.

The accuracy claim this method is allowed to support is "a small, validated
edge on top of the market" -- never "we know more than Vegas."
