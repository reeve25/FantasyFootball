# Shared system status

Updated 2026-09-10, 10:27 PM America/Los_Angeles.

Production: C:\Users\reeve\Documents\FantasyFootball\ff.py
One local Git repository; no remote or publication. Existing sources and engine
downloads remain historical references. Do not restart from those copies.

## Verified in this consolidation

- 57 offline regression tests passed: existing behavior, identity, scoring,
  trade math, missing data, source freshness, deadlines, caches and entry point.
- Live submitted lineup returned all 10 slots in 5.31 seconds.
- After refresh, live comparison 3.11 seconds; exact trade 1.98 seconds;
  bounded 12-candidate discovery across 11 managers 3.06 seconds.
- Cold full projection refresh completed in 92.12 seconds. Source cache fetches:
  Sleeper 2026-09-11 05:23:19 UTC; ESPN 05:24:26 UTC. These are fetch times,
  not verified publication times. Future requests must inspect current ages.
- Original data survives refresh failure. A forced timeout stops the worker
  and returns valid JSON identifying unfinished work.
- No model API used. SportsGameOdds and The Odds API keys are configured;
  current market calls were not part of this maintenance smoke test.

## Assistant access

Codex fantasy skill now routes here. A Claude Code skill and local CLAUDE.md
are prepared. Claude desktop/Cowork still needs this folder selected/granted;
its access was not verified from this task. Ordinary chats without local tools
must receive a fresh compact evidence packet. README.md explains the workflow.

## Advice boundaries

No current trade negotiation has been carried forward as a live fact. Fetch
ownership and use the user's latest terms. Discovery is bounded research, not
an exhaustive scan. Flock's exact stable Fair Trade! verdict and current news
still need observation for finalist recommendations. Do not treat engine
positivity as fairness or invent acceptance percentages.

The current projection adapter uses the league's documented default scoring;
live current-week display points use live scoring. If league scoring changes,
revalidate the future-week adapter before claiming comparable ROS math.

## Handoff

Normal advice: read BRIEF.md, run one focused ff.py operation, research only
material current facts, answer briefly. No code work unless maintenance is
requested. Store material new negotiations here with dates and sources.

## 2026-09-11 — Verified from local PowerShell

Engine verified by running it from local PowerShell against this folder:

- selftest: 29 + 28 pass.
- lineup: all 10 slots returned in ~2s.
- packet --market: live SportsGameOdds props returned in 3.9s.
- Evidence writes to outputs/ as expected.

Cowork's local sandbox was blocked by Windows KB5124008: device_bash could not
mount host shares. Resolved by uninstalling the update; Windows updates are
paused until mid-October 2026 and the KB reinstalls when they resume. The
Cowork VM still cannot run the engine — no scipy, PyPI blocked by egress
policy — so only `ff.py status` runs there. Local PowerShell remains the
execution path for everything else. See docs/TRAPS.md.

docs/TRAPS.md was written this session through that file bridge, porting the
trap list from prior sessions. The anchor-curve floor asked for in that port
needed no change: perceived_cap() already floors at zero and a selftest guards
it.

docs/TRAPS.md and USER_GUIDE.md are committed at 4006853; the Cowork status
entry at 3fcc0a1.

## 2026-09-11 — Cowork run of `lineup --market` (17:55 UTC)

Requested from Cowork. device_bash was dead (VM failed to start) and computer
use grants terminals click-only, so the engine could not be run on the laptop.
Ran instead in the Cowork cloud container against a staged copy of the folder:
all four pinned deps were already present, so ff.py ran, but api.sleeper.app
and api.sportsgameodds.com are both 403 at the container proxy and the market
keys live outside the repo. Result: stale snapshot, no live league, no market.

Two findings, both recorded in docs/TRAPS.md:

- `--market` does nothing on `lineup`. The canned question carries no player
  names, so match_players returns empty and the market call is skipped while
  market_status still reads "not_requested". Verified the other direction:
  `packet "Is Jaxon Smith-Njigba a start this week" --market` did reach the
  provider and returned sports_game_odds=missing_key from the container.
- The device sandbox broke again and computer use cannot reach a shell.

Engine output (snapshot 07:49 UTC, 606 min old; Sleeper feed 05:23 UTC and
ESPN 05:24 UTC, both flagged stale): submitted starters in the snapshot are
identical to the optimizer's lineup, so no lineup change was indicated.
Known subtotal 122.72 over 8 of 10 slots; Jake Bates and Jacksonville DEF
carry no projection (missing, not zero), so projected_total is null.
Nothing about this run establishes current injury status.

## 2026-09-11 — Cowork VM can now run the engine (23:00 UTC)

Contradicts the two environment traps recorded earlier today. Observed from
device_bash in the Cowork VM, this session:

- `api.sleeper.app` returns 200. League, rosters, users, `players/nfl`
  (12,227 entries) and `state/nfl` all fetched directly.
- PyPI is reachable: `pip install scipy` succeeded (scipy 1.15.3), which was
  the single blocker on importing `advisor_runtime.engine.ff_v6_3`.
- `ff.py selftest` passes 38 + 30 in the VM.
- `ff.py trade` completed in ~3.8s with `rosters.status = fresh`,
  live_refreshed_at 2026-09-11T23:01:27Z — the engine pulled live league
  ownership itself, so roster reads no longer need a manual cross-check here.

Unchanged: market providers still read false from the VM (`sports_game_odds`,
`the_odds_api`, `bettingpros`, `fantasypros`) because the keys live outside the
repo at %USERPROFILE%\.codex\secrets\. Market data remains PowerShell-only.

Projection snapshot used: generated 18:27 UTC, 274 min old; Sleeper feed
18:06 UTC and ESPN 18:07 UTC, both inside the 720-minute bar. No refresh run.

## 2026-09-11 — Walker / London trade evaluation (23:00 UTC)

Reeve asked whether to trade Drake London for Kenneth Walker III straight up,
and whether David Montgomery for Rome Odunze works alongside it. Counterparty
for both is roster 1, Pukkake Gang (baran222), who holds Walker and Odunze.

Engine results, blended basis, effective week 2, E[best8] pts/gm:

- London -> Walker: me -0.07, them -5.94. Sources straddle zero
  (ESPN +0.26, Sleeper -0.40). Dead even for me, large loss for them.
- Montgomery -> Odunze: me -1.31, them +1.68. Wrong direction.
- London + Montgomery -> Walker + Odunze: me -0.99, them +1.14.
- Montgomery -> Walker: me +2.73, them -2.62. Positive on all three
  sources (ESPN +4.19, Sleeper +1.16). Playoff weeks +3.33.
- Javonte Williams -> Walker: me +0.91, them -0.86. Positive on all three.
  The most acceptable shape found.
- Etienne -> Walker: me +1.76, them -1.65.

No offer sent. Nothing here is a negotiation in progress; Reeve has not
contacted baran222. Player status per the Sleeper API only, at Reeve's
direction for this evaluation: Odunze Questionable (leg); Walker, London and
Montgomery all Active with no designation. No reporting was used.
