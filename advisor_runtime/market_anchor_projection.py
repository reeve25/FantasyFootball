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

TOUCHDOWN_STAT = "td"
RECEPTION_STAT = "rec"

MARKET_ANCHOR_KEY = "market_anchor"
BLEND_KEY = "market_anchor_blend"

# T2d: deliberately narrowed to each position's core, reliably-posted
# yardage stat(s) only -- the exact scope of that ticket ("source the
# missing rec_yd / rush_yd SD"), not a full scoring replica. This is
# narrower than T4's original attempt, which required pass_td/pass_int/
# rush_td/rec_td/rec/WR-rush_yd/QB-rush_yd too and was null for every real
# player for TWO compounding reasons, only one of which was T2d's scope:
#   1. (T2d) rec_yd/rush_yd had no SD source at all -- fixed.
#   2. "rec_td"/"rush_td" can never be satisfied as REQUIRED stats:
#      SportsGameOdds only ever posts an aggregate anytime-TD market
#      ("touchdowns" -> stat key "td" in market_sources.
#      SPORTS_GAME_ODDS_STATS), never split by rushing vs. receiving. T2e
#      (this ticket) adds "td" back as an OPTIONAL stat instead -- see
#      resolve_touchdown_scoring/optional_stats_for below -- so it
#      contributes when the market has it without being required. Reception
#      counts (rec) were out of scope for T2e/T2d; a later session (see
#      STATUS.md) added "rec" as an OPTIONAL stat the same way, for RB/WR/TE.
#      WR/QB secondary rushing volume remains out of scope.
# anchor_fp is therefore a yardage+TD(+reception, RB/WR/TE) partial-scoring
# approximation by construction (see docs/MARKET_ANCHOR.md), still not a
# full replica of league scoring -- fumbles and two-point conversions are
# still never priced; see unmodeled_scoring_components below for explicit,
# per-player disclosure of exactly which real scoring components that is,
# rather than leaving a reader to notice the gap by omission.
# K is excluded outright -- Sleeper kicking uses nonlinear per-distance
# field-goal buckets with no single linear "kick_pts" coefficient, which
# this linear converter cannot model (market_anchor.py: "Nonlinear bonuses
# and position-dependent scoring need a separate adapter").
REQUIRED_STATS_BY_POSITION = {
    "QB": ["pass_yd"],
    "RB": ["rush_yd", "rec_yd"],
    "WR": ["rec_yd"],
    "TE": ["rec_yd"],
}
# T2e: every supported position can score an anytime touchdown (a QB mostly
# via rushing, since QBs essentially never receive); "td" is therefore
# offered as optional to all four, gated only by whether the league's own
# scoring makes it fairly priceable (see resolve_touchdown_scoring).
#
# Follow-up ticket (receptions): SportsGameOdds already posts a two-sided
# "receiving_receptions" market (market_sources.SPORTS_GAME_ODDS_STATS ->
# "rec") and market_anchor.stat_distribution already prices any two-sided
# count market via the same Poisson branch it uses for every other count
# stat -- "rec" needs no new SD table (it doesn't end with "_yd", so
# convert_snapshot never requires a yardage_sd entry for it) and no scoring
# synthesis like "td" needed (the market's own stat key already equals the
# league's own linear "rec" coefficient -- full PPR here, so this is never a
# guessed weight). Offered as optional, never required, so a player-week
# with no posted reception market still gets a real yardage(+TD) anchor
# rather than nulling out (see reception_scoring_usable/optional_stats_for).
# QB excluded: QBs essentially never catch passes, so pricing "rec" for them
# would be a market this repo has never observed, not a modeled component.
OPTIONAL_STATS_BY_POSITION = {
    "QB": [TOUCHDOWN_STAT],
    "RB": [TOUCHDOWN_STAT, RECEPTION_STAT],
    "WR": [TOUCHDOWN_STAT, RECEPTION_STAT],
    "TE": [TOUCHDOWN_STAT, RECEPTION_STAT],
}

# Real full-PPR scoring components this converter still does not price for
# anyone, regardless of market coverage -- no SGO market exists for these at
# all, so they can never degrade-gracefully like "td"/"rec"; they are simply
# absent from anchor_fp. Reported explicitly (see unmodeled_scoring_
# components) rather than left for a reader to notice by omission. Keyed by
# the real Sleeper scoring-settings stat name, so a component whose league
# coefficient is actually zero is correctly not reported as "unmodeled" (it
# wouldn't move anchor_fp even if priced).
UNMODELED_STATS_BY_POSITION = {
    "QB": ["pass_2pt", "rush_2pt", "fum_lost"],
    "RB": ["rush_2pt", "rec_2pt", "fum_lost"],
    "WR": ["rec_2pt", "rush_2pt", "fum_lost"],
    "TE": ["rec_2pt", "fum_lost"],
}


def unmodeled_scoring_components(
    scoring: dict[str, float], players: list[dict[str, Any]]
) -> dict[str, list[str]]:
    """{pid: [stat, ...]} -- real league-scored components this converter
    never prices for that position, restricted to ones the league actually
    assigns a nonzero weight (a zero-weighted stat isn't a modeling gap).
    Never mutates inputs; a position outside UNMODELED_STATS_BY_POSITION
    (K/DEF) is simply absent, not zero-filled."""
    out: dict[str, list[str]] = {}
    for player in players:
        pos = player.get("pos")
        candidates = UNMODELED_STATS_BY_POSITION.get(pos, [])
        present = sorted(stat for stat in candidates if scoring.get(stat))
        if present:
            out[str(player["pid"])] = present
    return out


def reception_scoring_usable(scoring: dict[str, float]) -> bool:
    """Whether the league's own "rec" coefficient exists and is numeric.

    Unlike touchdown_stat, "rec" needs no cross-stat agreement check --
    SportsGameOdds' reception market key already matches the real Sleeper
    scoring key one-to-one, so there is no ambiguous aggregate to resolve.
    """
    value = scoring.get(RECEPTION_STAT)
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def resolve_touchdown_scoring(scoring: dict[str, float]) -> tuple[dict[str, float], bool]:
    """(scoring-with-"td"-key-if-usable, td_usable). Never mutates the input.

    T2e. SportsGameOdds's "touchdowns" market is a single anytime-TD
    (rushing OR receiving, never passing) market with no per-position split
    -- see market_anchor.py's convert_snapshot docstring. It is only fairly
    priceable when the league's own rush_td and rec_td coefficients agree
    (this league: both 6.0): using a mismatched aggregate coefficient would
    misrepresent value, so when they differ (or either is absent) the TD
    component degrades to unavailable rather than guessing which one to use
    -- the ticket's "do not fabricate" rule applied to the scoring weight,
    not just the market-implied value. Weights always come from the
    caller's real scoring config; nothing here is hardcoded.
    """
    rush = scoring.get("rush_td")
    rec = scoring.get("rec_td")
    if rush is None or rush != rec:
        return dict(scoring), False
    resolved = dict(scoring)
    resolved[TOUCHDOWN_STAT] = rush
    return resolved, True


def optional_stats_for(
    players: list[dict[str, Any]], td_usable: bool, rec_usable: bool = False
) -> dict[str, list[str]]:
    """rec_usable defaults False so every pre-reception caller (T2e's own
    tests, T2f, T5's default `run_backtest` param) is byte-for-byte
    unchanged unless it opts in -- same discipline T2e used for td_usable."""
    enabled = {stat for stat, usable in ((TOUCHDOWN_STAT, td_usable), (RECEPTION_STAT, rec_usable)) if usable}
    if not enabled:
        return {}
    result = {}
    for player in players:
        stats = [stat for stat in OPTIONAL_STATS_BY_POSITION.get(player.get("pos"), []) if stat in enabled]
        if stats:
            result[str(player["pid"])] = stats
    return result


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

    T2e: the anytime-TD market ("td") is always passed to convert_snapshot as
    OPTIONAL, never required -- see resolve_touchdown_scoring and
    optional_stats_for. When the market isn't posted for a player-week (or
    the league's rush_td/rec_td coefficients don't agree closely enough to
    price it fairly at all), the anchor degrades to yardage-only rather than
    going null; `attribution[pid][week]["confidence"]`/`"optional_missing"`
    and the top-level `td_scoring_usable` report exactly which case applied.
    """
    players = [p for p in players if p.get("pos") in REQUIRED_STATS_BY_POSITION]
    provider_names, event_weeks = build_identity_inputs(line_rows)
    required_stats = required_stats_for(players)
    resolved_scoring, td_usable = resolve_touchdown_scoring(scoring)
    rec_usable = reception_scoring_usable(scoring)
    optional_stats = optional_stats_for(players, td_usable, rec_usable)
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
        scoring=resolved_scoring,
        required_stats=required_stats,
        yardage_sd=resolved_sd,
        fallbacks=fallbacks or {},
        optional_stats=optional_stats,
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
            scoring=resolved_scoring,
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
            # T2e: "confidence" is "yardage_only" when the anytime-TD market
            # wasn't posted for this player-week (or wasn't fairly
            # priceable at all -- see td_usable below), "conditional_market"
            # when it was and contributed. "incomplete"/"fallback" from a
            # required-stat gap always take priority (set by convert_snapshot).
            "confidence": anchor_row["confidence"],
            "optional_missing": anchor_row["optional_missing"],
            # Component-level disclosure (this session's fix): the actual
            # per-stat market-implied value that summed into anchor_fp, so a
            # caller (T5's backtest, in particular) can compare the market's
            # OWN implied stat line against a realized stat line component by
            # component -- distinguishing "the market was wrong about yards"
            # from "our blend/converter logic is wrong given a correct
            # anchor" -- rather than only ever comparing final fantasy-point
            # totals, which conflates the two.
            "implied_stats": dict(anchor_row["implied_stats"]),
        }
    return {
        "sources": sources,
        "diagnostics": converted["diagnostics"],
        "attribution": attribution,
        "provisional_sd_stats": sorted({key[2] for key in provisional_sd_keys}),
        # T2e: whether the league's own rush_td/rec_td coefficients agreed
        # closely enough to price the anytime-TD market at all this run --
        # see resolve_touchdown_scoring. False means every anchor this run
        # is yardage-only regardless of market coverage, not a per-player gap.
        "td_scoring_usable": td_usable,
        # Same idea for receptions: whether the league's own "rec" coefficient
        # was numeric this run. False means "rec" was never offered as an
        # optional stat to anyone, regardless of market coverage.
        "rec_scoring_usable": rec_usable,
        # This session's fix: real full-PPR components (fumbles, 2pt
        # conversions) this converter still never prices, regardless of
        # market coverage -- explicit disclosure so a caller cannot mistake
        # a yardage+TD+reception anchor for a complete scoring replica.
        "unmodeled_scoring_components": unmodeled_scoring_components(scoring, players),
        # T2f: the scoring dict actually used above (with "td" merged in when
        # usable), so a caller extending market_anchor_blend with
        # apply_consensus_fallback prices any stat-specific assumption with
        # the identical coefficients, not a second, possibly-inconsistent copy.
        "resolved_scoring": resolved_scoring,
    }


def apply_consensus_fallback(
    players_by_id: dict[str, dict[str, Any]],
    sources: dict[str, dict[str, dict[str, float]]],
    *,
    assumption_registry: list[dict[str, Any]] | None = None,
    priced_in_guard=None,
    scoring: dict[str, float] | None = None,
    weeks: range = range(1, 19),
) -> tuple[dict[str, dict[str, dict[str, float]]], dict[str, dict[str, str]]]:
    """T2f: extend market_anchor_blend to every week a fresh fetch didn't
    reach, using the player's existing sleeper+espn consensus
    (player["weekly_points"], the same field _projection_for_week's default
    path already reads) as that week's input to the identical
    assumptions.apply() call an anchored week already goes through -- so
    T3's 15% cap and every other guard apply uniformly to both, with no
    special-casing. "market_anchor" (pure) is untouched: this only extends
    "market_anchor_blend", and only ever fills a week market_anchor_blend
    doesn't already have a real (non-null) value for -- an anchored week is
    never touched or double-counted through the fallback path.

    Detecting "has a market line": exactly whatever compute_projection_sources
    already put in market_anchor_blend for that week from the fetched
    snapshot's own event_metadata (T2c's season_week field) -- no separate
    detection mechanism. In practice a single fetch only ever has near-term
    lines (SportsGameOdds posts player props ~1 week ahead, never a full
    season in one call), so today this means "the current week is anchored,
    every other week in range is consensus." See STATUS.md's T2f Decision
    Log for why a hard per-week switch was used instead of a partial
    within-week blend: the two estimates have no calibrated, comparable
    variance to combine (market_anchor_blend's variance already becomes
    "unknown" once any T3 adjustment applies, and the sleeper+espn consensus
    was never assigned one either), so there is no principled weighting
    besides "whichever single evidence source exists for that week."

    Returns (merged_sources, provenance). provenance[pid][week_str] is
    "anchored" (already a real posted-line-derived value) or "consensus"
    (no line existed for that week; the sleeper+espn average was used as
    T3's input instead). A week absent from provenance had neither a market
    anchor nor a consensus projection (bye/unprojected) -- still missing,
    never zero-filled.
    """
    registry = assumption_registry or []
    merged: dict[str, dict[str, dict[str, float]]] = {
        pid: {key: dict(points) for key, points in player_sources.items()}
        for pid, player_sources in sources.items()
    }
    provenance: dict[str, dict[str, str]] = {}
    for pid, player in players_by_id.items():
        blend_key_dict = merged.setdefault(
            pid, {MARKET_ANCHOR_KEY: {}, BLEND_KEY: {}}
        ).setdefault(BLEND_KEY, {})
        player_provenance = {week_str: "anchored" for week_str in blend_key_dict}
        consensus = player.get("weekly_points") or {}
        for week in weeks:
            week_str = str(week)
            if week_str in blend_key_dict:
                continue  # already anchored this run; never overwritten
            consensus_value = consensus.get(week_str)
            if consensus_value is None:
                continue  # genuinely no evidence for this week; leave missing
            synthetic_anchor = {"anchor_fp": float(consensus_value), "fp_variance": None}
            blended = assumptions_module.apply(
                synthetic_anchor, registry, player=pid, week=week,
                scoring=scoring, priced_in_guard=priced_in_guard,
            )
            if blended["adjusted_fp"] is not None:
                blend_key_dict[week_str] = blended["adjusted_fp"]
                player_provenance[week_str] = "consensus"
        if player_provenance:
            provenance[pid] = player_provenance
    return merged, provenance


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
