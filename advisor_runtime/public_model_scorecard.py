"""Point-in-time public-data projection scorecard and model trainer.

The evaluation seasons are 2021-2025.  Every row is forecast from information
available before that game week: rolling player history is shifted, consensus
rankings are selected before the first kickoff, and matchup features use only
prior opponent games.  Raw downloads are cached locally and never committed.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import nflreadpy as nfl
import numpy as np
import pandas as pd
import polars as pl
import xgboost as xgb
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "model_cache"
MODEL_DIR = ROOT / "models"
DEFAULT_REPORT = ROOT.parent / "docs" / "model_scorecard.json"
DEFAULT_MODEL = MODEL_DIR / "public_projection_xgb.json"
DEFAULT_METADATA = MODEL_DIR / "public_projection_metadata.json"
EVALUATION_SEASONS = tuple(range(2021, 2026))
SELECTION_SEASONS = (2020,)
DATA_SEASONS = tuple(range(2018, 2026))
POSITIONS = ("QB", "RB", "WR", "TE")

# Exact offensive scoring from league 1327873074195886081.  K/DEF are excluded
# because ffopportunity models offensive plays only.
LEAGUE_SCORING = {
    "pass_yd": 0.04,
    "pass_td": 4.0,
    "pass_int": -1.0,
    "rush_yd": 0.1,
    "rush_td": 6.0,
    "rec": 1.0,
    "rec_yd": 0.1,
    "rec_td": 6.0,
    "fum_lost": -2.0,
    "pass_2pt": 2.0,
    "rush_2pt": 2.0,
    "rec_2pt": 2.0,
}

BASE_FEATURES = ["actual_roll3", "career_actual_prior"]
XFPO_FEATURES = BASE_FEATURES + ["xfp_roll3", "career_xfp_prior", "td_gap_roll3"]
MARKET_FEATURES = XFPO_FEATURES + ["implied_total"]
STRUCTURAL_GROUPS = {
    "player_stats": ["target_share_roll3", "air_yards_share_roll3", "wopr_roll3", "racr_roll3"],
    "snap_counts": ["snap_share_roll3"],
    "participation": ["pass_play_participation_roll3"],
    "nextgen_stats": [
        "ngs_rec_separation_roll3",
        "ngs_rec_yac_oe_roll3",
        "ngs_rush_ryoe_pa_roll3",
        "ngs_pass_cpoe_roll3",
    ],
    "ftn_charting": [
        "ftn_motion_rate_roll3",
        "ftn_play_action_rate_roll3",
        "ftn_catchable_rate_roll3",
        "ftn_drop_rate_roll3",
    ],
}
CONSENSUS_FEATURES = ["weekly_ecr", "weekly_ecr_sd", "weekly_ecr_range"]


def normalize_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", text.lower())
    return "".join(ch for ch in text if ch.isalnum())


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(0.0, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def score_actual(frame: pd.DataFrame) -> pd.Series:
    return (
        _numeric(frame, "pass_yards_gained") * LEAGUE_SCORING["pass_yd"]
        + _numeric(frame, "pass_touchdown") * LEAGUE_SCORING["pass_td"]
        + _numeric(frame, "pass_interception") * LEAGUE_SCORING["pass_int"]
        + _numeric(frame, "rush_yards_gained") * LEAGUE_SCORING["rush_yd"]
        + _numeric(frame, "rush_touchdown") * LEAGUE_SCORING["rush_td"]
        + _numeric(frame, "receptions") * LEAGUE_SCORING["rec"]
        + _numeric(frame, "rec_yards_gained") * LEAGUE_SCORING["rec_yd"]
        + _numeric(frame, "rec_touchdown") * LEAGUE_SCORING["rec_td"]
        + (_numeric(frame, "rec_fumble_lost") + _numeric(frame, "rush_fumble_lost"))
        * LEAGUE_SCORING["fum_lost"]
        + _numeric(frame, "pass_two_point_conv") * LEAGUE_SCORING["pass_2pt"]
        + _numeric(frame, "rush_two_point_conv") * LEAGUE_SCORING["rush_2pt"]
        + _numeric(frame, "rec_two_point_conv") * LEAGUE_SCORING["rec_2pt"]
    )


def score_expected(frame: pd.DataFrame) -> pd.Series:
    return (
        _numeric(frame, "pass_yards_gained_exp") * LEAGUE_SCORING["pass_yd"]
        + _numeric(frame, "pass_touchdown_exp") * LEAGUE_SCORING["pass_td"]
        + _numeric(frame, "pass_interception_exp") * LEAGUE_SCORING["pass_int"]
        + _numeric(frame, "rush_yards_gained_exp") * LEAGUE_SCORING["rush_yd"]
        + _numeric(frame, "rush_touchdown_exp") * LEAGUE_SCORING["rush_td"]
        + _numeric(frame, "receptions_exp") * LEAGUE_SCORING["rec"]
        + _numeric(frame, "rec_yards_gained_exp") * LEAGUE_SCORING["rec_yd"]
        + _numeric(frame, "rec_touchdown_exp") * LEAGUE_SCORING["rec_td"]
        + _numeric(frame, "pass_two_point_conv_exp") * LEAGUE_SCORING["pass_2pt"]
        + _numeric(frame, "rush_two_point_conv_exp") * LEAGUE_SCORING["rush_2pt"]
        + _numeric(frame, "rec_two_point_conv_exp") * LEAGUE_SCORING["rec_2pt"]
    )


def _to_pandas(frame: Any) -> pd.DataFrame:
    return frame.to_pandas() if isinstance(frame, pl.DataFrame) else frame.copy()


def _base_frame(seasons: Iterable[int]) -> pd.DataFrame:
    frame = _to_pandas(nfl.load_ff_opportunity(list(seasons), "weekly"))
    frame = frame[(frame["week"] <= 18) & frame["position"].isin(POSITIONS)].copy()
    frame["season"] = pd.to_numeric(frame["season"], errors="coerce").astype(int)
    frame["week"] = pd.to_numeric(frame["week"], errors="coerce").astype(int)
    frame["player_id"] = frame["player_id"].astype(str)
    frame["actual_points"] = score_actual(frame)
    frame["expected_points"] = score_expected(frame)
    frame["actual_tds"] = (
        _numeric(frame, "pass_touchdown")
        + _numeric(frame, "rush_touchdown")
        + _numeric(frame, "rec_touchdown")
    )
    frame["expected_tds"] = (
        _numeric(frame, "pass_touchdown_exp")
        + _numeric(frame, "rush_touchdown_exp")
        + _numeric(frame, "rec_touchdown_exp")
    )
    frame["td_gap"] = frame["expected_tds"] - frame["actual_tds"]
    frame["norm_name"] = frame["full_name"].map(normalize_name)
    keep = [
        "season", "week", "game_id", "player_id", "full_name", "norm_name",
        "position", "posteam", "actual_points", "expected_points", "td_gap",
    ]
    return frame[keep]


def _schedule_features(seasons: Iterable[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    schedule = _to_pandas(nfl.load_schedules(list(seasons)))
    schedule = schedule[(schedule["game_type"] == "REG") & (schedule["week"] <= 18)].copy()
    schedule["gameday"] = pd.to_datetime(schedule["gameday"], errors="coerce")
    total_line = pd.to_numeric(schedule["total_line"], errors="coerce")
    spread_line = pd.to_numeric(schedule["spread_line"], errors="coerce")
    schedule["home_implied"] = (total_line - spread_line) / 2.0
    schedule["away_implied"] = (total_line + spread_line) / 2.0
    home = schedule[["season", "week", "home_team", "home_implied"]].rename(
        columns={"home_team": "posteam", "home_implied": "implied_total"}
    )
    away = schedule[["season", "week", "away_team", "away_implied"]].rename(
        columns={"away_team": "posteam", "away_implied": "implied_total"}
    )
    implied = pd.concat([home, away], ignore_index=True).drop_duplicates(["season", "week", "posteam"])
    cutoffs = schedule.groupby(["season", "week"], as_index=False)["gameday"].min()
    return implied, cutoffs


def _player_stats_features(seasons: Iterable[int]) -> pd.DataFrame:
    frame = _to_pandas(nfl.load_player_stats(list(seasons), "week"))
    frame["player_id"] = frame["player_id"].astype(str)
    columns = ["player_id", "season", "week", "target_share", "air_yards_share", "wopr", "racr"]
    return frame[[column for column in columns if column in frame]].drop_duplicates(["player_id", "season", "week"])


def _snap_features(seasons: Iterable[int]) -> pd.DataFrame:
    frame = _to_pandas(nfl.load_snap_counts(list(seasons)))
    frame["norm_name"] = frame["player"].map(normalize_name)
    frame["snap_share"] = pd.to_numeric(frame["offense_pct"], errors="coerce")
    if frame["snap_share"].max(skipna=True) > 1.5:
        frame["snap_share"] /= 100.0
    return frame[["season", "week", "team", "norm_name", "snap_share"]].rename(columns={"team": "posteam"})


def _participation_features(seasons: Iterable[int]) -> pd.DataFrame:
    frame = _to_pandas(nfl.load_participation(list(seasons)))
    game_parts = frame["nflverse_game_id"].astype(str).str.split("_", expand=True)
    frame["season"] = pd.to_numeric(game_parts[0], errors="coerce")
    frame["week"] = pd.to_numeric(game_parts[1], errors="coerce")
    frame["pass_like"] = (
        frame["route"].fillna("").astype(str).str.len().gt(0)
        | pd.to_numeric(frame["time_to_throw"], errors="coerce").notna()
        | pd.to_numeric(frame["ngs_air_yards"], errors="coerce").notna()
    )
    denominator = (
        frame[frame["pass_like"]]
        .groupby(["season", "week", "possession_team"], as_index=False)
        .size()
        .rename(columns={"size": "team_pass_plays", "possession_team": "posteam"})
    )
    exploded = frame[["season", "week", "possession_team", "pass_like", "offense_players"]].copy()
    exploded["player_id"] = exploded["offense_players"].fillna("").str.split(";")
    exploded = exploded.explode("player_id")
    exploded = exploded[exploded["player_id"].ne("") & exploded["pass_like"]]
    counts = (
        exploded.groupby(["season", "week", "possession_team", "player_id"], as_index=False)
        .size()
        .rename(columns={"size": "player_pass_plays", "possession_team": "posteam"})
    )
    counts = counts.merge(denominator, on=["season", "week", "posteam"], how="left")
    counts["pass_play_participation"] = counts["player_pass_plays"] / counts["team_pass_plays"].replace(0, np.nan)
    return counts[["season", "week", "posteam", "player_id", "pass_play_participation"]]


def _nextgen_features(seasons: Iterable[int]) -> pd.DataFrame:
    specs = {
        "receiving": {
            "avg_separation": "ngs_rec_separation",
            "avg_yac_above_expectation": "ngs_rec_yac_oe",
        },
        "rushing": {"rush_yards_over_expected_per_att": "ngs_rush_ryoe_pa"},
        "passing": {"completion_percentage_above_expectation": "ngs_pass_cpoe"},
    }
    merged: pd.DataFrame | None = None
    for stat_type, rename in specs.items():
        frame = _to_pandas(nfl.load_nextgen_stats(list(seasons), stat_type))
        frame = frame[frame["week"] > 0].copy()
        frame = frame.rename(columns=rename)
        columns = ["season", "week", "player_gsis_id", *rename.values()]
        frame = frame[columns].rename(columns={"player_gsis_id": "player_id"})
        frame["player_id"] = frame["player_id"].astype(str)
        merged = frame if merged is None else merged.merge(frame, on=["season", "week", "player_id"], how="outer")
    return merged if merged is not None else pd.DataFrame()


def _ftn_features(seasons: Iterable[int]) -> pd.DataFrame:
    available_seasons = [season for season in seasons if season >= 2022]
    frame = _to_pandas(nfl.load_ftn_charting(available_seasons))
    metrics = {
        "is_motion": "ftn_motion_rate",
        "is_play_action": "ftn_play_action_rate",
        "is_catchable_ball": "ftn_catchable_rate",
        "is_drop": "ftn_drop_rate",
    }
    for source in metrics:
        frame[source] = frame[source].astype(float)
    result = frame.groupby(["season", "week", "nflverse_game_id"], as_index=False)[list(metrics)].mean()
    return result.rename(columns={"nflverse_game_id": "game_id", **metrics})


def _ranking_features(cutoffs: pd.DataFrame) -> pd.DataFrame:
    rankings = nfl.load_ff_rankings("all")
    page_types = [
        *(f"weekly-{position.lower()}" for position in POSITIONS),
        *(f"redraft-{position.lower()}" for position in POSITIONS),
    ]
    rankings = rankings.filter(pl.col("page_type").is_in(page_types))
    frame = rankings.to_pandas()
    frame["scrape_date"] = pd.to_datetime(frame["scrape_date"], errors="coerce")
    frame["norm_name"] = frame["player"].map(normalize_name)
    for column in ("ecr", "sd", "best", "worst"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    rows: list[pd.DataFrame] = []
    for cutoff in cutoffs.itertuples(index=False):
        eligible = frame[frame["scrape_date"] < cutoff.gameday]
        if eligible.empty:
            continue
        latest_by_page = eligible.groupby("page_type")["scrape_date"].transform("max")
        current = eligible[eligible["scrape_date"] == latest_by_page].copy()
        current["season"] = int(cutoff.season)
        current["week"] = int(cutoff.week)
        current["ranking_scope"] = np.where(current["page_type"].str.startswith("weekly"), "weekly", "ros")
        current["ecr_range"] = current["worst"] - current["best"]
        rows.append(current[["season", "week", "ranking_scope", "norm_name", "team", "ecr", "sd", "ecr_range"]])
    if not rows:
        return pd.DataFrame()
    combined = pd.concat(rows, ignore_index=True)
    combined = combined.sort_values("ecr").drop_duplicates(["season", "week", "ranking_scope", "norm_name"])
    weekly = combined[combined["ranking_scope"] == "weekly"].rename(
        columns={"ecr": "weekly_ecr", "sd": "weekly_ecr_sd", "ecr_range": "weekly_ecr_range"}
    )
    ros = combined[combined["ranking_scope"] == "ros"].rename(
        columns={"ecr": "ros_ecr", "sd": "ros_ecr_sd", "ecr_range": "ros_ecr_range"}
    )
    return weekly[["season", "week", "norm_name", "weekly_ecr", "weekly_ecr_sd", "weekly_ecr_range"]].merge(
        ros[["season", "week", "norm_name", "ros_ecr", "ros_ecr_sd", "ros_ecr_range"]],
        on=["season", "week", "norm_name"],
        how="outer",
    )


def _rolling_features(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.sort_values(["player_id", "season", "week"]).copy()
    raw_to_rolling = {
        "actual_points": "actual_roll3",
        "expected_points": "xfp_roll3",
        "td_gap": "td_gap_roll3",
        "target_share": "target_share_roll3",
        "air_yards_share": "air_yards_share_roll3",
        "wopr": "wopr_roll3",
        "racr": "racr_roll3",
        "snap_share": "snap_share_roll3",
        "pass_play_participation": "pass_play_participation_roll3",
        "ngs_rec_separation": "ngs_rec_separation_roll3",
        "ngs_rec_yac_oe": "ngs_rec_yac_oe_roll3",
        "ngs_rush_ryoe_pa": "ngs_rush_ryoe_pa_roll3",
        "ngs_pass_cpoe": "ngs_pass_cpoe_roll3",
        "ftn_motion_rate": "ftn_motion_rate_roll3",
        "ftn_play_action_rate": "ftn_play_action_rate_roll3",
        "ftn_catchable_rate": "ftn_catchable_rate_roll3",
        "ftn_drop_rate": "ftn_drop_rate_roll3",
    }
    for source, target in raw_to_rolling.items():
        if source not in frame:
            frame[source] = np.nan
        frame[target] = frame.groupby("player_id")[source].transform(
            lambda values: values.shift(1).rolling(3, min_periods=1).mean()
        )
    frame["career_actual_prior"] = frame.groupby("player_id")["actual_points"].transform(
        lambda values: values.shift(1).expanding().mean()
    )
    frame["career_xfp_prior"] = frame.groupby("player_id")["expected_points"].transform(
        lambda values: values.shift(1).expanding().mean()
    )
    return frame


def build_feature_table(force: bool = False) -> pd.DataFrame:
    cache_path = CACHE_DIR / "public_features_v1.parquet"
    if cache_path.exists() and not force:
        return pd.read_parquet(cache_path)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    base = _base_frame(DATA_SEASONS)
    implied, cutoffs = _schedule_features(DATA_SEASONS)
    base = base.merge(implied, on=["season", "week", "posteam"], how="left")
    base = base.merge(_player_stats_features(DATA_SEASONS), on=["player_id", "season", "week"], how="left")
    base = base.merge(_snap_features(DATA_SEASONS), on=["season", "week", "posteam", "norm_name"], how="left")
    base = base.merge(_participation_features(DATA_SEASONS), on=["season", "week", "posteam", "player_id"], how="left")
    base = base.merge(_nextgen_features(DATA_SEASONS), on=["season", "week", "player_id"], how="left")
    base = base.merge(_ftn_features(DATA_SEASONS), on=["season", "week", "game_id"], how="left")
    base = base.merge(_ranking_features(cutoffs), on=["season", "week", "norm_name"], how="left")
    base = _rolling_features(base)
    base.to_parquet(cache_path, index=False)
    return base


def _matrix(frame: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    matrix = frame.reindex(columns=features).apply(pd.to_numeric, errors="coerce")
    positions = pd.get_dummies(frame["position"], prefix="pos", dtype=float)
    for position in POSITIONS:
        column = f"pos_{position}"
        if column not in positions:
            positions[column] = 0.0
    return pd.concat([matrix, positions[[f"pos_{position}" for position in POSITIONS]]], axis=1)


def _model() -> xgb.XGBRegressor:
    return xgb.XGBRegressor(
        objective="reg:absoluteerror",
        n_estimators=220,
        max_depth=3,
        learning_rate=0.035,
        min_child_weight=8,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=8.0,
        n_jobs=-1,
        random_state=20260915,
    )


def _baseline_prediction(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    position_mean = train.groupby("position")["actual_points"].mean().to_dict()
    overall = float(train["actual_points"].mean())
    values = test["actual_roll3"].combine_first(test["career_actual_prior"])
    return np.array([
        float(value) if pd.notna(value) else float(position_mean.get(position, overall))
        for value, position in zip(values, test["position"])
    ])


def walk_forward_predictions(
    frame: pd.DataFrame,
    features: list[str] | None,
    seasons: Iterable[int] = EVALUATION_SEASONS,
) -> pd.DataFrame:
    predictions: list[pd.DataFrame] = []
    for season in seasons:
        train = frame[frame["season"] < season].copy()
        test = frame[frame["season"] == season].copy()
        if train.empty or test.empty:
            continue
        calibration_season = season - 1
        calibration_train = frame[frame["season"] < calibration_season].copy()
        calibration = frame[frame["season"] == calibration_season].copy()
        if features is None:
            test_prediction = _baseline_prediction(train, test)
            calibration_prediction = _baseline_prediction(calibration_train, calibration) if not calibration_train.empty else _baseline_prediction(train, calibration)
        else:
            model = _model()
            model.fit(_matrix(train, features), train["actual_points"])
            test_prediction = model.predict(_matrix(test, features))
            if calibration_train.empty:
                calibration_train = train
            calibration_model = _model()
            calibration_model.fit(_matrix(calibration_train, features), calibration_train["actual_points"])
            calibration_prediction = calibration_model.predict(_matrix(calibration, features))
        calibration = calibration.copy()
        calibration["absolute_error"] = np.abs(calibration["actual_points"] - calibration_prediction)
        quantiles = calibration.groupby("position")["absolute_error"].quantile(0.80).to_dict()
        fallback_quantile = float(calibration["absolute_error"].quantile(0.80))
        result = test[["season", "week", "player_id", "full_name", "position", "actual_points"]].copy()
        result["prediction"] = test_prediction
        result["interval_radius"] = [quantiles.get(position, fallback_quantile) for position in result["position"]]
        predictions.append(result)
    return pd.concat(predictions, ignore_index=True)


def _mean_weekly_rank_correlation(frame: pd.DataFrame) -> float | None:
    values = []
    for _, group in frame.groupby(["season", "week"]):
        if len(group) < 5 or group["prediction"].nunique() < 2 or group["actual_points"].nunique() < 2:
            continue
        correlation = spearmanr(group["prediction"], group["actual_points"], nan_policy="omit").statistic
        if math.isfinite(correlation):
            values.append(float(correlation))
    return round(float(np.mean(values)), 4) if values else None


def weekly_metrics(predictions: pd.DataFrame) -> dict[str, Any]:
    errors = np.abs(predictions["prediction"] - predictions["actual_points"])
    by_position = {
        position: round(float(np.mean(np.abs(group["prediction"] - group["actual_points"]))), 4)
        for position, group in predictions.groupby("position")
    }
    by_season = {
        str(int(season)): round(float(np.mean(np.abs(group["prediction"] - group["actual_points"]))), 4)
        for season, group in predictions.groupby("season")
    }
    covered = errors <= predictions["interval_radius"]
    return {
        "n": int(len(predictions)),
        "mae": round(float(errors.mean()), 4),
        "mae_by_position": by_position,
        "mae_by_season": by_season,
        "mean_weekly_rank_correlation": _mean_weekly_rank_correlation(predictions),
        "interval_80_coverage": round(float(covered.mean()), 4),
        "interval_mean_width": round(float((predictions["interval_radius"] * 2.0).mean()), 4),
    }


def build_ros_frame(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    actual = frame[["season", "week", "player_id", "actual_points"]]
    for checkpoint in (3, 6, 9):
        current = frame[frame["week"] == checkpoint].copy()
        future = actual[(actual["week"] >= checkpoint) & (actual["week"] <= 17)].groupby(
            ["season", "player_id"], as_index=False
        )["actual_points"].mean().rename(columns={"actual_points": "ros_target"})
        current = current.merge(future, on=["season", "player_id"], how="inner")
        current["checkpoint"] = checkpoint
        current["weekly_ecr"] = current["ros_ecr"]
        current["weekly_ecr_sd"] = current["ros_ecr_sd"]
        current["weekly_ecr_range"] = current["ros_ecr_range"]
        rows.append(current)
    return pd.concat(rows, ignore_index=True)


def ros_metrics(
    frame: pd.DataFrame,
    features: list[str] | None,
    seasons: Iterable[int] = EVALUATION_SEASONS,
) -> dict[str, Any]:
    results: dict[str, float] = {}
    for checkpoint in (3, 6, 9):
        checkpoint_frame = frame[frame["checkpoint"] == checkpoint]
        errors = []
        for season in seasons:
            train = checkpoint_frame[checkpoint_frame["season"] < season]
            test = checkpoint_frame[checkpoint_frame["season"] == season]
            if train.empty or test.empty:
                continue
            if features is None:
                position_mean = train.groupby("position")["ros_target"].mean().to_dict()
                overall = float(train["ros_target"].mean())
                raw = test["actual_roll3"].combine_first(test["career_actual_prior"])
                prediction = np.array([
                    float(value) if pd.notna(value) else position_mean.get(position, overall)
                    for value, position in zip(raw, test["position"])
                ])
            else:
                model = _model()
                model.fit(_matrix(train, features), train["ros_target"])
                prediction = model.predict(_matrix(test, features))
            errors.extend(np.abs(prediction - test["ros_target"]).tolist())
        results[str(checkpoint)] = round(float(np.mean(errors)), 4) if errors else None
    return results


def _eligible(frame: pd.DataFrame) -> pd.DataFrame:
    prior_value = frame[["actual_roll3", "xfp_roll3", "career_actual_prior", "career_xfp_prior"]].max(axis=1)
    consensus = pd.to_numeric(frame["weekly_ecr"], errors="coerce") <= 300
    return frame[(prior_value >= 3.0) | consensus.fillna(False)].copy()


def score_feature_set(
    frame: pd.DataFrame,
    ros_frame: pd.DataFrame,
    features: list[str] | None,
    seasons: Iterable[int] = EVALUATION_SEASONS,
) -> dict[str, Any]:
    predictions = walk_forward_predictions(frame, features, seasons=seasons)
    result = weekly_metrics(predictions)
    result["ros_mae_at_checkpoint"] = ros_metrics(ros_frame, features, seasons=seasons)
    return result


def _coverage(frame: pd.DataFrame, columns: Iterable[str]) -> dict[str, float]:
    return {column: round(float(frame[column].notna().mean()), 4) for column in columns if column in frame}


def _season_wins(candidate: dict[str, Any], incumbent: dict[str, Any]) -> int:
    seasons = candidate["mae_by_season"].keys() & incumbent["mae_by_season"].keys()
    return sum(candidate["mae_by_season"][season] < incumbent["mae_by_season"][season] for season in seasons)


def run_scorecard(force: bool = False) -> tuple[dict[str, Any], pd.DataFrame, list[str]]:
    frame = _eligible(build_feature_table(force=force))
    ros_frame = build_ros_frame(frame)
    steps: dict[str, Any] = {}
    steps["1_trailing_average"] = score_feature_set(frame, ros_frame, None)
    steps["2_ffopportunity"] = score_feature_set(frame, ros_frame, XFPO_FEATURES)
    steps["3_implied_team_total"] = score_feature_set(frame, ros_frame, MARKET_FEATURES)
    market_wins = _season_wins(steps["3_implied_team_total"], steps["2_ffopportunity"])
    market_kept = (
        steps["3_implied_team_total"]["mae"] < steps["2_ffopportunity"]["mae"]
        and market_wins >= 3
    )
    steps["3_implied_team_total"]["season_wins"] = market_wins
    steps["3_implied_team_total"]["kept"] = market_kept
    base_features = MARKET_FEATURES if market_kept else XFPO_FEATURES

    structural_features: list[str] = []
    structural_ablation: dict[str, Any] = {}
    current_score = steps["3_implied_team_total"] if market_kept else steps["2_ffopportunity"]
    for source, candidates in STRUCTURAL_GROUPS.items():
        candidate_features = base_features + structural_features + candidates
        candidate_score = score_feature_set(frame, ros_frame, candidate_features)
        season_wins = _season_wins(candidate_score, current_score)
        kept = candidate_score["mae"] < current_score["mae"] and season_wins >= 3
        structural_ablation[source] = {
            "features": candidates,
            "weekly_mae": candidate_score["mae"],
            "delta_mae": round(candidate_score["mae"] - current_score["mae"], 4),
            "season_wins": season_wins,
            "kept": kept,
            "coverage": _coverage(frame, candidates),
            "ros_mae_at_checkpoint": candidate_score["ros_mae_at_checkpoint"],
        }
        if kept:
            structural_features.extend(candidates)
            current_score = candidate_score
    step4_features = base_features + structural_features
    steps["4_structural_usage"] = score_feature_set(frame, ros_frame, step4_features)
    steps["4_structural_usage"]["source_ablation"] = structural_ablation

    step5_features = step4_features + CONSENSUS_FEATURES
    steps["5_consensus_ecr"] = score_feature_set(frame, ros_frame, step5_features)
    steps["5_consensus_ecr"]["coverage"] = _coverage(frame, CONSENSUS_FEATURES)
    consensus_wins = _season_wins(steps["5_consensus_ecr"], steps["4_structural_usage"])
    consensus_kept = (
        steps["5_consensus_ecr"]["mae"] < steps["4_structural_usage"]["mae"]
        and consensus_wins >= 3
    )
    steps["5_consensus_ecr"]["season_wins"] = consensus_wins
    steps["5_consensus_ecr"]["kept"] = consensus_kept
    final_features = step5_features if consensus_kept else step4_features

    current_engine = None
    summary_path = ROOT.parent / "docs" / "backtest" / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        latest = summary.get("latest_scored") or summary.get("latest") or {}
        current_engine = {
            "scope": "local 2026 scored sample; not directly comparable to the historical walk-forward rows",
            "n": latest.get("player_weeks_scored"),
            "mae_by_source": latest.get("mae_by_source"),
        }
    report = {
        "as_of": "2026-09-15",
        "evaluation_seasons": list(EVALUATION_SEASONS),
        "selection_seasons": list(SELECTION_SEASONS),
        "scoring": LEAGUE_SCORING,
        "methodology": {
            "forecast_rule": "All rolling features are shifted one game; ECR scrape dates precede the first kickoff; train seasons always precede test season.",
            "selection_rule": "A source stays only when it reduces aggregate 2021-2025 walk-forward MAE and wins in at least three of five seasons.",
            "interval_rule": "Position-specific 80th percentile absolute residual from the immediately prior season, predicted by earlier seasons.",
            "route_note": "Public participation data supports pass-play on-field participation, not a verified all-route count; the proxy is tested and only retained if it improves MAE.",
        },
        "current_engine_local_baseline": current_engine,
        "steps": steps,
        "source_disposition": {
            "retained": {
                "ffopportunity_expected_points": True,
                "nflverse_implied_team_totals": market_kept,
                "structural_groups": {
                    source: details["kept"] for source, details in structural_ablation.items()
                },
                "fantasypros_ecr_via_nflverse": consensus_kept,
            },
            "unmeasured": {
                "ffanalytics_multi_source": (
                    "No public point-in-time historical projection archive was identified; "
                    "the package is integration code, so using current output in a historical "
                    "scorecard would leak future information."
                ),
                "player_props": (
                    "Historical player-prop snapshots require a paid archive; paid APIs were "
                    "not authorized, so no accuracy gain is claimed."
                ),
            },
        },
        "paid_props_plan": {
            "source": "The Odds API historical event odds/player props",
            "method": (
                "Store pre-kickoff snapshots, convert yardage/reception/TD markets to this "
                "league's scoring, join by player/game/market timestamp, and add only after "
                "the same walk-forward MAE, rank, ROS, and calibration gates pass."
            ),
            "expected_value": (
                "Props are direct market expectations for player outcomes and plausibly add "
                "information beyond team totals, but the gain remains unmeasured."
            ),
        },
        "final_features": final_features,
        "final_step": "5_consensus_ecr" if consensus_kept else "4_structural_usage",
    }
    return report, frame, final_features


def train_final_model(frame: pd.DataFrame, features: list[str], report: dict[str, Any]) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model = _model()
    matrix = _matrix(frame, features)
    model.fit(matrix, frame["actual_points"])
    model.save_model(DEFAULT_MODEL)
    walk_forward = walk_forward_predictions(frame, features)
    residuals = np.abs(walk_forward["prediction"] - walk_forward["actual_points"])
    interval_by_position = {
        position: float(np.quantile(residuals[walk_forward["position"].to_numpy() == position], 0.80))
        for position in POSITIONS
    }
    metadata = {
        "trained_through_season": int(frame["season"].max()),
        "features": features,
        "matrix_columns": list(matrix.columns),
        "interval_radius_80_by_position": interval_by_position,
        "scorecard_final_step": report["final_step"],
    }
    DEFAULT_METADATA.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="redownload and rebuild cached feature data")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report, frame, features = run_scorecard(force=args.force)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    train_final_model(frame, features, report)
    print(json.dumps(report, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
