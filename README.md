# Fantasy Football Advisor

> **Archived (2026-09-18).** Superseded by a narrower trade-arbitrage tool. Kept as a reference for the forecasting and evaluation work below.

A command-line decision engine for a 12-team PPR redraft league. It pulls live league state from the Sleeper API,
blends public projections with market signals, and answers questions like "should I trade X for Y?" with an evidence packet
instead of a gut call.

## Highlights
- **Measured forecasting, not vibes.** A point-in-time XGBoost projection model scored on **25,903 player-weeks (2021–2025)**
  in exact league scoring, with walk-forward validation. Final pipeline MAE **4.71 fantasy points**. Features that didn't
  pay for themselves (implied team totals, matchup-opponent shrinkage: 4.7065 → 4.7078 MAE) were measured and removed.
  Report: [`docs/model_scorecard.json`](docs/model_scorecard.json).
- **Market anchoring.** Sportsbook lines are converted to projected points and blended with the model, with a guard against
  double-counting the same signal ([`docs/MARKET_ANCHOR.md`](docs/MARKET_ANCHOR.md)).
- **Trade evaluation.** Roster-aware trade search plus a replica of a third-party trade calculator, checked against the live service.
- **Tested.** 235 offline tests (runtime + integration), with backtest reports under [`docs/backtest/`](docs/backtest/).

## Stack
Python · XGBoost · pandas · polars · Sleeper API · nflverse (nflreadpy) · unittest

## Run
```bash
pip install -r requirements.txt
python ff.py packet "Kenneth Walker for Drake London?" --offline   # evidence packet for a question
python ff.py trade --give "Player A" --get "Player B"              # a specific offer
python ff.py model-scorecard                                       # re-score the projection model
python -m unittest discover -s advisor_runtime/tests -t .   # runtime tests (offline)
```

## Layout
| Path | What |
|---|---|
| `ff.py` | CLI entry point |
| `advisor_runtime/` | engine, projection sources, market anchor, trade search, backtest |
| `advisor_runtime/models/` | trained XGBoost artifacts + metadata |
| `docs/` | design notes: forecasting, assumptions, known traps, backtests |
| `AGENTS.md`, `CLAUDE.md`, `BRIEF.md` | instructions for the AI coding agents used to build and run it |

Built with Claude Code and Codex as pair programmers; the agent instruction files are part of the repo on purpose.
