"""Bounded discovery using the SAME legal-lineup calculator as explicit offers."""
from itertools import combinations, zip_longest
import time
from . import advisor as a


def discover(snapshot, manager=None, limit=3, max_candidates=66):
    players = snapshot.get("players") or {}
    rosters = snapshot.get("rosters") or []
    mine = next(r for r in rosters if int(r["roster_id"]) == a.MY_ROSTER_ID)
    others = [r for r in rosters if r is not mine]
    if manager:
        others = [r for r in others if a.normalize_text(r.get("manager", "")) == a.normalize_text(manager)]
        if len(others) != 1:
            raise ValueError("Manager must match one live roster exactly")
    def pool(roster):
        ids = [p for p in roster["player_ids"] if players.get(p, {}).get("pos") in a.CORE_POSITIONS and a._finite(players.get(p, {}).get("projection_pg")) is not None]
        return sorted(ids, key=lambda p: (-players[p]["projection_pg"], p))[:8]
    def value(ids):
        return sum(players[p]["projection_pg"] for p in ids)
    my_pool = pool(mine)
    schedules = []
    for other in others:
        theirs = pool(other)
        groups = []
        for n, m in ((1, 1), (2, 1), (1, 2), (2, 2)):
            pairs = [(give, get) for give in combinations(my_pool, n) for get in combinations(theirs, m)]
            # Only a cheap ordering heuristic. These sums NEVER establish
            # football value, fairness or a recommendation.
            pairs.sort(key=lambda pair: (abs(value(pair[0]) - value(pair[1])), pair))
            groups.append(pairs)
        schedules.append([(other, *pair) for row in zip_longest(*groups) for pair in row if pair])
    candidates = [item for row in zip_longest(*schedules) for item in row if item][:max(1, min(250, max_candidates))]
    original = a.optimize_lineup
    cache, keepalive = {}, {}
    def cached(ids, snap, week, slots=None):
        keepalive[id(snap)] = snap
        key = (id(snap), tuple(sorted(ids)), week, tuple(slots or []))
        if key not in cache:
            cache[key] = original(ids, snap, week, slots)
        return cache[key]
    a.optimize_lineup = cached
    rows, checked, incomplete, negative, padding = [], 0, 0, 0, 0
    started = time.monotonic()
    try:
        for other, give, get in candidates:
            if time.monotonic() - started > 22:
                break
            terms = a.resolve_explicit_trade(snapshot, [players[p]["name"] for p in give], [players[p]["name"] for p in get])
            terms.update(a.trade_horizon(snapshot, terms))
            result = a.evaluate_trade(snapshot, terms, source_checks=False)
            checked += 1
            ours, theirs = result["perspective_delta_pg"], result["counterparty_delta_pg"]
            if ours is None or theirs is None:
                incomplete += 1
                continue
            if ours < .5 or theirs < 0:
                negative += 1
                continue
            if result["perspective_forced_drops"] or result["counterparty_forced_drops"]:
                # Exact explicit-offer math still supports forced drops. A
                # fast discovery screen avoids recommending padding packages.
                padding += 1
                continue
            # Every added asset must improve its recipient's legal lineup in
            # some remaining week; speculative bench depth needs human evidence.
            slots = result["slots_compared"]
            useful = True
            for roster, outgoing, incoming, full in ((mine, give, get, result["perspective_after_pg"]), (other, get, give, result["counterparty_after_pg"])):
                after = [p for p in roster["player_ids"] if p not in outgoing] + list(incoming)
                for p in incoming:
                    without, _ = a._roster_average([x for x in after if x != p], snapshot, result["weeks"], slots)
                    if without is not None and full - without <= 0:
                        useful = False
            if not useful:
                padding += 1
                continue
            rows.append((ours + min(theirs, 2) * .2, terms))
        rows.sort(key=lambda r: (-r[0], r[1]["give"], r[1]["get"]))
        finalists = [a.evaluate_trade(snapshot, terms) for _, terms in rows[:max(1, min(limit, 5))]]
    finally:
        a.optimize_lineup = original
    return {
        "decision_type": "trade_discovery", "status": "research_shortlist_only",
        "actionable_trades": [], "shortlist": finalists,
        "coverage": {"managers": len(others), "players_per_roster_limit": 8, "evaluated": checked, "candidate_budget": len(candidates), "exhaustive": False},
        "excluded": {"incomplete_projection_math": incomplete, "insufficient_gain_or_counterparty_loss": negative, "forced_drop_or_noncontributing_padding": padding},
        "source_freshness": a.evidence_freshness(snapshot),
        "warnings": [
            "No offer is validated by this screen. Check current role/news and independent forecasts, then the exact stable current-year PPR Redraft Flock Fair Trade! verdict.",
            "Fast search is bounded, uses up to two players per side, requires >=0.5 lineup PPG for Reeve, no projected counterparty loss, and a contribution from every asset. It can miss useful deals.",
            "An empty shortlist means this screen found no candidate; it does not prove no good trade exists.",
        ],
    }
