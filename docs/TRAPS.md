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

## Performance

The per-week view rebuild over the full ~3,100-player board was the historical
bottleneck (49,731-package scan, ~1 hour). The engine already fixes this, but
NOT by memoizing: _pg_week() restricts the lookup to roster IDs instead of
scanning the full board. That is deliberate — no identity cache means a
projection changed in place is reflected immediately in the next score. Do not
add lru_cache here; it would reintroduce staleness the current design avoids.
Verify any performance patch by diffing against the unpatched path.

## Environment

Market keys live outside the repo at %USERPROFILE%\.codex\secrets\ — they read
as unconfigured from any sandboxed environment. Expected, not a
misconfiguration. advisor.py hard-disables the legacy engine market layer
(BP_API_KEY="", QUICK=True) by design. Do not "fix" this.

Cowork's local sandbox is broken by Windows KB5124008 (Sept 2026): device_bash
cannot mount host shares. File staging and committing still work. Run the
engine from Codex until that clears.
