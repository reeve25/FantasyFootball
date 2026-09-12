"""T4 glue: turn a real SGO snapshot plus a T3 registry into
weekly_points_by_source entries the existing evaluator already knows how to
read (see advisor_runtime.advisor.select_projection_source, and
evaluate_trade's own independent_projection_checks, which discovers whatever
keys exist in weekly_points_by_source automatically).

This module imports market_anchor (scipy) and assumptions. Callers import it
lazily -- only when a projection source of "market_anchor" or "blend" is
actually requested -- so the default advice path never pays for or risks
scipy availability. No network calls live here: line rows are supplied by
the caller (typically advisor_runtime.market_sources.read_snapshot_rows over
a freshly fetched market-history file).
"""
from __future__ import annotations

import re
from typing import Any

from advisor_runtime import assumptions as assumptions_module
from advisor_runtime.market_anchor import convert_snapshot, default_yardage_sd

MARKET_ANCHOR_KEY = "market_anchor"
BLEND_KEY = "market_anchor_blend"

# T2d: deliberately narrowed to each position's core, reliably-posted
# yardage stat(s) only -- the exact scope of this ticket ("source the
# missing rec_yd / rush_yd SD"), not a full scoring replica. This is
# narrower than T4's original attempt, which required pass_td/pass_int/
# rush_td/rec_td/rec/WR-rush_yd/QB-rush_yd too and was null for every real
# player for TWO compounding reasons, only one of which is this ticket's
# scope:
#   1. (this ticket) rec_yd/rush_yd had no SD source at all -- fixed above.
#   2. (a separate, real bug, NOT fixed here) "rec_td"/"rush_td" can never
#      be satisfied: SportsGameOdds only ever posts an aggregate anytime-TD
#      market ("touchdowns" -> stat key "td" in market_sources.
#      SPORTS_GAME_ODDS_STATS), never split by rushing vs. receiving. Every
#      required_stats list that named "rec_td"/"rush_td" was structurally
#      unfulfillable regardless of SD. Secondary stats (WR rush_yd, RB
#      rec_yd's reliability, QB rush_yd, reception counts) also have
#      inconsistent real coverage. Left for a follow-up ticket -- see
#      STATUS.md's T2d Decision Log and next-prompt.
# anchor_fp is therefore a yardage-only partial-scoring approximation by
# construction (see docs/MARKET_ANCHOR.md), not a full replica of league
# scoring. K is excluded outright -- Sleeper kicking uses nonlinear
# per-distance field-goal buckets with no single linear "kick_pts"
# coefficient, which this linear converter cannot model (market_anchor.py:
# "Nonlinear bonuses and position-dependent scoring need a separate
# adapter").
REQUIRED_STATS_BY_POSITION = {
    "QB": ["pass_yd"],
    "RB": ["rush_yd", "rec_yd"],
    "WR": ["rec_yd"],
    "TE": ["rec_yd"],
}


def _parse_season_week(value: Any) -> int | None:
    """"Week 3" -> 3. Only the provider's own text; never inferred from fetch time."""
    if not value:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def build_identity_inputs(
    line_rows: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, int]]:
    """provider_names / event_weeks for convert_snapshot, from T2c line-row metadata.

    Rows written before T2c (2026-09-12) carry neither field and are silently
    excluded here -- convert_snapshot already turns an unresolved identity or
    week into a rejected-evidence diagnostic, never a guess.
    """
    provider_names: dict[str, str] = {}
    event_weeks: dict[str, int] = {}
    for row in line_rows:
        if row.get("row_type") != "line":
            continue
        if row.get("player_name"):
            provider_names.setdefault(row["player_id"], row["player_name"])
        week = _parse_season_week((row.get("event_metadata") or {}).get("season_week"))
        if week is not None:
            event_weeks.setdefault(row["event_id"], week)
    return provider_names, event_weeks


def required_stats_for(players: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        str(player["pid"]): list(REQUIRED_STATS_BY_POSITION[player["pos"]])
        for player in players
        if player.get("pos") in REQUIRED_STATS_BY_POSITION
    }


def build_default_yardage_sd(
    players: list[dict[str, Any]], weeks: range = range(1, 19)
) -> dict[tuple[str, int, str], float]:
    """T2d: {(pid, week, stat): sd} from market_anchor.YARDAGE_SD_DEFAULTS.

    Filled for every week 1-18 regardless of which week actually shows up in
    a given snapshot -- convert_snapshot only ever looks up the weeks that
    occur in real converted rows, so the extras are inert. A (position, stat)
    pair absent from YARDAGE_SD_DEFAULTS is simply not covered (that
    component stays a documented missing stat), never guessed here either.
    """
    sd: dict[tuple[str, int, str], float] = {}
    for player in players:
        pos = player.get("pos")
        pid = str(player.get("pid"))
        for stat in REQUIRED_STATS_BY_POSITION.get(pos, []):
            if not stat.endswith("_yd"):
                continue
            value = default_yardage_sd(pos, stat)
            if value is not None:
                for week in weeks:
                    sd[(pid, week, stat)] = value
    return sd


def compute_projection_sources(
    line_rows: list[dict[str, Any]],
    *,
    players: list[dict[str, Any]],
    scoring: dict[str, float],
    assumption_registry: list[dict[str, Any]] | None = None,
    priced_in_guard=None,
    yardage_sd: dict | None = None,
    fallbacks: dict | None = None,
    use_default_yardage_sd: bool = True,
) -> dict[str, Any]:
    """Return {"sources": {pid: {market_anchor_key: {week_str: fp}, blend_key: {...}}}, "diagnostics": [...]}.

    T2d: by default (use_default_yardage_sd=True), a player-week-stat with no
    explicit yardage_sd falls back to market_anchor.YARDAGE_SD_DEFAULTS's
    provisional per-position value -- explicit caller entries always win.
    Pass use_default_yardage_sd=False (or an explicit empty yardage_sd with
    it) to get T2a/T2c's original behavior: no SD means a documented missing
    component, never a guess (see STATUS.md's T2b entries -- still the
    per-player empirical validation these position defaults are provisional
    pending). fallbacks defaults empty regardless: no team-share default
    exists or is invented here. assumption_registry defaults empty: with no
    curated assumptions, the "blend" is just the anchor, which is the
    correct, honest result of T3's apply() given nothing to blend with.
    """
    players = [p for p in players if p.get("pos") in REQUIRED_STATS_BY_POSITION]
    provider_names, event_weeks = build_identity_inputs(line_rows)
    required_stats = required_stats_for(players)
    default_sd = build_default_yardage_sd(players) if use_default_yardage_sd else {}
    explicit_sd = yardage_sd or {}
    resolved_sd = {**default_sd, **explicit_sd}
    # Every (pid, week, stat) this run priced using a provisional position
    # default rather than a caller-supplied (eventually T2b-validated) value,
    # so consumers can see exactly which numbers below rest on
    # YARDAGE_SD_DEFAULTS -- keyed per player-week-stat, not just by stat
    # name, so an explicit override for one week doesn't get misreported as
    # provisional just because other weeks still use the default.
    provisional_sd_keys = {key for key in default_sd if key not in explicit_sd}
    converted = convert_snapshot(
        line_rows,
        provider_names=provider_names,
        event_weeks=event_weeks,
        players=players,
        scoring=scoring,
        required_stats=required_stats,
        yardage_sd=resolved_sd,
        fallbacks=fallbacks or {},
    )
    registry = assumption_registry or []
    sources: dict[str, dict[str, dict[str, float]]] = {}
    attribution: dict[str, dict[str, Any]] = {}
    for (pid, week), anchor_row in converted["rows"].items():
        player_sources = sources.setdefault(pid, {MARKET_ANCHOR_KEY: {}, BLEND_KEY: {}})
        if anchor_row["anchor_fp"] is not None:
            player_sources[MARKET_ANCHOR_KEY][str(week)] = anchor_row["anchor_fp"]
        blended = assumptions_module.apply(
            anchor_row,
            registry,
            player=pid,
            week=week,
            scoring=scoring,
            priced_in_guard=priced_in_guard,
        )
        if blended["adjusted_fp"] is not None:
            player_sources[BLEND_KEY][str(week)] = blended["adjusted_fp"]
        # Present even when empty (no curated assumptions yet): the ticket's
        # "assumptions-attribution block" is a required part of the output
        # shape, not conditional on there being anything to attribute.
        attribution.setdefault(pid, {})[str(week)] = {
            "anchor_fp": anchor_row["anchor_fp"],
            "adjusted_fp": blended["adjusted_fp"],
            "cap_applied": blended["cap_applied"],
            "attribution": blended["attribution"],
            "provisional_sd_stats": sorted(
                stat for stat in anchor_row["implied_stats"]
                if (pid, week, stat) in provisional_sd_keys
            ),
        }
    return {
        "sources": sources,
        "diagnostics": converted["diagnostics"],
        "attribution": attribution,
        "provisional_sd_stats": sorted({key[2] for key in provisional_sd_keys}),
    }


def inject_projection_sources(
    players_by_id: dict[str, dict[str, Any]], sources: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Return a COPY of players_by_id with market_anchor/blend keys added to
    weekly_points_by_source. Never mutates the input. A player with no
    computed row (unresolved identity, unsupported position, ...) is
    returned unchanged -- not padded with an empty entry."""
    updated = {}
    for pid, player in players_by_id.items():
        extra = sources.get(pid)
        if not extra:
            updated[pid] = player
            continue
        cell = dict(player)
        by_source = dict(cell.get("weekly_points_by_source") or {})
        for key, points in extra.items():
            if points:
                by_source[key] = dict(points)
        cell["weekly_points_by_source"] = by_source
        updated[pid] = cell
    return updated
