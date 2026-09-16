"""Optional official FantasyPros projection adapter.

The free prototype or HOF personal key can be placed in the private secrets
file. This adapter keeps expert projections separate from sportsbook evidence
and never treats an ECR rank as a calibrated point projection.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

import requests

try:
    from .market_sources import load_secrets, normalize_name
except ImportError:  # pragma: no cover
    from market_sources import load_secrets, normalize_name


BASE_URL = "https://api.fantasypros.com/public/v2/json"
HEADERS = {
    "User-Agent": "Reeve-Fantasy-Advisor/2.0",
    "Accept": "application/json",
}
CACHE_DIR = Path(__file__).resolve().parent / "data" / "provider_cache"
CACHE_TTL_SECONDS = 6 * 60 * 60


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _projection_points(stats: dict[str, Any], scoring: str) -> float | None:
    candidates = (
        ("points_ppr", "fpts_ppr", "fantasy_points_ppr", "points")
        if scoring.upper() == "PPR"
        else ("points", "fantasy_points")
    )
    for key in candidates:
        value = _number(stats.get(key))
        if value is not None:
            return value
    return None


def fetch_projections(
    season: int,
    *,
    week: int | None = None,
    horizon: str = "weekly",
    scoring: str = "PPR",
    force: bool = False,
) -> dict[str, Any]:
    key = load_secrets().get("FANTASYPROS_API_KEY")
    if not key:
        return {
            "status": "missing_key",
            "source": "FantasyPros",
            "horizon": horizon,
            "players": {},
        }
    params: dict[str, Any] = {
        "positions": "QB:RB:WR:TE:DST:K",
        "scoring": scoring.upper(),
    }
    if horizon == "weekly":
        if week is None:
            raise ValueError("A week is required for weekly projections")
        params["week"] = int(week)
    elif horizon == "ros":
        params["type"] = "ros"
    else:
        raise ValueError("horizon must be weekly or ros")
    cache_name = (
        f"fantasypros_{int(season)}_{horizon}_"
        f"{int(week) if week is not None else 'all'}_{scoring.lower()}.json"
    )
    cache_path = CACHE_DIR / cache_name
    if (
        not force
        and cache_path.exists()
        and time.time() - cache_path.stat().st_mtime < CACHE_TTL_SECONDS
    ):
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            cached["cache"] = "local_6h"
            return cached
        except (OSError, ValueError):
            pass
    try:
        response = requests.get(
            f"{BASE_URL}/nfl/{int(season)}/projections",
            headers={**HEADERS, "x-api-key": key},
            params=params,
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {
            "status": "provider_error",
            "source": "FantasyPros",
            "horizon": horizon,
            "error": type(exc).__name__,
            "players": {},
        }

    raw_players = payload.get("players") or payload.get("player") or []
    players: dict[str, list[dict[str, Any]]] = {}
    for row in raw_players:
        name = str(row.get("name") or row.get("player_name") or "")
        position = str(
            row.get("position_id") or row.get("position") or ""
        ).replace("DST", "DEF")
        if not name or not position:
            continue
        stats = row.get("stats") or row
        points = _projection_points(stats, scoring)
        identity = f"{normalize_name(name)}|{position}"
        players.setdefault(identity, []).append(
            {
                "fantasypros_player_id": str(
                    row.get("fpid") or row.get("player_id") or ""
                ),
                "name": name,
                "position": position,
                "team": row.get("team_id") or row.get("team"),
                "points": points,
                "games": _number(
                    stats.get("games")
                    or stats.get("projected_games")
                    or row.get("games")
                ),
                "stats": {
                    str(stat): value
                    for stat, value in stats.items()
                    if isinstance(value, (int, float))
                },
            }
        )
    unique = {
        identity: rows[0] for identity, rows in players.items() if len(rows) == 1
    }
    ambiguous = sorted(
        identity for identity, rows in players.items() if len(rows) > 1
    )
    result = {
        "status": "live" if unique else "no_projections",
        "source": "FantasyPros",
        "horizon": horizon,
        "scoring": scoring.upper(),
        "season": int(season),
        "week": int(week) if week is not None else None,
        "refreshed_at_utc": dt.datetime.now(
            dt.timezone.utc
        ).isoformat(timespec="seconds"),
        "players": unique,
        "ambiguous_identity_keys": ambiguous,
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(result, separators=(",", ":")), encoding="utf-8"
    )
    return result


def focused_expert_packet(
    players: list[dict[str, Any]],
    season: int,
    week: int,
    *,
    include_ros: bool = True,
) -> dict[str, Any]:
    weekly = fetch_projections(
        season, week=week, horizon="weekly", scoring="PPR"
    )
    ros = (
        fetch_projections(season, horizon="ros", scoring="PPR")
        if include_ros
        else {
            "status": "not_requested",
            "players": {},
            "source": "FantasyPros",
        }
    )
    result = {}
    for player in players:
        position = str(
            player.get("pos") or player.get("position") or ""
        ).replace("DST", "DEF")
        identity = (
            f"{normalize_name(str(player.get('name') or ''))}|{position}"
        )
        result[str(player.get("name") or identity)] = {
            "weekly": (weekly.get("players") or {}).get(identity),
            "rest_of_season": (ros.get("players") or {}).get(identity),
        }
    return {
        "source_status": {
            "weekly": weekly.get("status"),
            "rest_of_season": ros.get("status"),
        },
        "refreshed_at_utc": weekly.get("refreshed_at_utc")
        or ros.get("refreshed_at_utc"),
        "players": result,
        "policy": (
            "Independent expert projection evidence; never merged with "
            "sportsbook or pick'em labels."
        ),
    }
