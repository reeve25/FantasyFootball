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

`yardage_sd`/`fallbacks` are **not supplied** in this wiring (empty `{}`):
without a T2b-validated SD, every yardage-dependent stat (`rec_yd`,
`rush_yd`, `pass_yd`) stays a documented missing component, so `anchor_fp`
is null for any real skill player today. This is expected, not a wiring bug
-- see STATUS.md's T2b block. `market_anchor`/`blend` will stay null in
practice until T2b lands a validated SD source.

The packet also gets, only when a market_anchor/blend fetch ran:
`market_anchor_diagnostics` (rejected-evidence rows from `convert_snapshot`)
and `assumption_attribution` (`{pid: {week: {anchor_fp, adjusted_fp,
cap_applied, attribution}}}` -- present, possibly with an empty
`attribution` list, even when nothing was curated to attribute).

## Verified

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
null for both players: `market_anchor_diagnostics` shows
`"reason": "Yardage SD assumption required"` for both (pid 8112 Drake
London, pid 8151 Kenneth Walker) -- real fresh lines were fetched and both
players' identity/week resolved correctly (T2c metadata + the alias bridge
both worked), but neither has a documented receiving/rushing-yardage SD,
which is exactly the pre-existing T2b gap, not a new problem. Full test
suite: `python ff.py --selftest`, 94 + 31 passing.
