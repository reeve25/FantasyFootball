import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import polars as pl

from advisor_runtime import public_model_scorecard as scorecard


class PublicModelScorecardTests(unittest.TestCase):
    def test_exact_league_scoring(self):
        frame = pd.DataFrame([{
            "pass_yards_gained": 250,
            "pass_touchdown": 2,
            "pass_interception": 1,
            "rush_yards_gained": 20,
            "rush_touchdown": 1,
            "receptions": 5,
            "rec_yards_gained": 60,
            "rec_touchdown": 1,
            "rush_fumble_lost": 1,
            "pass_two_point_conv": 1,
        }])

        self.assertEqual(scorecard.score_actual(frame).iloc[0], 42.0)

    def test_rolling_features_use_only_prior_games(self):
        frame = pd.DataFrame({
            "player_id": ["p1"] * 4,
            "season": [2024] * 4,
            "week": [1, 2, 3, 4],
            "actual_points": [10.0, 20.0, 30.0, 40.0],
            "expected_points": [8.0, 16.0, 24.0, 32.0],
            "td_gap": [1.0, 2.0, 3.0, 4.0],
        })

        result = scorecard._rolling_features(frame)

        self.assertTrue(np.isnan(result.loc[result["week"] == 1, "actual_roll3"].iloc[0]))
        self.assertEqual(result.loc[result["week"] == 2, "actual_roll3"].iloc[0], 10.0)
        self.assertEqual(result.loc[result["week"] == 4, "actual_roll3"].iloc[0], 20.0)

    def test_rankings_select_latest_pre_kickoff_per_page(self):
        rankings = pl.DataFrame({
            "page_type": ["weekly-rb", "weekly-rb", "redraft-rb", "redraft-rb"],
            "scrape_date": ["2024-09-01", "2024-09-05", "2024-08-25", "2024-09-10"],
            "player": ["Example Back"] * 4,
            "team": ["BUF"] * 4,
            "ecr": [20.0, 10.0, 30.0, 1.0],
            "sd": [2.0] * 4,
            "best": [8.0] * 4,
            "worst": [12.0] * 4,
        })
        cutoffs = pd.DataFrame([{"season": 2024, "week": 1, "gameday": pd.Timestamp("2024-09-08")}])

        with patch.object(scorecard.nfl, "load_ff_rankings", return_value=rankings):
            result = scorecard._ranking_features(cutoffs)

        self.assertEqual(result.iloc[0]["weekly_ecr"], 10.0)
        self.assertEqual(result.iloc[0]["ros_ecr"], 30.0)

    def test_missing_betting_lines_remain_missing(self):
        schedules = pl.DataFrame({
            "season": [2024],
            "week": [1],
            "game_type": ["REG"],
            "gameday": ["2024-09-08"],
            "home_team": ["BUF"],
            "away_team": ["NYJ"],
            "total_line": [None],
            "spread_line": [None],
        })

        with patch.object(scorecard.nfl, "load_schedules", return_value=schedules):
            implied, _ = scorecard._schedule_features([2024])

        self.assertTrue(implied["implied_total"].isna().all())


if __name__ == "__main__":
    unittest.main()
