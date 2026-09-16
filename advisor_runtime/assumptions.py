"""Validated, offline assumption inputs and conservative weekly mean blending.

Internal weights are not calibrated probabilities. No network or evaluator
integration lives here. See docs/ASSUMPTIONS.md for the input contract.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path


ASSUMPTION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["player", "week_range", "stat_affected", "delta", "confidence",
                 "rationale", "source", "half_life_weeks"],
    "properties": {
        "player": {"type": "string", "minLength": 1},
        "week_range": {"type": "array", "minItems": 2, "maxItems": 2,
                       "items": {"type": "integer", "minimum": 1, "maximum": 18}},
        "stat_affected": {"type": "string", "minLength": 1},
        "delta": {"type": "number"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string", "minLength": 1},
        "source": {"type": "string", "minLength": 1},
        "half_life_weeks": {"type": "number", "exclusiveMinimum": 0},
        "type": {"enum": ["stat", "injury", "workload"]},
    },
    "allOf": [{"if": {"properties": {"stat_affected": {"const": "p_active"}}},
               "then": {"required": ["type"], "properties": {
                   "type": {"enum": ["injury", "workload"]},
                   "delta": {"minimum": -1, "maximum": 0}}}}],
}
REGISTRY_SCHEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema",
                   "title": "Internal assumption registry", "type": "array",
                   "uniqueItems": True, "items": ASSUMPTION_SCHEMA}


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _week(value):
    if type(value) is not int or not 1 <= value <= 18:
        raise ValueError("week must be an integer from 1 through 18")
    return value


def validate_registry(registry):
    """Validate schema plus ordered ranges/finite values; return a private copy."""
    if not isinstance(registry, list):
        raise ValueError("Registry must be a JSON array")
    seen = set()
    for item in registry:
        if not isinstance(item, dict):
            raise ValueError("Each assumption must be an object")
        if set(item) - set(ASSUMPTION_SCHEMA["properties"]) or set(ASSUMPTION_SCHEMA["required"]) - set(item):
            raise ValueError("Unknown or missing assumption fields")
        for key in ("player", "stat_affected", "rationale", "source"):
            if not isinstance(item[key], str) or not item[key].strip():
                raise ValueError(f"{key} must be nonempty text")
        span = item["week_range"]
        if not isinstance(span, list) or len(span) != 2:
            raise ValueError("week_range must be [first, last], inclusive")
        if _week(span[0]) > _week(span[1]):
            raise ValueError("week_range must be ordered")
        delta = _number(item["delta"], "delta")
        weight = _number(item["confidence"], "confidence")
        half_life = _number(item["half_life_weeks"], "half_life_weeks")
        if not 0 <= weight <= 1 or half_life <= 0:
            raise ValueError("Invalid confidence or half life")
        if item.get("type", "stat") not in ("stat", "injury", "workload"):
            raise ValueError("Unknown assumption type")
        if item["stat_affected"] == "p_active" and (
            item.get("type") not in ("injury", "workload") or not -1 <= delta <= 0
        ):
            raise ValueError("p_active requires injury/workload and delta in [-1, 0]")
        fingerprint = json.dumps(item, sort_keys=True, allow_nan=False)
        if fingerprint in seen:
            raise ValueError("Duplicate assumption")
        seen.add(fingerprint)
    return copy.deepcopy(registry)


def load_registry(path):
    """Load curated local JSON only; source fields are never fetched."""
    return validate_registry(json.loads(Path(path).read_text(encoding="utf-8-sig")))


def apply(anchor, registry, *, player, week, scoring=None,
          priced_in_guard=None, anchor_is_conditional=False):
    """Blend a T2 row for one Sleeper player ID/week; never mutate inputs.

    Guard(assumption, week) returns True=already priced, False=checked/unpriced,
    None=unknown. Missing/unknown guard suppresses adjustments. Exceptions
    propagate so a failed evidence check cannot masquerade as a successful one.
    p_active delta is relative to weight 1 and requires an explicitly conditional
    (fully active) anchor. This is an internal mean adjustment, not absence advice.
    """
    items = validate_registry(registry)
    _week(week)
    if not isinstance(player, str) or not player.strip():
        raise ValueError("player must be a Sleeper ID string")
    if type(anchor_is_conditional) is not bool:
        raise ValueError("anchor_is_conditional must be boolean")
    base = anchor.get("anchor_fp")
    if base is not None:
        base = _number(base, "anchor_fp")
    effects = []
    for index, item in enumerate(items):
        if item["player"] != player or not item["week_range"][0] <= week <= item["week_range"][1]:
            continue
        effect = {"assumption_index": index, "stat_affected": item["stat_affected"],
                  "rationale": item["rationale"], "source": item["source"],
                  "status": "pending", "applied_fp_delta": 0.0}
        effects.append(effect)
        if base is None:
            effect["status"] = "missing_anchor"
            continue
        priced = priced_in_guard(copy.deepcopy(item), week) if priced_in_guard else None
        if priced is not None and type(priced) is not bool:
            raise ValueError("Guard must return True, False, or None")
        if priced is not False:
            effect["status"] = "already_priced" if priced is True else "pricing_unknown"
            continue
        stat = item["stat_affected"]
        if stat == "p_active":
            if not anchor_is_conditional:
                effect["status"] = "availability_basis_unknown"
                continue
            fp_delta = base * item["delta"]
        elif stat == "fantasy_points":
            fp_delta = item["delta"]
        else:
            if scoring is None or stat not in scoring:
                raise ValueError(f"Explicit scoring coefficient required for {stat}")
            fp_delta = item["delta"] * _number(scoring[stat], stat)
        decay = 2 ** (-(week - item["week_range"][0]) / item["half_life_weeks"])
        effect["requested_fp_delta"] = _number(fp_delta * item["confidence"] * decay, "weighted delta")
        effect["status"] = "applied"
    # Gross cap prevents opposing assumptions from hiding large adjustments.
    gross = _number(math.fsum(abs(e.get("requested_fp_delta", 0)) for e in effects), "gross delta")
    limit = .15 * abs(base) if base is not None else None
    scale = min(1., limit / gross) if gross and limit is not None else 1.
    for effect in effects:
        effect["applied_fp_delta"] = effect.get("requested_fp_delta", 0.) * scale
    delta = math.fsum(e["applied_fp_delta"] for e in effects)
    return {"player": player, "week": week, "anchor_fp": base,
            "adjusted_fp": None if base is None else _number(base + delta, "adjusted_fp"),
            "adjustment_fp": None if base is None else delta,
            "cap_fp": limit, "cap_applied": scale < 1., "attribution": effects,
            "variance": anchor.get("fp_variance") if not gross else None,
            "variance_status": "unchanged" if not gross else "unknown_after_adjustment"}
