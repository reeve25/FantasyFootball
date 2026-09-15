# Design Proposal: Richer Conversational Trade Intents

**Status**: DESIGN-ONLY (Proposal). No code implementation until user review and approval.
**Scope**: Extends conversational intent routing beyond explicit trades ("X for Y") to discovery and roster-strategy intents:
1. `buy_low_targets` ("Who should I buy low on?")
2. `sell_high_targets` ("Who should I sell high on?")
3. `roster_surplus_trade_away` ("Who should I trade away?")

---

## 1. Intent Taxonomy

| Intent Key | User Phrasing Examples | Purpose & Objective | Output Shape |
|---|---|---|---|
| `buy_low_targets` | "Who are good buy-low targets?", "Buy-low RBs", "Who is underperforming their volume?" | Identify players whose recent fantasy output lags their underlying structural volume / opportunity, depressing their perceived trade cost while forward projections remain strong. | Ranked shortlist of targets with: player name, position, owner, expected FP vs actual FP delta, opportunity stability metrics, target acquisition cost tier. |
| `sell_high_targets` | "Who should I sell high on?", "Sell high candidates", "Who is overperforming?" | Identify players on Reeve's team (or league-wide) whose recent fantasy points exceed sustainable volume-driven baselines (e.g., unsustainable TD variance or temporary injury vacancies). | Ranked shortlist of candidates with: efficiency vs volume divergence, TD regression expectation, schedule trajectory. |
| `roster_surplus_trade_away` | "Who should I trade away?", "Where do I have surplus?", "Who can I afford to lose?" | Analyze Reeve's roster to find positions where startable depth yields near-zero marginal lineup contribution, making players prime trade collateral to upgrade positions of deficit. | Positional surplus breakdown, player trade collateral rating, target positions of need, suggested trade archetype. |

---

## 2. Signals and Evidence Hierarchy

To honor the core system principle ("The market is the single hardest-to-beat baseline; beat consensus through structure, not hot takes"):

### A. Opportunity vs. Efficiency Divergence (Expected Fantasy Points - xFP)
- **Signal**: Ratio or difference between **Actual Fantasy Points** and **Expected Fantasy Points (xFP)** based on opportunity volume.
  - Opportunity metrics: Route participation rate, target share, red-zone targets, end-zone targets, rush attempts inside the 10-yard line.
  - High volume + low TD conversion = **Buy-Low**.
  - Moderate volume + extreme TD conversion (e.g., 3 TDs on 6 touches) = **Sell-High**.
- **Evidence standard**: Never treat short-term noise as talent changes. Target share and route participation stabilize much faster (100–150 routes) than TD rate or yards per target.

### B. Sportsbook Market vs. Public Sentiment Delta
- **Signal**: Posted player props (SGO yardage/TD implied means) vs public consensus projections or recent box scores.
  - If a player scored 6 FP last week but Vegas props still imply a 14.5 FP mean, the market treats the bad game as variance, not a role demotion.
  - If public sentiment crashes harder than the sportsbook line, a market-validated buy-low window exists.

### C. Roster Marginal Utility Delta (The Surplus Signal)
- **Signal**: Weekly lineup delta if player is removed:
  $$\Delta_{\text{lineup}} = \text{Projected Score}(\text{Full Roster}) - \text{Projected Score}(\text{Roster} \setminus \{\text{Player}\})$$
- If a player's projected PPG is 14.0, but Reeve's bench and flex options yield a replacement of 13.5 PPG, that player's **marginal lineup contribution is only +0.5 PPG**.
- Trading that player for a +2.5 PPG starter upgrade at a thin position (e.g., TE or RB2) yields a net team gain of +2.0 PPG.
- This provides an objective, math-grounded answer to "Who should I trade away?" rather than subjective roster intuition.

---

## 3. Overfitting Guardrail: The n=190 Problem

### The Constraint
- The repository's scored backtest currently comprises **190 player-weeks** across real settled Week 1 games (`docs/backtest/summary.json`).
- Fitting multi-parameter regression models, complex weights, or machine learning models on a single week of data will heavily overfit to Week 1 anomalies (unusual snap shares, blowout game scripts, uncharacteristic red-zone usage).

### The Guardrail Principles
1. **Zero Empirical Parameter Fitting on Small Samples**:
   - No tuned regression coefficients fitted to 190 observations.
   - Use only structurally justified, established football domain heuristics:
     - Volume metrics (targets, rushes) have high auto-correlation ($r \approx 0.65\text{--}0.75$ week-to-week).
     - Efficiency metrics (yards per carry, TD rate) have low auto-correlation ($r \approx 0.15\text{--}0.25$).
2. **Missing is Unknown, Never Zero**:
   - If snap count or route participation is unavailable for a player, do not impute zero or assume benching. Tag the signal as `unknown` and exclude from ranking unless verified.
3. **Dual Gate Verification**:
   - Any buy-low or sell-high recommendation must be confirmed by both:
     a. Underlying volume stability (snap/target share), and
     b. Sportsbook market baseline (de-vigged prop total $\ge$ replacement level).

---

## 4. Backtest & Acceptance Plan

Before any implementation of these intents can be deemed production-ready, it must satisfy an automated backtest harness:

1. **Synthetic Historical Backtest Protocol**:
   - Evaluate whether players identified as "Buy-Low" in Week $W$ outperformed their Week $W$ fantasy points in Weeks $W+1 \dots W+3$.
   - Evaluate whether players identified as "Sell-High" in Week $W$ experienced negative regression in Weeks $W+1 \dots W+3$.
2. **Acceptance Threshold**:
   - Backtest run across at least 4 scored weeks (deferred until data accumulates, consistent with T8 discipline).
   - Buy-low candidates must show positive subsequent delta relative to box-score trend in $\ge 60\%$ of qualifying player-weeks.
   - Surplus trade recommendations must demonstrate positive legal lineup $\Delta_{\text{pg}}$ under the existing `evaluate_trade` engine.

---

## 5. Proposed Phasing

- **Phase 1 (Current Session / T7)**: Focus strictly on explicit trade routing ("Kenneth Walker for Drake London?") + sensitivity threshold.
- **Phase 2 (Post-T7 User Review)**: Review this design, refine data source requirements (e.g. Sleeper stats vs SGO volume metrics).
- **Phase 3 (Ticket Definition)**: Formalize as a discrete ticket (e.g. `T10 — Conversational Trade Discovery & Surplus Routing`) once approved.
