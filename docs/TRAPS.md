# Traps and doctrine

Hard-won findings from prior sessions. Read before changing engine logic or
pricing a trade.

## Doctrine

- Team strength is E[best8(X)], never best8(E[X]). The latter overstates
  high-variance rosters; the fix moved five teams in the power rankings.
- Never gate a trade on COIN_FLIP (2.76/gm). That is the per-player forecast
  MAE, not a minimum edge. Backtest (n=905, 3 seasons) measured ~100% capture
  at every magnitude. Report edge with p_right beside it; never suppress a
  positive-EV trade. The real filter is acceptance, not significance.
- The tradeable range in a 12-team league of protective managers is 0.5–2.0/gm.
- Run the engine. A hand estimate that contradicts it is wrong — one +2.5/gm
  hand estimate was actually -7.68/gm because the package emptied the TE slot.
- Bye weeks are a tiebreaker, not a filter.
- Never roster a QB2. The free-agent QB pool is nearly as strong as the starter.
- Call tail_flagged() before reporting any trade (exempt list, injury,
  suspension risk).

## Trade shape

- Consolidation trades (3-for-2, 2-for-1) look positive only on a flat weekly
  basis and go negative at any rho>0. Clean 2-for-2 deals hold up. Price with
  the information-bracket function before recommending.
- Stacking low-round bench filler to sweeten a deal reads as a scam to
  counterparties. Real players on both sides.
- The looks/acceptance metric had a floor bug — negative anchors for
  sub-replacement players inflated the score exactly when filler was stacked.
  Fixed: perceived_cap() floors at max(0.0, ...), every looks computation
  routes through it, and a selftest guards it. Treat looks as directional
  anyway; the manager's own read on fairness has been more reliable.
  Separate minor gap, not this bug: _scan_player_pool reads the raw anchor
  instead of perceived_cap — that only orders the candidate pool, never the
  acceptance score.
- The anchor curve's edge over ADP barely exists in August and becomes useful
  around Week 6 onward.
- Asymmetric scan filter: our best-8 gain above threshold. Requiring both teams
  to gain on the same value function is structurally broken for 2-FLEX PPR.

## Data sources

- Prefer sportsbook/market lines over projection-site consensus. Books reprice
  on news; projection sites lag.
- ESPN inflates RB projections ~+1.29/gm above market. Use the de-biasing blend.
- The Rotowire weekly feed is FLAT (median week-to-week CV 0.014 vs 0.35–0.50
  for a real weekly set). Bye, worst-week, and playoff-split numbers carry no
  week-level information. State this rather than claiming weekly precision.
- consensus_line carries no timestamp. Stale season props produce large false
  positives — always cross-check current player status.
- Never trust a roster read from a single web fetch; it can fabricate a
  plausible-looking roster. Cross-check before pricing anything on it.
- Position forecast SDs: RB 3.85, WR 3.20, QB 3.02, TE 2.27.
- Thin book coverage on bench depth is not a problem — those players contribute
  ~0.00 to best-8.
- A null sportsbooks block under --market means one of two things: the
  player's game has already started or finished (no live props — expected, not
  a gap), or no lines are posted (a real coverage gap). Check kickoff before
  treating it as missing data. Either way, a comparison where one side has
  market data and the other doesn't is not on a common basis — drop --market so
  both sit on projections, or treat the gap as unpriced.

## Performance

The per-week view rebuild over the full ~3,100-player board was the historical
bottleneck (49,731-package scan, ~1 hour). The engine already fixes this, but
NOT by memoizing: _pg_week() restricts the lookup to roster IDs instead of
scanning the full board. That is deliberate — no identity cache means a
projection changed in place is reflected immediately in the next score. Do not
add lru_cache here; it would reintroduce staleness the current design avoids.
Verify any performance patch by diffing against the unpatched path.

## Known bugs

- device_commit_files can report success while writing stale bytes when reusing
  a container path already committed from. It returns {"written":[...]} with no
  rejections and bumps mtime. Read the file back or check its size after any
  repeat write to the same path; write from a fresh path if it mismatches.
- discover excluded 27 of 60 candidates (45%) for incomplete_projection_math on
  a bounded scan, 24.9s of a 45s ceiling. An empty shortlist does not mean no
  good trade exists — nearly half were never priced.
- The Cowork VM cannot run the engine. scipy is absent and PyPI is blocked by
  egress policy, so anything importing ff_v6_3 fails at `from scipy.stats
  import poisson`. Only `status` runs there.
  SUPERSEDED 2026-09-11 23:00 UTC: both halves of this are now false in the
  VM. `pip install scipy` succeeds (1.15.3) and api.sleeper.app returns 200,
  so selftest (38+30) and a live-roster `trade` both run there. Egress is not
  stable across sessions — re-test rather than assuming either state.
- `--market` is a silent no-op on `lineup`, `rankings`, `movers` and
  `transactions`. ff.py builds those from a canned question string, and the
  market block runs `match_players(question, current)` — the canned strings
  contain no player names, so `focus` is empty and `focused_market_packet` is
  never called. Worse, `market_status` is left reading "not_requested; use
  --market when it can change this decision" even though the user did request
  it. Only `packet "<question naming players>"` and `trade` (which uses
  give/get ids) actually reach the sportsbooks. Observed 2026-09-11.
- latest.json records the executing environment's own path spelling: VM runs
  store /sessions/.../mnt/FantasyFootball/outputs/..., PowerShell runs store
  C:\Users\reeve\... Anything resolving paths from latest.json breaks across
  environments.

## Environment

Market data is PowerShell-only. Keys live outside the repo at
%USERPROFILE%\.codex\secrets\, so `ff.py status` run from the Cowork VM reports
all four providers false — sports_game_odds, the_odds_api, bettingpros,
fantasypros (observed 2026-09-11). Expected, not a misconfiguration.
advisor.py hard-disables the legacy engine market layer (BP_API_KEY="",
QUICK=True) by design. Do not "fix" this.

The Cowork device sandbox is unreliable again: on 2026-09-11 device_bash
returned "Workspace unavailable. The isolated Linux environment on this device
failed to start." device_list_dir / device_stage_files / device_commit_files
still worked throughout, so the file bridge survives a dead VM.

Cowork computer use cannot drive a terminal. Windows PowerShell, Terminal and
File Explorer all resolve at tier "click" — visible and left-clickable, no
typing, key presses or paste. Clicking the File Explorer taskbar icon never
raised a window above the masked full-screen apps, so launching a .bat by
double-click did not work either. There is currently no path from Cowork to a
local shell: market runs need Reeve at the keyboard, or a .bat he clicks.

The Windows KB5124008 sandbox break (Sept 2026) is resolved: uninstalling the
update restored the device_bash mount. Windows updates are paused until
mid-October 2026 — the KB reinstalls when they resume and will break the mount
again.
