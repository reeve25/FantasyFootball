import json
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Any
import xgboost as xgb

from advisor_runtime.public_model_scorecard import (
    ROOT, MODEL_DIR, DEFAULT_METADATA, build_feature_table, select_tier, _matrix
)

def run_inference(season: int, week: int) -> dict[str, Any]:
    if not DEFAULT_METADATA.exists():
        return {"status": "error", "reason": "No public projection metadata found; run model-scorecard first."}
    
    cache_path = ROOT / "data" / "model_cache" / f"public_inference_{season}_w{week}.json"
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return cached
        except ValueError:
            pass

    metadata = json.loads(DEFAULT_METADATA.read_text(encoding="utf-8"))
    
    # 1. Build features including dummy rows for the target week
    # Force rebuild to fetch the latest 2026 data
    try:
        frame = build_feature_table(force=True, inference_season=season, inference_week=week)
    except Exception as e:
        return {"status": "error", "reason": f"Failed to build feature table: {type(e).__name__} {e}"}
        
    current_week = frame[(frame["season"] == season) & (frame["week"] == week)].copy()
    if current_week.empty:
        return {"status": "error", "reason": f"No players found for {season} week {week}"}
        
    # Check if ffopportunity actually covers the prior week.
    # If not, the roll3 features are silently pulling from the previous season,
    # which is stale. We must detect this and remove the ffopportunity columns
    # from available_columns so the fallback triggers.
    prior_season = season if week > 1 else season - 1
    prior_week = week - 1 if week > 1 else 18
    # We check the base dataframe BEFORE dummy rows to see if prior week exists
    prior_opp = frame[(frame["season"] == prior_season) & (frame["week"] == prior_week)]
    opp_missing = prior_opp["xfp_roll3"].isna().all() and prior_opp["expected_points"].isna().all()

    # Determine which features actually exist (coverage > 5% to ignore random stragglers)
    threshold = len(current_week) * 0.05
    available_columns = {
        col for col in current_week.columns
        if current_week[col].notna().sum() > threshold
    }
    
    if opp_missing:
        # Forcibly remove ffopportunity features so we fall back
        for col in ["xfp_roll3", "career_xfp_prior", "td_gap_roll3"]:
            available_columns.discard(col)
    
    tier_name, reason = select_tier(available_columns, metadata["tiers"])
    
    if not tier_name:
        return {
            "status": "fallback",
            "reason": reason,
            "tier_applied": None,
            "projections": {}
        }
        
    tier_info = metadata["tiers"][tier_name]
    features = tier_info["features"]
    
    model_path = MODEL_DIR / f"public_projection_xgb_{tier_name}.json"
    if not model_path.exists():
        return {"status": "error", "reason": f"Model for tier {tier_name} not found."}
        
    model = xgb.XGBRegressor()
    model.load_model(model_path)
    
    matrix = _matrix(current_week, features)
    predictions = model.predict(matrix)
    
    projections = {}
    for pid, pos, pred in zip(current_week["player_id"], current_week["position"], predictions):
        # Apply standard interval bounds
        radius = tier_info["interval_radius_80_by_position"].get(pos, 5.0)
        projections[pid] = {
            "pts": round(float(pred), 2),
            "floor": round(float(pred - radius), 2),
            "ceiling": round(float(pred + radius), 2),
        }
        
    result = {
        "status": "success",
        "tier_applied": tier_name,
        "freshness": "features fetched at inference time",
        "reason": reason,
        "projections": projections,
    }
    
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    
    return result
