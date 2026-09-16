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
