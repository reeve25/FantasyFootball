import unittest
from unittest import mock

from advisor_runtime import flock


class FlockTests(unittest.TestCase):
    def setUp(self):
        flock._CACHE.clear()

    def test_fairness_verdict_matches_web_client_thresholds(self):
        self.assertEqual(flock.fairness_verdict(100, 100)["verdict"], "Fair Trade!")
        self.assertEqual(flock.fairness_verdict(108, 100)["verdict"], "Fair Trade!")
        self.assertEqual(flock.fairness_verdict(109, 100)["verdict"], "You slightly win!")
        self.assertEqual(flock.fairness_verdict(120, 100)["verdict"], "You win!")
        self.assertEqual(flock.fairness_verdict(160, 100)["verdict"], "You're robbing them!")

    def test_check_trade_maps_sleeper_ids_and_orients_sides(self):
        snapshot = {
            "league": {
                "season": 2026,
                "known_format_fallback": "12-team; full PPR; 4-point pass TD",
                "starter_slots": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX"],
                "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX"] + ["BN"] * 5,
                "scoring_settings": {"rec": 1.0},
            }
        }
        trade = {
            "give_ids": ["8112"],
            "give": ["Drake London"],
            "get_ids": ["8151"],
            "get": ["Kenneth Walker"],
        }
        rankings = {
            "format": "REDRAFT",
            "subformat": "1QB",
            "lastUpdated": {"Expert": "2026-09-15 21:37:56"},
            "data": [
                {"playerId": 8112, "playerName": "Drake London", "averageRank": 23.25},
                {"playerId": 8151, "playerName": "Kenneth Walker", "averageRank": 11},
            ],
        }
        with (
            mock.patch.object(flock, "_rankings", return_value=rankings),
            mock.patch.object(
                flock,
                "_json",
                return_value={"user": 62, "opponent": 62, "suggestions": None},
            ) as request,
        ):
            result = flock.check_trade(snapshot, trade)

        self.assertEqual(result["verdict"], "Fair Trade!")
        self.assertTrue(result["is_fair_trade"])
        payload = request.call_args.kwargs["json"]
        self.assertEqual(payload["opponentReceives"], [{"player_id": 8112, "rank": 23}])
        self.assertEqual(payload["userReceives"], [{"player_id": 8151, "rank": 11}])
        self.assertEqual(payload["settings"]["scoring"], "PPR")
        self.assertEqual(payload["settings"]["league_size"], 12)


if __name__ == "__main__":
    unittest.main()
