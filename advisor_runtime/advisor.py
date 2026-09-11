#!/usr/bin/env python3
"""Chat-first evidence runtime for Reeve's 2026 fantasy-football advisor.

This code never calls a language-model API. It prepares a small, auditable
decision packet for the Codex/ChatGPT conversation that is already running.
Sleeper is authoritative for league and roster facts; the legacy engine is a
projection input and math oracle only, not an autonomous decision maker.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import math
import os
import re
import sys
import tempfile
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import requests

try:
    from .fantasypros_source import focused_expert_packet
    from .market_sources import focused_market_packet, source_configuration
    from .sleeper_live import fetch_live_context
except ImportError:  # pragma: no cover - command-line import path
    from fantasypros_source import focused_expert_packet
    from market_sources import focused_market_packet, source_configuration
    from sleeper_live import fetch_live_context


ROOT = Path(__file__).resolve().parent
ENGINE_PATH = ROOT / "engine" / "ff_v6_3.py"
CONFIG_PATH = ROOT / "config.json"
DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "snapshot.json"
HISTORY_DIR = DATA_DIR / "history"
ENGINE_CACHE_DIR = ROOT / ".ffcache"

DEFAULT_CONFIG = {
    "league_id": "1327873074195886081",
    "my_roster_id": 9,
    "snapshot_ttl_minutes": 360,
    "season_end_week": 17,
    "playoff_weeks": [15, 16, 17],
    "packet_character_limit": 24000,
}
CORE_POSITIONS = {"QB", "RB", "WR", "TE"}
ALL_POSITIONS = CORE_POSITIONS | {"K", "DEF"}
BENCH_SLOTS = {"BN", "IR", "TAXI"}
HARD_INACTIVE = {"OUT", "IR", "PUP", "SUSPENDED", "INACTIVE"}
ALIASES = {
    "jsn": "Jaxon Smith-Njigba",
    "tlaw": "Trevor Lawrence",
    "cmc": "Christian McCaffrey",
    "arsb": "Amon-Ra St. Brown",
    "monty": "David Montgomery",
}


def load_config() -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            config.update(raw)
    return config


CONFIG = load_config()
LEAGUE_ID = str(CONFIG["league_id"])
MY_ROSTER_ID = int(CONFIG["my_roster_id"])


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def _timestamp(value: Any) -> dt.datetime | None:
    try:
        if isinstance(value, (int, float)):
            stamp = float(value)
            return dt.datetime.fromtimestamp(stamp / 1000 if stamp > 1e11 else stamp, dt.timezone.utc)
        stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.replace(tzinfo=dt.timezone.utc) if stamp.tzinfo is None else stamp
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _age_minutes(value: Any) -> float | None:
    stamp = _timestamp(value)
    return round(max(0.0, (utc_now() - stamp).total_seconds() / 60), 1) if stamp else None


def evidence_freshness(snapshot: dict[str, Any]) -> dict[str, Any]:
    """A new packet or snapshot never refreshes the underlying observations."""
    timestamps = (snapshot.get("engine") or {}).get("source_cache_fetched_at_utc") or {}
    sources = {}
    max_age = float(CONFIG.get("projection_max_age_minutes", 720))
    for name in ("sleeper_projection_feed", "espn"):
        age = _age_minutes(timestamps.get(name))
        sources[name] = {"fetched_at_utc": timestamps.get(name), "age_minutes": age,
                         "status": "unknown" if age is None else "fresh" if age <= max_age else "stale"}
    roster_stamp = (snapshot.get("league") or {}).get("live_refreshed_at_utc")
    roster_age = _age_minutes(roster_stamp)
    roster_status = "unverified" if roster_age is None else "fresh" if roster_age <= float(CONFIG.get("roster_max_age_minutes", 5)) else "stale"
    return {"projection_sources": sources, "projection_max_age_minutes": max_age,
            "rosters": {"fetched_at_utc": roster_stamp, "age_minutes": roster_age, "status": roster_status},
            "all_projection_sources_fresh": all(row["status"] == "fresh" for row in sources.values())}


def _ros_summary(player: dict[str, Any], weeks: list[int]) -> dict[str, Any]:
    """Keep an active-game rate distinct from incomplete ROS evidence."""
    byes = {int(value) for value in player.get("bye_weeks") or []}
    expected = [week for week in weeks if week not in byes]
    points = player.get("weekly_points") or {}
    known = [_finite(points.get(str(week), points.get(week))) for week in expected]
    values = [value for value in known if value is not None]
    complete = bool(expected) and len(values) == len(expected)
    return {"projection_pg": round(sum(values) / len(values), 4) if complete else None,
            "projection_state": "remaining_week_ensemble" if complete else "partial_weekly" if values else "missing",
            "projection_horizon": {"weeks": weeks, "nonbye_weeks": len(expected), "projected_weeks": len(values),
                                   "complete": complete, "known_week_mean_pg": round(sum(values) / len(values), 4) if values else None}}


def json_safe(value: Any) -> Any:
    """Convert pandas/numpy values and sets to strict JSON primitives."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, dict):
        return {str(key): json_safe(cell) for key, cell in value.items()}
    if isinstance(value, (list, tuple, set, range)):
        return [json_safe(cell) for cell in value]
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_text(text: str) -> str:
    plain = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip()


def _display_name(player: dict[str, Any], player_id: str) -> str:
    return (
        player.get("full_name")
        or player.get("name")
        or " ".join(
            part for part in (player.get("first_name"), player.get("last_name")) if part
        )
        or (f"{player_id} D/ST" if len(player_id) <= 4 else player_id)
    )


def load_engine(quick: bool = False):
    """Load v6.3 with undocumented markets and autonomous heuristics disabled."""
    if not ENGINE_PATH.exists():
        raise FileNotFoundError(f"Projection engine not found: {ENGINE_PATH}")
    spec = importlib.util.spec_from_file_location("reeve_projection_oracle", ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the projection engine")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CACHE = str(ENGINE_CACHE_DIR)
    # The preserved engine's non-quick board path reaches legacy pick'em and
    # betting endpoints.  The new advisor has its own licensed, focused
    # market layer, so the projection oracle always runs in projection-only
    # mode.  This also prevents an accidental rebuild from automating a
    # pick'em board that is reserved for user-directed browser inspection.
    module.QUICK = True
    module.BP_API_KEY = ""
    module.BP_KEY = {}
    module.check_receptions = lambda *args, **kwargs: {
        "legacy_market_probe": "disabled"
    }
    module.src_underdog = lambda *args, **kwargs: module.pd.DataFrame()
    return module


def _weekly_state(
    key: str,
    week: int,
    weekly_points: dict[str, dict[int, Any]],
    bye_weeks: dict[str, set[int]],
    weekly_meta: dict[str, Any] | None = None,
) -> str:
    if week in set((bye_weeks or {}).get(key, set())):
        return "bye"
    if _finite((weekly_points.get(key) or {}).get(week)) is not None:
        return "projected"
    meta = (weekly_meta or {}).get(key, {}) or {}
    status = normalize_text(str(meta.get("inj") or "")).upper()
    if status in HARD_INACTIVE:
        return "hard_inactive"
    return "absent"


def _projection_for_week(player: dict[str, Any], week: int) -> tuple[float | None, str]:
    if week in set(player.get("bye_weeks") or []):
        # A bye is a known zero, not an unknown projection. Returning None
        # makes one unavoidable QB/TE bye poison a whole-season roster mean.
        return 0.0, "bye"
    status = normalize_text(
        str(player.get("injury_status") or player.get("status") or "")
    ).upper()
    if status in HARD_INACTIVE and week == int(player.get("current_week") or week):
        return 0.0, "hard_inactive"
    weekly = player.get("weekly_points") or {}
    if str(week) in weekly:
        value = _finite(weekly.get(str(week)))
        if value is not None:
            return value, "weekly_projection"
    return None, "missing"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        json.dump(json_safe(payload), handle, indent=2, sort_keys=True, allow_nan=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def _archive_summary(snapshot: dict[str, Any]) -> None:
    generated = str(snapshot.get("generated_at_utc") or "").replace(":", "-")
    if not generated:
        return
    summary = {
        "schema_version": snapshot.get("schema_version"),
        "generated_at_utc": snapshot.get("generated_at_utc"),
        "week": (snapshot.get("league") or {}).get("current_week"),
        "players": {
            player_id: {
                "name": player.get("name"),
                "pos": player.get("pos"),
                "projection_pg": player.get("projection_pg"),
                "projection_state": player.get("projection_state"),
            }
            for player_id, player in (snapshot.get("players") or {}).items()
            if player.get("projection_pg") is not None
        },
    }
    path = HISTORY_DIR / f"{generated}.json"
    if not path.exists():
        _atomic_json(path, summary)


def _prior_projection(previous: dict[str, Any] | None, player_id: str) -> float | None:
    if not previous:
        return None
    return _finite(
        (((previous.get("players") or {}).get(player_id) or {}).get("projection_pg"))
    )


def build_snapshot(force: bool = False, quick: bool = False) -> dict[str, Any]:
    """Build the durable projection snapshot; no LLM and no betting action."""
    previous = None
    if SNAPSHOT_PATH.exists():
        try:
            previous = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = None

    engine = load_engine(quick=quick)
    problems = engine.selftest()
    if problems:
        raise RuntimeError(
            "Projection engine self-test failed: " + " | ".join(problems)
        )

    original_directory = Path.cwd()
    try:
        os.chdir(ROOT)
        board = engine.board_cached(force=force)
        weekly = engine.weekly_cached(force=force)
        pipeline = engine.build_weekly_projection_pipeline(
            weekly, board=board, force=force, use_market=False
        )
        rosters, users, player_db, picks, transactions = engine.league_cached()
    finally:
        os.chdir(original_directory)

    weekly_points = pipeline.get("final") or {}
    weekly_byes = pipeline.get("bye") or {}
    weekly_meta = pipeline.get("meta") or {}
    weekly_spread = pipeline.get("spread") or {}
    source_audit = pipeline.get("source_audit")
    current_week = max(1, int(engine.current_week(weekly)))
    end_week = int(CONFIG["season_end_week"])
    weeks = list(range(current_week, end_week + 1))

    # v6.3's ros_pg treats a completely absent weekly row as zero. We retain
    # it only when at least one remaining non-bye weekly observation exists.
    board = engine.attach_ros_values(
        board,
        weekly_points,
        weekly_byes,
        wk_spread=weekly_spread,
        source_audit=source_audit,
        weeks=weeks,
    )
    if "support" not in board:
        board = engine.support(board)
    board_index = board.set_index("key", drop=False)

    owner_by_player: dict[str, int] = {}
    for roster in rosters:
        for raw_id in roster.get("players") or []:
            owner_by_player[str(raw_id)] = int(roster["roster_id"])
    user_by_id = {
        str(user.get("user_id")): str(
            (user.get("metadata") or {}).get("team_name")
            or user.get("display_name")
            or "Manager"
        )
        for user in users
    }
    manager_by_roster = {
        int(roster["roster_id"]): user_by_id.get(
            str(roster.get("owner_id")), f"Roster {roster['roster_id']}"
        )
        for roster in rosters
    }

    player_rows: dict[str, dict[str, Any]] = {}
    for raw_id, raw_player in player_db.items():
        if not isinstance(raw_player, dict):
            continue
        player_id = str(raw_id)
        name = _display_name(raw_player, player_id)
        pos = str(
            raw_player.get("position") or ("DEF" if len(player_id) <= 4 else "")
        )
        key = engine.norm(name, pos) if pos in CORE_POSITIONS else ""
        board_row = None
        if key and key in board_index.index:
            board_row = board_index.loc[key]
            if getattr(board_row, "ndim", 1) > 1:
                board_row = board_row.iloc[0]

        def board_value(field: str) -> Any:
            if board_row is None or field not in board_row:
                return None
            return json_safe(board_row[field])

        remaining_observations = (
            [
                _finite((weekly_points.get(key) or {}).get(week))
                for week in weeks
                if week not in set(weekly_byes.get(key) or set())
            ]
            if key
            else []
        )
        has_weekly_evidence = bool(remaining_observations) and all(
            value is not None for value in remaining_observations
        )
        ros_value = (
            sum(remaining_observations) / len(remaining_observations)
            if has_weekly_evidence
            else None
        )
        season_value = _finite(board_value("value_pg"))
        projection = ros_value
        projection_state = (
            "remaining_week_ensemble"
            if ros_value is not None
            else "partial_weekly"
            if any(value is not None for value in remaining_observations)
            else "missing"
        )
        previous_projection = _prior_projection(previous, player_id)
        change = (
            round(projection - previous_projection, 4)
            if projection is not None and previous_projection is not None
            else None
        )
        if change is not None and abs(change) < 0.00005:
            change = 0.0
        meta = (weekly_meta.get(key) or {}) if key else {}
        player_rows[player_id] = {
            "pid": player_id,
            "key": key or None,
            "name": name,
            "pos": pos or None,
            "team": meta.get("team")
            or raw_player.get("team")
            or board_value("team"),
            "status": raw_player.get("status"),
            "injury_status": meta.get("inj") or raw_player.get("injury_status"),
            "injury_body_part": meta.get("body")
            or raw_player.get("injury_body_part"),
            "owner_roster_id": owner_by_player.get(player_id),
            "owner": manager_by_roster.get(owner_by_player.get(player_id)),
            "current_week": current_week,
            "projection_pg": round(projection, 4)
            if projection is not None
            else None,
            "projection_state": projection_state,
            "season_projection_pg": round(season_value, 4)
            if season_value is not None
            else None,
            "previous_projection_pg": previous_projection,
            "projection_change_pg": change,
            "source_projection_pg": _finite(board_value("proj_pg")),
            "source_spread_pg": _finite(board_value("spread_pg")),
            "support": board_value("ros_support") or board_value("support"),
            "support_reason": board_value("support_why"),
            "role_conflict_weeks": board_value("ros_role_conflicts"),
            "weekly_source_spread_pg": _finite(
                board_value("ros_weekly_spread")
            ),
            "weekly_points": {
                str(week): round(value, 4)
                for week in weeks
                if (
                    value := _finite(
                        (weekly_points.get(key) or {}).get(week)
                    )
                )
                is not None
            }
            if key
            else {},
            "weekly_points_by_source": {
                "sleeper_projection_feed": {
                    str(week): round(value, 4)
                    for week in weeks
                    if (value := _finite(((pipeline.get("rotowire") or {}).get(key) or {}).get(week))) is not None
                },
                "espn": {
                    str(week): round(value, 4)
                    for week in weeks
                    if (value := _finite(((pipeline.get("espn") or {}).get(week) or {}).get(key))) is not None
                },
            } if key else {},
            "weekly_states": {
                str(week): _weekly_state(
                    key, week, weekly_points, weekly_byes, weekly_meta
                )
                for week in weeks
            }
            if key
            else {},
            "bye_weeks": sorted(
                int(week)
                for week in set(weekly_byes.get(key) or set())
                if int(week) <= end_week
            )
            if key
            else [],
            "source_provenance": {
                "baseline": "Sleeper projection feed + ESPN weekly ensemble",
                "sleeper_published_at": meta.get("last_mod"),
                "market_in_baseline": False,
                "legacy_market_fields_ignored": True,
            },
        }
        player_rows[player_id].update(_ros_summary(player_rows[player_id], weeks))

    roster_rows = []
    for roster in rosters:
        roster_id = int(roster["roster_id"])
        roster_rows.append(
            {
                "roster_id": roster_id,
                "manager": manager_by_roster.get(
                    roster_id, f"Roster {roster_id}"
                ),
                "player_ids": [
                    str(value) for value in roster.get("players") or []
                ],
                "starter_ids": [
                    str(value) for value in roster.get("starters") or []
                ],
                "reserve_ids": [
                    str(value) for value in roster.get("reserve") or []
                ],
                "waiver_position": (roster.get("settings") or {}).get(
                    "waiver_position"
                ),
                "wins": (roster.get("settings") or {}).get("wins"),
                "losses": (roster.get("settings") or {}).get("losses"),
                "ties": (roster.get("settings") or {}).get("ties"),
            }
        )

    starter_slots = [
        "QB",
        "RB",
        "RB",
        "WR",
        "WR",
        "TE",
        "FLEX",
        "FLEX",
        "K",
        "DEF",
    ]
    core_slots = [slot for slot in starter_slots if slot not in {"K", "DEF"}]
    partial_snapshot = {
        "players": player_rows,
        "league": {"starter_slots": starter_slots},
    }
    rankings = []
    for roster in roster_rows:
        totals = []
        fallback_count = 0
        for week in weeks:
            result = optimize_lineup(
                roster["player_ids"],
                partial_snapshot,
                week,
                starter_slots=core_slots,
            )
            if result["feasible"] and result["projected_total"] is not None:
                totals.append(float(result["projected_total"]))
                fallback_count += int(result.get("fallback_count") or 0)
        strength = round(sum(totals) / len(totals), 3) if totals else None
        rankings.append(
            {
                "roster_id": roster["roster_id"],
                "manager": roster["manager"],
                "core_starter_pg": strength,
                "weeks_measured": len(totals),
                "fallback_assignments": fallback_count,
            }
        )
    rankings.sort(
        key=lambda row: row["core_starter_pg"]
        if row["core_starter_pg"] is not None
        else -math.inf,
        reverse=True,
    )
    for rank, row in enumerate(rankings, start=1):
        row["rank"] = rank

    snapshot = {
        "schema_version": 2,
        "generated_at_utc": iso_now(),
        "engine": {
            "version": "v6.3-projection-oracle",
            "selftest": "OK",
            "projection_only_mode": True,
            "autonomous_trade_search": False,
            "manual_news_overrides": False,
            "legacy_network_markets_disabled": True,
            "market_in_baseline": False,
            "season_player_count": int(len(board)),
            "projection_sources": [
                "Sleeper projection feed",
                "ESPN weekly projections",
            ],
            "source_cache_fetched_at_utc": {
                name: dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat(timespec="seconds")
                for name, path in {
                    "sleeper_projection_feed": ENGINE_CACHE_DIR / "weekly.pkl",
                    "espn": ENGINE_CACHE_DIR / "espn_weekly.pkl",
                }.items()
                if path.exists()
            },
        },
        "league": {
            "platform": "Sleeper",
            "league_id": LEAGUE_ID,
            "current_week": current_week,
            "my_roster_id": MY_ROSTER_ID,
            "starter_slots": starter_slots,
            "playoff_weeks": list(CONFIG["playoff_weeks"]),
            "season_end_week": end_week,
            "known_format_fallback": "12-team; full PPR; 4-point pass TD",
        },
        "players": player_rows,
        "rosters": roster_rows,
        "power_rankings": rankings,
        "draft_pick_count": len(picks),
        "transaction_count_at_snapshot": len(transactions),
    }
    if previous:
        _archive_summary(previous)
    _atomic_json(SNAPSHOT_PATH, snapshot)
    return snapshot


def load_snapshot() -> dict[str, Any]:
    if not SNAPSHOT_PATH.exists():
        raise FileNotFoundError("No advisor snapshot exists yet")
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    if int(snapshot.get("schema_version") or 0) != 2:
        raise ValueError("The saved snapshot uses an older schema and must be refreshed")
    league = snapshot.get("league") or {}
    weeks = list(range(int(league.get("current_week") or 1), int(league.get("season_end_week") or CONFIG["season_end_week"]) + 1))
    for player in (snapshot.get("players") or {}).values():
        player.update(_ros_summary(player, weeks))
    return snapshot


def snapshot_age_minutes(snapshot: dict[str, Any]) -> float:
    generated = dt.datetime.fromisoformat(str(snapshot["generated_at_utc"]))
    return max(0.0, (utc_now() - generated).total_seconds() / 60)


def ensure_snapshot(
    no_refresh: bool = False, quick: bool = False
) -> dict[str, Any]:
    try:
        snapshot = load_snapshot()
    except (FileNotFoundError, ValueError):
        return build_snapshot(force=False, quick=quick)
    ttl = float(CONFIG["snapshot_ttl_minutes"])
    if not no_refresh and snapshot_age_minutes(snapshot) > ttl:
        try:
            return build_snapshot(force=False, quick=quick)
        except Exception as exc:
            snapshot.setdefault("runtime_warnings", []).append(
                "Projection refresh failed; using saved snapshot: "
                + type(exc).__name__
            )
    return snapshot


def _player_universe(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        player
        for player in (snapshot.get("players") or {}).values()
        if player.get("pos") in ALL_POSITIONS
        and (player.get("team") or player.get("owner_roster_id") is not None)
    ]


def match_players(
    question: str, snapshot: dict[str, Any], limit: int = 12
) -> list[dict[str, Any]]:
    """Resolve exact identities without the Tee/Jayden Higgins bug.

    Exact normalized full names and vetted aliases run first. A one-word name
    is accepted only if it uniquely identifies one active player across the
    universe. Consumed full-name spans are never reused as surnames.
    """
    normalized_question = normalize_text(question)
    padded = f" {normalized_question} "
    players = _player_universe(snapshot)
    ordered: list[tuple[int, dict[str, Any]]] = []
    seen: set[str] = set()
    occupied: list[tuple[int, int]] = []

    for player in sorted(
        players,
        key=lambda row: len(normalize_text(row.get("name") or "")),
        reverse=True,
    ):
        full = normalize_text(player.get("name") or "")
        if not full:
            continue
        pattern = re.compile(
            rf"(?<![a-z0-9]){re.escape(full)}(?![a-z0-9])"
        )
        for match in pattern.finditer(normalized_question):
            player_id = str(player["pid"])
            if player_id not in seen:
                ordered.append((match.start(), player))
                seen.add(player_id)
                occupied.append((match.start(), match.end()))
            break

    by_full = {
        normalize_text(player.get("name") or ""): player for player in players
    }
    for alias, canonical in ALIASES.items():
        marker = f" {normalize_text(alias)} "
        target = by_full.get(normalize_text(canonical))
        if marker in padded and target and str(target["pid"]) not in seen:
            position = padded.index(marker)
            ordered.append((position, target))
            seen.add(str(target["pid"]))

    surname_index: dict[str, list[dict[str, Any]]] = {}
    for player in players:
        words = normalize_text(player.get("name") or "").split()
        if words and len(words[-1]) >= 4:
            surname_index.setdefault(words[-1], []).append(player)
    for token, candidates in surname_index.items():
        if len(candidates) != 1:
            continue
        pattern = re.compile(
            rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])"
        )
        for match in pattern.finditer(normalized_question):
            if any(
                start <= match.start() and match.end() <= end
                for start, end in occupied
            ):
                continue
            player = candidates[0]
            if str(player["pid"]) not in seen:
                ordered.append((match.start(), player))
                seen.add(str(player["pid"]))
            break

    ordered.sort(key=lambda item: item[0])
    return [player for _, player in ordered[:limit]]


def classify_intent(question: str) -> str:
    text = normalize_text(question)
    if any(
        phrase in text
        for phrase in (
            "recent trade",
            "completed trade",
            "trade in sleeper",
            "league chat",
            "who won the trade",
            "latest transaction",
        )
    ):
        return "recent_transactions"
    if any(
        phrase in text
        for phrase in (
            "biggest projection",
            "projection mover",
            "risers and fallers",
            "risers",
            "fallers",
            "increases",
            "decreases",
        )
    ):
        return "projection_movers"
    if any(
        phrase in text
        for phrase in (
            "rank the league",
            "rank every team",
            "power ranking",
            "league rankings",
        )
    ):
        return "league_rankings"
    if any(
        phrase in text
        for phrase in (
            "trade target",
            "buy low",
            "sell high",
            "construct a trade",
            "find a trade",
        )
    ):
        return "trade_targets"
    if (
        ("analyze" in text or "analyse" in text)
        and ("team" in text or "manager" in text)
    ) or any(
        phrase in text
        for phrase in (
            "analyze team",
            "analyse team",
            "analyze this manager",
            "improve their team",
            "compare teams",
            "team comparison",
        )
    ):
        return "team_analysis"
    if any(word in text.split() for word in ("trade", "offer")) or any(
        phrase in text
        for phrase in (
            "send for",
            "give for",
            "receive for",
            "accept this",
        )
    ):
        return "explicit_trade"
    if any(
        phrase in text
        for phrase in (
            "waiver",
            "free agent",
            "pick up",
            "add ",
            "stream a defense",
            "stream defense",
            "stream kicker",
            "who is available",
            "best stash",
        )
    ):
        return "waiver"
    if "lineup" in text or "projected starters" in text:
        return "lineup"
    if any(
        phrase in f" {text} "
        for phrase in (" compare ", " versus ", " vs ", " outlook ", " better ros ")
    ):
        return "comparison"
    return "general"


def _eligible(position: str | None, slot: str) -> bool:
    position = str(position or "").upper()
    slot = str(slot).upper()
    if slot in ALL_POSITIONS:
        return position == slot
    if slot in {"FLEX", "W/R/T", "WRRB_FLEX"}:
        return position in {"RB", "WR", "TE"}
    if slot in {"SUPER_FLEX", "SUPERFLEX", "Q/W/R/T"}:
        return position in CORE_POSITIONS
    if slot == "REC_FLEX":
        return position in {"WR", "TE"}
    return False


def optimize_lineup(
    player_ids: list[str],
    snapshot: dict[str, Any],
    week: int,
    starter_slots: list[str] | None = None,
) -> dict[str, Any]:
    """Return exact legal slot assignments, including K and D/ST.

    Unknown is not zero. Unknown projections are used only when necessary to
    fill a legal slot, and make projected_total null while preserving the
    known subtotal.
    """
    players_by_id = snapshot.get("players") or {}
    slots = list(
        starter_slots
        or (snapshot.get("league") or {}).get("starter_slots")
        or []
    )
    candidates = []
    for raw_id in player_ids:
        player_id = str(raw_id)
        player = players_by_id.get(player_id)
        if not player or player.get("pos") not in ALL_POSITIONS:
            continue
        points, source = _projection_for_week(player, int(week))
        candidates.append(
            {
                "player_id": player_id,
                "name": player.get("name") or player_id,
                "position": player.get("pos"),
                "team": player.get("team"),
                "points": points,
                "projection_source": source,
            }
        )

    # Restrictive slots first prevents FLEX from consuming a required RB/WR/TE.
    eligible_indices = {
        slot: tuple(index for index, player in enumerate(candidates) if _eligible(player["position"], slot))
        for slot in slots
    }
    order = sorted(
        range(len(slots)),
        key=lambda index: len(eligible_indices[slots[index]]),
    )

    @lru_cache(maxsize=None)
    def solve(
        depth: int, used_mask: int
    ) -> tuple[float, tuple[int, ...]] | None:
        if depth == len(order):
            return 0.0, ()
        slot = slots[order[depth]]
        best: tuple[float, tuple[int, ...]] | None = None
        for index in eligible_indices[slot]:
            if used_mask & (1 << index):
                continue
            player = candidates[index]
            score = (
                float(player["points"])
                if player["points"] is not None
                else -1_000_000.0
            )
            tail = solve(depth + 1, used_mask | (1 << index))
            if tail is None:
                continue
            candidate = (score + tail[0], (index,) + tail[1])
            if best is None or candidate[0] > best[0]:
                best = candidate
        return best

    solution = solve(0, 0)
    if solution is None:
        missing = [
            slot
            for slot in slots
            if not any(
                _eligible(player["position"], slot) for player in candidates
            )
        ]
        return {
            "week": int(week),
            "feasible": False,
            "starter_slots": slots,
            "assignments": [],
            "missing_slots": missing or ["insufficient eligible players"],
            "projected_total": None,
            "known_subtotal": 0.0,
            "fallback_count": 0,
        }

    selected_by_slot: dict[int, dict[str, Any]] = {}
    for depth, candidate_index in enumerate(solution[1]):
        selected_by_slot[order[depth]] = candidates[candidate_index]
    assignments = [
        {"slot": slot, **selected_by_slot[slot_index]}
        for slot_index, slot in enumerate(slots)
    ]
    known = [
        float(row["points"])
        for row in assignments
        if row["points"] is not None
    ]
    unknown = [
        row["name"] for row in assignments if row["points"] is None
    ]
    return {
        "week": int(week),
        "feasible": True,
        "starter_slots": slots,
        "assignments": assignments,
        "starters": assignments,
        "missing_slots": [],
        "projected_total": round(sum(known), 3) if not unknown else None,
        "known_subtotal": round(sum(known), 3),
        "unknown_projection_players": unknown,
        "fallback_count": sum(
            row["projection_source"] == "season_fallback"
            for row in assignments
        ),
    }


def _baseline_quality_note(player: dict[str, Any]) -> str:
    """Translate source diagnostics into plain, decision-useful language."""
    projection = _finite(player.get("projection_pg"))
    status = normalize_text(
        str(player.get("injury_status") or player.get("status") or "")
    ).upper()
    if projection is None:
        return "No usable rest-of-season projection is available."
    if projection == 0.0 and status in HARD_INACTIVE:
        return (
            f"The current baseline assigns zero while the player is {status}; "
            "verify any return-timeline change before valuing the player."
        )
    weekly_spread = _finite(player.get("weekly_source_spread_pg"))
    season_spread = _finite(player.get("source_spread_pg"))
    messages = []
    if weekly_spread is not None and weekly_spread >= 2.0:
        messages.append(
            f"weekly baseline sources differ by about {weekly_spread:.1f} points"
        )
    if season_spread is not None and season_spread >= 1.0:
        messages.append(
            f"season baseline sources differ by about {season_spread:.1f} points per game"
        )
    if player.get("projection_state") == "season_fallback":
        messages.append("rest-of-season value uses a season fallback")
    if not messages:
        return "Available baseline sources are reasonably aligned."
    return "; ".join(messages).capitalize() + "."


def _compact_player(
    player: dict[str, Any], week: int, detailed: bool = True
) -> dict[str, Any]:
    points, point_source = _projection_for_week(player, week)
    base = {
        "player_id": str(player.get("pid")),
        "name": player.get("name"),
        "position": player.get("pos"),
        "team": player.get("team"),
        "owner_roster_id": player.get("owner_roster_id"),
        "owner": player.get("owner") or "FREE AGENT",
        "status": player.get("injury_status") or player.get("status"),
        "week_projection": points,
        "week_projection_source": point_source,
        "weekly_projection": {str(week): points},
        "ros_projection_pg": player.get("projection_pg"),
        "engine_value_pg": player.get("projection_pg"),
        "projection_state": player.get("projection_state"),
        "projection_horizon": player.get("projection_horizon"),
    }
    if detailed:
        base.update(
            {
                "injury_body_part": player.get("injury_body_part"),
                "season_projection_pg": player.get(
                    "season_projection_pg"
                ),
                "previous_projection_pg": player.get(
                    "previous_projection_pg"
                ),
                "projection_change_pg": player.get(
                    "projection_change_pg"
                ),
                "source_spread_pg": player.get("source_spread_pg"),
                "weekly_source_spread_pg": player.get(
                    "weekly_source_spread_pg"
                ),
                "baseline_quality_note": _baseline_quality_note(player),
                "role_conflict_weeks": player.get("role_conflict_weeks"),
                "bye_weeks": player.get("bye_weeks"),
            }
        )
    return base


def _sync_live(
    snapshot: dict[str, Any], live: dict[str, Any] | None
) -> dict[str, Any]:
    if not live:
        return snapshot
    synced = dict(snapshot)
    synced["runtime_warnings"] = list(dict.fromkeys(list(snapshot.get("runtime_warnings") or []) + list(live.get("runtime_warnings") or [])))
    synced["league"] = dict(snapshot.get("league") or {})
    synced["league"].update(
        {
            "current_week": live.get(
                "week", synced["league"].get("current_week")
            ),
            "season": live.get("season"),
            "league_name": live.get("league_name"),
            "total_rosters": live.get("total_rosters"),
            "starter_slots": live.get("starter_slots")
            or synced["league"].get("starter_slots"),
            "roster_positions": live.get("roster_positions"),
            "scoring_settings": live.get("scoring_settings"),
            "league_settings": live.get("league_settings"),
            "current_matchup": live.get("current_matchup"),
            "live_refreshed_at_utc": live.get("refreshed_at_utc"),
        }
    )
    owner_map = {
        str(key): int(value)
        for key, value in (live.get("owner_by_player") or {}).items()
    }
    manager_map = {
        int(row["roster_id"]): row.get("manager")
        for row in live.get("rosters") or []
    }
    projection_map = live.get("projection_by_player") or {}
    metadata_map = live.get("player_metadata_by_id") or {}
    synced_players = {}
    for player_id, player in (snapshot.get("players") or {}).items():
        cell = dict(player)
        metadata = metadata_map.get(str(player_id)) or {}
        for field in ("injury_status", "injury_body_part", "status", "team", "game_date", "opponent"):
            if field in metadata:
                cell[field] = metadata[field]
        owner_id = owner_map.get(str(player_id))
        cell["owner_roster_id"] = owner_id
        cell["owner"] = manager_map.get(owner_id)
        cell["current_week"] = int(
            live.get("week") or cell.get("current_week") or 1
        )
        live_projection = projection_map.get(str(player_id))
        if isinstance(live_projection, dict):
            for field in ("game_date", "opponent"):
                if live_projection.get(field) is not None:
                    cell[field] = live_projection[field]
        if (
            isinstance(live_projection, dict)
            and _finite(live_projection.get("points")) is not None
        ):
            cell["live_week_projection"] = round(
                float(live_projection["points"]), 4
            )
            cell["live_projection_stats"] = dict(
                live_projection.get("stats") or {}
            )
            cell["live_projection_updated_at"] = (
                live_projection.get("last_modified")
            )
            cell["weekly_points"] = dict(cell.get("weekly_points") or {})
            week_key = str(cell["current_week"])
            source_maps = {
                name: dict(values)
                for name, values in (cell.get("weekly_points_by_source") or {}).items()
            }
            if source_maps:
                source_maps.setdefault("sleeper_projection_feed", {})[week_key] = cell["live_week_projection"]
                cell["weekly_points_by_source"] = source_maps
                espn_points = _finite((source_maps.get("espn") or {}).get(week_key))
                cell["weekly_points"][week_key] = round(
                    (cell["live_week_projection"] + espn_points) / 2.0
                    if espn_points is not None else cell["live_week_projection"], 4
                )
            elif _finite(cell["weekly_points"].get(week_key)) is None:
                # Old snapshots lack source components. Preserve a known
                # ensemble instead of silently replacing it with one display feed.
                cell["weekly_points"][week_key] = cell["live_week_projection"]
        synced_players[str(player_id)] = cell
    synced["players"] = synced_players
    synced["live_source_provenance"] = live.get("source_provenance") or {}
    roster_provenance = (live.get("source_provenance") or {}).get("rosters") or {}
    if roster_provenance.get("fetched_at_utc"):
        synced["league"]["live_refreshed_at_utc"] = roster_provenance["fetched_at_utc"]
    synced["rosters"] = [
        {
            **row,
            "player_ids": [
                str(value) for value in row.get("player_ids") or []
            ],
            "starter_ids": [
                str(value) for value in row.get("starter_ids") or []
            ],
            "reserve_ids": [
                str(value) for value in row.get("reserve_ids") or []
            ],
        }
        for row in live.get("rosters")
        or snapshot.get("rosters")
        or []
    ]
    return synced


def _find_player_by_name(
    snapshot: dict[str, Any], requested: str
) -> dict[str, Any]:
    normalized = normalize_text(requested)
    exact = [
        player
        for player in _player_universe(snapshot)
        if normalize_text(player.get("name") or "") == normalized
    ]
    if len(exact) == 1:
        return exact[0]
    alias = ALIASES.get(normalized)
    if alias:
        exact = [
            player
            for player in _player_universe(snapshot)
            if normalize_text(player.get("name") or "")
            == normalize_text(alias)
        ]
        if len(exact) == 1:
            return exact[0]
    matches = match_players(requested, snapshot, limit=8)
    if len(matches) == 1:
        return matches[0]
    choices = (
        ", ".join(player.get("name") or "?" for player in matches) or "none"
    )
    raise ValueError(
        f"Could not uniquely resolve '{requested}'. Matches: {choices}"
    )


def resolve_explicit_trade(
    snapshot: dict[str, Any],
    give_names: Iterable[str],
    get_names: Iterable[str],
    manager: str | None = None,
    perspective_manager: str | None = None,
    perspective_roster_id: int | None = None,
) -> dict[str, Any]:
    if perspective_manager and perspective_roster_id is not None:
        raise ValueError(
            "Choose either a perspective manager or perspective roster ID, not both"
        )
    rosters = snapshot.get("rosters") or []
    if perspective_manager:
        perspective_rows = [
            row
            for row in rosters
            if normalize_text(row.get("manager") or "")
            == normalize_text(perspective_manager)
        ]
        if len(perspective_rows) != 1:
            raise ValueError(
                f"Could not uniquely resolve perspective manager '{perspective_manager}'"
            )
        perspective_rid = int(perspective_rows[0]["roster_id"])
    elif perspective_roster_id is not None:
        perspective_rid = int(perspective_roster_id)
        if not any(
            int(row["roster_id"]) == perspective_rid for row in rosters
        ):
            raise ValueError(
                f"Perspective roster {perspective_rid} is not in this live league"
            )
    else:
        perspective_rid = MY_ROSTER_ID

    give = [_find_player_by_name(snapshot, name) for name in give_names]
    receive = [_find_player_by_name(snapshot, name) for name in get_names]
    if not give or not receive:
        raise ValueError(
            "A trade must contain at least one player on each side"
        )
    if any(
        int(player.get("owner_roster_id") or -1) != perspective_rid
        for player in give
    ):
        raise ValueError(
            "Every outgoing player must be on the selected perspective "
            "roster in live Sleeper"
        )
    incoming_owners = {
        player.get("owner_roster_id") for player in receive
    }
    if None in incoming_owners:
        raise ValueError(
            "A requested incoming player is a free agent, not a trade target"
        )
    if manager:
        manager_rows = [
            row
            for row in snapshot.get("rosters") or []
            if normalize_text(row.get("manager") or "")
            == normalize_text(manager)
        ]
        if len(manager_rows) != 1:
            raise ValueError(
                f"Could not uniquely resolve manager '{manager}'"
            )
        if incoming_owners != {int(manager_rows[0]["roster_id"])}:
            raise ValueError(
                "The named manager does not own every incoming player"
            )
    if len(incoming_owners) != 1:
        raise ValueError(
            "All incoming players must belong to one manager"
        )
    other_rid = int(next(iter(incoming_owners)))
    if other_rid == perspective_rid:
        raise ValueError("Both sides of a trade cannot be the same roster")
    manager_by_roster = {
        int(row["roster_id"]): row.get("manager") for row in rosters
    }
    return {
        "give_ids": [str(player["pid"]) for player in give],
        "get_ids": [str(player["pid"]) for player in receive],
        "give": [str(player["name"]) for player in give],
        "get": [str(player["name"]) for player in receive],
        "perspective_rid": perspective_rid,
        "perspective_manager": manager_by_roster.get(perspective_rid),
        "other_rid": other_rid,
        "other_manager": manager_by_roster.get(other_rid),
        "terms_explicit": True,
    }


def _roster_average(
    player_ids: list[str],
    snapshot: dict[str, Any],
    weeks: list[int],
    slots: list[str],
) -> tuple[float | None, list[dict[str, Any]]]:
    results = [
        optimize_lineup(player_ids, snapshot, week, slots)
        for week in weeks
    ]
    totals = [
        float(row["projected_total"])
        for row in results
        if row["projected_total"] is not None
    ]
    average = (
        round(sum(totals) / len(totals), 4)
        if len(totals) == len(weeks) and totals
        else None
    )
    return average, results


def _legalize_roster(
    player_ids: list[str],
    roster: dict[str, Any],
    snapshot: dict[str, Any],
    weeks: list[int],
    slots: list[str],
) -> tuple[list[str], list[str]]:
    current = list(dict.fromkeys(str(player_id) for player_id in player_ids))
    league = snapshot.get("league") or {}
    settings = league.get("league_settings") or {}
    roster_positions = [
        str(slot).upper()
        for slot in league.get("roster_positions") or []
    ]
    active_cap = len(
        [slot for slot in roster_positions if slot not in {"IR", "TAXI"}]
    )
    if active_cap <= 0:
        active_cap = max(
            0,
            len(roster.get("player_ids") or [])
            - len(roster.get("reserve_ids") or []),
        )

    configured_reserve_slots = settings.get("reserve_slots")
    if configured_reserve_slots is None:
        reserve_cap = roster_positions.count("IR")
    else:
        reserve_cap = max(0, int(configured_reserve_slots or 0))

    existing_reserve = [
        str(player_id)
        for player_id in roster.get("reserve_ids") or []
        if str(player_id) in current
    ]
    reserve_ids = list(dict.fromkeys(existing_reserve))

    def reserve_eligible(player_id: str) -> bool:
        player = (snapshot.get("players") or {}).get(player_id) or {}
        status = normalize_text(
            str(player.get("injury_status") or player.get("status") or "")
        ).upper()
        if status in {"IR", "INJURED RESERVE", "PUP"}:
            return True
        flag_by_status = {
            "OUT": "reserve_allow_out",
            "DOUBTFUL": "reserve_allow_doubtful",
            "NA": "reserve_allow_na",
            "SUSPENDED": "reserve_allow_sus",
            "DNR": "reserve_allow_dnr",
            "COVID": "reserve_allow_cov",
        }
        flag = flag_by_status.get(status)
        return bool(flag and int(settings.get(flag) or 0))

    open_reserve = max(0, reserve_cap - len(reserve_ids))
    if open_reserve:
        eligible = [
            player_id
            for player_id in current
            if player_id not in reserve_ids and reserve_eligible(player_id)
        ]
        reserve_ids.extend(sorted(eligible)[:open_reserve])

    active = [
        player_id for player_id in current if player_id not in set(reserve_ids)
    ]
    dropped: list[str] = []
    while len(active) > active_cap:
        candidates = []
        for player_id in active:
            player = (snapshot.get("players") or {}).get(player_id) or {}
            if player.get("pos") not in CORE_POSITIONS:
                continue
            trial = [value for value in current if value != player_id]
            average, _ = _roster_average(
                trial, snapshot, weeks, slots
            )
            drop_value = _finite(player.get("projection_pg"))
            if drop_value is None:
                weekly_values = [
                    value
                    for raw in (player.get("weekly_points") or {}).values()
                    if (value := _finite(raw)) is not None
                ]
                drop_value = (
                    sum(weekly_values) / len(weekly_values)
                    if weekly_values
                    else -math.inf
                )
            candidates.append(
                (
                    average,
                    drop_value,
                    player_id,
                    player.get("name") or player_id,
                )
            )
        if not candidates:
            raise ValueError(
                "Roster is over the active-player limit, but no modeled "
                "skill-position player can be evaluated as a forced drop"
            )
        complete = [row for row in candidates if row[0] is not None]
        if complete:
            best_average = max(float(row[0]) for row in complete)
            tied = [
                row
                for row in complete
                if abs(float(row[0]) - best_average) < 1e-9
            ]
            # Equal lineup outcomes must never break toward the premium asset.
            # The lower independent ROS value is the safer forced drop.
            _, _, remove_id, _ = min(
                tied, key=lambda row: (row[1], row[3], row[2])
            )
        else:
            # If every trial lineup is incomplete, do not let player-id order
            # pick the cut. Preserve the highest-value asset deterministically.
            _, _, remove_id, _ = min(
                candidates, key=lambda row: (row[1], row[3], row[2])
            )
        current.remove(remove_id)
        active.remove(remove_id)
        dropped.append(remove_id)
    return current, dropped


def trade_horizon(snapshot: dict[str, Any], terms: dict[str, Any]) -> dict[str, Any]:
    """Trade benefits start only in an unstarted, usable scoring period."""
    league = snapshot.get("league") or {}
    week = int(league.get("current_week") or 1)
    if terms.get("effective_week") is not None:
        requested = int(terms["effective_week"])
        if requested < week:
            raise ValueError("A trade cannot become effective in a completed week")
        if requested > week:
            return {"effective_week": requested, "timing_basis": "explicit future effective week"}
    involved = {int(terms.get("perspective_rid", MY_ROSTER_ID)), int(terms["other_rid"])}
    players = snapshot.get("players") or {}
    ids = {str(pid) for row in snapshot.get("rosters") or [] if int(row["roster_id"]) in involved for pid in row.get("player_ids") or []}
    dates = [_timestamp((players.get(pid) or {}).get("game_date")) for pid in ids
             if (players.get(pid) or {}).get("pos") in CORE_POSITIONS
             and week not in set((players.get(pid) or {}).get("bye_weeks") or [])]
    settings = league.get("league_settings") or {}
    review_delay = int(settings.get("trade_review_days") or 0)
    cutoff = utc_now() + dt.timedelta(days=review_delay)
    verified_future = bool(dates) and all(date is not None and date > cutoff for date in dates)
    return {"effective_week": week if verified_future else week + 1,
            "timing_basis": "all relevant games start after the review period" if verified_future else "next-week assumption: game timing started, unknown, or within review period"}


def _trade_validation(snapshot: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    freshness = evidence_freshness(snapshot)
    reasons = []
    if freshness["rosters"]["status"] != "fresh":
        reasons.append("ownership_not_fresh")
    if not freshness["all_projection_sources_fresh"]:
        reasons.append("projection_sources_stale_or_unverified")
    mine = _finite(result.get("perspective_delta_pg"))
    theirs = _finite(result.get("counterparty_delta_pg"))
    if mine is None or theirs is None:
        reasons.append("incomplete_lineup_math")
    if mine is not None and mine <= 0:
        reasons.append("no_projected_upgrade")
    if theirs is not None and theirs < 0:
        reasons.append("counterparty_projected_loss")
    checks = result.get("independent_projection_checks") or {}
    complete = [row for row in checks.values() if _finite(row.get("perspective_delta_pg")) is not None and _finite(row.get("counterparty_delta_pg")) is not None]
    if len(complete) < 2:
        reasons.append("fewer_than_two_complete_projection_sources")
    elif any(float(row["perspective_delta_pg"]) <= 0 or float(row["counterparty_delta_pg"]) < 0 for row in complete):
        reasons.append("source_disagreement_or_counterparty_loss")
    # A positive lineup delta does not establish market price or acceptance.
    edge_supported = not reasons
    reasons.append("recent_format_matched_trade_value_evidence_required")
    return {"actionable": False, "projection_edge_supported": edge_supported,
            "status": "exploratory", "reason_codes": reasons,
            "acceptance_probability": None,
            "instruction": "Do not call this fair, a winning actionable offer, or likely accepted until the evidence gaps are resolved. Team fit alone cannot establish trade value."}


def evaluate_trade(
    snapshot: dict[str, Any], terms: dict[str, Any], *, source_checks: bool = True
) -> dict[str, Any]:
    if not terms.get("terms_explicit"):
        raise ValueError("Trade math requires explicit, resolved terms")
    rosters = {
        int(row["roster_id"]): row
        for row in snapshot.get("rosters") or []
    }
    perspective_rid = int(
        terms.get("perspective_rid", MY_ROSTER_ID)
    )
    mine = rosters.get(perspective_rid)
    other = rosters.get(int(terms["other_rid"]))
    if not mine or not other:
        raise ValueError(
            "One side of the trade is missing from live Sleeper rosters"
        )
    give_ids = [str(value) for value in terms["give_ids"]]
    get_ids = [str(value) for value in terms["get_ids"]]
    if not set(give_ids).issubset(set(mine.get("player_ids") or [])):
        raise ValueError(
            "Outgoing ownership changed on the perspective roster; "
            "refresh live Sleeper state"
        )
    if not set(get_ids).issubset(set(other.get("player_ids") or [])):
        raise ValueError(
            "Incoming ownership changed; refresh the live roster"
        )

    week = int(
        (snapshot.get("league") or {}).get("current_week") or 1
    )
    end_week = int(
        (snapshot.get("league") or {}).get("season_end_week")
        or CONFIG["season_end_week"]
    )
    effective_week = max(week, int(terms.get("effective_week") or week))
    weeks = list(range(effective_week, end_week + 1))
    slots = [
        slot
        for slot in (snapshot.get("league") or {}).get("starter_slots")
        or []
        if slot not in BENCH_SLOTS
    ]
    # K/DST are unchanged by ordinary skill-player offers and often lack a ROS
    # projection. They cancel out, but remain explicitly disclosed.
    math_slots = [slot for slot in slots if slot not in {"K", "DEF"}]
    mine_before_ids = [
        str(value) for value in mine.get("player_ids") or []
    ]
    other_before_ids = [
        str(value) for value in other.get("player_ids") or []
    ]
    mine_after = [
        value for value in mine_before_ids if value not in give_ids
    ] + get_ids
    other_after = [
        value for value in other_before_ids if value not in get_ids
    ] + give_ids
    mine_after, mine_drops = _legalize_roster(
        mine_after, mine, snapshot, weeks, math_slots
    )
    other_after, other_drops = _legalize_roster(
        other_after, other, snapshot, weeks, math_slots
    )
    mine_before, mine_before_weekly = _roster_average(
        mine_before_ids, snapshot, weeks, math_slots
    )
    mine_after_value, mine_after_weekly = _roster_average(
        mine_after, snapshot, weeks, math_slots
    )
    other_before, _ = _roster_average(
        other_before_ids, snapshot, weeks, math_slots
    )
    other_after_value, _ = _roster_average(
        other_after, snapshot, weeks, math_slots
    )

    def delta(
        after: float | None, before: float | None
    ) -> float | None:
        return (
            round(after - before, 4)
            if after is not None and before is not None
            else None
        )

    playoff_weeks = [
        int(value)
        for value in (snapshot.get("league") or {}).get("playoff_weeks")
        or []
        if effective_week <= int(value) <= end_week
    ]
    if playoff_weeks:
        mine_playoff_before, _ = _roster_average(
            mine_before_ids, snapshot, playoff_weeks, math_slots
        )
        mine_playoff_after, _ = _roster_average(
            mine_after, snapshot, playoff_weeks, math_slots
        )
    else:
        mine_playoff_before = mine_playoff_after = None
    players = snapshot.get("players") or {}
    result = {
        "basis": (
            "mean of each week's best legal skill-position lineup; "
            "byes score zero and missing projections remain unavailable"
        ),
        "weeks": weeks,
        "effective_week": effective_week,
        "timing_basis": terms.get("timing_basis", "explicit arithmetic scenario; no execution timing verified"),
        "slots_compared": math_slots,
        "unchanged_slots_excluded": [
            slot for slot in slots if slot not in math_slots
        ],
        "give": terms["give"],
        "get": terms["get"],
        "perspective_roster_id": perspective_rid,
        "perspective_manager": mine.get("manager"),
        "counterparty_roster_id": int(terms["other_rid"]),
        "counterparty_manager": other.get("manager"),
        "perspective_before_pg": mine_before,
        "perspective_after_pg": mine_after_value,
        "perspective_delta_pg": delta(mine_after_value, mine_before),
        "counterparty_before_pg": other_before,
        "counterparty_after_pg": other_after_value,
        "counterparty_delta_pg": delta(other_after_value, other_before),
        "perspective_playoff_delta_pg": delta(
            mine_playoff_after, mine_playoff_before
        ),
        "perspective_forced_drops": [
            (players.get(player_id) or {}).get("name") or player_id
            for player_id in mine_drops
        ],
        "counterparty_forced_drops": [
            (players.get(player_id) or {}).get("name") or player_id
            for player_id in other_drops
        ],
        "perspective_weekly_lineup_changes": [
            {
                "week": before["week"],
                "before": before["projected_total"],
                "after": after["projected_total"],
                "delta": delta(after["projected_total"], before["projected_total"]),
                "added_starters": [
                    row["name"] for row in after.get("assignments", [])
                    if row["player_id"] not in {p["player_id"] for p in before.get("assignments", [])}
                ],
                "removed_starters": [
                    row["name"] for row in before.get("assignments", [])
                    if row["player_id"] not in {p["player_id"] for p in after.get("assignments", [])}
                ],
            }
            for before, after in zip(mine_before_weekly, mine_after_weekly)
        ],
        "my_before_pg": mine_before,
        "my_after_pg": mine_after_value,
        "my_delta_pg": delta(mine_after_value, mine_before),
        "their_before_pg": other_before,
        "their_after_pg": other_after_value,
        "their_delta_pg": delta(other_after_value, other_before),
        "my_playoff_delta_pg": delta(
            mine_playoff_after, mine_playoff_before
        ),
        "my_forced_drops": [
            (players.get(player_id) or {}).get("name") or player_id
            for player_id in mine_drops
        ],
        "their_forced_drops": [
            (players.get(player_id) or {}).get("name") or player_id
            for player_id in other_drops
        ],
        "noise_warning": (
            "Small deltas are not proof; projection and role uncertainty "
            "can dominate them."
        ),
    }
    # Keep the established own-team field names for existing consumers, but
    # mark them as aliases only when roster 9 is actually the perspective.
    if perspective_rid != MY_ROSTER_ID:
        for key in (
            "my_before_pg",
            "my_after_pg",
            "my_delta_pg",
            "their_before_pg",
            "their_after_pg",
            "their_delta_pg",
            "my_playoff_delta_pg",
            "my_forced_drops",
            "their_forced_drops",
        ):
            result.pop(key, None)
    if source_checks:
        result["independent_projection_checks"] = {}
        source_names = sorted({
            source
            for player in players.values()
            for source in (player.get("weekly_points_by_source") or {})
        })
        for source in source_names:
            single_source = dict(snapshot)
            single_source["players"] = {
                pid: {
                    **player,
                    "weekly_points": dict((player.get("weekly_points_by_source") or {}).get(source) or {}),
                }
                for pid, player in players.items()
            }
            check = evaluate_trade(single_source, terms, source_checks=False)
            result["independent_projection_checks"][source] = {
                field: check[field] for field in (
                    "perspective_delta_pg", "counterparty_delta_pg",
                    "perspective_playoff_delta_pg", "perspective_forced_drops",
                    "counterparty_forced_drops",
                )
            }
        result["trade_validation"] = _trade_validation(snapshot, result)
    return result


def projection_movers(
    snapshot: dict[str, Any], limit: int = 20
) -> list[dict[str, Any]]:
    rows = []
    for player in _player_universe(snapshot):
        current = _finite(player.get("projection_pg"))
        previous = _finite(player.get("previous_projection_pg"))
        change = _finite(player.get("projection_change_pg"))
        if change is None and current is not None and previous is not None:
            change = current - previous
        if (
            current is None
            or previous is None
            or change is None
            or abs(change) < 1e-9
        ):
            continue
        rows.append(
            {
                "player_id": str(player.get("pid")),
                "name": player.get("name"),
                "position": player.get("pos"),
                "team": player.get("team"),
                "owner": player.get("owner") or "FREE AGENT",
                "previous_pg": round(previous, 4),
                "current_pg": round(current, 4),
                "delta_pg": round(change, 4),
            }
        )
    rows.sort(
        key=lambda row: (
            abs(float(row["delta_pg"])),
            float(row["delta_pg"]),
        ),
        reverse=True,
    )
    return rows[:limit]


def _available(
    snapshot: dict[str, Any],
    week: int,
    positions: set[str] | None = None,
    per_position: int = 6,
) -> list[dict[str, Any]]:
    wanted = positions or ALL_POSITIONS
    grouped: dict[str, list[dict[str, Any]]] = {
        position: [] for position in wanted
    }
    for player in _player_universe(snapshot):
        if (
            player.get("owner_roster_id") is not None
            or player.get("pos") not in wanted
        ):
            continue
        compact = _compact_player(player, week, detailed=False)
        value = _finite(compact.get("week_projection"))
        if value is None:
            value = _finite(compact.get("ros_projection_pg"))
        compact["sort_value"] = value
        grouped[str(player["pos"])].append(compact)
    out = []
    for position in sorted(grouped):
        rows = grouped[position]
        rows.sort(
            key=lambda row: row["sort_value"]
            if row["sort_value"] is not None
            else -math.inf,
            reverse=True,
        )
        for row in rows[:per_position]:
            row.pop("sort_value", None)
            out.append(row)
    return out


def _manager_matches(
    question: str, snapshot: dict[str, Any]
) -> list[dict[str, Any]]:
    text = normalize_text(question)
    matches = []
    for roster in snapshot.get("rosters") or []:
        manager = normalize_text(roster.get("manager") or "")
        if manager and re.search(
            rf"(?<![a-z0-9]){re.escape(manager)}(?![a-z0-9])",
            text,
        ):
            matches.append(roster)
    return matches


def _roster_stub(
    roster: dict[str, Any], snapshot: dict[str, Any], week: int
) -> dict[str, Any]:
    players = snapshot.get("players") or {}
    return {
        "roster_id": int(roster["roster_id"]),
        "manager": roster.get("manager"),
        "record": [
            roster.get("wins"),
            roster.get("losses"),
            roster.get("ties"),
        ],
        "waiver_position": roster.get("waiver_position"),
        "players": [
            _compact_player(players[player_id], week, detailed=False)
            for player_id in roster.get("player_ids") or []
            if player_id in players
        ],
    }


def _trade_target_roster_table(
    snapshot: dict[str, Any], week: int
) -> tuple[list[str], dict[str, dict[str, str]], list[dict[str, Any]]]:
    """Normalize every owned player without repeating verbose field names.

    A normal 12-team roster dump is too large when every player is encoded as
    a full ``_compact_player`` object.  More importantly, the generic packet
    trimmer used to respond by removing each roster's players entirely.  This
    table keeps the complete live ownership graph and the decision-useful
    player facts, while declaring the positional array schema once.

    Ownership is represented by nesting each player row under its live Sleeper
    roster.  Unknown/new Sleeper IDs are retained with null metadata instead
    of being silently dropped.
    """
    fields = [
        "player_id",
        "name",
        "position",
        "team",
        "lineup_role",
        "week_projection",
        "week_projection_state",
        "ros_projection_pg",
        "projection_change_pg",
        "status",
        "bye_weeks",
    ]
    codes = {
        "lineup_role": {
            "S": "submitted starter",
            "R": "reserve/IR",
            "B": "bench",
        },
        "week_projection_state": {
            "W": "weekly projection",
            "I": "confirmed inactive zero",
            "Y": "bye",
            "U": "unknown/missing; never zero-filled",
        },
    }
    projection_codes = {
        "weekly_projection": "W",
        "hard_inactive": "I",
        "bye": "Y",
        "missing": "U",
    }
    players = {
        str(player_id): player
        for player_id, player in (snapshot.get("players") or {}).items()
    }
    roster_rows = []
    for roster in snapshot.get("rosters") or []:
        starter_ids = {
            str(player_id)
            for player_id in roster.get("starter_ids") or []
            if str(player_id) != "0"
        }
        reserve_ids = {
            str(player_id)
            for player_id in roster.get("reserve_ids") or []
        }
        player_rows = []
        for raw_player_id in roster.get("player_ids") or []:
            player_id = str(raw_player_id)
            player = players.get(player_id) or {}
            points, projection_state = _projection_for_week(player, week)
            if player_id in starter_ids:
                lineup_role = "S"
            elif player_id in reserve_ids:
                lineup_role = "R"
            else:
                lineup_role = "B"
            player_rows.append(
                [
                    player_id,
                    player.get("name"),
                    player.get("pos") or player.get("position"),
                    player.get("team"),
                    lineup_role,
                    points,
                    projection_codes.get(projection_state, "U"),
                    _finite(player.get("projection_pg")),
                    _finite(player.get("projection_change_pg")),
                    player.get("injury_status") or player.get("status"),
                    sorted(
                        int(value)
                        for value in player.get("bye_weeks") or []
                        if str(value).isdigit()
                    ),
                ]
            )
        roster_rows.append(
            {
                "roster_id": int(roster["roster_id"]),
                "manager": roster.get("manager"),
                "record": [
                    roster.get("wins"),
                    roster.get("losses"),
                    roster.get("ties"),
                ],
                "waiver_position": roster.get("waiver_position"),
                "players": player_rows,
            }
        )
    return fields, codes, roster_rows


def _compact_league(snapshot: dict[str, Any]) -> dict[str, Any]:
    league = snapshot.get("league") or {}
    scoring = {
        key: value
        for key, value in (league.get("scoring_settings") or {}).items()
        if _finite(value) not in (None, 0.0)
    }
    return {
        "platform": "Sleeper",
        "league_id": league.get("league_id") or LEAGUE_ID,
        "name": league.get("league_name"),
        "season": league.get("season"),
        "week": league.get("current_week"),
        "teams": league.get("total_rosters")
        or len(snapshot.get("rosters") or []),
        "my_roster_id": MY_ROSTER_ID,
        "starter_slots": league.get("starter_slots"),
        "playoff_weeks": league.get("playoff_weeks"),
        "nonzero_scoring": scoring,
        "relevant_settings": {
            key: value
            for key, value in (league.get("league_settings") or {}).items()
            if key
            in {
                "waiver_type",
                "waiver_day_of_week",
                "waiver_clear_days",
                "trade_deadline",
                "playoff_week_start",
                "num_teams",
            }
        },
        "current_matchup": league.get("current_matchup"),
        "live_refreshed_at_utc": league.get("live_refreshed_at_utc"),
    }


def _safe_packet_size(packet: dict[str, Any]) -> int:
    return len(
        json.dumps(
            json_safe(packet), separators=(",", ":"), allow_nan=False
        )
    )


def build_packet(
    question: str,
    snapshot: dict[str, Any],
    explicit_trade: dict[str, Any] | None = None,
    deep: bool = False,
    live_context: dict[str, Any] | None = None,
    include_market: bool = True,
) -> dict[str, Any]:
    """Build one intent-shaped packet. It never calls an LLM."""
    current = _sync_live(snapshot, live_context)
    week = int(
        (current.get("league") or {}).get("current_week") or 1
    )
    intent = (
        "explicit_trade"
        if explicit_trade
        else classify_intent(question)
    )
    focus = match_players(question, current)
    warnings = list(current.get("runtime_warnings") or [])
    freshness = evidence_freshness(current)
    if freshness["rosters"]["status"] != "fresh":
        warnings.append("Roster ownership is stale or unverified; saved ownership cannot establish that an offer or waiver move is available now.")
    if not freshness["all_projection_sources_fresh"]:
        warnings.append("One or more underlying projection sources are stale or have no verified fetch time; creating this packet did not refresh them.")
    if not live_context:
        warnings.append("Offline evidence: current ownership, injury changes, and game timing have not been refreshed.")
    if explicit_trade:
        wanted = set(explicit_trade.get("give_ids") or []) | set(
            explicit_trade.get("get_ids") or []
        )
        focus = [
            player
            for player_id, player in (
                current.get("players") or {}
            ).items()
            if player_id in wanted
        ]

    packet: dict[str, Any] = {
        "schema_version": 2,
        "question": question,
        "decision_type": intent,
        "research_time_utc": iso_now(),
        "projection_snapshot": {
            "generated_at_utc": current.get("generated_at_utc"),
            "age_minutes": round(snapshot_age_minutes(current), 1)
            if current.get("generated_at_utc")
            else None,
            "engine": (current.get("engine") or {}).get("version"),
            "market_in_baseline": False,
            "source_freshness": freshness["projection_sources"],
        },
        "evidence_quality": freshness,
        "league": _compact_league(current),
        "focused_players": [
            _compact_player(player, week) for player in focus
        ],
        "exact_engine_decision_math": None,
        "warnings": warnings,
        "research_contract": {
            "news": (
                "Check official team/NFL status and reputable current "
                "reporting for material role changes."
            ),
            "market": (
                "Use markets as a forecasting update, not betting advice; "
                "preserve missing and disagreement."
            ),
            "expert": (
                "Keep expert consensus separate from sportsbook and "
                "pick'em evidence."
            ),
        },
    }

    if include_market and focus:
        market = focused_market_packet(
            focus,
            deep=deep,
            projection_universe=list((current.get("players") or {}).values()),
        )
        packet["market_evidence"] = market
        if (
            market.get("source_status", {}).get("sports_game_odds")
            != "live"
        ):
            warnings.append(
                "Primary sportsbook player-prop feed is unavailable or "
                "has no posted line."
            )
        player_market = market.get("players") or {}
        covered = sum(
            1
            for player in focus
            if (
                player_market.get(str(player.get("name") or ""), {})
                .get("sportsbooks")
            )
        )
        if len(focus) > 1 and 0 < covered < len(focus):
            warnings.append(
                "Market evidence is asymmetric: posted sportsbook props "
                f"were found for {covered} of {len(focus)} focused "
                "players. Do not treat the uncovered player as a zero or "
                "as a negative market signal."
            )
    if include_market and focus and source_configuration().get("fantasypros"):
        packet["expert_projection_evidence"] = focused_expert_packet(
            focus,
            int(
                (current.get("league") or {}).get("season")
                or utc_now().year
            ),
            week,
            include_ros=True,
        )

    if intent == "comparison":
        if len(focus) < 2:
            warnings.append(
                "Fewer than two players were uniquely identified."
            )
    elif intent == "explicit_trade":
        if explicit_trade:
            explicit_trade = {**explicit_trade, **trade_horizon(current, explicit_trade)}
            trade_math = evaluate_trade(
                current, explicit_trade
            )
            packet["exact_engine_decision_math"] = trade_math
            decisive_fields = (
                "perspective_before_pg",
                "perspective_after_pg",
                "perspective_delta_pg",
                "counterparty_before_pg",
                "counterparty_after_pg",
                "counterparty_delta_pg",
            )
            unavailable = [
                field
                for field in decisive_fields
                if trade_math.get(field) is None
            ]
            if unavailable:
                warnings.append(
                    "Trade lineup math is incomplete because a required "
                    "weekly projection or legal starter assignment is "
                    "unavailable. Missing fields: "
                    + ", ".join(unavailable)
                    + ". Treat any populated partial or playoff delta as "
                    "non-decisive."
                )
            involved = {
                int(
                    explicit_trade.get(
                        "perspective_rid", MY_ROSTER_ID
                    )
                ),
                int(explicit_trade["other_rid"]),
            }
            packet["involved_rosters"] = [
                _roster_stub(roster, current, week)
                for roster in current.get("rosters") or []
                if int(roster["roster_id"]) in involved
            ]
        else:
            warnings.append(
                "Trade language was detected, but no structured offer was "
                "supplied; do not infer give/get sides from ownership."
            )
    elif intent == "lineup":
        if live_context:
            packet["current_lineup"] = (
                live_context.get("current_lineup") or []
            )
            packet["current_lineup_total"] = live_context.get(
                "current_lineup_total"
            )
            packet["current_lineup_source"] = (
                "live Sleeper submitted starters"
            )
        else:
            mine = next(
                (
                    row
                    for row in current.get("rosters") or []
                    if int(row["roster_id"]) == MY_ROSTER_ID
                ),
                None,
            )
            packet["current_lineup"] = (
                optimize_lineup(
                    mine.get("player_ids") or [], current, week
                )
                if mine
                else {"feasible": False, "assignments": []}
            )
            warnings.append(
                "Live submitted starters were unavailable; shown lineup "
                "is an optimizer result."
            )
    elif intent == "waiver":
        positions = set()
        text = normalize_text(question)
        if "defense" in text or "dst" in text:
            positions.add("DEF")
        if "kicker" in text:
            positions.add("K")
        packet["available_players"] = _available(
            current, week, positions or None
        )
        mine = next(
            (
                row
                for row in current.get("rosters") or []
                if int(row["roster_id"]) == MY_ROSTER_ID
            ),
            None,
        )
        if mine:
            packet["my_roster"] = _roster_stub(
                mine, current, week
            )
    elif intent == "league_rankings":
        # Ownership changes between full projection refreshes. Reuse the
        # saved forecasts, but rank today's rosters rather than saved teams.
        weeks = list(range(week, int(CONFIG["season_end_week"]) + 1))
        slots = [slot for slot in (current.get("league") or {}).get("starter_slots", [])
                 if slot not in BENCH_SLOTS and slot not in {"K", "DEF"}]
        rankings = []
        for roster in current.get("rosters") or []:
            mean, results = _roster_average(roster.get("player_ids") or [], current, weeks, slots)
            rankings.append({"roster_id": roster["roster_id"], "manager": roster.get("manager"),
                             "core_starter_pg": mean, "weeks_measured": len(weeks),
                             "complete": mean is not None})
        rankings.sort(key=lambda row: -(row["core_starter_pg"] if row["core_starter_pg"] is not None else -math.inf))
        for rank, row in enumerate(rankings, 1):
            row["rank"] = rank if row["complete"] else None
        packet["power_rankings"] = rankings
        packet["ranking_basis"] = (
            "skill-position optimized starter projections; K/DST excluded "
            "and no manager-personality inference"
        )
    elif intent == "team_analysis":
        matched_rosters = _manager_matches(question, current)
        if not matched_rosters and focus:
            owner_ids = {
                int(player["owner_roster_id"])
                for player in focus
                if player.get("owner_roster_id") is not None
            }
            matched_rosters = [
                roster
                for roster in current.get("rosters") or []
                if int(roster["roster_id"]) in owner_ids
            ]
        if not matched_rosters:
            warnings.append(
                "No manager/team was uniquely identified; returning "
                "compact league rosters."
            )
            matched_rosters = current.get("rosters") or []
        packet["teams"] = [
            _roster_stub(roster, current, week)
            for roster in matched_rosters
        ]
        packet["league_baseline"] = (
            current.get("power_rankings") or []
        )
    elif intent == "projection_movers":
        packet["projection_movers"] = projection_movers(current)
        if not packet["projection_movers"]:
            warnings.append(
                "No comparable prior projection snapshot exists yet."
            )
    elif intent == "trade_targets":
        player_fields, codes, roster_rows = _trade_target_roster_table(
            current, week
        )
        packet["league_roster_player_fields"] = player_fields
        packet["league_roster_codes"] = codes
        packet["league_rosters"] = roster_rows
        packet["ownership_source"] = (
            "live Sleeper; each player row belongs to its containing roster"
            if live_context
            else "saved Sleeper snapshot; each player row belongs to its containing roster"
        )
        packet["power_rankings"] = [
            {
                key: value
                for key, value in row.items()
                if key
                in {
                    "roster_id",
                    "rid",
                    "manager",
                    "rank",
                    "core_starter_pg",
                    "lineup_pg",
                }
            }
            for row in current.get("power_rankings") or []
        ]
    elif intent == "recent_transactions":
        packet["recent_transactions"] = (
            (live_context or {}).get("recent_transactions") or []
        )
        packet["chat_visibility"] = (
            "Sleeper transactions are visible through the official API. "
            "League chat text is not; use signed-in browser evidence or "
            "a screenshot."
        )
    elif not focus:
        mine = next(
            (
                row
                for row in current.get("rosters") or []
                if int(row["roster_id"]) == MY_ROSTER_ID
            ),
            None,
        )
        if mine:
            packet["my_roster"] = _roster_stub(
                mine, current, week
            )

    limit = int(CONFIG["packet_character_limit"])
    # Reserve room for the self-reported size field so the hard limit applies
    # to the bytes actually handed to the model, not just the pre-metadata
    # payload.
    working_limit = max(0, limit - 64)
    size = _safe_packet_size(packet)
    if size > working_limit:
        # Remove duplicated roster details, never focused evidence.
        trim_keys = ["teams", "involved_rosters", "my_roster"]
        if intent != "trade_targets":
            trim_keys.insert(0, "league_rosters")
        for key in trim_keys:
            rows = packet.get(key)
            if isinstance(rows, list):
                packet[key] = [
                    {
                        field: value
                        for field, value in row.items()
                        if field != "players"
                    }
                    for row in rows
                ]
            elif isinstance(rows, dict):
                packet[key] = {
                    field: value
                    for field, value in rows.items()
                    if field != "players"
                }
        warnings.append(
            "Roster player detail was trimmed to respect the packet limit."
        )
        size = _safe_packet_size(packet)
    if size > working_limit and intent == "trade_targets":
        # Rankings are useful context but are reconstructable later.  The live
        # ownership/player table is not, so protect it when space is tight.
        packet.pop("power_rankings", None)
        warnings.append(
            "Power rankings were omitted to preserve complete live roster ownership."
        )
        size = _safe_packet_size(packet)
    packet["packet_size_characters"] = 0
    size = _safe_packet_size(packet)
    packet["packet_size_characters"] = size
    size = _safe_packet_size(packet)
    packet["packet_size_characters"] = size
    if size > limit:
        raise RuntimeError(
            f"Decision packet is {size:,} characters; limit is {limit:,}"
        )
    return json_safe(packet)


def live_context(snapshot: dict[str, Any], *, include_transactions: bool = False) -> dict[str, Any]:
    return fetch_live_context(
        LEAGUE_ID,
        MY_ROSTER_ID,
        snapshot.get("players") or {},
        include_transactions=include_transactions,
    )


def status_packet(
    snapshot: dict[str, Any], live: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "snapshot_generated_at_utc": snapshot.get("generated_at_utc"),
        "snapshot_age_minutes": round(snapshot_age_minutes(snapshot), 1),
        "evidence_quality": evidence_freshness(_sync_live(snapshot, live)),
        "engine": snapshot.get("engine"),
        "league": _compact_league(_sync_live(snapshot, live)),
        "sources": source_configuration(),
        "model_api_required": False,
        "interface": "ChatGPT/Codex conversation",
    }


def _csv_names(values: list[str]) -> list[str]:
    return [
        part.strip()
        for raw in values
        for part in raw.split(",")
        if part.strip()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reeve fantasy advisor evidence runtime"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    refresh = sub.add_parser("refresh")
    refresh.add_argument("--rebuild", action="store_true")
    refresh.add_argument("--quick", action="store_true")

    status = sub.add_parser("status")
    status.add_argument("--live", action="store_true")

    packet = sub.add_parser("packet")
    packet.add_argument("question", nargs="+")
    packet.add_argument("--deep", action="store_true")
    packet.add_argument("--no-market", action="store_true")
    packet.add_argument("--no-refresh", action="store_true")
    packet.add_argument("--offline", action="store_true")

    trade = sub.add_parser("trade")
    trade.add_argument("--give", action="append", required=True)
    trade.add_argument("--get", action="append", required=True)
    trade.add_argument("--manager")
    trade.add_argument("--for-manager")
    trade.add_argument("--for-roster-id", type=int)
    trade.add_argument("--deep", action="store_true")
    trade.add_argument("--no-market", action="store_true")
    trade.add_argument("--no-refresh", action="store_true")
    trade.add_argument("--offline", action="store_true")

    sub.add_parser("lineup")
    sub.add_parser("rankings")
    sub.add_parser("movers")
    sub.add_parser("transactions")

    args = parser.parse_args(argv)
    try:
        if args.command == "refresh":
            refreshed = build_snapshot(
                force=args.rebuild, quick=args.quick
            )
            print(
                json.dumps(
                    status_packet(refreshed),
                    separators=(",", ":"),
                    allow_nan=False,
                )
            )
            return 0

        no_refresh = bool(getattr(args, "no_refresh", False))
        snapshot = ensure_snapshot(no_refresh=no_refresh)
        use_live = not bool(getattr(args, "offline", False))
        live = live_context(snapshot) if use_live else None
        if args.command == "status":
            status_live = live_context(snapshot) if args.live else None
            print(
                json.dumps(
                    status_packet(snapshot, status_live),
                    separators=(",", ":"),
                    allow_nan=False,
                )
            )
            return 0

        if args.command == "trade":
            synced = _sync_live(snapshot, live)
            terms = resolve_explicit_trade(
                synced,
                _csv_names(args.give),
                _csv_names(args.get),
                args.manager,
                args.for_manager,
                args.for_roster_id,
            )
            perspective_name = terms.get("perspective_manager")
            if int(terms["perspective_rid"]) == MY_ROSTER_ID:
                subject = "I"
            else:
                subject = str(
                    perspective_name
                    or f"roster {terms['perspective_rid']}"
                )
            question = (
                f"Should {subject} give {' + '.join(terms['give'])} "
                f"for {' + '.join(terms['get'])}?"
            )
            result = build_packet(
                question,
                synced,
                explicit_trade=terms,
                deep=args.deep,
                live_context=live,
                include_market=not args.no_market,
            )
        else:
            fixed_questions = {
                "lineup": (
                    "Show my exact submitted lineup and projected total"
                ),
                "rankings": "Rank every team in the league",
                "movers": (
                    "Show the biggest projection risers and fallers"
                ),
                "transactions": (
                    "Show the most recent completed trades and transactions"
                ),
            }
            question = (
                " ".join(args.question).strip()
                if args.command == "packet"
                else fixed_questions[args.command]
            )
            result = build_packet(
                question,
                snapshot,
                deep=bool(getattr(args, "deep", False)),
                live_context=live,
                include_market=not bool(
                    getattr(args, "no_market", False)
                ),
            )
        print(
            json.dumps(
                result, separators=(",", ":"), allow_nan=False
            )
        )
        return 0
    except (
        FileNotFoundError,
        RuntimeError,
        ValueError,
        OSError,
        requests.RequestException,
    ) as exc:
        print(
            json.dumps(
                {"error": str(exc), "type": type(exc).__name__},
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
