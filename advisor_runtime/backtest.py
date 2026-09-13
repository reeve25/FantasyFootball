"""T5: score stored market-history projections against realized results.

Consumes, never re-derives:
- T2c's settled-event metadata (``event_metadata.season_week`` and
  ``event_metadata.status.startsAt``) already persisted on every "line" row
  in advisor_runtime/data/market_history/sports_game_odds/*.jsonl.
- T2/T2d/T2e's market anchor: ``market_anchor_projection.
  compute_projection_sources`` is re-run against a historical snapshot's own
  raw "line" rows, because market_anchor/blend values were never persisted
  at fetch time -- only the raw lines were. Backtesting them means
  reconstructing them from history with the exact same converter used live,
  not reading a stored "anchor" field that does not exist.
- T2f's fallback: ``market_anchor_projection.apply_consensus_fallback`` is
  used both for the real historical record and to build a consensus-only
  counterfactual (see ``score_event_player``'s docstring) so an anchored
  week and a consensus week can be compared for the very same real
  player-week, which no single stored snapshot alone provides yet (SGO has
  only ever posted lines for the current week in every fetch this repo has
  made so far).

Realized stats source (T5's own uncertain item, resolved by inspection, not
invention): no module anywhere in this repo fetches settled box scores.
Sleeper's public projections endpoint (already used by ``sleeper_live.
_projection_map``) is mirrored by a stats endpoint at the same host,
``https://api.sleeper.app/stats/nfl/{season}/{week}`` -- same Sleeper pid
namespace, same stat vocabulary, verified live against a definitely-settled
past week (2025 week 1) before being wired in here. No new dependency, no
new provider, no invented data. See STATUS.md's T5 Decision Log.

No fabrication, anywhere in this module: a (player, week) is only ever
scored when (a) at least one local snapshot was captured strictly before
that event's own recorded kickoff time and (b) Sleeper's stats endpoint
reports that player as having actually played that week (``stats.gp``). If
nothing qualifies -- true today, since Week 1 has not finished -- ``run_
backtest`` returns ``{"status": "no_eligible_weeks", ...}`` and writes that
fact to disk, never a synthetic or estimated result.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from pathlib import Path
from typing import Any, Callable

from advisor_runtime import market_sources
from advisor_runtime import sleeper_live
from advisor_runtime.market_anchor_projection import (
    apply_consensus_fallback,
    compute_projection_sources,
)
from advisor_runtime.market_sources import load_name_aliases, resolve_provider_name

REALIZED_STATS_URL = "https://api.sleeper.app/stats/nfl"
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "backtest"
SOURCES = ("market_anchor", "market_anchor_blend", "sleeper_projection_feed")


def _parse_season_week(value: Any) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def _parse_iso(value: Any) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def fetch_realized_stats(season: str, week: int) -> dict[str, dict[str, Any]]:
    """{Sleeper pid: {"played": bool, "stats": {...numeric stat keys...}}}.

    Mirrors sleeper_live._projection_map's own request shape against the
    stats endpoint instead of the projections endpoint. ``played`` is
    Sleeper's own ``gp`` (games played) field -- the only thing this module
    trusts to mean "this week is actually settled for this player," since a
    week can have some games final and others not yet played.
    """
    suffix = (
        "?season_type=regular&position[]=QB&position[]=RB&position[]=WR"
        "&position[]=TE&position[]=K&position[]=DEF"
    )
    rows = sleeper_live._get_json(
        f"{REALIZED_STATS_URL}/{season}/{week}{suffix}", source="realized_stats"
    )
    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("stats") or []
    out: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        pid = str(row.get("player_id") or (row.get("player") or {}).get("player_id") or "")
        if not pid:
            continue
        stats = row.get("stats") or {}
        out[pid] = {
            "played": bool(stats.get("gp")),
            "stats": {
                str(key): value
                for key, value in stats.items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            },
        }
    return out


def scan_pre_kickoff_events(history_dir: Path) -> dict[str, dict[str, Any]]:
    """{event_id: {season_week, kickoff_utc, snapshot_path, snapshot_fetched_at}}.

    Only events with at least one local snapshot fetched strictly before
    that event's own recorded ``status.startsAt``. When more than one
    qualifying snapshot exists for the same event (repeated pre-kickoff
    fetches), the EARLIEST is kept -- the most conservative pre-kickoff
    view, matching T2b's own acceptance framing. Rows written before T2c
    (no ``event_metadata``) are silently excluded, same as everywhere else
    that field is consumed -- nothing is inferred for them.
    """
    events: dict[str, dict[str, Any]] = {}
    earliest_dt: dict[str, dt.datetime] = {}
    for path in sorted(history_dir.glob("*.jsonl")):
        try:
            rows = market_sources.read_snapshot_rows(path)
        except OSError:
            continue
        for row in rows:
            if row.get("row_type") != "line" or not row.get("event_metadata"):
                continue
            event_id = row.get("event_id")
            fetched_dt = _parse_iso(row.get("fetched_at_utc"))
            kickoff = (row["event_metadata"].get("status") or {}).get("startsAt")
            kickoff_dt = _parse_iso(kickoff)
            week = _parse_season_week(row["event_metadata"].get("season_week"))
            if not event_id or fetched_dt is None or kickoff_dt is None or week is None:
                continue
            if fetched_dt >= kickoff_dt:
                continue  # captured at or after kickoff -- not usable for T2b/T5
            if event_id not in earliest_dt or fetched_dt < earliest_dt[event_id]:
                earliest_dt[event_id] = fetched_dt
                events[event_id] = {
                    "season_week": week,
                    "kickoff_utc": kickoff,
                    "snapshot_path": path,
                    "snapshot_fetched_at": row.get("fetched_at_utc"),
                }
    return events


def _identity_map(engine_players: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    aliases = load_name_aliases()
    by_name: dict[str, dict[str, Any]] = {}
    for player in engine_players:
        name = str(player.get("name") or "")
        if not name:
            continue
        by_name.setdefault(resolve_provider_name(name, aliases), player)
    return by_name


def event_players(
    event_id: str, event_info: dict[str, Any], engine_players: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Sleeper {pid, name, pos} records for every identity-resolved player
    named in this event's own line rows -- the same join market_anchor.
    convert_snapshot performs at read time, run once up front here so the
    caller knows which pids to ask Sleeper's stats endpoint about."""
    rows = market_sources.read_snapshot_rows(event_info["snapshot_path"])
    event_rows = [
        row for row in rows if row.get("row_type") == "line" and row.get("event_id") == event_id
    ]
    aliases = load_name_aliases()
    by_name = _identity_map(engine_players)
    seen_ids: set[str] = set()
    resolved: list[dict[str, Any]] = []
    for row in event_rows:
        name = row.get("player_name")
        if not name:
            continue
        player = by_name.get(resolve_provider_name(name, aliases))
        if player is None:
            continue
        pid = str(player.get("pid"))
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        resolved.append({"pid": pid, "name": player.get("name"), "pos": player.get("pos")})
    return resolved


def historical_sleeper_projection(snapshot_path: Path, pid: str, week: int) -> float | None:
    """The Sleeper-only projection this repo had already stored for
    (pid, week) at the time of this specific snapshot -- T2's original
    append-only "projection" row_type, never the live+ESPN-blended figure
    (that blend is never persisted, only computed at request time)."""
    for row in market_sources.read_snapshot_rows(snapshot_path):
        if (
            row.get("row_type") == "projection"
            and str(row.get("player_id")) == str(pid)
            and row.get("week") == week
        ):
            value = row.get("points")
            return float(value) if isinstance(value, (int, float)) else None
    return None


def score_event_player(
    event_id: str,
    event_info: dict[str, Any],
    player: dict[str, Any],
    *,
    scoring: dict[str, float],
    realized: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """One player-week's scored record, or None if nothing is scoreable
    (player didn't actually play, or no realized stats exist for them).

    Reports two provenance rows for the same real outcome, using T2f's own
    functions rather than a parallel implementation:
    - "anchored": market_anchor/market_anchor_blend as reconstructed from
      this event's actual posted lines (apply_consensus_fallback is not
      needed here -- a real anchor exists).
    - "consensus": what market_anchor_blend would have been with NO market
      line at all, built the same way apply_consensus_fallback does it live
      (the historically-stored Sleeper-only projection run through T3's
      identical apply() call). This is a counterfactual for the SAME
      player-week and outcome, not a second independent historical
      snapshot -- no fetch this repo has made yet has ever covered a week
      before the market started pricing it. Labelled accordingly; never
      presented as an independently observed second forecast.
    """
    pid = player["pid"]
    week = event_info["season_week"]
    realized_row = realized.get(pid)
    if realized_row is None or not realized_row.get("played"):
        return None
    realized_fp = sleeper_live._score(realized_row.get("stats") or {}, scoring)
    if realized_fp is None:
        return None

    rows = market_sources.read_snapshot_rows(event_info["snapshot_path"])
    event_rows = [
        row for row in rows if row.get("row_type") == "line" and row.get("event_id") == event_id
    ]
    anchored = compute_projection_sources(event_rows, players=[player], scoring=scoring)
    anchor_fp = anchored["sources"].get(pid, {}).get("market_anchor", {}).get(str(week))
    anchored_blend_fp = anchored["sources"].get(pid, {}).get("market_anchor_blend", {}).get(str(week))

    sleeper_fp = historical_sleeper_projection(event_info["snapshot_path"], pid, week)
    consensus_blend_fp = None
    if sleeper_fp is not None:
        synthetic_player = {"pid": pid, "weekly_points": {str(week): sleeper_fp}}
        merged, _ = apply_consensus_fallback(
            {pid: synthetic_player}, {}, scoring=anchored["resolved_scoring"], weeks=range(week, week + 1)
        )
        consensus_blend_fp = merged.get(pid, {}).get("market_anchor_blend", {}).get(str(week))

    def error(predicted: float | None) -> float | None:
        return None if predicted is None else abs(predicted - realized_fp)

    return {
        "event_id": event_id,
        "pid": pid,
        "name": player.get("name"),
        "week": week,
        "realized_fp": round(realized_fp, 4),
        "anchored": {
            "market_anchor": anchor_fp,
            "market_anchor_blend": anchored_blend_fp,
            "sleeper_projection_feed": sleeper_fp,
            "error": {
                "market_anchor": error(anchor_fp),
                "market_anchor_blend": error(anchored_blend_fp),
                "sleeper_projection_feed": error(sleeper_fp),
            },
        },
        "consensus_counterfactual": {
            "market_anchor_blend": consensus_blend_fp,
            "error": {"market_anchor_blend": error(consensus_blend_fp)},
        },
        "anchor_confidence": anchored["attribution"].get(pid, {}).get(str(week), {}).get("confidence"),
    }


def _mae(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    errors_by_source = {source: [] for source in SOURCES}
    for record in records:
        for source, value in record["anchored"]["error"].items():
            if value is not None:
                errors_by_source[source].append(value)
    anchored_vs_consensus = [
        (record["anchored"]["error"]["market_anchor_blend"], record["consensus_counterfactual"]["error"]["market_anchor_blend"])
        for record in records
        if record["anchored"]["error"]["market_anchor_blend"] is not None
        and record["consensus_counterfactual"]["error"]["market_anchor_blend"] is not None
    ]
    anchored_errors = [a for a, _ in anchored_vs_consensus]
    consensus_errors = [c for _, c in anchored_vs_consensus]
    return {
        "player_weeks_scored": len(records),
        "mae_by_source": {source: _mae(errors) for source, errors in errors_by_source.items()},
        "n_by_source": {source: len(errors) for source, errors in errors_by_source.items()},
        "anchored_vs_consensus_counterfactual": {
            "n": len(anchored_vs_consensus),
            "anchored_blend_mae": _mae(anchored_errors),
            "consensus_only_blend_mae": _mae(consensus_errors),
            "anchored_minus_consensus_mae": (
                round(_mae(anchored_errors) - _mae(consensus_errors), 4)
                if anchored_errors and consensus_errors else None
            ),
            "note": (
                "Negative means the market anchor beat a consensus-only blend "
                "on these same real outcomes; positive means consensus-only "
                "would have done better. This is the first real evidence of "
                "whether the anchor does anything, not a claim it always will."
            ),
        },
    }


def run_backtest(
    *,
    history_dir: Path | None = None,
    engine_players: list[dict[str, Any]] | None = None,
    scoring: dict[str, float] | None = None,
    season: str | None = None,
    realized_fetcher: Callable[[str, int], dict[str, dict[str, Any]]] = fetch_realized_stats,
    out_dir: Path | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Run the full T5 backtest and (by default) write results to disk.

    Any of engine_players/scoring/season left None triggers a live load
    (advisor.load_snapshot()) -- kept lazy and optional so tests can supply
    small fixtures instead of the real ~12,200-player snapshot.
    """
    history_dir = history_dir or market_sources.MARKET_HISTORY_DIR
    out_dir = out_dir or DEFAULT_OUT_DIR
    if engine_players is None or scoring is None or season is None:
        from advisor_runtime import advisor  # lazy: heavy, not needed by tests

        snapshot = advisor.load_snapshot()
        if engine_players is None:
            engine_players = list((snapshot.get("players") or {}).values())
        if scoring is None:
            scoring = (snapshot.get("league") or {}).get("scoring_settings") or {}
        if season is None:
            season = str((snapshot.get("league") or {}).get("season") or "")

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    checked_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    events = scan_pre_kickoff_events(history_dir)
    if not events:
        result = {
            "status": "no_eligible_weeks",
            "run_id": run_id,
            "checked_at_utc": checked_at,
            "reason": "No local snapshot was captured strictly before its event's recorded kickoff time.",
            "candidate_events": 0,
            "player_weeks_scored": 0,
        }
        if write:
            _write_run(out_dir, run_id, result)
        return result

    realized_cache: dict[int, dict[str, dict[str, Any]]] = {}
    records: list[dict[str, Any]] = []
    weeks_checked: set[int] = set()
    for event_id, event_info in events.items():
        week = event_info["season_week"]
        weeks_checked.add(week)
        if week not in realized_cache:
            realized_cache[week] = realized_fetcher(season, week)
        players = event_players(event_id, event_info, engine_players)
        for player in players:
            record = score_event_player(
                event_id, event_info, player, scoring=scoring, realized=realized_cache[week]
            )
            if record is not None:
                records.append(record)

    if not records:
        result = {
            "status": "no_eligible_weeks",
            "run_id": run_id,
            "checked_at_utc": checked_at,
            "reason": (
                "Pre-kickoff snapshots exist, but Sleeper's stats endpoint "
                "reports no scoreable player as having played yet for "
                f"week(s) {sorted(weeks_checked)}."
            ),
            "candidate_events": len(events),
            "weeks_checked": sorted(weeks_checked),
            "player_weeks_scored": 0,
        }
        if write:
            _write_run(out_dir, run_id, result)
        return result

    result = {
        "status": "scored",
        "run_id": run_id,
        "checked_at_utc": checked_at,
        "season": season,
        "weeks_checked": sorted(weeks_checked),
        "candidate_events": len(events),
        **summarize(records),
        "records": records,
    }
    if write:
        _write_run(out_dir, run_id, result)
    return result


def _write_run(out_dir: Path, run_id: str, result: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_path = out_dir / f"{run_id}.json"
    run_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    summary_path = out_dir / "summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if not isinstance(summary, dict) or not isinstance(summary.get("runs"), list):
            summary = {"runs": []}
    except (OSError, ValueError):
        summary = {"runs": []}
    entry = {
        key: result.get(key)
        for key in (
            "run_id", "checked_at_utc", "status", "player_weeks_scored",
            "candidate_events", "mae_by_source", "anchored_vs_consensus_counterfactual",
        )
        if key in result
    }
    entry["run_file"] = run_path.name
    summary["runs"].append(entry)
    summary["latest"] = entry
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
