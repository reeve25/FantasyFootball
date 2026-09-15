# Agent task-to-code map

Use this map after `BRIEF.md` and `STATUS.md`. Search named symbols first; read
whole files only when the task truly spans them.

| Task area | Start with | Focused tests |
|---|---|---|
| Public CLI, timeouts, compact packets, run artifacts | `ff.py`: `parser`, `worker`, `compact`, `main` | `tests/test_entrypoint.py`, `advisor_runtime/tests/test_entrypoint.py` |
| Packet shape, intent, lineup, trade math | `advisor_runtime/advisor.py`: `classify_intent`, `build_packet`, `optimize_lineup`, `evaluate_trade`, `select_projection_source` | `advisor_runtime/tests/test_advisor_v2.py`, `tests/test_evidence_integrity.py` |
| Live Sleeper league data and short cache | `advisor_runtime/sleeper_live.py`: `_get_json`, `fetch_live_context` | `tests/test_live_requests.py` |
| Sportsbook providers and market-history writes | `advisor_runtime/market_sources.py`: `sports_game_odds`, `_write_sports_game_odds_snapshot`, `focused_market_packet`, `fetch_event_status` | `advisor_runtime/tests/test_market_sources.py`, `test_market_history.py` |
| Market conversion | `advisor_runtime/market_anchor.py`: `convert_snapshot`, `touchdown_distribution` | `advisor_runtime/tests/test_market_anchor.py` |
| Projection-source injection and fallback | `advisor_runtime/market_anchor_projection.py`: `compute_projection_sources`, `apply_consensus_fallback`, `inject_projection_sources` | `test_market_anchor_projection.py`, `test_projection_source.py` |
| Assumption blending and priced-in guard | `advisor_runtime/assumptions.py`: `apply`; `delta_table.py`: `compute_deltas`, `build_priced_in_guard` | `test_assumptions.py`, `test_delta_table.py` |
| Backtest behavior and scored acceptance | `advisor_runtime/backtest.py`: `run_backtest`, `score_event_player`, `summarize`; `ff.py:worker` | `advisor_runtime/tests/test_backtest.py`, `tests/test_entrypoint.py` |
| Trade discovery | `advisor_runtime/trade_search.py`: `discover` | `advisor_runtime/tests/test_trade_search.py` |
| Legacy projection adapter only | `advisor_runtime/advisor.py:load_engine` identifies the narrow calls into `advisor_runtime/engine/ff_v6_3.py` | `tests/test_oracle_performance.py` plus the caller's focused tests |

## Do not open routinely

- `advisor_runtime/data/snapshot.json`, provider/live caches, `.ffcache/`, or
  market-history files: inspect metadata or selected rows through existing
  readers and CLI output.
- `outputs/`, diagnostics logs, or full evidence bundles: start with the compact
  packet and open only the named field needed to debug.
- `docs/backtest/<run>.json`: use `docs/backtest/summary.json` unless individual
  records are required.
- `advisor_runtime/engine/ff_v6_3.py`: it is a large preserved adapter. Enter it
  only when evidence points to an engine symbol rather than the wrapper.
- `migration_backups/` and old Git history during ordinary implementation.

## Test commands

Run the narrow test module first, for example:

`python -m unittest discover -s tests -p test_entrypoint.py -q`

Then run the complete, fast offline suite:

`python ff.py selftest`

For a real scored-backtest acceptance gate, use:

`python ff.py backtest --require-scored`
