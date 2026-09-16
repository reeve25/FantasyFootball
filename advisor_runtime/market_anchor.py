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


# T2d: provisional per-position, per-stat weekly yardage SDs (in yards),
# pending T2b's real settled-week empirical validation. See STATUS.md's T2d
# Decision Log for the full sourcing rationale. These are deliberately never
# per-player -- a per-player number needs T2b's settled-week validation, not
# a default, and this module never derives one on its own; a caller decides
# whether/how to use this table (see market_anchor_projection.py).
#
# Two considered and rejected real-data sources, in the order this repo asks
# them to be tried:
#  1. Cross-book line dispersion within one snapshot (different books post
#     different single thresholds for the same player/stat -- real and
#     common, ~42% of markets in one live fetch). Rejected: that dispersion
#     measures disagreement among bookmakers' own point estimates of the
#     mean, not the player's week-to-week outcome variance -- a different,
#     much smaller quantity. Using it would produce a confidently-labeled
#     but systematically-too-narrow SD, which is worse than an honest,
#     explicitly-provisional default.
#  2. True alt-line markets (the same book quoting multiple distinct
#     thresholds for the same player/stat, which would let two or more
#     quantiles of one consistent distribution be fit directly). Rejected:
#     the raw SGO payload was inspected and does not offer these -- exactly
#     one over/under pair per player/stat/event is requested and returned.
#
# PRIMARY stats (the position's dominant yardage stat) are instead derived
# from the engine's own backtested per-game FANTASY-POINT forecast SD
# (advisor_runtime/engine/ff_v6_3.py's SIGMA_POS -- measured residual SD of
# preseason projection vs. realised score, n=905 trades/3 seasons; see
# docs/TRAPS.md), divided by that stat's own linear scoring weight. This
# assumes ~all of a position's point variance comes from its dominant
# yardage stat, which overstates the true yardage-specific SD (some of that
# point variance is really touchdown/reception variance) -- a deliberate
# conservative bias (wider, less confident), never an underestimate:
#   QB pass_yd: 3.02 / 0.04 = 75.5   RB rush_yd: 3.85 / 0.10 = 38.5
#   WR rec_yd:  3.20 / 0.10 = 32.0   TE rec_yd:  2.27 / 0.10 = 22.7
# These land inside commonly cited public ranges for weekly NFL passing
# (~60-75 yd), rushing (~25-40 yd) and receiving (~20-35 yd) SDs, which is a
# sanity check on the conversion, not an independent empirical source.
#
# SECONDARY stats (present for some players at a position without defining
# it -- a receiving back's rec_yd, a mobile QB's rush_yd, a gadget WR's
# rush_yd) have no equivalent position-level backtest to convert, so each
# uses a separately-reasoned, smaller, conservative constant instead; see
# STATUS.md's T2d Decision Log for the reasoning behind each.
YARDAGE_SD_DEFAULTS = {
    ("QB", "pass_yd"): 75.5,
    ("QB", "rush_yd"): 16.0,
    ("RB", "rush_yd"): 38.5,
    ("RB", "rec_yd"): 15.0,
    ("WR", "rec_yd"): 32.0,
    ("WR", "rush_yd"): 9.0,
    ("TE", "rec_yd"): 22.7,
}


def default_yardage_sd(position, stat):
    """A provisional per-position weekly yardage SD, or None if uncovered.

    See YARDAGE_SD_DEFAULTS above for sourcing. Never per-player -- callers
    needing a validated per-player number must wait for T2b, not this.
    """
    return YARDAGE_SD_DEFAULTS.get((position, stat))


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
