# Current development state

Updated 2026-09-15 (America/Los_Angeles). This file is a current-state handoff,
not a session log. Use `git log` and focused component docs for history.

## Repository

- Production entry point: `ff.py`; internal code is under `advisor_runtime/`.
- Branch: `main`, with local commits not yet synchronized to `origin/main`.
- Existing untracked local tooling includes `.claude/`, `.mcp.json`,
  `.playwright-mcp/`, `.serena/`, `Claude outputs/`, and `docs/TOOLING.md`.
  Preserve it unless a task explicitly addresses tooling setup.
- Historical runtime data, caches, and normal run output are ignored by Git.
  Raw backtest reports currently remain tracked under `docs/backtest/`.

## Verified production state

- Snapshot schema 2 is present; the saved projection snapshot was generated at
  `2026-09-15T00:00:01Z`.
- The latest scored backtest contains 190 player-weeks. Its tracked summary is
  `docs/backtest/summary.json`.
- T2 through T7 and T9 are complete. T2b passed against real settled Week 1
  players; T6 added line/projection deltas and the anti-double-count guard;
  T7 conversational trade routing defects fixed (dynamically resolving third-party trades, removing prose from decision report, removing duplicate sensitivity key). T9 fixed discovery tie-break and contribution defects. QBs market_anchor projection vastly improved by including pass_td and rush_yd. T10 added conversational intents for surplus/buy-low/sell-high.
- The 2021-2025 point-in-time public-model scorecard is available through
  `python ff.py model-scorecard`. It scores 25,903 player-weeks in exact league
  scoring, retains ffopportunity, nflverse usage/participation/NGS/FTN signals,
  and historical FantasyPros ECR, and writes the measured report to
  `docs/model_scorecard.json` plus a trained XGBoost artifact under
  `advisor_runtime/models/`. Implied team totals and fitted matchup-opponent
  shrinkage were both measured and removed (matchup shrinkage regressed the
  2024 walk-forward season, 4.7065 -> 4.7078 MAE, for a negligible aggregate
  gain; see `docs/HANDOFF.md`). Final step is `5_consensus_ecr`, MAE 4.7101.
- The full offline suite passes: 200 runtime tests plus 35 outer integration
  tests (235 total). Real acceptance check `python ff.py packet "Kenneth Walker
  for Drake London?" --offline --flock` PASS with live Flock ranks, values,
  suggestions, and exact `You win!` verdict evidence.

## Open development work

- Flock's public web API is now integrated behind `--flock` for explicit offers
  and discovery finalists. The API is undocumented, so failures remain
  fail-closed and the browser workflow remains a fallback audit.
- Structural volume metrics (snap share and target share) are now fully integrated
  via the live Sleeper stats API into the runtime snapshot and surface naturally
  for buy-low/sell-high trade intents without additional manual fetching. Empirical
  weights have deliberately not been fitted yet.
- T8 risk-aware decisions remains intentionally deferred until several weeks of
  scored data exist.
- Live 2026 inference for the public model is implemented via feature-tier variants (`full`, `no_ftn_ngs`, `opp_ecr`), which dynamically drop down to the richest available tier depending on current-week data availability. A fallback is explicitly surfaced if foundational `ffopportunity` data is missing.
- Historical player props and ffanalytics archives remain unmeasured for the
  explicit reasons recorded in `docs/model_scorecard.json`.
- No real curated assumption entries exist yet; current assumption tests use
  fixtures. The T6 any-book rule and 3.0-unit movement threshold remain
  explicitly provisional.

## Active objective

Task 3 (feature-tier variants and live tier selection) is complete. The next independent objective is Task 4: same-sample head-to-head comparison of the trained public model blend vs sleeper+espn on identical player-weeks, wiring the blend in as opt-in first.

## Validation and handoff

- For code changes, run the focused test and then `python ff.py selftest`.
- A backtest acceptance run must use `python ff.py backtest --require-scored`;
  `no_eligible_weeks`, unknown finality, invalid inputs, or zero scored rows do
  not satisfy acceptance even when the diagnostic run itself completed.
- Before commit, review exact staged content with `git diff --cached` and run
  `git diff --cached --check`.
