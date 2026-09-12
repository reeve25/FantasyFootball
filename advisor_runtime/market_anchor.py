"""Offline, conditional market means. Not wired into advice until T4.

One snapshot per call. Identity/event metadata and fallback assumptions are
explicit inputs because historical line rows do not preserve them. Confidence
is an evidence label, not a calibrated probability. See docs/MARKET_ANCHOR.md.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict

from scipy.optimize import brentq
from scipy.stats import poisson

from advisor_runtime.market_sources import load_name_aliases, resolve_provider_name


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Expected finite number")
    return result


def implied_probability(price):
    price = number(price)
    if abs(price) < 100:
        raise ValueError("Expected American odds with magnitude >= 100")
    return -price / (100 - price) if price < 0 else 100 / (100 + price)


def stat_distribution(line, over_price, under_price, *, sd=None):
    """Normal location with caller-supplied SD, or Poisson count model.

    Integer thresholds are rejected: push probabilities require a different
    conditional likelihood. A single priced threshold cannot identify SD.
    """
    line = number(line)
    if line < 0 or line.is_integer():
        raise ValueError("Require a nonnegative noninteger threshold (no pushes)")
    over, under = map(implied_probability, (over_price, under_price))
    probability = over / (over + under)
    if sd is not None:
        sd = number(sd)
        if sd <= 0:
            raise ValueError("SD must be positive")
        mean = line + sd * statistics.NormalDist().inv_cdf(probability)
        if mean < 0:
            raise ValueError("Normal approximation implies negative production")
        return {"mean": mean, "variance": sd * sd,
                "model": "normal_approximation", "p_over": probability}
    if line % 1 != 0.5:
        raise ValueError("Count markets require a half-integer threshold")
    upper = max(10., line * 2)
    while poisson.sf(math.floor(line), upper) < probability:
        upper *= 2
    mean = brentq(lambda mu: poisson.sf(math.floor(line), mu) - probability,
                  0., upper)
    return {"mean": mean, "variance": mean, "model": "poisson",
            "p_over": probability}


def convert_snapshot(rows, *, provider_names, event_weeks, players, scoring,
                     required_stats, yardage_sd, fallbacks=None):
    """Return {(Sleeper pid, week): row} plus rejected-evidence diagnostics.

    players: [{pid, name}]. required_stats: {pid: [stat, ...]} explicitly
    enumerates all scoring components; missing components make anchor_fp null.
    scoring: linear Sleeper stat coefficients (no default scoring injected).
    yardage_sd: {(pid, week, stat): SD}. fallbacks: same keys, each containing
    team_stat_mean, share, source_ts, rationale. Team stat mean must be derived
    externally from a team total; points alone cannot identify player yards.
    """
    aliases = load_name_aliases()
    identities = defaultdict(list)
    for player in players:
        identities[resolve_provider_name(player["name"], aliases)].append(str(player["pid"]))
    groups = defaultdict(dict)
    diagnostics = []
    timestamps = set()
    for row in rows:
        if row.get("row_type") != "line":
            continue
        ts = row.get("fetched_at_utc")
        if not ts:
            raise ValueError("Line missing fetch timestamp")
        timestamps.add(ts)
        key = tuple(row.get(k) for k in ("event_id", "player_id", "book", "market", "line"))
        side = row.get("side")
        if side not in ("over", "under"):
            continue
        if side in groups[key]:
            raise ValueError("Duplicate side; pass exactly one snapshot")
        groups[key][side] = row
    if len(timestamps) > 1:
        raise ValueError("Do not mix fetches")
    estimates = defaultdict(list)
    events = {}
    for (event, provider_id, book, stat, line), pair in groups.items():
        matches = identities.get(resolve_provider_name(provider_names.get(provider_id, ""), aliases), [])
        week = event_weeks.get(event)
        if len(matches) != 1 or not isinstance(week, int) or isinstance(week, bool) or not 1 <= week <= 18:
            diagnostics.append({"event": event, "provider_id": provider_id, "reason": "unresolved_identity_or_week"})
            continue
        pid = matches[0]
        if stat not in required_stats.get(pid, []):
            continue
        if (pid, week) in events and events[pid, week] != event:
            raise ValueError("Multiple events for one player-week")
        events[pid, week] = event
        try:
            if set(pair) != {"over", "under"}:
                raise ValueError("Missing matching side")
            sd = yardage_sd.get((pid, week, stat))
            if stat.endswith("_yd") and sd is None:
                raise ValueError("Yardage SD assumption required")
            distribution = stat_distribution(line, pair["over"]["price"], pair["under"]["price"], sd=sd)
        except (ValueError, TypeError, KeyError) as exc:
            diagnostics.append({"pid": pid, "week": week, "stat": stat, "book": book, "reason": str(exc)})
            continue
        estimates[pid, week, stat].append(distribution)
    fallbacks = fallbacks or {}
    keys = set(events) | {(pid, week) for pid, week, stat in fallbacks}
    output = {}
    for pid, week in sorted(keys):
        stats, distributions, missing, used_fallback, sources = {}, {}, [], [], set()
        required = required_stats.get(pid, [])
        if not required or len(set(required)) != len(required):
            raise ValueError("Require unique scoring components for every player")
        if "rush_rec_yd" in required and ({"rush_yd", "rec_yd"} & set(required)):
            raise ValueError("Overlapping yardage components")
        if "td" in required and ({"rush_td", "rec_td"} & set(required)):
            raise ValueError("Overlapping touchdown components")
        for stat in required:
            number(scoring[stat])  # fail closed for unsupported scoring
            values = estimates.get((pid, week, stat), [])
            if values:
                # Equal-book mixture preserves within- and between-book variance.
                mean = statistics.mean(d["mean"] for d in values)
                variance = statistics.mean(d["variance"] + (d["mean"] - mean)**2 for d in values)
                stats[stat] = mean
                distributions[stat] = {"mean": mean, "variance": variance, "books": len(values), "models": sorted({d["model"] for d in values})}
                sources.update(timestamps)
            elif (pid, week, stat) in fallbacks:
                fallback = fallbacks[pid, week, stat]
                share, total = number(fallback["share"]), number(fallback["team_stat_mean"])
                if not 0 <= share <= 1 or total < 0 or not fallback.get("source_ts") or not fallback.get("rationale"):
                    raise ValueError("Invalid documented team-share fallback")
                stats[stat] = share * total
                used_fallback.append({"stat": stat, **fallback})
                sources.add(fallback["source_ts"])
            else:
                missing.append(stat)
        output[pid, week] = {
            "anchor_fp": None if missing else sum(stats[s] * number(scoring[s]) for s in required),
            "implied_stats": stats, "stat_distributions": distributions,
            "source_ts": min(sources) if sources else None,
            "source_timestamps": sorted(sources),
            "confidence": "incomplete" if missing else "fallback" if used_fallback else "conditional_market",
            "missing_stats": missing, "fallbacks": used_fallback,
            "fp_variance": None,  # cross-stat covariance is not identified
        }
    return {"rows": output, "diagnostics": diagnostics}
