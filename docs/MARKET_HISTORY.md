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
`fetched_at_utc`. One projection row is written per player in the fetch's
**projection universe**, at the same timestamp as its line rows, whether or
not that player had any posted line — a question about one player still
leaves a projection baseline for every other player to compare against later.
From `ff.py packet`/`trade` (the worker in `ff.py`, the actual code path
behind the public entry point) the projection universe is `current["players"]`
already held in memory: every player Sleeper knows about, currently ~12,200,
not just the packet's focused players. Most of those have no current-week
projection (only players the engine actively projects do — ~455 of ~12,200 in
one observed fetch); those rows still get written, with `points: null` and
`stats: {}`, rather than being skipped, so "no projection yet" stays
distinguishable from "never checked." This makes each snapshot file a few MB
(~4.3MB observed for ~12,200 projection rows plus ~7,300 line rows) and,
since history is append-only and never pruned, that accumulates on disk one
file per fetch — prune manually if that becomes a problem; the writer itself
does not. `market_sources.sports_game_odds` and `focused_market_packet` take
the universe as an explicit `projection_universe` argument (defaulting to the
focused `players` list when omitted, e.g. from a direct unit-level call)
rather than hard-coding the full-board lookup, so the provider layer stays
testable without an engine snapshot. A missing projection is recorded as
`points: null` and `stats: {}` rather than being omitted — join on
`player_name` (or match `stats.<market>` against a line row's `market`) to
compare book movement against projection movement, since the two row types
don't share an ID space. Projection rows live in the same file as line rows
(not a parallel store) so a single fetch's evidence — what the books posted
and what the engine projected — stays in one place at one timestamp, with no
separate file to keep in sync.

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
