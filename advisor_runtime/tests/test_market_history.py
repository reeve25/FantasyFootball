"""Offline checks for permanent SportsGameOdds fetch observations."""

from __future__ import annotations

import copy
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


RUNTIME_DIR = Path(__file__).resolve().parents[1]
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import market_sources  # noqa: E402


FETCH_TIME = "2026-09-11T20:00:00.123456+00:00"
FEED_TIME = "1999-01-01T00:00:00Z"


def prop(player_id="p1", stat="receiving_yards", books=None, **changes):
    value = {
        "periodID": "game",
        "betTypeID": "ou",
        "sideID": "over",
        "playerID": player_id,
        "statID": stat,
        "fairOverUnder": 50.5,
        "lastUpdatedAt": FEED_TIME,
        "byBookmaker": books if books is not None else {
            "book-a": {"overUnder": 50.5, "lastUpdatedAt": FEED_TIME},
            "book-b": {"overUnder": 51.5, "lastUpdatedAt": FEED_TIME},
        },
    }
    value.update(changes)
    return value


def payload(odds=None):
    return {"data": [{
        "eventID": "event-1",
        "lastUpdatedAt": FEED_TIME,
        "status": {"startsAt": FEED_TIME},
        "players": {
            "p1": {"name": "Focus Player"},
            "p2": {"name": "Other Player"},
        },
        "odds": odds if odds is not None else {"prop": prop()},
    }]}


class MarketHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.history = Path(directory.name) / "history"
        self.cache = Path(directory.name) / "cache"
        for name, value in (
            ("MARKET_HISTORY_DIR", self.history),
            ("CACHE_DIR", self.cache),
        ):
            patch = mock.patch.object(market_sources, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        secrets = mock.patch.object(market_sources, "load_secrets", return_value={
            "SPORTSGAMEODDS_API_KEY": "offline-fixture",
        })
        secrets.start()
        self.addCleanup(secrets.stop)
        network = mock.patch.object(market_sources.requests, "get", side_effect=AssertionError(
            "history tests must not use the network"
        ))
        network.start()
        self.addCleanup(network.stop)

    def rows(self, path):
        return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]

    def test_same_timestamp_fetches_preserve_separate_immutable_observations(self):
        first = market_sources._write_sports_game_odds_snapshot(payload(), FETCH_TIME)
        first_path = Path(first["path"])
        original_bytes = first_path.read_bytes()
        changed = payload()
        changed["data"][0]["odds"]["prop"]["byBookmaker"]["book-a"]["overUnder"] = 47.5
        second = market_sources._write_sports_game_odds_snapshot(changed, FETCH_TIME)

        self.assertEqual(first["status"], "written")
        self.assertEqual(second["status"], "written")
        self.assertEqual(first["rows"], 2)
        self.assertEqual(second["rows"], 2)
        self.assertTrue(first_path.is_absolute())
        self.assertNotEqual(first["path"], second["path"])
        self.assertEqual(len(list(self.history.glob("*.jsonl"))), 2)
        self.assertEqual(first_path.read_bytes(), original_bytes)
        first_lines = {row["book"]: row["line"] for row in self.rows(first["path"])}
        second_lines = {row["book"]: row["line"] for row in self.rows(second["path"])}
        self.assertEqual(first_lines, {"book-a": 50.5, "book-b": 51.5})
        self.assertEqual(second_lines, {"book-a": 47.5, "book-b": 51.5})

    def test_raw_history_keeps_all_players_books_markets_and_outliers(self):
        books = {f"book-{index}": {"overUnder": 50.5 + index} for index in range(6)}
        books["outlier"] = {"overUnder": 999.5}
        odds = {"focus": prop(books=books), "duplicate": prop(books=copy.deepcopy(books))}
        for stat in market_sources.SPORTS_GAME_ODDS_STATS:
            odds[stat] = prop(player_id="p2", stat=stat, books={"other-book": {"overUnder": "4.5"}})
        source = payload(odds)
        other_event = copy.deepcopy(source["data"][0])
        other_event["eventID"] = "event-2"
        other_event["odds"] = {"focus": prop(books={"book-0": {"overUnder": 70.5}})}
        source["data"].append(other_event)
        response = mock.Mock()
        response.json.return_value = source
        with mock.patch.object(market_sources.requests, "get", return_value=response):
            result = market_sources.sports_game_odds([{"name": "Focus Player"}])

        rows = self.rows(result["line_snapshot"]["path"])
        line_rows = [row for row in rows if row["row_type"] == "line"]
        projection_rows = [row for row in rows if row["row_type"] == "projection"]
        self.assertEqual(len(line_rows), 8 + len(market_sources.SPORTS_GAME_ODDS_STATS))
        self.assertEqual(len(projection_rows), 1)
        self.assertEqual(len(rows), len(line_rows) + len(projection_rows))
        keys = {(row["event_id"], row["player_id"], row["book"], row["market"], row["side"]) for row in line_rows}
        self.assertEqual(len(keys), len(line_rows))
        self.assertEqual(
            {row["book"] for row in line_rows if row["player_id"] == "p1" and row["event_id"] == "event-1"},
            set(books),
        )
        self.assertIn(999.5, [row["line"] for row in line_rows])
        self.assertEqual(
            {row["market"] for row in line_rows if row["player_id"] == "p2"},
            set(market_sources.SPORTS_GAME_ODDS_STATS.values()),
        )
        self.assertEqual({row["side"] for row in line_rows}, {"over"})
        self.assertEqual(projection_rows[0]["player_name"], "Focus Player")
        self.assertEqual(projection_rows[0]["points"], None)
        self.assertEqual(projection_rows[0]["stats"], {})
        self.assertNotIn("other player", result["players"])
        self.assertLessEqual(len(result["players"]["focus player"]["rec_yd"]["books"]), 5)

    def test_snapshot_filters_unavailable_invalid_and_unsupported_lines_and_ignores_feed_times(self):
        books = {
            "posted": {"overUnder": "5.5", "available": True, "lastUpdatedAt": FEED_TIME},
            "zero": {"overUnder": 0, "lastUpdatedAt": FEED_TIME},
            "closed": {"overUnder": 4.5, "available": False},
            "missing": {},
            "null": {"overUnder": None},
            "text": {"overUnder": "not-a-line"},
            "nan": {"overUnder": float("nan")},
            "infinity": {"overUnder": float("inf")},
            "negative-infinity": {"overUnder": float("-inf")},
        }
        source = payload({
            "good": prop(books=books),
            "under": prop(sideID="under"),
            "quarter": prop(periodID="1q"),
            "moneyline": prop(betTypeID="ml"),
            "unsupported": prop(statID="unknown_stat"),
            "no-player": prop(playerID=None),
            "no-side": prop(sideID=""),
        })
        result = market_sources._write_sports_game_odds_snapshot(source, FETCH_TIME)
        rows = self.rows(result["path"])
        self.assertEqual(result["rows"], 4)
        self.assertEqual(result["line_rows"], 4)
        self.assertEqual(result["projection_rows"], 0)
        self.assertEqual(
            {row["book"]: row["line"] for row in rows},
            {"posted": 5.5, "zero": 0.0, "book-a": 50.5, "book-b": 51.5},
        )
        self.assertEqual(
            {row["book"]: row["side"] for row in rows},
            {"posted": "over", "zero": "over", "book-a": "under", "book-b": "under"},
        )
        self.assertEqual(result["fetched_at_utc"], FETCH_TIME)
        for row in rows:
            self.assertEqual(
                set(row),
                {"row_type", "source", "event_id", "player_id", "book", "market", "side", "line", "price", "fetched_at_utc"},
            )
            self.assertEqual(row["row_type"], "line")
            self.assertEqual(row["source"], "SportsGameOdds")
            self.assertEqual(row["fetched_at_utc"], FETCH_TIME)
            self.assertEqual(row["player_id"], "p1")
            self.assertIsNone(row["price"])
        self.assertNotIn(FEED_TIME, Path(result["path"]).read_text(encoding="utf-8"))

    def test_snapshot_persists_both_sides_with_price_and_full_projection_row(self):
        odds = {
            "over": prop(
                books={
                    "book-a": {"overUnder": 50.5, "odds": -110, "lastUpdatedAt": FEED_TIME},
                }
            ),
            "under": prop(
                sideID="under",
                books={
                    "book-a": {"overUnder": 50.5, "odds": -105, "lastUpdatedAt": FEED_TIME},
                },
            ),
        }
        source = payload(odds)
        players = [
            {
                "pid": "9001",
                "name": "Focus Player",
                "current_week": 3,
                "live_week_projection": 14.25,
                "live_projection_stats": {"rec_yd": 61.2, "rec": 4.8},
            }
        ]
        result = market_sources._write_sports_game_odds_snapshot(source, FETCH_TIME, players)
        rows = self.rows(result["path"])
        line_rows = {row["side"]: row for row in rows if row["row_type"] == "line"}
        projection_rows = [row for row in rows if row["row_type"] == "projection"]

        self.assertEqual(result["rows"], 3)
        self.assertEqual(result["line_rows"], 2)
        self.assertEqual(result["projection_rows"], 1)
        self.assertEqual(line_rows["over"]["line"], 50.5)
        self.assertEqual(line_rows["over"]["price"], -110)
        self.assertEqual(line_rows["under"]["line"], 50.5)
        self.assertEqual(line_rows["under"]["price"], -105)

        self.assertEqual(len(projection_rows), 1)
        projection = projection_rows[0]
        self.assertEqual(projection["player_id"], "9001")
        self.assertEqual(projection["player_name"], "Focus Player")
        self.assertEqual(projection["week"], 3)
        self.assertEqual(projection["points"], 14.25)
        self.assertEqual(projection["stats"], {"rec_yd": 61.2, "rec": 4.8})
        self.assertEqual(projection["fetched_at_utc"], FETCH_TIME)

    def test_projection_universe_overrides_focused_players_for_snapshot_only(self):
        response = mock.Mock()
        response.json.return_value = payload()
        universe = [
            {"pid": "1", "name": "Focus Player", "live_week_projection": 10.0, "live_projection_stats": {}},
            {"pid": "2", "name": "Bench Guy", "live_week_projection": 3.0, "live_projection_stats": {}},
            {"pid": "3", "name": "Other Player", "live_week_projection": 7.0, "live_projection_stats": {}},
        ]
        with mock.patch.object(market_sources.requests, "get", return_value=response):
            result = market_sources.sports_game_odds(
                [{"name": "Focus Player"}], projection_universe=universe
            )

        rows = self.rows(result["line_snapshot"]["path"])
        projection_rows = [row for row in rows if row["row_type"] == "projection"]
        self.assertEqual({row["player_name"] for row in projection_rows}, {"Focus Player", "Bench Guy", "Other Player"})
        self.assertEqual(len(projection_rows), 3)
        # The provider-facing selection is unaffected: only the requested player comes back.
        self.assertEqual(set(result["players"]), {"focus player"})

    def test_every_fresh_fetch_records_engine_time_and_force_refresh_bypasses_cache(self):
        first_payload = payload()
        second_payload = copy.deepcopy(first_payload)
        second_payload["data"][0]["odds"]["prop"]["byBookmaker"]["book-a"]["overUnder"] = 49.5
        responses = []
        for source in (first_payload, second_payload):
            response = mock.Mock()
            response.json.return_value = source
            responses.append(response)
        before = dt.datetime.now(dt.timezone.utc)
        with mock.patch.object(market_sources.requests, "get", side_effect=responses) as get:
            first = market_sources.sports_game_odds([{"name": "Focus Player"}])
            first_path = Path(first["line_snapshot"]["path"])
            original_bytes = first_path.read_bytes()
            second = market_sources.sports_game_odds([{"name": "Focus Player"}], force_refresh=True)
            cached = market_sources.sports_game_odds([{"name": "Focus Player"}])
        after = dt.datetime.now(dt.timezone.utc)

        self.assertEqual(get.call_count, 2)
        self.assertEqual(first["cache"], "fresh")
        self.assertEqual(second["cache"], "fresh")
        self.assertEqual(cached["cache"], "local_10m")
        self.assertEqual(cached["line_snapshot"], {"status": "cache_hit_no_snapshot"})
        self.assertEqual(cached["players"], second["players"])
        self.assertEqual(len(list(self.history.glob("*.jsonl"))), 2)
        self.assertEqual(first_path.read_bytes(), original_bytes)
        for result, expected in ((first, 50.5), (second, 49.5)):
            rows = self.rows(result["line_snapshot"]["path"])
            line_rows = [row for row in rows if row["row_type"] == "line"]
            projection_rows = [row for row in rows if row["row_type"] == "projection"]
            self.assertEqual({row["book"]: row["line"] for row in line_rows}, {"book-a": expected, "book-b": 51.5})
            self.assertEqual(len(projection_rows), 1)
            self.assertEqual(projection_rows[0]["player_name"], "Focus Player")
            stamp = result["line_snapshot"]["fetched_at_utc"]
            self.assertEqual({row["fetched_at_utc"] for row in rows}, {stamp})
            timestamp = dt.datetime.fromisoformat(stamp)
            self.assertEqual(timestamp.utcoffset(), dt.timedelta(0))
            self.assertLessEqual(before, timestamp)
            self.assertLessEqual(timestamp, after)

    def test_failed_http_or_json_fetch_does_not_create_history(self):
        http_failure = mock.Mock()
        http_failure.raise_for_status.side_effect = market_sources.requests.HTTPError("fixture")
        json_failure = mock.Mock()
        json_failure.json.side_effect = ValueError("fixture")
        for response in (http_failure, json_failure):
            with self.subTest(response=response), mock.patch.object(market_sources.requests, "get", return_value=response):
                result = market_sources.sports_game_odds([{"name": "Focus Player"}])
            self.assertEqual(result["status"], "provider_error")
            self.assertEqual(list(self.history.glob("*.jsonl")), [])
            self.assertFalse((self.cache / "sportsgameodds_nfl_props.json").exists())


if __name__ == "__main__":
    unittest.main()
