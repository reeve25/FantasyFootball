# T4 projection-source switch

`ff.py trade --projection-source {sleeper,espn,market_anchor,blend}` selects
which weekly-points basis `evaluate_trade` uses. Omitting the flag leaves
today's existing default (`player["weekly_points"]`, already a sleeper+espn
average) completely unchanged -- no function in the evaluator
(`_projection_for_week`, `optimize_lineup`, `_roster_average`,
`_legalize_roster`, `evaluate_trade`) was modified to add this switch.

## Mechanism

`evaluate_trade` already builds `independent_projection_checks` by
substituting each key found in any player's `weekly_points_by_source` into
`weekly_points`, then recursing on itself (`source_checks=False`). T4 reuses
that exact substitution as the switch itself instead of adding a parameter
threaded through five functions:

- `advisor.select_projection_source(snapshot, source)` returns a snapshot
  copy where every player's `weekly_points` is replaced by
  `weekly_points_by_source[key]` for the requested source
  (`sleeper` -> `sleeper_projection_feed`, `espn` -> `espn`,
  `market_anchor` -> `market_anchor`, `blend` -> `market_anchor_blend`). A
  player missing that key gets `weekly_points = {}`, which
  `_projection_for_week` already reports as `"missing"`, never a zero.
- `ff.py`'s worker calls this only when `--projection-source` is given, then
  calls the unmodified `build_packet`/`evaluate_trade` on the result. The
  `independent_projection_checks` comparison table comes along for free and,
  once market_anchor/blend keys exist, includes them automatically --
  satisfying "compare blend vs. Sleeper-only side by side" without any
  change to `evaluate_trade` itself.

See STATUS.md's T4 Decision Log entry for why this mechanism was chosen over
threading a `projection_source` parameter through the evaluator.

## Computing market_anchor / blend

Only `--projection-source market_anchor` or `blend` triggers this (`sleeper`
and `espn` need no fetch, since those keys already exist). For the traded
players only:

1. `market_sources.sports_game_odds(focus, force_refresh=True)` fetches a
   fresh snapshot; `market_sources.read_snapshot_rows(path)` reads its rows.
2. `market_anchor_projection.compute_projection_sources(...)` bridges
   identity/week via T2c's `player_name`/`event_metadata` fields
   (`build_identity_inputs`), builds `required_stats` per position
   (`REQUIRED_STATS_BY_POSITION` -- QB/RB/WR/TE only; K has no linear
   `kick_pts` scoring coefficient and is excluded), runs T2's
   `convert_snapshot`, then T3's `assumptions.apply()` per player-week
   (empty registry by default -- with nothing curated yet, "blend" is
   correctly identical to the anchor). Real league `scoring_settings` are
   used; no coefficient is invented.
3. `inject_projection_sources(...)` adds `market_anchor`/`market_anchor_blend`
   keys to `weekly_points_by_source` for players with at least one non-null
   week -- additively, never mutating existing keys, never padding a fully
   null player with an empty entry.

**Updated by T2d (2026-09-12).** `yardage_sd` now defaults to
`market_anchor_projection.build_default_yardage_sd(players)` --
`market_anchor.YARDAGE_SD_DEFAULTS`'s provisional per-position values,
applied whenever `compute_projection_sources` isn't told
`use_default_yardage_sd=False` or given an explicit override for that exact
(pid, week, stat). See STATUS.md's T2d entry for how those defaults were
sourced (the engine's own backtested `SIGMA_POS`, converted from
fantasy-point to yardage units for primary stats; separately-reasoned
constants for secondary stats) and the two real, cross-book/alt-line
approaches that were checked and rejected first. `fallbacks` is still not
supplied (empty `{}`): no team-share default exists or is invented.
`REQUIRED_STATS_BY_POSITION` was also narrowed by T2d to each position's
core yardage stat(s) only (`QB: [pass_yd]`, `RB: [rush_yd, rec_yd]`,
`WR: [rec_yd]`, `TE: [rec_yd]`) after finding that `rec_td`/`rush_td` can
never resolve -- SportsGameOdds only posts an aggregate anytime-TD market,
never split by rushing/receiving -- which had been silently nulling every
T4 result independently of the SD gap. `anchor_fp` is therefore a
yardage-only partial approximation, more so than originally designed.
A player-week the fetch has no lines for still nulls appropriately; a
player-week it does cover now produces a real, non-null number.

The packet also gets, only when a market_anchor/blend fetch ran:
`market_anchor_diagnostics` (rejected-evidence rows from `convert_snapshot`)
and `assumption_attribution` (`{pid: {week: {anchor_fp, adjusted_fp,
cap_applied, attribution}}}` -- present, possibly with an empty
`attribution` list, even when nothing was curated to attribute).

## Verified (T4, 2026-09-12, superseded in part by T2d below)

`python ff.py trade --give "Drake London" --get "Kenneth Walker III"` rerun
with each source, live, 2026-09-12:

| source | perspective_delta_pg | counterparty_delta_pg | playoff delta |
| --- | --- | --- | --- |
| (default, unset) | -0.0093 | -6.0097 | -0.6907 |
| sleeper | -0.4044 | -5.1222 | -1.3756 |
| espn | 0.3853 | -6.5896 | -0.0066 |
| market_anchor | null | null | null |
| blend | null | null | null |

`sleeper`/`espn` exactly reproduce the default run's own
`independent_projection_checks` entries for those sources, confirming the
switch and the existing comparison agree. `market_anchor`/`blend` came back
null at the time: `market_anchor_diagnostics` showed `"reason": "Yardage SD
assumption required"` for both players -- fixed by T2d below (though see
T2d's own new finding on why the *trade-level* row still won't show a
number even now).

## T2d re-verification (2026-09-12): per-player anchors are real; the trade rollup has a separate, new limit

With the SD sourced and `REQUIRED_STATS_BY_POSITION` narrowed to core
yardage stats (see STATUS.md's T2d entry), the same command now produces
real per-player, per-week `market_anchor`/`market_anchor_blend` values --
verified for 6 real players across QB/RB/WR in docs/T2_ACCEPTANCE.json's
`t2d_check` (e.g. Drake London 5.51 anchor vs. 13.93 default, a plausible
~40% yardage-only share). `independent_projection_checks` in that packet
now includes real `market_anchor`/`market_anchor_blend` entries alongside
`espn`/`sleeper_projection_feed`, exactly as designed.

The trade's own top-level `perspective_delta_pg`/`counterparty_delta_pg`
under `--projection-source market_anchor`/`blend` still comes back null,
for a different reason than before: `evaluate_trade` averages every week
from the trade's effective week through week 17, and a single market fetch
only ever has lines for the current week. `weekly_points_by_source[
"market_anchor"]` therefore has just one week's entry, and `_roster_average`
requires every week in range to resolve. No SD fix addresses this -- it's a
structural mismatch between single-week market coverage and a multi-week
evaluator, left open for a future ticket (not T5, per STATUS.md's T2d
next-prompt, unless it blocks T5's own acceptance).

## T2e re-verification (2026-09-13): the anchor includes touchdowns now

`market_anchor` was yardage-only through T2d because `REQUIRED_STATS_BY_
POSITION` had dropped `rec_td`/`rush_td` (unfulfillable -- SGO only posts an
aggregate anytime-TD market). T2e parses that aggregate market into an
expected-TDs value and adds it as an OPTIONAL component (present when
posted, degrades to yardage-only rather than null when not -- see
STATUS.md's T2e entry and docs/MARKET_ANCHOR.md). Same 6 players, same
command shape, live 2026-09-13 (docs/T2_ACCEPTANCE.json's `t2e_check`):

| player | pos | default | T2d (yardage-only) | T2e (yardage+TD) |
| --- | --- | --- | --- | --- |
| Trevor Lawrence | QB | 17.79 | 9.32 (52%) | 11.34 (64%) |
| Justin Herbert | QB | 18.67 | 9.44 (51%) | 10.79 (58%) |
| Javonte Williams | RB | 16.32 | 8.61 (53%) | 13.98 (86%) |
| Kenneth Walker III | RB | 14.18 | 7.97 (56%) | 12.48 (88%) |
| Drake London | WR | 13.93 | 5.51 (40%) | 7.68 (55%) |
| Rome Odunze | WR | 11.73 | 3.92 (33%) | 6.28 (54%) |

All 6 got a real, non-fabricated TD component this run and moved materially
closer to the default. The trade-level multi-week rollup limitation
described above is unchanged by T2e -- it's about weeks 2-17 having no
market data at all, not about which stats the anchor includes.
