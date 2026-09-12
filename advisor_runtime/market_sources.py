"""Focused market reads for the chat advisor.

Only named players are returned to the model.  Raw league-wide bookmaker
payloads stay out of the decision packet to control both noise and tokens.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import statistics
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests


HEADERS = {"User-Agent": "Reeve-Fantasy-Advisor/2.0", "Accept": "application/json"}
CACHE_DIR = Path(__file__).resolve().parent / "data" / "provider_cache"
MARKET_HISTORY_DIR = Path(__file__).resolve().parent / "data" / "market_history" / "sports_game_odds"
SPORTS_GAME_ODDS_STATS = {
    "passing_yards": "pass_yd",
    "passing_touchdowns": "pass_td",
    "passing_interceptions": "pass_int",
    "passing_attempts": "pass_att",
    "rushing_yards": "rush_yd",
    "rushing_attempts": "rush_att",
    "receiving_yards": "rec_yd",
    "receiving_receptions": "rec",
    "rushing+receiving_yards": "rush_rec_yd",
    "touchdowns": "td",
    "kicking_totalPoints": "kick_pts",
}
ODDS_API_STATS = {
    "player_pass_yds": "pass_yd",
    "player_pass_tds": "pass_td",
    "player_pass_interceptions": "pass_int",
    "player_pass_attempts": "pass_att",
    "player_rush_yds": "rush_yd",
    "player_rush_attempts": "rush_att",
    "player_reception_yds": "rec_yd",
    "player_receptions": "rec",
    "player_rush_reception_yds": "rush_rec_yd",
    "player_anytime_td": "anytime_td",
    "player_kicking_points": "kick_pts",
}
NFL_TEAMS = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "JAC": "Jacksonville Jaguars", "KC": "Kansas City Chiefs", "LAC": "Los Angeles Chargers",
    "LAR": "Los Angeles Rams", "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints",
    "NYG": "New York Giants", "NYJ": "New York Jets", "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers",
    "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}


# Dropped outright rather than turned into a word break: an apostrophe or
# period inside a name is punctuation, not a word boundary. "De'Von" and
# "O.J." must fold to "devon" and "oj" to match a provider spelling that
# simply omits them ("Devon", "OJ") -- turning them into spaces instead
# leaves an extra token ("de von") that never matches. Curly-quote variants
# never reach here: NFKD + ascii-encode already drops anything non-ASCII.
_NAME_JOIN_STRIP = str.maketrans("", "", "'`.")


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = text.translate(_NAME_JOIN_STRIP)
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text.lower()).split())


NAME_ALIASES_PATH = Path(__file__).resolve().parent / "name_aliases.json"


def load_name_aliases() -> dict[str, str]:
    """Map a provider name spelling to the engine's canonical spelling.

    Covers what punctuation normalization can't: nicknames vs legal names
    ("Cam Ward" / "Cameron Ward"), dropped generational suffixes ("Travis
    Etienne" / "Travis Etienne Jr."), and provider misspellings. Both sides
    are stored raw in the data file and normalized here, so the file reads
    as plain names, not regex. Keyed and valued by ``normalize_name`` output;
    callers resolve a raw name by normalizing it and looking it up here,
    falling back to the normalized form itself when there's no entry.
    """
    try:
        raw = json.loads(NAME_ALIASES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    aliases: dict[str, str] = {}
    for entry in raw.get("aliases") or []:
        provider_key = normalize_name(str(entry.get("provider_name") or ""))
        engine_key = normalize_name(str(entry.get("engine_name") or ""))
        if provider_key and engine_key:
            aliases[provider_key] = engine_key
    return aliases


def resolve_provider_name(raw_name: str, aliases: dict[str, str]) -> str:
    key = normalize_name(raw_name)
    return aliases.get(key, key)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and result not in (float("inf"), float("-inf")) else None


def _median(values: list[float]) -> float | None:
    return round(float(statistics.median(values)), 3) if values else None


def _latest(values: list[Any]) -> str | None:
    clean = sorted(str(value) for value in values if value)
    return clean[-1] if clean else None


def _local_secret_path() -> Path:
    configured = os.getenv("REEVE_FANTASY_SECRETS_FILE", "").strip()
    if configured:
        return Path(configured)
    # The Microsoft Store Python sandbox cannot reliably see LOCALAPPDATA.
    # Keep secrets outside the synced project in the user's private Codex dir.
    profile = Path(os.getenv("USERPROFILE") or Path.home())
    return profile / ".codex" / "secrets" / "reeve-fantasy-advisor.env"


def load_secrets() -> dict[str, str]:
    """Load keys without ever returning them in a status or decision packet."""
    values: dict[str, str] = {}
    path = _local_secret_path()
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    for key in (
        "SPORTSGAMEODDS_API_KEY",
        "THE_ODDS_API_KEY",
        "BETTINGPROS_API_KEY",
        "FANTASYPROS_API_KEY",
    ):
        if os.getenv(key):
            values[key] = os.environ[key].strip()
    return values


def _cache_read(name: str, ttl_seconds: int) -> Any | None:
    path = CACHE_DIR / name
    if (
        not path.exists()
        or time.time() - path.stat().st_mtime > ttl_seconds
    ):
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _cache_write(name: str, payload: Any) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / name
    path.write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8"
    )


def _write_sports_game_odds_snapshot(
    payload: Any,
    fetched_at_utc: str,
    players: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Preserve raw posted lines and matching projections before selection.

    The caller supplies the engine's HTTP fetch time, never a feed timestamp.
    Each fetch creates a new file exclusively; history is never replaced/pruned.
    Both sides of a posted line are kept as separate rows (an explicit ``side``
    field), each carrying its own price, so a later reader can tell a line
    move from a juice move. Side/book selection for the decision packet stays
    a read-time job in ``sports_game_odds`` below; this only stops discarding
    the under side and the price at write time. ``row_type`` distinguishes the
    two row shapes sharing this file: "line" (book-posted) and "projection"
    (the engine's own value for that player at the same fetch).

    Projection rows are gated to players this fetch actually says something
    about: those with a projection value, and those with at least one posted
    book line in this same fetch. A player with a posted line and no
    projection is kept deliberately -- that gap is the signal, not noise.
    Everyone else in the engine's player pool is dropped. Ungated, a fetch
    wrote a row for all ~12,200 players in the Sleeper database and 96% of
    them carried ``points: null`` with empty ``stats``.

    The two row shapes do not share an id namespace: line rows carry the
    provider's playerID ("CAMERON_WARD_1_NFL"), projection rows the engine's
    pid ("1"). They are bridged on ``resolve_provider_name`` (normalize_name
    plus the ``name_aliases.json`` lookup) of the provider's own event players
    map -- the same join ``sports_game_odds`` uses at read time, so the gate
    keeps exactly the players a reader could later match. See docs/TRAPS.md
    for why the id namespaces can never simply be unified.
    """
    aliases = load_name_aliases()
    rows: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    provider_names: dict[str, str] = {}
    for event in payload.get("data") or []:
        event_id = str(event.get("eventID") or "")
        event_players = event.get("players") or {}
        # Preserve provider observations, not a week inferred from fetch time.
        # Nested additive metadata keeps the existing line/projection contract.
        event_metadata = {
            "sport_id": event.get("sportID"),
            "league_id": event.get("leagueID"),
            "season_week": (event.get("info") or {}).get("seasonWeek"),
            "status": dict(event.get("status") or {}),
            "teams": {
                side: {
                    "team_id": ((event.get("teams") or {}).get(side) or {}).get("teamID"),
                    "names": dict((((event.get("teams") or {}).get(side) or {}).get("names") or {})),
                }
                for side in ("home", "away")
            },
        }
        for odd in (event.get("odds") or {}).values():
            market = SPORTS_GAME_ODDS_STATS.get(str(odd.get("statID") or ""))
            side = str(odd.get("sideID") or "")
            if (
                odd.get("periodID") != "game"
                or odd.get("betTypeID") != "ou"
                or not side
                or not odd.get("playerID")
                or not market
            ):
                continue
            player_id = str(odd["playerID"])
            provider = event_players.get(odd.get("playerID")) or {}
            raw_player_name = str(provider.get("name") or " ".join(
                part for part in (provider.get("firstName"), provider.get("lastName")) if part
            ))
            provider_names.setdefault(
                player_id,
                resolve_provider_name(
                    str(
                        provider.get("name")
                        or " ".join(
                            part
                            for part in (provider.get("firstName"), provider.get("lastName"))
                            if part
                        )
                    ),
                    aliases,
                ),
            )
            for book, raw in (odd.get("byBookmaker") or {}).items():
                line = _number(raw.get("overUnder"))
                if raw.get("available") is False or line is None:
                    continue
                key = (event_id, player_id, str(book), market, side)
                rows[key] = {
                    "row_type": "line",
                    "source": "SportsGameOdds",
                    "event_id": event_id,
                    "player_id": player_id,
                    "book": str(book),
                    "market": market,
                    "side": side,
                    "line": line,
                    "price": _number(raw.get("odds")),
                    "fetched_at_utc": fetched_at_utc,
                    "player_name": raw_player_name or None,
                    "event_metadata": event_metadata,
                }
    lined_names = {provider_names.get(row["player_id"], "") for row in rows.values()}
    lined_names.discard("")
    projection_rows = []
    for player in players or []:
        points = _number(player.get("live_week_projection"))
        if points is None and normalize_name(str(player.get("name") or "")) not in lined_names:
            continue
        stats = player.get("live_projection_stats")
        projection_rows.append(
            {
                "row_type": "projection",
                "source": "engine_projection",
                "player_id": str(player.get("pid") or ""),
                "player_name": str(player.get("name") or ""),
                "week": player.get("current_week"),
                "points": points,
                "stats": dict(stats) if isinstance(stats, dict) else {},
                "fetched_at_utc": fetched_at_utc,
            }
        )
    MARKET_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = fetched_at_utc.replace(":", "").replace("+0000", "Z")
    path = MARKET_HISTORY_DIR / f"{stamp}-{uuid.uuid4().hex}.jsonl"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        for row in rows.values():
            handle.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
        for row in projection_rows:
            handle.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "status": "written",
        "path": str(path),
        "rows": len(rows) + len(projection_rows),
        "line_rows": len(rows),
        "projection_rows": len(projection_rows),
        "fetched_at_utc": fetched_at_utc,
    }


def source_configuration() -> dict[str, bool]:
    secrets = load_secrets()
    return {
        "sports_game_odds": bool(secrets.get("SPORTSGAMEODDS_API_KEY")),
        "the_odds_api": bool(secrets.get("THE_ODDS_API_KEY")),
        "bettingpros": bool(secrets.get("BETTINGPROS_API_KEY")),
        "fantasypros": bool(secrets.get("FANTASYPROS_API_KEY")),
        "pickem_browser_available": True,
        "underdog_automated": False,
    }


def _book_summary(books: list[dict[str, Any]], source: str) -> dict[str, Any]:
    by_book: dict[str, dict[str, Any]] = {}
    for row in books:
        book = str(row.get("book") or "unknown")
        previous = by_book.get(book)
        if previous is None or str(row.get("updated_at") or "") > str(
            previous.get("updated_at") or ""
        ):
            by_book[book] = row
    books = list(by_book.values())
    raw_book_count = len(books)
    raw_lines = [
        float(row["line"])
        for row in books
        if _number(row.get("line")) is not None
    ]
    excluded = []
    if len(raw_lines) >= 4:
        center = float(statistics.median(raw_lines))
        deviations = [abs(value - center) for value in raw_lines]
        mad = float(statistics.median(deviations))
        tolerance = max(2.0, 4.0 * mad, abs(center) * 0.12)
        kept = []
        for row in books:
            line = _number(row.get("line"))
            if line is not None and abs(line - center) > tolerance:
                excluded.append(
                    {"book": row.get("book"), "line": line}
                )
            else:
                kept.append(row)
        if len(kept) >= 3:
            books = kept
    lines = [float(row["line"]) for row in books if _number(row.get("line")) is not None]
    opens = [float(row["open_line"]) for row in books if _number(row.get("open_line")) is not None]
    current = _median(lines)
    opened = _median(opens)
    return {
        "source": source,
        "consensus_line": current,
        "book_consensus_line": current,
        "projection_line": current,
        "projection_line_method": "robust_book_median",
        "open_line": opened,
        "line_move": round(current - opened, 3) if current is not None and opened is not None else None,
        "range": [min(lines), max(lines)] if lines else None,
        "book_count": len(books),
        "raw_book_count": raw_book_count,
        "excluded_outliers": excluded,
        "updated_at": _latest([row.get("updated_at") for row in books]),
        "books": books[:5],
    }


def sports_game_odds(
    players: list[dict[str, Any]],
    *,
    force_refresh: bool = False,
    projection_universe: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    secrets = load_secrets()
    api_key = secrets.get("SPORTSGAMEODDS_API_KEY")
    if not api_key:
        return {"status": "missing_key", "source": "SportsGameOdds", "players": {}}
    aliases = load_name_aliases()
    wanted = {normalize_name(str(player.get("name") or "")) for player in players}
    wanted.discard("")
    odd_ids = ",".join(
        f"{stat}-PLAYER_ID-game-ou-over" for stat in SPORTS_GAME_ODDS_STATS
    )
    params = urlencode(
        {
            "leagueID": "NFL",
            "oddsAvailable": "true",
            "oddIDs": odd_ids,
            "includeOpposingOdds": "true",
            "includeOpenCloseOdds": "true",
            "limit": "24",
        }
    )
    payload = None if force_refresh else _cache_read("sportsgameodds_nfl_props.json", 10 * 60)
    cache_label = "local_10m" if payload is not None else "fresh"
    line_snapshot = {"status": "cache_hit_no_snapshot"}
    if payload is None:
        try:
            response = requests.get(
                f"https://api.sportsgameodds.com/v2/events?{params}",
                headers={**HEADERS, "x-api-key": api_key},
                timeout=45,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            return {
                "status": "provider_error",
                "source": "SportsGameOdds",
                "error": type(exc).__name__,
                "players": {},
            }
        fetched_at_utc = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")
        line_snapshot = _write_sports_game_odds_snapshot(
            payload,
            fetched_at_utc,
            players if projection_universe is None else projection_universe,
        )
        _cache_write("sportsgameodds_nfl_props.json", payload)

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    meta: dict[tuple[str, str], dict[str, Any]] = {}
    # Every player the provider names under a supported market this fetch,
    # over side or not, valid book line or not -- independent of ``wanted``
    # and of whether a book actually posted a usable line. This is the
    # "did the provider say anything at all about this player" signal that
    # focused_market_packet needs to tell "no match" apart from "matched,
    # game already locked" apart from "never had a market source problem."
    provider_identity: dict[str, str] = {}
    for event in payload.get("data") or []:
        event_players = event.get("players") or {}
        matchup = " @ ".join(
            str(value)
            for value in (
                (((event.get("teams") or {}).get("away") or {}).get("names") or {}).get("long"),
                (((event.get("teams") or {}).get("home") or {}).get("names") or {}).get("long"),
            )
            if value
        )
        for odd in (event.get("odds") or {}).values():
            if (
                odd.get("periodID") != "game"
                or odd.get("betTypeID") != "ou"
                or odd.get("sideID") != "over"
                or not odd.get("playerID")
            ):
                continue
            stat = SPORTS_GAME_ODDS_STATS.get(str(odd.get("statID") or ""))
            player = event_players.get(odd.get("playerID")) or {}
            player_name = str(
                player.get("name")
                or " ".join(part for part in (player.get("firstName"), player.get("lastName")) if part)
            )
            key = resolve_provider_name(player_name, aliases)
            if stat:
                provider_identity.setdefault(key, str(odd.get("playerID")))
            if not stat or key not in wanted:
                continue
            books = []
            for book, raw in (odd.get("byBookmaker") or {}).items():
                if raw.get("available") is False:
                    continue
                line = _number(raw.get("overUnder"))
                if line is None:
                    continue
                books.append(
                    {
                        "book": str(book),
                        "line": line,
                        "price": _number(raw.get("odds")),
                        "open_line": _number(raw.get("openOverUnder")),
                        "updated_at": raw.get("lastUpdatedAt"),
                    }
                )
            if not books:
                continue
            grouped.setdefault(key, {}).setdefault(stat, []).extend(books)
            meta[(key, stat)] = {
                "fair_line": _number(odd.get("fairOverUnder")),
                "market_line": _number(odd.get("bookOverUnder")),
                "fair_price": _number(odd.get("fairOdds")),
                "market_price": _number(odd.get("bookOdds")),
                "matchup": matchup or None,
                "event_start": (event.get("status") or {}).get("startsAt"),
            }

    result: dict[str, Any] = {}
    for name, stats in grouped.items():
        result[name] = {}
        for stat, books in stats.items():
            summary = _book_summary(books, "SportsGameOdds")
            summary.update(meta.get((name, stat), {}))
            fair_line = _number(summary.get("fair_line"))
            consensus = _number(summary.get("consensus_line"))
            line_range = summary.get("range")
            if fair_line is not None and consensus is not None and line_range:
                if float(line_range[0]) <= fair_line <= float(line_range[1]):
                    # Keep ``consensus_line`` equal to the observable median
                    # shown in ``books`` and ``range``.  A provider's
                    # price-adjusted fair line can still be the projection
                    # input only within the posted book range. Label it
                    # separately from the observable book consensus.
                    summary["projection_line"] = fair_line
                    summary["projection_line_method"] = (
                        "provider_fair_line_within_book_range"
                    )
                else:
                    summary["projection_line"] = consensus
                    summary["projection_line_method"] = (
                        "robust_book_median; provider_fair_line_rejected"
                    )
            else:
                summary["projection_line"] = consensus
                summary["projection_line_method"] = "robust_book_median"
            opened = _number(summary.get("open_line"))
            final = _number(summary.get("consensus_line"))
            summary["line_move"] = (
                round(final - opened, 3)
                if final is not None and opened is not None
                else None
            )
            result[name][stat] = summary
    return {
        "status": "live" if result else "no_posted_lines",
        "source": "SportsGameOdds",
        "cache": cache_label,
        "line_snapshot": line_snapshot,
        "refreshed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "players": result,
        "provider_identity": provider_identity,
    }


def _odds_markets(position: str) -> list[str]:
    if position == "QB":
        return ["player_pass_yds", "player_pass_tds", "player_pass_interceptions", "player_pass_attempts"]
    if position == "RB":
        return ["player_rush_yds", "player_rush_attempts", "player_reception_yds", "player_receptions", "player_anytime_td"]
    if position in {"WR", "TE"}:
        return ["player_reception_yds", "player_receptions", "player_anytime_td"]
    if position == "K":
        return ["player_kicking_points"]
    return []


def the_odds_api(players: list[dict[str, Any]], enabled: bool = False) -> dict[str, Any]:
    """Cost-aware independent check.  It runs only for an explicitly deep packet."""
    secrets = load_secrets()
    api_key = secrets.get("THE_ODDS_API_KEY")
    if not enabled:
        return {"status": "not_requested", "source": "The Odds API", "players": {}}
    if not api_key:
        return {"status": "missing_key", "source": "The Odds API", "players": {}}
    relevant = [
        player for player in players
        if player.get("team") in NFL_TEAMS and _odds_markets(str(player.get("pos") or player.get("position") or ""))
    ]
    if not relevant:
        return {"status": "no_relevant_players", "source": "The Odds API", "players": {}}
    try:
        events = _cache_read("the_odds_api_nfl_events.json", 60 * 60)
        if events is None:
            event_response = requests.get(
                "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/events",
                params={"apiKey": api_key},
                headers=HEADERS,
                timeout=30,
            )
            event_response.raise_for_status()
            events = event_response.json()
            _cache_write("the_odds_api_nfl_events.json", events)
        by_event: dict[str, list[dict[str, Any]]] = {}
        for player in relevant:
            team_name = NFL_TEAMS[str(player.get("team"))]
            event = next(
                (row for row in events if row.get("home_team") == team_name or row.get("away_team") == team_name),
                None,
            )
            if event:
                by_event.setdefault(str(event["id"]), []).append(player)

        grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for event_id, event_players in list(by_event.items())[:4]:
            markets = sorted(
                {
                    market
                    for player in event_players
                    for market in _odds_markets(str(player.get("pos") or player.get("position") or ""))
                }
            )
            market_key = hashlib.sha256(
                ",".join(markets).encode("utf-8")
            ).hexdigest()[:12]
            cache_name = (
                f"the_odds_api_{event_id}_{market_key}.json"
            )
            event = _cache_read(cache_name, 10 * 60)
            if event is None:
                response = requests.get(
                    f"https://api.the-odds-api.com/v4/sports/americanfootball_nfl/events/{event_id}/odds",
                    params={
                        "apiKey": api_key,
                        "regions": "us",
                        "oddsFormat": "american",
                        "markets": ",".join(markets),
                    },
                    headers=HEADERS,
                    timeout=30,
                )
                if not response.ok:
                    continue
                event = response.json()
                _cache_write(cache_name, event)
            wanted = {normalize_name(str(player.get("name") or "")) for player in event_players}
            for bookmaker in event.get("bookmakers") or []:
                for market in bookmaker.get("markets") or []:
                    stat = ODDS_API_STATS.get(str(market.get("key") or ""))
                    if not stat:
                        continue
                    for outcome in market.get("outcomes") or []:
                        if outcome.get("name") != "Over" or not outcome.get("description"):
                            continue
                        name = normalize_name(str(outcome["description"]))
                        line = _number(outcome.get("point"))
                        if name not in wanted or line is None:
                            continue
                        grouped.setdefault(name, {}).setdefault(stat, []).append(
                            {
                                "book": bookmaker.get("title") or bookmaker.get("key"),
                                "line": line,
                                "price": _number(outcome.get("price")),
                                "open_line": None,
                                "updated_at": market.get("last_update") or bookmaker.get("last_update"),
                            }
                        )
        result = {
            name: {stat: _book_summary(books, "The Odds API") for stat, books in stats.items()}
            for name, stats in grouped.items()
        }
        return {
            "status": "live" if result else "no_posted_lines",
            "source": "The Odds API",
            "refreshed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "players": result,
        }
    except (requests.RequestException, ValueError, KeyError) as exc:
        return {
            "status": "provider_error",
            "source": "The Odds API",
            "error": type(exc).__name__,
            "players": {},
        }


def underdog(players: list[dict[str, Any]]) -> dict[str, Any]:
    """Intentionally disabled; use a focused signed-in browser check.

    This guard remains even though the production packet never calls this
    adapter.  It prevents a future caller from turning a public pick'em
    endpoint into an automated feed without a fresh policy decision.
    """
    return {
        "status": "manual_browser_on_request",
        "source": "Underdog",
        "players": {},
    }

    # Historical parser retained below as inert reference while the legacy
    # engine is phased out.  No statement below this return can make a request.
    wanted = {normalize_name(str(player.get("name") or "")) for player in players}
    wanted.discard("")
    try:
        response = requests.get(
            "https://api.underdogfantasy.com/beta/v5/over_under_lines",
            headers=HEADERS,
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {
            "status": "provider_error",
            "source": "Underdog",
            "error": type(exc).__name__,
            "players": {},
        }
    player_by_id = {
        str(player.get("id")): player
        for player in payload.get("players") or []
        if player.get("sport_id") == "NFL"
    }
    appearance_by_id = {
        str(appearance.get("id")): appearance
        for appearance in payload.get("appearances") or []
    }
    stat_map = {
        "season_receiving_yards": ("season", "rec_yd"),
        "season_rec_tds": ("season", "rec_td"),
        "season_rush_yards": ("season", "rush_yd"),
        "season_rush_tds": ("season", "rush_td"),
        "season_pass_yards": ("season", "pass_yd"),
        "season_pass_tds": ("season", "pass_td"),
        "receiving_rec": ("game", "rec"),
        "receiving_yds": ("game", "rec_yd"),
        "rushing_yds": ("game", "rush_yd"),
        "rush_rec_tds": ("game", "rush_rec_td"),
        "passing_yds": ("game", "pass_yd"),
    }
    result: dict[str, Any] = {}
    for row in payload.get("over_under_lines") or []:
        over_under = row.get("over_under") or {}
        appearance_stat = over_under.get("appearance_stat") or {}
        mapped = stat_map.get(str(appearance_stat.get("stat") or ""))
        if not mapped:
            continue
        appearance = appearance_by_id.get(str(appearance_stat.get("appearance_id") or "")) or {}
        player = player_by_id.get(str(appearance.get("player_id") or "")) or {}
        display_name = " ".join(
            part for part in (player.get("first_name"), player.get("last_name")) if part
        )
        key = normalize_name(display_name)
        line = _number(row.get("stat_value"))
        if key not in wanted or line is None:
            continue
        period, stat = mapped
        prices = {
            str(option.get("choice") or option.get("choice_id") or "").lower(): _number(option.get("american_price"))
            for option in row.get("options") or []
        }
        result.setdefault(key, {}).setdefault(period, {})[stat] = {
            "source": "Underdog",
            "line": line,
            "higher_price": prices.get("higher"),
            "lower_price": prices.get("lower"),
            "title": over_under.get("title"),
            "updated_at": row.get("updated_at") or over_under.get("updated_at"),
        }
    return {
        "status": "live" if result else "no_posted_lines",
        "source": "Underdog",
        "refreshed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "players": result,
    }


def _previous_snapshot_path(current_path: Path) -> Path | None:
    """The file immediately older than ``current_path`` in the history dir.

    Filenames start with the fetch's UTC stamp, so lexical sort is chronological
    sort. Returns None for the very first snapshot, or if ``current_path`` isn't
    present (a caller passed something outside MARKET_HISTORY_DIR).
    """
    files = sorted(MARKET_HISTORY_DIR.glob("*.jsonl"))
    try:
        index = files.index(current_path)
    except ValueError:
        return None
    return files[index - 1] if index > 0 else None


def _line_row_player_ids(path: Path) -> set[str]:
    """Provider player_ids with at least one posted line row in ``path``."""
    ids: set[str] = set()
    try:
        with path.open(encoding="utf-8") as handle:
            for raw_line in handle:
                try:
                    row = json.loads(raw_line)
                except ValueError:
                    continue
                if row.get("row_type") == "line":
                    ids.add(str(row.get("player_id")))
    except OSError:
        return set()
    return ids


def read_snapshot_rows(path: str | Path) -> list[dict[str, Any]]:
    """Every parsed row (line or projection) from one market-history file.

    Malformed lines are skipped rather than failing the whole read; this is a
    read of an append-only, exclusively-created file, so a bad line would
    mean disk corruption, not a race with the writer.
    """
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for raw_line in handle:
            try:
                rows.append(json.loads(raw_line))
            except ValueError:
                continue
    return rows


def _player_resolution_status(
    player: dict[str, Any],
    *,
    sportsbook: dict[str, Any] | None,
    provider_id: str | None,
    previous_line_ids: set[str] | None,
) -> dict[str, Any]:
    """Never let a focused player's market evidence go silently missing.

    Three failure classes, each independently visible rather than folded into
    a single ok/not-ok flag: the provider never named this player at all
    (unresolved_no_match); the provider named them but the engine has no
    projection to react to sportsbook evidence with (resolved_no_projection);
    and the provider named them and posted lines for them last fetch but
    posted none this fetch (lost_book_coverage) -- a real market event (game
    locked, prop pulled, status change), not silence to be mistaken for "no
    signal." None (not False) marks "not checked," e.g. no prior snapshot
    exists yet or this call was a cache hit with nothing new to compare.
    """
    resolved = provider_id is not None
    has_projection = _number(player.get("live_week_projection")) is not None
    has_lines_now = bool(sportsbook)
    lost_coverage: bool | None = None
    if resolved and previous_line_ids is not None:
        lost_coverage = provider_id in previous_line_ids and not has_lines_now
    flags = []
    if not resolved:
        flags.append("unresolved_no_match")
    elif not has_projection:
        flags.append("resolved_no_projection")
    if lost_coverage:
        flags.append("lost_book_coverage")
    return {
        "resolved": resolved,
        "has_projection": has_projection,
        "lost_book_coverage_since_previous_snapshot": lost_coverage,
        "flags": flags,
    }


def focused_market_packet(
    players: list[dict[str, Any]],
    deep: bool = False,
    *,
    force_refresh: bool = False,
    projection_universe: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    primary = sports_game_odds(
        players, force_refresh=force_refresh, projection_universe=projection_universe
    )
    validator = the_odds_api(players, enabled=deep)
    identity = primary.get("provider_identity") or {}
    previous_line_ids: set[str] | None = None
    snapshot_info = primary.get("line_snapshot") or {}
    if snapshot_info.get("status") == "written" and snapshot_info.get("path"):
        previous_path = _previous_snapshot_path(Path(snapshot_info["path"]))
        if previous_path is not None:
            previous_line_ids = _line_row_player_ids(previous_path)
    by_player: dict[str, Any] = {}
    coverage_warnings: list[str] = []
    for player in players:
        name = str(player.get("name") or "")
        key = normalize_name(name)
        sportsbook = primary.get("players", {}).get(key)
        resolution_status = _player_resolution_status(
            player,
            sportsbook=sportsbook,
            provider_id=identity.get(key),
            previous_line_ids=previous_line_ids,
        )
        if "lost_book_coverage" in resolution_status["flags"]:
            coverage_warnings.append(
                f"Lost sportsbook coverage: {name or key} had posted lines in "
                "the previous market-history snapshot and has none in this "
                "fetch. Treat this as a signal (game locked, book pulled the "
                "prop, or a status change) -- never as a zero or as silence."
            )
        by_player[name or key] = {
            "sportsbooks": sportsbook,
            "projection_update": market_projection_update(
                player, sportsbook
            ),
            "resolution_status": resolution_status,
            "pickem_boards": {
                "status": "manual_browser_on_request",
                "reason": (
                    "Keep pick'em evidence separate and inspect the signed-in "
                    "board or user screenshot for the specific decision."
                ),
            },
            "independent_check": validator.get("players", {}).get(key),
        }
    return {
        "line_snapshot": primary.get("line_snapshot"),
        "source_status": {
            "sports_game_odds": primary.get("status"),
            "pickem_boards": "manual_browser_on_request",
            "the_odds_api": validator.get("status"),
        },
        "players": by_player,
        "coverage_warnings": coverage_warnings,
    }


FANTASY_WEIGHTS = {
    "pass_yd": 0.04,
    "pass_td": 4.0,
    "pass_int": -1.0,
    "rush_yd": 0.1,
    "rec_yd": 0.1,
    "rec": 1.0,
    "kick_pts": 1.0,
}


def market_projection_update(
    player: dict[str, Any], sportsbook: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Replace only posted projection components with sportsbook fair lines.

    This is deliberately a delta from the Sleeper display projection, not a
    made-up full projection from a partial prop menu. Missing components remain
    in the baseline and every replacement is disclosed.
    """
    if not sportsbook:
        return None
    baseline_points = _number(player.get("live_week_projection"))
    stats = player.get("live_projection_stats") or {}
    if baseline_points is None or not isinstance(stats, dict):
        return {
            "status": "missing_baseline_components",
            "adjusted_points": None,
            "replacements": [],
        }
    delta = 0.0
    replacements = []
    for stat, weight in FANTASY_WEIGHTS.items():
        summary = sportsbook.get(stat) or {}
        market_line = _number(
            summary.get("projection_line")
            if "projection_line" in summary
            else summary.get("consensus_line")
        )
        baseline_stat = _number(stats.get(stat))
        if market_line is None or baseline_stat is None:
            continue
        contribution = (market_line - baseline_stat) * weight
        delta += contribution
        replacements.append(
            {
                "stat": stat,
                "baseline": baseline_stat,
                "market": market_line,
                "book_consensus": _number(
                    summary.get("book_consensus_line")
                    if "book_consensus_line" in summary
                    else summary.get("consensus_line")
                ),
                "market_method": summary.get("projection_line_method"),
                "fantasy_point_delta": round(contribution, 3),
                "book_count": summary.get("book_count"),
                "range": summary.get("range"),
                "updated_at": summary.get("updated_at"),
            }
        )
    if not replacements:
        return {
            "status": "no_comparable_components",
            "baseline_points": baseline_points,
            "adjusted_points": None,
            "replacements": [],
        }
    return {
        "status": "partial_market_update",
        "baseline_points": round(baseline_points, 3),
        "adjusted_points": round(baseline_points + delta, 3),
        "delta_points": round(delta, 3),
        "replacements": replacements,
        "warning": (
            "Partial update only. Unposted components remain at the baseline; "
            "touchdown prices are not converted without a two-sided no-vig probability."
        ),
    }
