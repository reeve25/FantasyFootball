"""Small, live Sleeper reads used at decision time.

This module deliberately avoids projection-model work.  It owns the facts that
can change between two questions: league settings, roster ownership, submitted
starter slots, transactions, and the current week's Sleeper projection feed.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


SLEEPER_API = "https://api.sleeper.app/v1"
SLEEPER_PROJECTIONS = "https://api.sleeper.app/projections/nfl"
HEADERS = {"User-Agent": "Reeve-Fantasy-Advisor/2.0"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
SESSION.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=3,
            connect=3,
            read=2,
            backoff_factor=0.35,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
    ),
)


def _get_json(url: str, timeout: int = 45) -> Any:
    response = SESSION.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


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


def _score(stats: dict[str, Any], scoring: dict[str, Any]) -> float:
    points = 0.0
    found = False
    for stat, multiplier in scoring.items():
        value = stats.get(stat)
        if isinstance(value, (int, float)) and isinstance(multiplier, (int, float)):
            points += float(value) * float(multiplier)
            found = True
    if not found:
        for key in ("pts_ppr", "pts_half_ppr", "pts_std"):
            value = stats.get(key)
            if isinstance(value, (int, float)):
                return round(float(value), 3)
    return round(points, 3)


def _projection_map(
    season: str, week: int, scoring: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    suffix = (
        "?season_type=regular&position[]=QB&position[]=RB&position[]=WR"
        "&position[]=TE&position[]=K&position[]=DEF"
    )
    rows = _get_json(f"{SLEEPER_PROJECTIONS}/{season}/{week}{suffix}", timeout=90)
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
) -> list[dict[str, Any]]:
    transactions: list[dict[str, Any]] = []
    for query_week in range(max(1, week - 2), week + 1):
        try:
            rows = _get_json(f"{SLEEPER_API}/league/{league_id}/transactions/{query_week}")
        except requests.RequestException:
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
) -> dict[str, Any]:
    """Return the small live layer that must override cached roster facts."""
    state = _get_json(f"{SLEEPER_API}/state/nfl")
    league = _get_json(f"{SLEEPER_API}/league/{league_id}")
    rosters = _get_json(f"{SLEEPER_API}/league/{league_id}/rosters")
    users = _get_json(f"{SLEEPER_API}/league/{league_id}/users")
    try:
        matchups = _get_json(
            f"{SLEEPER_API}/league/{league_id}/matchups/"
            f"{max(1, int(state.get('week') or 1))}"
        )
    except requests.RequestException:
        matchups = []

    season = str(league.get("season") or state.get("season") or "2026")
    week = max(1, int(state.get("week") or 1))
    scoring = league.get("scoring_settings") or {}
    projections = _projection_map(season, week, scoring)
    managers = _manager_names(users or [], rosters or [])
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
        player = snapshot_players.get(player_id) or {}
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
        "current_lineup": lineup,
        "current_lineup_total": round(sum(float(row.get("points") or 0) for row in lineup), 2),
        "recent_transactions": _transaction_rows(
            league_id, week, managers, snapshot_players
        )[:30],
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
