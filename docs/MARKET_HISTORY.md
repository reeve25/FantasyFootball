# Sportsbook line history

Every successful fresh SportsGameOdds HTTP fetch creates a new JSONL file in
`advisor_runtime/data/market_history/sports_game_odds/`. Files use exclusive
creation with a UTC timestamp and unique suffix. Existing snapshots are never
overwritten or pruned. Keep this directory when clearing disposable caches.

Each file mixes two row shapes, distinguished by `row_type`.

`row_type: "line"` rows contain `source`, `event_id`, `player_id`, `book`,
`market`, `side`, `line`, `price`, and `fetched_at_utc`. Player IDs are
**SportsGameOdds IDs**, not Sleeper IDs. Market names use the engine's stat
keys, such as `rec_yd` and `pass_yd`; these are full-game over/under lines.
`side` is `over` or `under`, exactly as the feed labeled that entry — both
sides are stored as separate rows; selecting one side is a read-time job, not
a write-time filter. `price` is the odds attached to that book/side (e.g.
`-110`), so a line move can be told apart from a juice move. Event IDs
distinguish separate games. Within each fetch there is one row per
event/player/book/market/side.

`row_type: "projection"` rows contain `source` (`"engine_projection"`),
`player_id` (the engine's **Sleeper ID**, a different ID space from the line
rows' SportsGameOdds IDs), `player_name`, `week`, `points` (the engine's
live week fantasy-point projection), `stats` (the per-market projection
components, keyed the same as `market` on line rows, e.g. `rec_yd`), and
`fetched_at_utc`, at the same timestamp as that fetch's line rows.

From `ff.py packet`/`trade` (the worker in `ff.py`, the actual code path
behind the public entry point) the candidate **projection universe** passed
in is `current["players"]` already held in memory: every player Sleeper
knows about, currently ~12,200, not just the packet's focused players — a
question about one player still leaves a baseline for every other player to
compare against later. `market_sources.sports_game_odds` and
`focused_market_packet` take this as an explicit `projection_universe`
argument (defaulting to the focused `players` list when omitted, e.g. from a
direct unit-level call) rather than hard-coding the full-board lookup, so the
provider layer stays testable without an engine snapshot.

The writer then gates that universe down to players this fetch actually says
something about: those with a projection value, and those with at least one
posted book line in this same fetch (bridged to the provider's own name via
`resolve_provider_name`, below). Everyone else is dropped rather than written
as an all-null row. Ungated, one fetch wrote a row for all ~12,200 players in
the Sleeper database, 96% of them `points: null` with empty `stats`, at
~4.3MB; gated, the same fetch was ~500 rows at well under 2MB. A player with a
posted line and no engine projection is kept deliberately, with `points: null`
and `stats: {}` — that gap is a signal (a rookie or free agent the engine
hasn't projected but a book has posted a prop for), not noise to prune.
Projection rows live in the same file as line rows (not a parallel store) so
a single fetch's evidence — what the books posted and what the engine
projected — stays in one place at one timestamp, with no separate file to
keep in sync.

**Bridging the two id namespaces.** Line rows and projection rows never share
an id space (SportsGameOdds playerID vs. Sleeper pid — see docs/TRAPS.md), so
the gate above, and `sports_game_odds`'s own read-time player selection, join
on name instead: `normalize_name()` folds case, whitespace, and drops
apostrophes/periods outright rather than turning them into a word break (so
"De'Von"/"Devon" and "O.J."/"OJ" already fold together), then
`resolve_provider_name()` looks the result up in
`advisor_runtime/name_aliases.json` for the mismatches punctuation can't fix:
nicknames and legal-vs-common names ("Cam Ward" / "Cameron Ward"), dropped
generational suffixes ("Travis Etienne" / "Travis Etienne Jr."), and provider
misspellings. A name that still doesn't resolve — or a provider entry with no
name at all, which happens — surfaces as `unresolved_no_match` in
`focused_market_packet`'s `resolution_status` rather than disappearing.

The snapshot includes every available numeric book line in the fetched payload
for the engine's supported markets, before focused-player selection, outlier
filtering, or the five-book display limit. It does not add extra provider calls
or broaden the existing query. Fair/consensus values are not book-line rows.
This is a raw observation log, not a delta table: comparing rows across fetches
is a read-time job for later tooling.

`fetched_at_utc` is recorded by the engine immediately after a successful HTTP
response is decoded. No feed timestamp is read or stored by the history writer.
This is the time the engine obtained the response, not a claim about when the
provider or book updated the line. Cache hits create no new snapshot.

To fetch now through the public entry point, bypassing the SportsGameOdds cache:

```powershell
python ff.py packet "Show sportsbook lines for Drake London" --market-refresh
```

The packet's `market_evidence.line_snapshot` reports the written path, total
row count (`rows`, split into `line_rows` and `projection_rows`), and fetch
timestamp, or `cache_hit_no_snapshot`. History-write failures surface as
command errors rather than silently discarding the observation. This storage
adds no dependencies and does not change market or projection calculations.

## Per-player resolution status

Every focused player gets a `resolution_status` block in
`market_evidence.players.<name>`, never silently omitted and never
zero-substituted for missing evidence:

```json
"resolution_status": {
  "resolved": true,
  "has_projection": false,
  "lost_book_coverage_since_previous_snapshot": null,
  "flags": ["resolved_no_projection"]
}
```

- `resolved` — the provider named this player under a supported market this
  fetch (via `resolve_provider_name`), independent of whether any book posted
  a usable line. False means `unresolved_no_match`: a real name mismatch, or
  a provider entry with no name at all (observed for one player — an empty
  `players` entry in the raw payload, nothing to alias).
- `has_projection` — the engine's `live_week_projection` is not null. Only
  meaningful when `resolved` is true; a player who fails to resolve is
  reported as unresolved, not conflated with "no projection."
- `lost_book_coverage_since_previous_snapshot` — `true`/`false` when this was
  a fresh fetch with an earlier snapshot to compare against and the player
  was resolved; `null` ("not checked") on a cache hit or the very first
  snapshot. `true` means the provider's own player registry ID (found via
  `provider_identity` on the `sports_game_odds` result) had a posted line in
  the immediately prior snapshot file and has none now — the loudest signal
  this store can produce, since it means the market moved, not that nothing
  happened. It surfaces twice: in this per-player block, and prepended to the
  packet's top-level `warnings` as `focused_market_packet`'s
  `coverage_warnings`, ahead of every other market warning.
- `flags` — the subset of `unresolved_no_match`, `resolved_no_projection`,
  `lost_book_coverage` that applies; empty when none do.
