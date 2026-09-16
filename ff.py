#!/usr/bin/env python3
"""The single public entry point for Reeve's shared fantasy system.

Run inside the current assistant's subscription; no model APIs. Slow work runs
in a child process so timeouts also stop threads and blocked network requests.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temp.replace(path)


def compact(packet):
    """Remove duplication, retain warnings, provenance, and every trade gate."""
    out = dict(packet)
    out.pop("research_contract", None)
    out.pop("packet_size_characters", None)
    for key in ("involved_rosters", "my_roster", "teams"):
        out.pop(key, None)
    math = out.get("exact_engine_decision_math")
    if isinstance(math, dict):
        math = dict(math)
        for key in list(math):
            if key.startswith(("my_", "their_")):
                math.pop(key)
        changes = math.get("perspective_weekly_lineup_changes", [])
        if changes:
            math["first_effective_week_lineup_change"] = changes[0]
            math.pop("perspective_weekly_lineup_changes", None)
        out["exact_engine_decision_math"] = math
    return out


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--timeout", type=float, default=None, help="Whole request limit in seconds (default 45; refresh 120)")
    p.add_argument("--full", action="store_true", help="Return full evidence; default saves it locally and returns compact JSON")
    p.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Local health and freshness; no network")
    sub.add_parser("selftest", help="Offline regression tests")
    refresh = sub.add_parser("refresh", help="Explicitly rebuild projection evidence")
    refresh.add_argument("--rebuild", action="store_true", help="Bypass upstream caches")
    for command in ("packet", "trade", "lineup", "rankings", "movers", "transactions", "discover"):
        q = sub.add_parser(command)
        q.add_argument("--offline", action="store_true")
        q.add_argument("--market", action="store_true", help="Add focused current sportsbook evidence")
        if command in {"packet", "trade"}:
            q.add_argument("--market-refresh", action="store_true", help="Fetch SportsGameOdds now, bypassing its 10-minute cache; implies --market")
        q.add_argument("--deep", action="store_true", help="Also use configured metered odds check")
        if command == "packet":
            q.add_argument("question", nargs="+")
        if command == "trade":
            q.add_argument("--give", action="append", required=True)
            q.add_argument("--get", action="append", required=True)
            q.add_argument("--manager")
            q.add_argument("--for-manager")
            q.add_argument("--for-roster-id", type=int)
            q.add_argument("--effective-week", type=int)
            q.add_argument(
                "--projection-source",
                choices=["sleeper", "espn", "market_anchor", "blend"],
                help=(
                    "Evaluate on one projection source instead of the "
                    "existing sleeper+espn default. market_anchor/blend "
                    "fetch fresh sportsbook lines for the traded players and "
                    "are unvalidated pending T2b (see STATUS.md); omitting "
                    "this flag leaves existing behavior unchanged."
                ),
            )
        if command == "discover":
            q.add_argument("--manager")
            q.add_argument("--limit", type=int, default=3)
            q.add_argument("--candidates", type=int, default=66)
    return p


def local_status():
    from advisor_runtime import advisor as a
    from advisor_runtime.market_sources import source_configuration
    try:
        snapshot = a.load_snapshot()
    except (OSError, ValueError):
        snapshot = {}
    revision = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=3)
    return {
        "system": "Reeve Fantasy Football", "canonical_folder": str(ROOT),
        "entry_point": str(ROOT / "ff.py"), "git_revision": revision.stdout.strip() or None,
        "snapshot_generated_at_utc": snapshot.get("generated_at_utc"),
        "snapshot_age_minutes": round(a.snapshot_age_minutes(snapshot), 1) if snapshot else None,
        "source_freshness": a.evidence_freshness(snapshot) if hasattr(a, "evidence_freshness") else snapshot.get("source_freshness", "See packet source timestamps"),
        "sources": source_configuration(), "model_api_required": False,
        "network_calls": 0, "refresh_is_explicit": True,
    }


def worker(args):
    from advisor_runtime import advisor as a
    checkpoint = Path(os.environ["FF_CHECKPOINT"])
    def save(value):
        write_json(checkpoint, a.json_safe(value))
    if args.command == "refresh":
        snapshot = a.build_snapshot(force=args.rebuild, quick=True)
        save({"status": "refreshed", **a.status_packet(snapshot)})
        return
    try:
        snapshot = a.load_snapshot()
    except (FileNotFoundError, ValueError):
        snapshot = {"players": {}, "rosters": [], "league": {}, "runtime_warnings": ["No projection snapshot. Run ff.py refresh for future-week forecasts."]}
    snapshot.setdefault("runtime_warnings", [])
    if snapshot.get("generated_at_utc") and a.snapshot_age_minutes(snapshot) > a.CONFIG["snapshot_ttl_minutes"]:
        snapshot["runtime_warnings"].append("Projection snapshot is stale. This request will not silently rebuild it; run ff.py refresh --rebuild once when current future-week evidence is needed.")
    save({"status": "working", "stage": "live_league", "warnings": snapshot["runtime_warnings"]})
    live = None
    if not args.offline:
        try:
            from advisor_runtime.sleeper_live import fetch_live_context
            include_transactions = args.command == "transactions" or (
                args.command == "packet"
                and a.classify_intent(" ".join(args.question)) == "recent_transactions"
            )
            live = fetch_live_context(a.LEAGUE_ID, a.MY_ROSTER_ID, snapshot.get("players") or {}, include_transactions=include_transactions)
        except Exception as exc:
            snapshot["runtime_warnings"].append(f"Live league unavailable ({type(exc).__name__}); ownership and status are unverified.")
    else:
        snapshot["runtime_warnings"].append("Offline: live ownership, availability and submitted starters are unverified.")
    current = a._sync_live(snapshot, live)
    # Full detail is saved outside model context, so the internal packet need
    # not fail merely because a trade has many weekly lineup changes.
    a.CONFIG["packet_character_limit"] = 200000
    # Optional providers must never block the initial useful packet.
    a.focused_expert_packet = lambda *x, **y: {"status": "not_requested"}
    terms = None
    if args.command == "trade":
        terms = a.resolve_explicit_trade(current, a._csv_names(args.give), a._csv_names(args.get), args.manager, args.for_manager, args.for_roster_id)
        if args.effective_week is not None:
            terms["effective_week"] = args.effective_week
        question = f"Evaluate giving {' + '.join(terms['give'])} for {' + '.join(terms['get'])}"
    else:
        question = " ".join(args.question) if args.command == "packet" else {
            "lineup": "Show my exact submitted lineup and projected total",
            "rankings": "Rank every team in the league",
            "movers": "Show the biggest projection risers and fallers",
            "transactions": "Show the most recent completed trades and transactions",
            "discover": "Find trade targets across the league",
        }[args.command]
    projection_source = getattr(args, "projection_source", None)
    market_anchor_diagnostics = None
    market_anchor_attribution = None
    if args.command == "trade" and projection_source in ("market_anchor", "blend"):
        # T4: fetch fresh lines for only the traded players and compute the
        # T2 anchor + T3 blend, injected additively into
        # weekly_points_by_source. Never touches players["weekly_points"]
        # directly -- select_projection_source below does that, and only for
        # the players/sources it is asked to use.
        from advisor_runtime.market_anchor_projection import (
            compute_projection_sources,
            inject_projection_sources,
        )
        from advisor_runtime.market_sources import read_snapshot_rows, sports_game_odds

        involved_ids = sorted(set(terms["give_ids"] + terms["get_ids"]))
        focus = [current["players"][pid] for pid in involved_ids]
        fetch = sports_game_odds(focus, force_refresh=True)
        snapshot_info = fetch.get("line_snapshot") or {}
        if snapshot_info.get("status") == "written" and snapshot_info.get("path"):
            line_rows = [
                row for row in read_snapshot_rows(snapshot_info["path"])
                if row.get("row_type") == "line"
            ]
            anchor_players = [
                {"pid": pid, "name": current["players"][pid].get("name"), "pos": current["players"][pid].get("pos")}
                for pid in involved_ids
            ]
            result = compute_projection_sources(
                line_rows,
                players=anchor_players,
                scoring=(current.get("league") or {}).get("scoring_settings") or {},
            )
            current["players"] = inject_projection_sources(current["players"], result["sources"])
            market_anchor_diagnostics = result["diagnostics"]
            market_anchor_attribution = result["attribution"]
            if result["provisional_sd_stats"]:
                current.setdefault("runtime_warnings", []).append(
                    "T2d: market_anchor/blend used provisional per-position yardage "
                    f"SD defaults for {', '.join(result['provisional_sd_stats'])} "
                    "(no T2b-validated per-player SD exists yet); see STATUS.md's "
                    "T2d Decision Log."
                )
        else:
            current.setdefault("runtime_warnings", []).append(
                f"market_anchor/blend requested but no fresh sportsbook snapshot was written "
                f"(status: {snapshot_info.get('status')!r}); the projection-source switch could "
                "not be applied for this run."
            )
            projection_source = None
    if projection_source:
        current = a.select_projection_source(current, projection_source)
    packet = a.build_packet(question, current, explicit_trade=terms, live_context=live, include_market=False)
    packet["market_status"] = "not_requested; use --market when it can change this decision"
    if projection_source or market_anchor_diagnostics is not None:
        packet["projection_source_requested"] = getattr(args, "projection_source", None)
        packet["projection_source_applied"] = projection_source
        if market_anchor_diagnostics is not None:
            packet["market_anchor_diagnostics"] = market_anchor_diagnostics
        if market_anchor_attribution is not None:
            packet["assumption_attribution"] = market_anchor_attribution
    save(packet)
    if args.command == "discover":
        from advisor_runtime.trade_search import discover
        packet = discover(current, manager=args.manager, limit=args.limit, max_candidates=args.candidates)
        save(packet)
    market_refresh = getattr(args, "market_refresh", False)
    if (args.market or args.deep or market_refresh) and args.command != "discover":
        focus = [current["players"][pid] for pid in set(terms["give_ids"] + terms["get_ids"])] if terms else a.match_players(question, current)
        if focus:
            from advisor_runtime.market_sources import focused_market_packet
            market = focused_market_packet(
                focus,
                deep=args.deep,
                force_refresh=market_refresh,
                projection_universe=list((current.get("players") or {}).values()),
            )
            packet["market_evidence"] = market
            packet.setdefault("warnings", [])[:0] = market.get("coverage_warnings") or []
            packet["market_status"] = "checked; inspect source coverage and timestamps"
            save(packet)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--selftest"]:
        argv = ["selftest"]
    if not argv:
        argv = ["status"]
    args = parser().parse_args(argv)
    if args._worker:
        # Provider progress is diagnostic text, never mixed into JSON evidence.
        try:
            with contextlib.redirect_stdout(sys.stderr):
                worker(args)
        except ValueError as exc:
            write_json(Path(os.environ["FF_CHECKPOINT"]), {"status": "request_error", "error": str(exc), "warnings": ["Correct the request before retrying; no decision was produced."]})
            return 1
        return 0
    started = time.monotonic()
    if args.command == "status":
        print(json.dumps(local_status(), allow_nan=False))
        return 0
    timeout = args.timeout if args.timeout is not None else (120 if args.command in {"refresh", "selftest"} else 45)
    if not 0 < timeout <= 600:
        raise SystemExit("--timeout must be greater than 0 and at most 600 seconds")
    if args.command == "selftest":
        deadline = time.monotonic() + timeout
        test_result = 0
        try:
            for test_directory in ("advisor_runtime/tests", "tests"):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired("selftest", timeout)
                result = subprocess.run(
                    [sys.executable, "-m", "unittest", "discover", "-s", test_directory, "-q"],
                    cwd=ROOT, timeout=remaining,
                )
                test_result = result.returncode or test_result
            return test_result
        except subprocess.TimeoutExpired:
            print(json.dumps({"status": "timed_out", "stage": "selftest"}))
            return 2
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    directory = OUTPUTS / run_id
    directory.mkdir(parents=True)
    checkpoint = directory / "evidence.json"
    env = dict(os.environ, FF_CHECKPOINT=str(checkpoint), PYTHONIOENCODING="utf-8")
    lock = ROOT / "advisor_runtime" / "data" / ".refresh.lock"
    lock_handle = None
    if args.command == "refresh":
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock_handle = lock.open("x", encoding="utf-8")
            lock_handle.write(str(os.getpid()))
            lock_handle.flush()
        except FileExistsError:
            print(json.dumps({"status": "refresh_already_running", "lock": str(lock)}))
            return 2
    timed_out = False
    try:
        # communicate/run kills and reaps the entire worker process on timeout;
        # threads belong to that process, so requests cannot outlive the command.
        with (directory / "diagnostics.log").open("w", encoding="utf-8") as log:
            try:
                result = subprocess.run([sys.executable, str(ROOT / "ff.py"), "--_worker", *argv], cwd=ROOT, env=env, stdout=log, stderr=log, timeout=timeout)
                return_code = result.returncode
            except subprocess.TimeoutExpired:
                timed_out, return_code = True, 2
    finally:
        if lock_handle is not None:
            lock_handle.close()
            lock.unlink(missing_ok=True)
    try:
        packet = json.loads(checkpoint.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        packet = {"status": "unavailable", "warnings": ["No evidence was completed. See local diagnostics."]}
    if timed_out or return_code:
        packet["run_status"] = "deadline_reached" if timed_out else "incomplete"
        packet.setdefault("warnings", []).append("Request stopped within its time budget; only completed evidence is included. Do not claim unfinished checks passed.")
    else:
        packet["run_status"] = "complete"
    packet["elapsed_seconds"] = round(time.monotonic() - started, 2)
    packet["evidence_file"] = str(checkpoint)
    write_json(checkpoint, packet)
    output = packet if args.full else compact(packet)
    encoded = json.dumps(output, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    # Discovery's complete ownership graph can be fetched deliberately; normal
    # chat gets a bounded packet instead of an accidental whole-league dump.
    if not args.full and len(encoded) > 14000:
        for key in ("league_rosters", "power_rankings", "available_players", "focused_players"):
            if len(encoded) <= 14000:
                break
            if key in output:
                output.pop(key)
                output.setdefault("details_in_evidence_file", []).append(key)
                encoded = json.dumps(output, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if not args.full and len(encoded) > 14000:
        output = {key: packet.get(key) for key in ("decision_type", "run_status", "elapsed_seconds", "evidence_file", "warnings")}
        output["status"] = "full_evidence_saved; inspect relevant fields from evidence_file"
        encoded = json.dumps(output, ensure_ascii=False, allow_nan=False)
    write_json(directory / "packet.json", output)
    write_json(OUTPUTS / "latest.json", {"run_id": run_id, "packet": str(directory / "packet.json"), "evidence": str(checkpoint)})
    print(encoded)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
