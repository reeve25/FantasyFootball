# Current development state

Updated 2026-09-14 (America/Los_Angeles). This file is a current-state handoff,
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
- T2 through T6 are complete. T2b passed against real settled Week 1 players;
  T6 added line/projection deltas and the anti-double-count guard.
- The workflow acceptance change is covered by the focused public-entrypoint
  integration test. The full offline suite passes: 189 runtime tests plus 32
  outer integration tests.

## Open development work

- T9 is the clearest next code objective: fix and test discovery sorting and
  unknown-contribution behavior in `advisor_runtime/trade_search.py`.
- T7 conversational routing and T8 risk-aware decisions are not started. T8
  remains intentionally deferred until several weeks of scored data exist.
- No real curated assumption entries exist yet; current assumption tests use
  fixtures. The T6 any-book rule and 3.0-unit movement threshold remain
  explicitly provisional.

## Active objective

No ticket is active. The workflow update is complete: compact current state,
agent code map, non-vacuous scored-backtest acceptance, and shared Git
discipline. Do not start T7, T8, or T9 without a new explicit objective.

## Validation and handoff

- For code changes, run the focused test and then `python ff.py selftest`.
- A backtest acceptance run must use `python ff.py backtest --require-scored`;
  `no_eligible_weeks`, unknown finality, invalid inputs, or zero scored rows do
  not satisfy acceptance even when the diagnostic run itself completed.
- Before commit, review exact staged content with `git diff --cached` and run
  `git diff --cached --check`.
