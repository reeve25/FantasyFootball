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

## 2026-09-11 — Cowork execution blocked

Cowork's local sandbox is blocked by Windows KB5124008: device_bash cannot
mount host shares, so Cowork has no execution path to this folder. Its file
bridge still works — staging, listing and writing files are unaffected. Codex
or local PowerShell is the execution path until this clears.

docs/TRAPS.md was written this session through that file bridge, porting the
trap list from prior sessions. It is uncommitted by request; commit it from
Codex alongside the untracked USER_GUIDE.md.

Working tree after this entry: HEAD 3eda04e, STATUS.md modified, docs/TRAPS.md
and USER_GUIDE.md untracked, no other tracked file modified.

Unresolved: `ff.py status` and `ff.py lineup` were not run this session, and
were deliberately not run on a staged copy. The 10-slot lineup check is still
outstanding on this revision. The anchor-curve floor needed no change —
perceived_cap() already floors at zero and a selftest guards it.
