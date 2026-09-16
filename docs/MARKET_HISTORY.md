# Sportsbook line history

Every successful fresh SportsGameOdds HTTP fetch creates a new JSONL file in
`advisor_runtime/data/market_history/sports_game_odds/`. Files use exclusive
creation with a UTC timestamp and unique suffix. Existing snapshots are never
overwritten or pruned. Keep this directory when clearing disposable caches.

Each row contains `source`, `event_id`, `player_id`, `book`, `market`, `line`,
and `fetched_at_utc`. Player IDs are **SportsGameOdds IDs**, not Sleeper IDs.
Market names use the engine's stat keys, such as `rec_yd` and `pass_yd`; these
are full-game over/under lines. Event IDs distinguish separate games. Within
each fetch there is one row per event/player/book/market.

The snapshot includes every available numeric book line in the fetched payload
for the engine's supported markets, before focused-player selection, outlier
filtering, or the five-book display limit. It does not add extra provider calls
or broaden the existing query. Fair/consensus values are not book-line rows.

`fetched_at_utc` is recorded by the engine immediately after a successful HTTP
response is decoded. No feed timestamp is read or stored by the history writer.
This is the time the engine obtained the response, not a claim about when the
provider or book updated the line. Cache hits create no new snapshot.

To fetch now through the public entry point, bypassing the SportsGameOdds cache:

```powershell
python ff.py packet "Show sportsbook lines for Drake London" --market-refresh
```

The packet's `market_evidence.line_snapshot` reports the written path, row count,
and fetch timestamp, or `cache_hit_no_snapshot`. History-write failures surface
as command errors rather than silently discarding the observation. This storage
adds no dependencies and does not change market or projection calculations.
