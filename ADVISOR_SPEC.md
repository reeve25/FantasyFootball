# ADVISOR_SPEC.md — Fantasy Football Superhuman Advisor
# Single source of truth. EVERY agent session starts by reading this file.
# Update the State + Decision Log at the end of every session. Commit everything.

## 1. Goal
A conversational trade/start-sit advisor that is *structurally smarter than consensus*:
market-anchored weekly projections, explicit testable assumptions, evaluated against
the user's ACTUAL lineup on a per-week PPG basis (playoff weeks weighted separately).
User already follows news. The advisor's job is implications + assumptions, not recaps.

## 2. Prediction philosophy (the "smart" method)
The market (Vegas player props + team totals, de-vigged) is the single hardest-to-beat
baseline for weekly player production. We do NOT try to out-guess it with hot takes.
We beat consensus through STRUCTURE:

1. ANCHOR: derive market-implied fantasy points per player-week from our own SGO
   snapshots (we store both sides + prices — that's enough to de-vig and reconstruct
   implied stat distributions). This is the baseline projection.
2. ADJUST with explicit, registered assumptions only. Each assumption is:
   {player, week_range, stat_affected, delta, confidence 0-1, rationale, source,
   half_life_weeks}. Examples: QB situation -> target share + efficiency; injury
   history -> weekly P(active) distribution (Walker-type workload/injury risk is a
   games-played probability, not a hunch); coaching/pace -> team-total share.
3. BLEND conservatively: adjusted = anchor + SUM(confidence_i * delta_i), with a hard
   cap (total adjustment <= 15% of anchor unless evidence is exceptional).
   Anti-double-count rule: if the delta table shows the line ALREADY moved on a news
   item, the market has priced it — do not adjust again for it.
4. OUTPUT a distribution (mean + variance), not a point. Variance drives floor/ceiling
   and risk-aware trade logic (e.g., a championship-window team may want MORE variance).
5. EVALUATE on weekly legal-lineup PPG with byes/FLEX/replacements (evaluator exists),
   playoff weeks reported separately.

## 3. Accuracy is measurable — and we measure it
Every stored projection snapshot is scored against actuals after the week.
Track: MAE of our blend vs (a) raw market anchor, (b) Sleeper projection, (c) ESPN.
Per-assumption-type hit rate (do QB-situation adjustments actually beat market?).
This backtest loop is what makes the advisor genuinely smarter over time instead of
just louder. Accuracy claim = "small, validated edge on top of the market," never
"we know more than Vegas."

## 4. Data inventory (current state — from engine summary)
- advisor_runtime/data/market_history/sports_game_odds: append-only SGO snapshots,
  both sides as separate rows with side field, price/odds persisted, engine-generated
  UTC timestamps, cache hits write nothing. Gitignored.
- Projection rows ("row_type: projection") written at same timestamp as line rows.
- Gated projection universe (~500 rows: players with a projection or posted line).
- name_aliases.json + normalize_name: SGO playerID <-> Sleeper pid join, 99.5% resolve.
- resolution_status per player + lost-book-coverage warning.
- Lineup evaluator: weekly legal lineups, replacements, FLEX, byes. Working.
- Trade evaluation exists (tested: Walker <-> London), ~5.5s + stale-projection refresh.
- Known gaps: market evidence attached AFTER lineup calc (not feeding forecasts);
  component adjustments substitute lines for stats without using prices; no backtest;
  no delta table; conversational routing done manually by assistant; no championship
  probability.

## 5. Architecture target (build ON the engine, no redesign)
projections layer (NEW: market_anchor -> assumption_registry -> blend -> distribution)
    -> existing lineup/trade evaluator (UNCHANGED interface: player-week points in,
      weekly PPG out)
evidence layer (SGO snapshots, delta table, Sleeper/ESPN) feeds projections layer.
advisor layer (conversation routing, decision report) sits on top.

## 6. Build order
See TICKETS.md. T1-T5 = core smart-prediction loop. T6-T8 = leverage. Do not reorder
without a note in the Decision Log.

## 7. Decision Log
| Date | Decision | Why |
|------|----------|-----|
| 2026-09-12 | Repo is source of truth; agents interchangeable | Session limits on Astra/Claude Code make chat-memory workflows die on switch |

## 8. Session-end protocol (MANDATORY for every agent, any tool)
1. Run the ticket's acceptance check. Paste result into the ticket.
2. Update State (section 4) if anything changed.
3. Append one line to Decision Log if you made any judgment call.
4. Commit with message format: `T<n>: <what>`.
5. Write SESSION_LOG.md entry: done / blockers / exact next prompt to use.
