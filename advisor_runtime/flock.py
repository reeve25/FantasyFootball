"""Public Flock Fantasy rankings and trade-calculator client."""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any

import requests


BASE_URL = "https://api.flockfantasy.com"
TIMEOUT_SECONDS = 12
_CACHE: dict[tuple[str, int], Any] = {}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _json(method: str, path: str, **kwargs) -> Any:
    last_error = None
    for _ in range(2):
        try:
            response = requests.request(
                method,
                f"{BASE_URL}{path}",
                timeout=TIMEOUT_SECONDS,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
    raise last_error


def fairness_verdict(user_value: float, opponent_value: float) -> dict[str, Any]:
    """Mirror Flock's web-client verdict thresholds exactly."""
    user = float(user_value)
    opponent = float(opponent_value)
    midpoint = (user + opponent) / 2.0
    difference_pct = abs(user - opponent) / midpoint * 100 if midpoint else 0.0
    if difference_pct > 42.5:
        verdict = "You're robbing them!" if user > opponent else "They're robbing you!"
    elif difference_pct > 17:
        verdict = "You win!" if user > opponent else "You lose!"
    elif difference_pct > 8.5:
        verdict = "You slightly win!" if user > opponent else "You slightly lose!"
    else:
        verdict = "Fair Trade!"
    return {
        "verdict": verdict,
        "is_fair_trade": verdict == "Fair Trade!",
        "difference_pct": round(difference_pct, 4),
    }


def _rankings(year: int) -> dict[str, Any]:
    key = ("rankings", year)
    if key not in _CACHE:
        _CACHE[key] = _json(
            "GET",
            "/rankings",
            params={"format": "REDRAFT", "pickType": "general", "year": year},
        )
    return _CACHE[key]


def _scoring_label(league: dict[str, Any]) -> str | None:
    receptions = (league.get("scoring_settings") or {}).get("rec")
    if receptions is None:
        text = " ".join(
            str(league.get(field) or "")
            for field in ("scoring", "known_format_fallback")
        ).lower()
        if "full ppr" in text:
            receptions = 1
        elif "half ppr" in text:
            receptions = 0.5
        elif "non ppr" in text or "standard" in text:
            receptions = 0
    if receptions is None or not math.isfinite(float(receptions)):
        return None
    return "PPR" if float(receptions) >= 0.75 else "HALF" if float(receptions) >= 0.25 else "NON"


def _settings(snapshot: dict[str, Any]) -> dict[str, Any]:
    league = snapshot.get("league") or {}
    slots = list(league.get("starter_slots") or [])
    settings: dict[str, Any] = {
        "format": "REDRAFT",
        "enable_superflex": any(slot in {"SUPER_FLEX", "SUPERFLEX", "Q/W/R/T"} for slot in slots),
    }
    scoring = _scoring_label(league)
    if scoring:
        settings["scoring"] = scoring
    league_size = league.get("total_rosters")
    if not isinstance(league_size, int):
        match = re.search(r"\b(\d+)\s*-?\s*team\b", str(league.get("known_format_fallback") or ""), re.IGNORECASE)
        league_size = int(match.group(1)) if match else None
    if isinstance(league_size, int) and league_size > 1:
        settings["league_size"] = league_size
    for field, slot in (("qb", "QB"), ("rb", "RB"), ("wr", "WR"), ("te", "TE")):
        count = slots.count(slot)
        if count:
            settings[field] = count
    flex = sum(slots.count(slot) for slot in ("FLEX", "W/R/T", "WRRB_FLEX"))
    if flex:
        settings["flex"] = flex
    bench = list(league.get("roster_positions") or []).count("BN")
    if bench:
        settings["bench"] = bench
    return settings


def _side(
    requested_ids: list[str],
    requested_names: list[str],
    ranking_by_id: dict[int, dict[str, Any]],
    flock_by_sleeper: dict[str, int],
    flock_by_name: dict[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload, evidence = [], []
    for index, name in enumerate(requested_names):
        sleeper_id = requested_ids[index] if index < len(requested_ids) else None
        flock_id = flock_by_sleeper.get(str(sleeper_id)) if sleeper_id is not None else None
        if flock_id is None:
            flock_id = flock_by_name.get(name.casefold())
        ranking = ranking_by_id.get(int(flock_id)) if flock_id is not None else None
        rank = ranking.get("averageRank") if ranking else None
        if flock_id is None or not isinstance(rank, (int, float)) or not math.isfinite(float(rank)):
            raise ValueError(f"Flock has no current 2026 redraft rank for {name}")
        rounded_rank = round(float(rank))
        payload.append({"player_id": int(flock_id), "rank": rounded_rank})
        evidence.append(
            {
                "name": name,
                "sleeper_id": sleeper_id,
                "flock_player_id": int(flock_id),
                "average_rank": float(rank),
            }
        )
    return payload, evidence


def check_trade(snapshot: dict[str, Any], trade: dict[str, Any]) -> dict[str, Any]:
    """Return Flock's live redraft values and exact web-client verdict."""
    try:
        league = snapshot.get("league") or {}
        year = int(league.get("season") or dt.datetime.now(dt.timezone.utc).year)
        rankings = _rankings(year)
        ranking_rows = rankings.get("data") or []
        ranking_by_id = {
            int(row["playerId"]): row
            for row in ranking_rows
            if row.get("playerId") is not None
        }
        flock_by_sleeper = {str(player_id): player_id for player_id in ranking_by_id}
        flock_by_name = {
            str(row.get("playerName") or "").casefold(): int(row["playerId"])
            for row in ranking_rows
            if row.get("playerName") and row.get("playerId") is not None
        }
        outgoing, outgoing_evidence = _side(
            [str(value) for value in trade.get("give_ids") or []],
            [str(value) for value in trade.get("give") or []],
            ranking_by_id,
            flock_by_sleeper,
            flock_by_name,
        )
        incoming, incoming_evidence = _side(
            [str(value) for value in trade.get("get_ids") or []],
            [str(value) for value in trade.get("get") or []],
            ranking_by_id,
            flock_by_sleeper,
            flock_by_name,
        )
        settings = _settings(snapshot)
        result = _json(
            "POST",
            "/trades/calculate",
            json={
                "selectedExpert": "EXPERT",
                "opponentReceives": outgoing,
                "userReceives": incoming,
                "settings": settings,
            },
        )
        verdict = fairness_verdict(result["user"], result["opponent"])
        return {
            "status": "checked",
            "source": "Flock Fantasy public web API",
            "observed_at_utc": _now(),
            "season": year,
            "format": rankings.get("format") or "REDRAFT",
            "subformat": rankings.get("subformat"),
            "scoring": settings.get("scoring"),
            "ranking_last_updated": rankings.get("lastUpdated"),
            "give": outgoing_evidence,
            "get": incoming_evidence,
            "user_value": result["user"],
            "opponent_value": result["opponent"],
            "suggestions": result.get("suggestions"),
            **verdict,
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "source": "Flock Fantasy public web API",
            "observed_at_utc": _now(),
            "reason": type(exc).__name__,
            "detail": str(exc),
            "is_fair_trade": None,
        }
