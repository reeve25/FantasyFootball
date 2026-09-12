# Shared system status

Updated 2026-09-12.

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

## 2026-09-11 — London talks with roster 1 closed, no deal

Reported by Reeve. Counterparty roster 1, Pukkake Gang (baran222).

- Talks ended with no trade. Nothing is pending or open with this manager.
- They wanted Drake London and offered Emeka Egbuka plus a lesser piece.
- They floated Kenneth Walker III in conversation but never formally offered
  him. Treat Walker as unpriced talk, not an offer that was on the table.
- Roster shape confirmed on both sides of the table: they are WR-rich and
  RB-poor. Any future package that sends them WRs for RBs is fighting that
  gradient; RB-for-Walker shapes are the ones that fit it.

Superseded by this entry: the exploratory numbers in the earlier 2026-09-11
23:00 UTC evaluation entry were priced before this outcome was known. They
remain valid as engine output, but no offer from them was ever live.

Environment, recorded again here because it changes what can be run from
Cowork: the Cowork sandbox now reaches api.sleeper.app and PyPI, scipy
installs, and the full engine runs there — selftest and a live-roster trade
both completed. Details and the superseded traps are in the 23:00 UTC entry
above and in docs/TRAPS.md. Egress has not been stable across sessions;
re-test rather than assuming it.

## 2026-09-12 — Planning-kit reconciliation (docs merge, no engine changes)

A new planning kit (ADVISOR_SPEC.md, TICKETS.md, SESSION_LOG.md at repo root)
was merged into the existing docs. One source of truth, zero duplication:

- docs/FORECASTING.md created from ADVISOR_SPEC.md sections 2–3: the
  market-anchored prediction method (anchor/adjust/blend/output/evaluate),
  assumption registry format, conservative blending with its 15% cap and
  anti-double-count rule, and the backtest/accuracy-measurement loop.
- ADVISOR_SPEC.md's other sections are superseded rather than copied
  verbatim, to avoid a second copy of the same facts: its goal statement
  (section 1) by BRIEF.md's own "League and objective"; its data inventory
  (section 4) by this file's 2026-09-11 entries and docs/TRAPS.md, which
  already cover the market-history writer, name-alias resolution, and
  resolution_status in more current detail; its build-order pointer
  (section 6) by docs/TICKETS.md; its Decision Log (section 7) by this
  file going forward — the one existing row is carried forward below; and
  its session-end protocol (section 8) by AGENTS.md's Ticket work section.
  ADVISOR_SPEC.md is deleted.
- TICKETS.md moved to docs/TICKETS.md. T1 ("spec bootstrap: create this file
  structure") is deleted — this reconciliation completes it. Ticket file
  paths and module names were checked against the real repo: T2/T3/T5's
  proposed new modules (advisor_runtime/market_anchor.py, assumptions.py,
  backtest.py) sit correctly alongside the existing market_sources.py/
  sleeper_live.py/trade_search.py. T4's and T7's vague "wire into the
  evaluator" / "stale-projection logic already exists" pointers were
  replaced with the actual functions: `_projection_for_week()` and
  `evaluate_trade()` in advisor_runtime/advisor.py for T4,
  `evidence_freshness()` / `CONFIG["snapshot_ttl_minutes"]` for T7. Two
  things stayed marked uncertain rather than guessed: T4's exact mechanism
  for a projection-source switch, and T5's source for realized/actual
  weekly stat lines (no existing module fetches final box scores).
- SESSION_LOG.md (header row only, no entries) folded into this file:
  ticket-session summaries now get a dated entry here instead of a separate
  table. Its Decision Log row from ADVISOR_SPEC.md section 7 is carried
  forward: 2026-09-12 — repo is source of truth, agents interchangeable,
  because session limits on Astra/Claude Code make chat-memory workflows
  die on switch. SESSION_LOG.md is deleted.
- Build order: T2 → T3 → T4 → T5 (market anchor, assumption registry, wire
  into evaluator, backtest harness) before T6, the delta table, which is
  deferred.

**Conflict logged, not resolved.** ADVISOR_SPEC.md's assumption registry
assigns each assumption an explicit confidence value (0–1) and describes
injury/workload risk as a registered "P(active) distribution." BRIEF.md's
evidence-quality rules say "Do not invent calibrated confidence percentages
or manager acceptance probabilities." Whether an internal blending weight
(`confidence_i` in `adjusted = anchor + SUM(confidence_i * delta_i)`) is the
kind of thing that rule means to forbid, or whether the rule is about claims
made to Reeve rather than internal pipeline parameters, is not decided here.
docs/FORECASTING.md transcribes the method as specified without resolving
this. Per BRIEF.md's precedence: until this is decided, no session should
present an assumption's confidence value to Reeve as a calibrated
probability.

## 2026-09-12 — Decision: confidence/P(active) conflict resolved, T3 unblocked

Confidence values and P(active) in the assumption registry are internal
blend weights only, never reported as advisor-facing calibrated
probabilities (BRIEF.md governs all user-facing output). Weights are
validated solely via the T5 backtest and default conservative until then.

This resolves the conflict flagged after commit aa7711d. T3 is unblocked.

## 2026-09-12 — T2a converter implemented; T2b empirical validation blocked

Implemented advisor_runtime/market_anchor.py: paired-price de-vig, explicit
yardage SD / Poisson count assumptions, existing provider-name alias joins,
per-stat distributions, supplied linear league scoring, documented team-share
fallback inputs, and null incomplete anchors. No evaluator changes or T3 work.
Model/input limitations are recorded in docs/MARKET_ANCHOR.md.

Actual regression run: `python ff.py selftest` passed 61 runtime + 31 other
tests (92 total), including eight new converter tests. Windows sandbox could
not launch installed Python; the approved local execution succeeded.

The T2 acceptance prerequisite check was run in PowerShell over all eight
history files and the provider cache; saved result: docs/T2_ACCEPTANCE.json.
All 18 cached events were unsettled; zero stored line rows could be linked to
a settled event through that metadata. New-format line rows also omit names.
No independent consensus-close/final-box-score fixture was available locally.
The required three-player numerical comparison therefore could not run and
has NOT passed. Synthetic unit checks do not satisfy that acceptance.

Split T2 into T2a (converter, complete) and T2b (real settled-week verification,
pending), as required by the session rule. Changes committed for handoff;
the pre-existing confidence-decision edit is preserved outside this commit.
No external historical data was purchased or fetched.

Exact next prompt: "Read the project docs. Work T2b only: obtain verified
settled-week SGO closing lines with both prices, provider names/event weeks,
and independent consensus-close plus final-box-score references for three
players; run T2's approximately-one-FP acceptance, refine the converter if
needed, update STATUS.md and commit. Do not start T3."

## 2026-09-12 — T2c settled-event metadata complete

User explicitly requested T2c then T2b in this session, with a separate T2c
commit first. Raw SGO cache inspection found eventID, status.startsAt,
info.seasonWeek, home/away team identities, player names and settlement flags.
New line writes preserve player_name and event_metadata additively; all old
fields and projection rows remain unchanged. No backfill or inferred weeks.

Acceptance run: `python ff.py selftest` passed 63 + 31 tests (94 total),
including metadata preservation/missing-field tests and existing reader tests.
`python ff.py packet "Show sportsbook lines for Cam Ward" --market-refresh`
then completed a real fresh fetch at 2026-09-12T19:31 UTC; the new snapshot
was checked for nonempty player name, kickoff time and provider season week.
Evidence: outputs/20260912T193111Z-c720eb26/evidence.json. Projection freshness
warnings in that packet are unrelated to the metadata-write acceptance.
Verdict: T2c PASS. Commit as "T2c" before proceeding to T2b.

## 2026-09-12 — T2b verdict: BLOCKED, approval required

T2c committed first as 7cc0a80. Fresh SGO metadata still reports zero settled
events among 18; NFL schedule verification shows Week 1 remains in progress
(https://www.nfl.com/schedules). The earliest local snapshot is September 11
19:05 UTC, after kickoff of the games already final. Thus no three-player
settled QB/RB/WR cohort with local pre-kickoff snapshots can be validated today.
Recheck evidence is recorded in docs/T2_ACCEPTANCE.json; no numerical anchor,
actual-distribution or approximately-one-FP consensus-close pass is claimed.

Proposed timing change, NOT approved or executed: resume after Week 1 settles
(September 15 UTC), using saved pre-kickoff evidence and retaining both original
acceptance checks. No substitution of post-kickoff lines, historical external
fixtures, or raw thresholds for consensus closing means was made. Stopping per
the user's explicit approval rule, without proceeding to T3 or T5.

Exact next prompt if approved: "Resume T2b after Week 1 settles. Use saved
pre-kickoff snapshots for a QB/RB/WR cohort; verify actual box-score distribution
shape and the original approximately-one-FP consensus-close criterion. If any
further substitution is needed, propose it and stop for approval. Record the
verdict in docs/T2_ACCEPTANCE.json and STATUS.md, then commit."

## 2026-09-12 — T3 complete: assumption registry and conservative blender

Done: advisor_runtime/assumptions.py implements the JSON registry schema,
strict local input validation/loading, stat-to-FP weighting, half-life decay,
availability-weight support, conservative aggregate cap and a tri-state
double-count guard interface. Returns reconciled FP attribution without numeric
confidence/P(active) fields; does not mutate inputs or perform network research.
docs/ASSUMPTIONS.md documents the contract. No T4 wiring or T6 implementation.

Acceptance actually run: `python ff.py selftest` passed 74 runtime + 31 other
tests (105 total), including 11 new T3 tests. The required cap, decay and
double-count guard cases all passed, alongside availability, negative scoring,
missing anchors, JSON loading, validation and immutability. No substitution.
T3 verdict: PASS. Blockers: none for T3. Commit message:
"T3: assumption registry and blender".

### Decision Log — conservative defaults selected for T3

- User explicitly deferred T2b and authorized T3. T2b remains unvalidated;
  no weaker test or settled-slate substitution was performed.
- Cap the gross sum of absolute weighted effects at 15% of abs(anchor),
  scaling attribution proportionally. This bounds net movement in either
  direction even when effects offset. No exceptional-evidence override;
  zero anchors cannot move and missing anchors stay missing.
- Half-life starts at week_range[0]; ranges are inclusive and season-scoped.
  Confidence is required input in [0,1], not assigned a guessed default.
- Stat deltas use explicit linear scoring. Availability delta is relative to
  active weight 1, constrained to [-1,0] for injury/workload. It is applied
  only to an explicitly conditional-on-playing anchor, weighted and decayed
  before the same cap. It never serves as an injury eligibility override.
- The T6 hook returns True=priced, False=checked/unpriced, None=unknown.
  Missing/unknown checks suppress effects; errors propagate. No permissive
  default and no line-movement implementation in this ticket.
- Changed means do not imply a calibrated variance: variance is unknown after
  a nonzero requested effect. Unchanged anchors retain supplied variance.
  Internal confidence and availability weights are not exposed as calibrated
  probabilities; BRIEF.md remains authoritative for advisor output.

Exact starting prompt for T4:
"Read BRIEF.md, STATUS.md, docs/FORECASTING.md, docs/TICKETS.md and
docs/ASSUMPTIONS.md. Work T4 only: wire sleeper | espn | market_anchor | blend
projection selection into the evaluator, choosing and documenting conservative
defaults. T2b remains deferred and unvalidated; do not work it or weaken its
acceptance. Use the T3 registry/blender contract and preserve unknown/priced-in
guards; never expose internal weights as calibrated probabilities. Run T4's
Walker/London acceptance with weekly PPG, playoff delta, bye effects and
assumption attribution, comparing blend versus Sleeper-only. If acceptance
cannot be satisfied as written, stop for approval rather than substitute.
Run selftests, update STATUS.md with results/blockers and commit. Do not start
T5 or T6."

## 2026-09-12 — T4 complete: projection-source switch wired into the evaluator

Done: `ff.py trade --projection-source {sleeper,espn,market_anchor,blend}`.
See docs/PROJECTION_SOURCE.md for the mechanism and full verified results.
New files: `advisor_runtime/market_anchor_projection.py` (glue: T2c line-row
metadata -> `market_anchor.convert_snapshot` -> `assumptions.apply`, per
player-week), `docs/PROJECTION_SOURCE.md`. Changed: `advisor_runtime/
advisor.py` (`select_projection_source`, additive), `advisor_runtime/
market_sources.py` (`read_snapshot_rows`, additive), `ff.py` (`trade`'s new
flag and worker wiring). No existing function was modified: `_projection_for_
week`, `optimize_lineup`, `_roster_average`, `_legalize_roster` and
`evaluate_trade` are byte-for-byte unchanged from T3.

### Decision Log — mechanism for the projection-source switch

- **Default stays "no switch," not "blend."** T4's own ticket text named
  blend as the default; this session's explicit rule ("existing evaluator
  and trade math behavior must not change when the new projection source is
  disabled") overrides that, and T2b is still unvalidated (blocked, per the
  2026-09-12 T2b entry above) -- defaulting live trade math to an unvalidated
  source would be reckless. Omitting `--projection-source` reproduces
  today's exact default (`weekly_points`, the existing sleeper+espn average).
- **Mechanism: reuse `evaluate_trade`'s own substitution, don't parameterize
  the evaluator.** The ticket flagged the switch mechanism itself as
  uncertain (CONFIG flag vs. a `projection_source` parameter threaded through
  `_projection_for_week`/`optimize_lineup`/`_roster_average`/
  `_legalize_roster`/`evaluate_trade`). Reading `evaluate_trade`, its own
  `independent_projection_checks` already substitutes
  `weekly_points_by_source[key]` into `weekly_points` for whatever source
  keys exist, then recurses with `source_checks=False` -- this is already
  the "same interface" the ticket asked for. `select_projection_source()`
  reuses that exact substitution as a snapshot-copy helper; none of the five
  evaluator functions needed a new parameter, so none were touched, which is
  a strictly stronger safety guarantee than a default argument would have
  been. This was picked over the parameter-threading approach because it
  required zero changes to tested code and reused an already-correct,
  already-tested mechanism instead of adding a second one.
- **market_anchor/blend computation is opt-in and isolated.** Only
  `--projection-source market_anchor`/`blend` imports
  `market_anchor_projection` (and transitively scipy) and fetches a fresh
  snapshot; `sleeper`/`espn` need neither. `yardage_sd`/`fallbacks` are
  passed empty -- no SD is invented for this ticket, consistent with T2b
  remaining unvalidated and deferred. `REQUIRED_STATS_BY_POSITION` covers
  QB/RB/WR/TE only; K is excluded because Sleeper kicking has no single
  linear `kick_pts` coefficient, which the linear converter cannot model.
- **A player with no computed anchor is never injected as an empty/null
  entry.** `inject_projection_sources` only adds a `weekly_points_by_source`
  key when at least one week has a real value, so `market_anchor`/
  `market_anchor_blend` simply don't appear in `independent_projection_checks`
  when both traded players are fully null -- no misleading all-null column.
- **The assumptions-attribution block is always present in output**, with an
  empty `attribution` list when nothing is curated to attribute (true today
  for every real player) -- required by the acceptance's output shape, not
  conditional on there being a nonzero adjustment.

### Acceptance: run, not substituted

Live rerun, 2026-09-12, `ff.py trade --give "Drake London" --get "Kenneth
Walker III"`, once per source:

| source | perspective_delta_pg | counterparty_delta_pg | playoff delta |
| --- | --- | --- | --- |
| default (flag omitted) | -0.0093 | -6.0097 | -0.6907 |
| sleeper | -0.4044 | -5.1222 | -1.3756 |
| espn | 0.3853 | -6.5896 | -0.0066 |
| market_anchor | null | null | null |
| blend | null | null | null |

`sleeper`/`espn` exactly reproduce the unmodified default run's own
`independent_projection_checks["sleeper_projection_feed"]`/`["espn"]`
entries -- proof the switch and the existing comparison agree, not just that
each runs without error. `market_anchor`/`blend` are honestly null: real
fresh lines were fetched and both players' identity/week resolved correctly
(the T2c metadata and the name-alias bridge both worked --
`market_anchor_diagnostics` shows zero identity/week failures for either
player), but both are rejected with `"reason": "Yardage SD assumption
required"` for `rec_yd`/`rush_yd`. This is the pre-existing T2b gap surfacing
correctly through the new wiring, not a new problem, and nothing was
substituted to paper over it -- no SD was invented to force a nonzero result.
Test suite: `python ff.py --selftest`, 94 runtime + 31 other tests (125
total) pass, including 20 new tests (5 for `select_projection_source`, 12
for `market_anchor_projection`, 2 for `read_snapshot_rows`, 1 proving
`evaluate_trade`'s unmodified `independent_projection_checks` discovers an
injected source on its own).

**Unrelated flaky test found while verifying, not fixed (out of scope for
T4):** `test_focused_market_packet_flags_and_warns_on_lost_book_coverage` in
`advisor_runtime/tests/test_market_history.py` fails intermittently
(~2 of 10 runs) on the pre-T4 commit (d9bb992) with no T4 changes present at
all -- confirmed by running it 10x against a git-stashed baseline. Cause not
investigated (likely a real-clock timestamp/file-ordering race in
`_previous_snapshot_path`, since that test's two fetches use `datetime.now()`
rather than a fixed fetch time, unlike most of that file's other tests). A
lone failure of just this test on a future `ff.py --selftest` run is this
known flake, not a regression; re-run to confirm before treating it as one.

**Out of scope, left for later tickets, not silently expanded into:**
`--projection-source` only exists on `trade`; `packet`/`lineup`/`rankings`
display paths (`_compact_player`, the `rankings` roster table) still call
`_projection_for_week` with no source argument and are unaffected. T7
(conversational routing) is the natural place to decide whether those need
it too.

Blockers: T2b (real settled-week SD/consensus-close validation) remains the
only thing standing between `market_anchor`/`blend` and a nonzero result;
nothing in T4 unblocks it, and T4 does not attempt to.

Exact starting prompt for T5:
"Read BRIEF.md, STATUS.md, docs/FORECASTING.md, docs/TICKETS.md and
docs/PROJECTION_SOURCE.md. Work T5 only: build
advisor_runtime/backtest.py scoring stored projection snapshots against
actual results (MAE per source: anchor/Sleeper/ESPN/blend). T2b and the
market_anchor/blend yardage-SD gap remain unvalidated and deferred -- do not
work T2b, invent an SD, or treat market_anchor/blend's current null output
as a defect to fix under T5. The ticket flags where actual weekly stat lines
would come from as uncertain: no existing module in advisor_runtime fetches
final box scores today. Resolve that by reading the real code/APIs available
(Sleeper's stats endpoints, if any) rather than guessing or fabricating
results data; if no reliable local source exists, stop and report that
rather than substituting synthetic actuals. Run T5's acceptance (a report
file for at least one completed week, numbers sanity-checked). If acceptance
cannot be satisfied as written, stop for approval rather than substitute.
Run selftests, update STATUS.md with results/blockers and commit. Do not
start T6 or T7."
