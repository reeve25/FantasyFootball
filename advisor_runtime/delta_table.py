"""T6: per-book line/price movement between two market-history snapshots,
plus projection movement, wired into T3's anti-double-count guard.

Additive only: this module reads existing "line"/"projection" rows via
market_sources.read_snapshot_rows and, when persisted, writes a NEW file
into the same append-only market_history directory with row_type "delta" --
the exact same exclusive-create/never-overwrite convention
market_sources._write_sports_game_odds_snapshot already uses. No existing
row shape changes; no existing reader (market_anchor.convert_snapshot,
backtest.py, market_anchor_projection.py) is touched, since they all filter
strictly on row_type == "line"/"projection" and will simply never see a
"delta" row type they were never asked to read.

This is deliberately a two-snapshot COMPARISON, not a live subscription or a
scheduled job -- "when to compare" (e.g. wiring this into every live fetch)
is an automation/wiring decision left for a future ticket, per the user's
explicit "do not start T7/T8" scope for this session. The comparison itself
is the leverage T6 was asked to build.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable

from advisor_runtime import market_sources
from advisor_runtime.market_sources import (
    load_name_aliases,
    parse_season_week,
    resolve_provider_name,
)

# The line-market stat keys a single posted threshold can be checked for
# movement against directly (see market_sources.SPORTS_GAME_ODDS_STATS).
# "fantasy_points" and "p_active" (T3's other two stat_affected kinds) have
# no single corresponding market line, so a priced-in decision for those
# always comes back unknown (None) here -- never guessed from an unrelated
# line's movement.
LINE_MARKET_STATS = frozenset(market_sources.SPORTS_GAME_ODDS_STATS.values())

# Default: a same-direction per-book move must be at least this large, in
# the stat's own raw units, to count as "priced in." This is a plain,
# disclosed heuristic -- not a fitted or validated threshold. Any single
# book meeting it is enough (see priced_in_guard's own docstring for why
# "any book," not "consensus/median," was chosen).
DEFAULT_LINE_MOVE_THRESHOLD = 3.0


def compute_line_deltas(
    baseline_rows: list[dict[str, Any]], current_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Per-(event, provider player, book, market, side) line/price movement.

    Only emits a row when the SAME key exists in BOTH snapshots -- a side
    posted in only one of the two is not comparable movement, and is left
    out entirely rather than treated as a zero move (missing is unknown,
    never zero, same rule as everywhere else in this pipeline). Carries
    season_week (T2c event_metadata, parsed via market_sources.
    parse_season_week) only when both rows actually have it -- a delta row
    with week=None is real, just not week-attributable, and callers that
    need a week (the priced-in guard) skip it rather than guess.
    """

    def index(rows):
        out = {}
        for row in rows:
            if row.get("row_type") != "line":
                continue
            key = (row.get("event_id"), row.get("player_id"), row.get("book"),
                   row.get("market"), row.get("side"))
            out[key] = row
        return out

    baseline_by_key = index(baseline_rows)
    current_by_key = index(current_rows)
    deltas = []
    for key, current in current_by_key.items():
        baseline = baseline_by_key.get(key)
        if baseline is None:
            continue
        event_id, player_id, book, market, side = key
        baseline_week = parse_season_week((baseline.get("event_metadata") or {}).get("season_week"))
        current_week = parse_season_week((current.get("event_metadata") or {}).get("season_week"))
        season_week = baseline_week if baseline_week == current_week else None
        baseline_line, current_line = baseline.get("line"), current.get("line")
        baseline_price, current_price = baseline.get("price"), current.get("price")
        deltas.append({
            "row_type": "delta", "delta_kind": "line", "source": "SportsGameOdds",
            "event_id": event_id, "player_id": player_id, "player_name": current.get("player_name"),
            "book": book, "market": market, "side": side, "season_week": season_week,
            "baseline_fetched_at_utc": baseline.get("fetched_at_utc"),
            "current_fetched_at_utc": current.get("fetched_at_utc"),
            "baseline_line": baseline_line, "current_line": current_line,
            "line_move": (
                round(current_line - baseline_line, 4)
                if isinstance(baseline_line, (int, float)) and isinstance(current_line, (int, float))
                else None
            ),
            "baseline_price": baseline_price, "current_price": current_price,
            "price_move": (
                round(current_price - baseline_price, 4)
                if isinstance(baseline_price, (int, float)) and isinstance(current_price, (int, float))
                else None
            ),
        })
    return deltas


def compute_projection_deltas(
    baseline_rows: list[dict[str, Any]], current_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Per-(Sleeper pid, week) engine projection movement -- "alongside" the
    line deltas above, per the ticket's own phrasing. Same never-guess rule:
    only emitted when both snapshots actually persisted a projection row for
    that player-week (see market_sources._write_sports_game_odds_snapshot's
    own gating -- a player with no live_week_projection at fetch time has no
    row to compare from)."""

    def index(rows):
        out = {}
        for row in rows:
            if row.get("row_type") != "projection":
                continue
            out[(row.get("player_id"), row.get("week"))] = row
        return out

    baseline_by_key = index(baseline_rows)
    current_by_key = index(current_rows)
    deltas = []
    for key, current in current_by_key.items():
        baseline = baseline_by_key.get(key)
        if baseline is None:
            continue
        pid, week = key
        baseline_points, current_points = baseline.get("points"), current.get("points")
        deltas.append({
            "row_type": "delta", "delta_kind": "projection", "source": "engine_projection",
            "player_id": pid, "player_name": current.get("player_name"), "week": week,
            "baseline_fetched_at_utc": baseline.get("fetched_at_utc"),
            "current_fetched_at_utc": current.get("fetched_at_utc"),
            "baseline_points": baseline_points, "current_points": current_points,
            "points_move": (
                round(current_points - baseline_points, 4)
                if isinstance(baseline_points, (int, float)) and isinstance(current_points, (int, float))
                else None
            ),
        })
    return deltas


def compute_deltas(
    baseline_rows: list[dict[str, Any]], current_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Both delta kinds, combined -- the full new row_type this ticket adds."""
    return compute_line_deltas(baseline_rows, current_rows) + compute_projection_deltas(baseline_rows, current_rows)


def write_delta_snapshot(
    baseline_path: str | Path, current_path: str | Path, *, out_dir: Path | None = None
) -> dict[str, Any]:
    """Compute deltas between two real stored snapshots and persist them as
    a NEW file (never appended into either input file) in the same
    market_history directory, using the identical exclusive-create/unique-
    name convention as market_sources._write_sports_game_odds_snapshot.
    Existing files -- including the two being compared -- are never opened
    for writing."""
    out_dir = out_dir or market_sources.MARKET_HISTORY_DIR
    baseline_rows = market_sources.read_snapshot_rows(baseline_path)
    current_rows = market_sources.read_snapshot_rows(current_path)
    deltas = compute_deltas(baseline_rows, current_rows)
    for row in deltas:
        row["baseline_snapshot_path"] = str(baseline_path)
        row["current_snapshot_path"] = str(current_path)
    fetched_at_utc = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")
    stamp = fetched_at_utc.replace(":", "").replace("+0000", "Z")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stamp}-delta-{uuid.uuid4().hex}.jsonl"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        for row in deltas:
            handle.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "status": "written", "path": str(path), "rows": len(deltas),
        "line_deltas": sum(1 for r in deltas if r["delta_kind"] == "line"),
        "projection_deltas": sum(1 for r in deltas if r["delta_kind"] == "projection"),
    }


def _resolve_provider_id(
    sleeper_pid: str, engine_players_by_id: dict[str, dict[str, Any]],
    provider_names_by_provider_id: dict[str, str], aliases: dict[str, str],
) -> str | None:
    """Bridge a Sleeper pid (the assumption registry's own identity) to the
    SGO provider id the delta rows are keyed by -- the same name-resolution
    join every other T2-series module uses (market_anchor_projection.
    build_identity_inputs, backtest.event_players); never a new/invented id."""
    player = engine_players_by_id.get(sleeper_pid)
    if not player or not player.get("name"):
        return None
    target = resolve_provider_name(player["name"], aliases)
    for provider_id, provider_name in provider_names_by_provider_id.items():
        if resolve_provider_name(provider_name, aliases) == target:
            return provider_id
    return None


def build_priced_in_guard(
    deltas: list[dict[str, Any]],
    engine_players: list[dict[str, Any]],
    *,
    line_move_threshold: float = DEFAULT_LINE_MOVE_THRESHOLD,
) -> Callable[[dict[str, Any], int], bool | None]:
    """Return a callable matching assumptions.apply's own priced_in_guard
    contract: guard(assumption, week) -> True (already priced) / False
    (checked, unpriced) / None (unknown -- suppressed, same as no guard).

    Design, stated plainly rather than left implicit:
    - Matches by Sleeper pid -> name -> SGO provider id (never a new id).
    - Only stat_affected values that are themselves a single postable market
      line (LINE_MARKET_STATS: pass_yd, rush_yd, rec_yd, rec, td, ...) can be
      checked at all; "fantasy_points"/"p_active" have no one line to read
      movement from, so those always return None (unknown, suppressed) --
      the same fail-closed default the T3 contract already documents for
      "no hook."
    - "ANY one book," not a cross-book median/consensus, showing a
      same-direction move at or above `line_move_threshold` is enough to
      flag priced-in. This is a deliberate, disclosed choice, not an
      oversight: requiring consensus agreement across books would have
      missed this ticket's own real acceptance case (a single book's real,
      large correction while four others hadn't moved yet -- see STATUS.md's
      T6 entry) and errs toward the SAFER failure mode for an anti-double-
      count guard -- suppressing an assumption too eagerly (once) costs one
      missed adjustment; double-counting costs a systematically inflated
      projection every time it happens. A future ticket could tighten this
      to require 2+ agreeing books once real data shows single-book false
      positives are common; not attempted here.
    - Direction must match: an assumption predicting a stat INCREASE is
      never treated as priced-in by a market DECREASE (that's new,
      contradicting information, not the same news already reflected) --
      and vice versa.
    - No matching delta data at all (unresolved identity, no line posted for
      that stat, or the delta's own week doesn't fall in the assumption's
      week_range) returns None, never a guess.
    """
    aliases = load_name_aliases()
    engine_players_by_id = {str(p.get("pid")): p for p in engine_players}
    provider_names_by_provider_id = {
        str(row["player_id"]): row["player_name"]
        for row in deltas if row.get("delta_kind") == "line" and row.get("player_name")
    }
    line_deltas = [row for row in deltas if row.get("delta_kind") == "line"]

    def guard(assumption: dict[str, Any], week: int) -> bool | None:
        stat = assumption.get("stat_affected")
        if stat not in LINE_MARKET_STATS:
            return None
        provider_id = _resolve_provider_id(
            assumption["player"], engine_players_by_id, provider_names_by_provider_id, aliases
        )
        if provider_id is None:
            return None
        moves = [
            row["line_move"]
            for row in line_deltas
            if row.get("player_id") == provider_id
            and row.get("market") == stat
            and row.get("side") == "over"
            and row.get("season_week") == week
            and row.get("line_move") is not None
        ]
        if not moves:
            return None
        delta_sign = 1 if assumption.get("delta", 0) > 0 else (-1 if assumption.get("delta", 0) < 0 else 0)
        if delta_sign == 0:
            return None
        for move in moves:
            if move * delta_sign > 0 and abs(move) >= line_move_threshold:
                return True
        return False

    return guard
