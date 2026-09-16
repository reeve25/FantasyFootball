"""Small, live Sleeper reads used at decision time.

This module deliberately avoids projection-model work.  It owns the facts that
can change between two questions: league settings, roster ownership, submitted
starter slots, transactions, and the current week's Sleeper projection feed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter


SLEEPER_API = "https://api.sleeper.app/v1"
SLEEPER_PROJECTIONS = "https://api.sleeper.app/projections/nfl"
HEADERS = {"User-Agent": "Reeve-Fantasy-Advisor/2.0"}
REQUEST_TIMEOUT = (3.05, 8.0)
FACT_TTL_SECONDS = 60
CACHE_DIR = Path(__file__).resolve().parent / "data" / "live_cache"
_LOCAL = threading.local()


def _session() -> requests.Session:
    # Each worker owns a connection pool. No automatic retries or Retry-After
    # sleeps: the CLI also enforces a whole-process deadline.
    if not hasattr(_LOCAL, "session"):
        session = requests.Session()
        session.headers.update(HEADERS)
        session.mount("https://", HTTPAdapter(max_retries=0))
        _LOCAL.session = session
    return _LOCAL.session


def _get_json(
    url: str,
    timeout: tuple[float, float] = REQUEST_TIMEOUT,
    *,
    provenance: dict[str, Any] | None = None,
    source: str | None = None,
) -> Any:
    """Read a bounded-age cache, otherwise one short request; never stale fallback."""
    path = CACHE_DIR / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    now = time.time()
    cached = False
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = float(envelope["fetched_at"])
        age = now - fetched_at
        cached = 0 <= age <= FACT_TTL_SECONDS
        payload = envelope["payload"] if cached else None
    except (OSError, ValueError, KeyError, TypeError):
        payload = None
    if not cached:
        response = _session().get(url, timeout=timeout)
        try:
            response.raise_for_status()
            payload = response.json()
        finally:
            response.close()
        fetched_at = time.time()
        # Atomic replacement permits Claude and ChatGPT to read the same cache.
        temporary = None
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", delete=False, dir=CACHE_DIR, suffix=".tmp"
            ) as handle:
                temporary = Path(handle.name)
                json.dump({"fetched_at": fetched_at, "payload": payload}, handle)
            os.replace(temporary, path)
        except OSError:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    if provenance is not None:
        provenance[source or url] = {
            "fetched_at_utc": dt.datetime.fromtimestamp(
                fetched_at, tz=dt.timezone.utc
            ).isoformat(timespec="seconds"),
            "age_seconds": round(max(0.0, time.time() - fetched_at), 1),
            "cache": "local_60s" if cached else "network",
        }
    return payload


def _name(player: dict[str, Any] | None, player_id: str) -> str:
    player = player or {}
    return (
        player.get("name")
        or player.get("full_name")
        or " ".join(
            part for part in (player.get("first_name"), player.get("last_name")) if part
        )
        or (f"{player_id} D/ST" if len(player_id) <= 4 else player_id)
    )


def _position(player: dict[str, Any] | None, player_id: str) -> str:
    player = player or {}
    position = player.get("pos") or player.get("position")
    if position:
        return str(position)
    return "DEF" if len(player_id) <= 4 else ""


def _score(stats: dict[str, Any], scoring: dict[str, Any]) -> float | None:
    points = 0.0
    found = False
    for stat, multiplier in scoring.items():
        value = stats.get(stat)
        if (
            isinstance(value, (int, float)) and not isinstance(value, bool)
            and isinstance(multiplier, (int, float)) and not isinstance(multiplier, bool)
            and math.isfinite(value) and math.isfinite(multiplier)
        ):
            points += float(value) * float(multiplier)
            found = True
    return round(points, 3) if found else None


def _projection_map(
    season: str, week: int, scoring: dict[str, Any],
    provenance: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    suffix = (
        "?season_type=regular&position[]=QB&position[]=RB&position[]=WR"
        "&position[]=TE&position[]=K&position[]=DEF"
    )
    rows = _get_json(
        f"{SLEEPER_PROJECTIONS}/{season}/{week}{suffix}",
        provenance=provenance, source="projections",
    )
    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("projections") or []
    out: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        player_id = str(row.get("player_id") or (row.get("player") or {}).get("player_id") or "")
        if not player_id:
            continue
        stats = row.get("stats") or {}
        player_meta = row.get("player") or {}
        out[player_id] = {
            "points": _score(stats, scoring),
            "stats": {
                str(key): value
                for key, value in stats.items()
                if isinstance(value, (int, float))
            },
            "opponent": player_meta.get("opponent"),
            "game_date": player_meta.get("game_date"),
            "last_modified": player_meta.get("last_modified")
            or row.get("last_modified"),
            "source_label": "Sleeper projection display feed",
            "player_metadata": {
                key: player_meta[key]
                for key in (
                    "full_name", "first_name", "last_name", "position", "team",
                    "status", "injury_status", "injury_body_part", "news_updated",
                )
                if key in player_meta
            },
        }
    return out


def _manager_names(users: list[dict[str, Any]], rosters: list[dict[str, Any]]) -> dict[int, str]:
    by_user = {
        str(user.get("user_id")): str(
            (user.get("metadata") or {}).get("team_name")
            or user.get("display_name")
            or "Manager"
        )
        for user in users
    }
    return {
        int(roster["roster_id"]): by_user.get(str(roster.get("owner_id")), f"Roster {roster['roster_id']}")
        for roster in rosters
    }


def _transaction_rows(
    league_id: str,
    week: int,
    managers: dict[int, str],
    players: dict[str, dict[str, Any]],
    provenance: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    transactions: list[dict[str, Any]] = []
    weeks = list(range(max(1, week - 2), week + 1))
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            query_week: pool.submit(
                _get_json, f"{SLEEPER_API}/league/{league_id}/transactions/{query_week}",
                provenance=provenance, source=f"transactions_week_{query_week}",
            )
            for query_week in weeks
        }
    for query_week, future in futures.items():
        try:
            rows = future.result()
        except (requests.RequestException, ValueError):
            if warnings is not None:
                warnings.append(f"Sleeper transactions for week {query_week} were unavailable.")
            continue
        for tx in rows or []:
            if tx.get("status") != "complete":
                continue
            roster_ids = [int(value) for value in tx.get("roster_ids") or []]
            adds = tx.get("adds") or {}
            drops = tx.get("drops") or {}
            sides = []
            for roster_id in roster_ids:
                acquired = [
                    _name(players.get(str(pid)), str(pid))
                    for pid, rid in adds.items()
                    if int(rid) == roster_id
                ]
                sent = [
                    _name(players.get(str(pid)), str(pid))
                    for pid, rid in drops.items()
                    if int(rid) == roster_id
                ]
                sides.append(
                    {
                        "roster_id": roster_id,
                        "manager": managers.get(roster_id, f"Roster {roster_id}"),
                        "acquired": acquired,
                        "sent": sent,
                    }
                )
            timestamp_ms = tx.get("status_updated") or tx.get("created")
            timestamp = None
            if isinstance(timestamp_ms, (int, float)):
                timestamp = dt.datetime.fromtimestamp(
                    timestamp_ms / 1000, tz=dt.timezone.utc
                ).isoformat(timespec="seconds")
            transactions.append(
                {
                    "transaction_id": str(tx.get("transaction_id") or ""),
                    "week": query_week,
                    "type": tx.get("type"),
                    "timestamp_utc": timestamp,
                    "sides": sides,
                    "draft_picks": tx.get("draft_picks") or [],
                    "waiver_bid": (tx.get("settings") or {}).get("waiver_bid"),
                }
            )
    transactions.sort(key=lambda row: row.get("timestamp_utc") or "", reverse=True)
    return transactions


def fetch_live_context(
    league_id: str,
    roster_id: int,
    snapshot_players: dict[str, dict[str, Any]],
    *,
    include_transactions: bool = False,
) -> dict[str, Any]:
    """Return current league facts, with observed timestamps and a 60s cache."""
    provenance: dict[str, Any] = {}
    warnings: list[str] = []
    urls = {
        "state": f"{SLEEPER_API}/state/nfl",
        "league": f"{SLEEPER_API}/league/{league_id}",
        "rosters": f"{SLEEPER_API}/league/{league_id}/rosters",
        "users": f"{SLEEPER_API}/league/{league_id}/users",
    }
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            name: pool.submit(_get_json, url, provenance=provenance, source=name)
            for name, url in urls.items()
        }
        state, league, rosters, users = (
            futures[name].result() for name in ("state", "league", "rosters", "users")
        )
    season = str(league.get("season") or state.get("season") or "2026")
    week = max(1, int(state.get("week") or 1))
    scoring = league.get("scoring_settings") or {}
    managers = _manager_names(users or [], rosters or [])
    with ThreadPoolExecutor(max_workers=3) as pool:
        projection_future = pool.submit(_projection_map, season, week, scoring, provenance)
        stats_future = pool.submit(_get_json, f"{SLEEPER_API}/stats/nfl/regular/{season}", provenance=provenance, source="season_stats")
        matchup_future = pool.submit(
            _get_json, f"{SLEEPER_API}/league/{league_id}/matchups/{week}",
            provenance=provenance, source="matchups",
        )
        transaction_future = (
            pool.submit(
                _transaction_rows, league_id, week, managers, snapshot_players,
                provenance, warnings,
            ) if include_transactions else None
        )
        try:
            projections = projection_future.result()
        except (requests.RequestException, ValueError, TypeError):
            projections = {}
            warnings.append("Current Sleeper projections and player status were unavailable.")
        try:
            matchups = matchup_future.result()
        except (requests.RequestException, ValueError, TypeError):
            matchups = []
            warnings.append("Current Sleeper matchup was unavailable.")
        transactions = transaction_future.result() if transaction_future else []
        try:
            season_stats = stats_future.result() or {}
        except Exception:
            season_stats = {}
            warnings.append("Sleeper season stats feed was unavailable.")
    team_targets = {}
    for pid, pstats in season_stats.items():
        tm = (snapshot_players.get(pid) or {}).get("team")
        if tm and pstats.get("rec_tgt") is not None:
            team_targets[tm] = team_targets.get(tm, 0) + float(pstats["rec_tgt"])

    player_metadata = {}
    for player_id, row in projections.items():
        if not row.get("player_metadata"):
            continue
        meta = row["player_metadata"]
        if player_id in season_stats:
            p_stats = season_stats[player_id]
            off_snp = p_stats.get("off_snp", 0)
            tm_off_snp = p_stats.get("tm_off_snp", 0)
            if tm_off_snp and off_snp is not None:
                meta["snap_share_pct"] = round(off_snp / tm_off_snp * 100, 1)

            targets = p_stats.get("rec_tgt", 0)
            tm = meta.get("team") or (snapshot_players.get(player_id) or {}).get("team")
            if tm and targets is not None and team_targets.get(tm):
                meta["target_share_pct"] = round(targets / team_targets[tm] * 100, 1)
        player_metadata[player_id] = meta

    roster_positions = [str(slot) for slot in league.get("roster_positions") or []]
    starter_slots = [slot for slot in roster_positions if slot not in {"BN", "IR", "TAXI"}]
    owner_by_player: dict[str, int] = {}
    roster_rows: list[dict[str, Any]] = []

    for roster in rosters or []:
        rid = int(roster["roster_id"])
        player_ids = [str(pid) for pid in roster.get("players") or []]
        for player_id in player_ids:
            owner_by_player[player_id] = rid
        roster_rows.append(
            {
                "roster_id": rid,
                "manager": managers.get(rid, f"Roster {rid}"),
                "player_ids": player_ids,
                "starter_ids": [str(pid) for pid in roster.get("starters") or []],
                "reserve_ids": [str(pid) for pid in roster.get("reserve") or []],
                "waiver_position": (roster.get("settings") or {}).get("waiver_position"),
                "wins": (roster.get("settings") or {}).get("wins"),
                "losses": (roster.get("settings") or {}).get("losses"),
                "ties": (roster.get("settings") or {}).get("ties"),
                "points_for": (roster.get("settings") or {}).get("fpts"),
            }
        )

    mine = next((row for row in roster_rows if row["roster_id"] == int(roster_id)), None)
    if mine is None:
        raise ValueError(f"Roster {roster_id} is not in league {league_id}")

    lineup = []
    for index, slot in enumerate(starter_slots):
        player_id = mine["starter_ids"][index] if index < len(mine["starter_ids"]) else ""
        if not player_id or player_id == "0":
            lineup.append({"slot": slot, "player_id": None, "name": "EMPTY", "position": None, "points": 0.0})
            continue
        player = {**(snapshot_players.get(player_id) or {}), **player_metadata.get(player_id, {})}
        lineup.append(
            {
                "slot": slot,
                "player_id": player_id,
                "name": _name(player, player_id),
                "position": _position(player, player_id),
                "team": player.get("team"),
                "status": player.get("injury_status") or player.get("status"),
                "points": (
                    projections.get(player_id) or {}
                ).get("points"),
            }
        )

    matchup_by_roster = {
        int(row["roster_id"]): row for row in matchups or []
        if row.get("roster_id") is not None
    }
    matchup_groups: dict[int, list[int]] = {}
    for row in matchups or []:
        if row.get("matchup_id") is None or row.get("roster_id") is None:
            continue
        matchup_groups.setdefault(int(row["matchup_id"]), []).append(
            int(row["roster_id"])
        )
    my_matchup = matchup_by_roster.get(int(roster_id))
    opponent_roster_id = None
    if my_matchup and my_matchup.get("matchup_id") is not None:
        members = matchup_groups.get(int(my_matchup["matchup_id"]), [])
        opponent_roster_id = next(
            (value for value in members if value != int(roster_id)), None
        )

    return {
        "refreshed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source_provenance": provenance,
        "runtime_warnings": warnings,
        "season": season,
        "week": week,
        "league_name": str(league.get("name") or "Sleeper league"),
        "total_rosters": int(league.get("total_rosters") or len(roster_rows)),
        "scoring_settings": scoring,
        "league_settings": league.get("settings") or {},
        "roster_positions": roster_positions,
        "starter_slots": starter_slots,
        "my_roster": mine,
        "rosters": roster_rows,
        "owner_by_player": owner_by_player,
        "projection_by_player": projections,
        "player_metadata_by_id": player_metadata,
        "current_lineup": lineup,
        "current_lineup_total": (
            round(sum(float(row["points"]) for row in lineup), 2)
            if all(row.get("points") is not None for row in lineup) else None
        ),
        "current_lineup_known_subtotal": round(
            sum(float(row["points"]) for row in lineup if row.get("points") is not None), 2
        ),
        "transactions_requested": include_transactions,
        "recent_transactions": transactions[:30],
        "current_matchup": {
            "matchup_id": my_matchup.get("matchup_id")
            if my_matchup
            else None,
            "my_points": my_matchup.get("points") if my_matchup else None,
            "opponent_roster_id": opponent_roster_id,
            "opponent_manager": managers.get(opponent_roster_id)
            if opponent_roster_id is not None
            else None,
            "opponent_points": (
                matchup_by_roster.get(opponent_roster_id) or {}
            ).get("points")
            if opponent_roster_id is not None
            else None,
        },
    }
