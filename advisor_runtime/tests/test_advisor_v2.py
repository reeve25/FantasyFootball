"""Offline acceptance tests for the chat-first fantasy advisor.

The fixture intentionally resembles a compact schema-v2 snapshot, but every
number is synthetic.  Nothing in this module may make a network request.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


RUNTIME_DIR = Path(__file__).resolve().parents[1]
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import advisor  # noqa: E402  (the runtime path must be selected first)


STARTER_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF"]


def _player(
    pid: str,
    name: str,
    pos: str,
    team: str,
    owner_roster_id: int | None,
    week_points: float | None,
    projection_pg: float | None,
    *,
    previous_projection_pg: float | None = None,
    projection_change_pg: float | None = None,
) -> dict:
    owner_names = {9: "Reeve", 4: "Gridiron Gods", 7: "Sunday Scaries"}
    weekly_points = {} if week_points is None else {"1": week_points, "15": week_points + 0.4}
    return {
        "pid": pid,
        "key": f"{name.lower()}|{pos}",
        "name": name,
        "full_name": name,
        "pos": pos,
        "position": pos,
        "team": team,
        "owner_roster_id": owner_roster_id,
        "owner": owner_names.get(owner_roster_id),
        "value_pg": projection_pg,
        "projection_pg": projection_pg,
        "previous_projection_pg": previous_projection_pg,
        "projection_change_pg": projection_change_pg,
        "weekly_points": weekly_points,
        "bye_weeks": [],
        "injury_status": None,
        "status": "Active",
        "injury_body_part": None,
        "support": "strong",
        "support_reason": "synthetic two-source agreement",
        "season_market_components": 2,
        "market_real_pct": 70,
        "market_bridge_pct": 0,
        "projection_spread_pg": 0.5,
        "weekly_source_spread_pg": 0.4,
        "staleness": None,
        "tail_risk": None,
        "override": None,
    }


def fixture_snapshot() -> dict:
    """Return one complete, intentionally small schema-v2 league snapshot."""
    players = {
        # Reeve's submitted ten starters.
        "qb": _player("qb", "Trevor Lawrence", "QB", "JAX", 9, 17.8, 17.8),
        "rb1": _player(
            "rb1", "Travis Etienne", "RB", "JAX", 9, 15.1, 15.1,
            previous_projection_pg=17.6, projection_change_pg=-2.5,
        ),
        "rb2": _player("rb2", "Javonte Williams", "RB", "DAL", 9, 15.5, 15.5),
        "wr1": _player("wr1", "Drake London", "WR", "ATL", 9, 15.8, 15.8),
        "wr2": _player("wr2", "Davante Adams", "WR", "LAR", 9, 12.3, 12.3),
        "te": _player("te", "Colston Loveland", "TE", "CHI", 9, 14.2, 14.2),
        "flex1": _player("flex1", "David Montgomery", "RB", "HOU", 9, 13.8, 13.8),
        "flex2": _player(
            "flex2", "Jaxon Smith-Njigba", "WR", "SEA", 9, 19.7, 19.7,
            previous_projection_pg=18.5, projection_change_pg=1.2,
        ),
        "k": _player("k", "Jake Bates", "K", "DET", 9, 7.2, 7.2),
        "def": _player("def", "Jacksonville Jaguars", "DEF", "JAX", 9, 9.5, 9.5),
        # The similarly named bench player is critical to the exact-name tests.
        "jayden": _player("jayden", "Jayden Higgins", "WR", "HOU", 9, 8.2, 8.2),
        "benchqb": _player("benchqb", "Bo Nix", "QB", "DEN", 9, 14.0, 14.0),
        # Other rosters.
        "tee": _player(
            "tee", "Tee Higgins", "WR", "CIN", 4, 16.4, 16.4,
            previous_projection_pg=13.4, projection_change_pg=3.0,
        ),
        "breece": _player("breece", "Breece Hall", "RB", "NYJ", 4, 16.9, 16.9),
        "nabers": _player("nabers", "Malik Nabers", "WR", "NYG", 7, 18.1, 18.1),
        # A missing projection is unknown, not zero and not a projection mover.
        "parker": _player(
            "parker", "Parker Washington", "WR", "JAX", None, None, None,
            previous_projection_pg=9.0, projection_change_pg=None,
        ),
        "free": _player("free", "Free Agent Runner", "RB", "LV", None, 8.8, 8.8),
    }

    my_ids = [
        "qb", "rb1", "rb2", "wr1", "wr2", "te", "flex1", "flex2", "k", "def",
        "jayden", "benchqb",
    ]
    rosters = [
        {
            "roster_id": 9,
            "manager": "Reeve",
            "player_ids": my_ids,
            "starter_ids": my_ids[:10],
            "reserve_ids": [],
            "players": [
                {"pid": pid, "name": players[pid]["name"], "pos": players[pid]["pos"]}
                for pid in my_ids
            ],
            "activity": {"completed_trades": 0, "moves": 2},
        },
        {
            "roster_id": 4,
            "manager": "Gridiron Gods",
            "player_ids": ["tee", "breece"],
            "starter_ids": ["tee", "breece"],
            "reserve_ids": [],
            "players": [
                {"pid": pid, "name": players[pid]["name"], "pos": players[pid]["pos"]}
                for pid in ("tee", "breece")
            ],
            "activity": {"completed_trades": 1, "moves": 3},
        },
        {
            "roster_id": 7,
            "manager": "Sunday Scaries",
            "player_ids": ["nabers"],
            "starter_ids": ["nabers"],
            "reserve_ids": [],
            "players": [{"pid": "nabers", "name": "Malik Nabers", "pos": "WR"}],
            "activity": {"completed_trades": 0, "moves": 1},
        },
    ]
    value_map = {
        pid: {"value_pg": p["value_pg"], "pos": p["pos"], "name": p["name"]}
        for pid, p in players.items()
        if p["value_pg"] is not None
    }
    weekly_points = {p["key"]: dict(p["weekly_points"]) for p in players.values()}
    return {
        "schema_version": 2,
        "generated_at_utc": advisor.iso_now(),
        "engine": {
            "version": "v6.3-test",
            "selftest": "OK",
            "market_mode": "fixture",
            "season_market_player_count": 8,
            "weekly_market_overlay_count": 8,
            "bettingpros_key_configured": False,
        },
        "league": {
            "platform": "Sleeper",
            "league_id": "1327873074195886081",
            "season": 2026,
            "current_week": 1,
            "my_roster_id": 9,
            "starter_slots": list(STARTER_SLOTS),
            "starters": "1 QB, 2 RB, 2 WR, 1 TE, 2 FLEX, K, DEF",
            "scoring": "full PPR; four-point passing TD",
        },
        "players": players,
        "rosters": rosters,
        "power_rankings": [
            {"rid": 4, "manager": "Gridiron Gods", "rank": 1, "lineup_pg": 126.2},
            {"rid": 9, "manager": "Reeve", "rank": 2, "lineup_pg": 124.8},
            {"rid": 7, "manager": "Sunday Scaries", "rank": 3, "lineup_pg": 119.1},
        ],
        "waiver_top": {
            "QB": [],
            "RB": [{"pid": "free", "name": "Free Agent Runner", "value_pg": 8.8}],
            "WR": [{"pid": "parker", "name": "Parker Washington", "value_pg": None}],
            "TE": [],
            "K": [],
            "DEF": [],
        },
        "upgrade_candidates": [],
        "recent_transactions": [
            {
                "transaction_id": "trade-1",
                "week": 1,
                "type": "trade",
                "timestamp_utc": "2026-09-06T18:00:00+00:00",
                "sides": [
                    {"roster_id": 4, "manager": "Gridiron Gods", "acquired": ["Breece Hall"], "sent": []},
                    {"roster_id": 7, "manager": "Sunday Scaries", "acquired": [], "sent": ["Breece Hall"]},
                ],
            }
        ],
        "value_map": value_map,
        "weekly_points": weekly_points,
        "weekly_byes": {p["key"]: [] for p in players.values()},
        "rosters_raw": [
            {
                "roster_id": roster["roster_id"],
                "owner_id": str(roster["roster_id"]),
                "players": list(roster["player_ids"]),
                "reserve": list(roster["reserve_ids"]),
            }
            for roster in rosters
        ],
    }


def fixture_live_context(snapshot: dict | None = None) -> dict:
    snapshot = snapshot or fixture_snapshot()
    starter_ids = ["qb", "rb1", "rb2", "wr1", "wr2", "te", "flex1", "flex2", "k", "def"]
    lineup = []
    for slot, pid in zip(STARTER_SLOTS, starter_ids):
        player = snapshot["players"][pid]
        lineup.append(
            {
                "slot": slot,
                "player_id": pid,
                "name": player["name"],
                "position": player["pos"],
                "team": player["team"],
                "status": player["status"],
                "points": player["weekly_points"].get("1"),
            }
        )
    return {
        "refreshed_at_utc": "2026-09-07T20:00:00+00:00",
        "season": "2026",
        "week": 1,
        "league_name": "LemarJacksSons",
        "total_rosters": 12,
        "starter_slots": list(STARTER_SLOTS),
        "roster_positions": list(STARTER_SLOTS) + ["BN"] * 5 + ["IR"],
        "my_roster": {
            "roster_id": 9,
            "manager": "Reeve",
            "player_ids": list(snapshot["rosters"][0]["player_ids"]),
            "starter_ids": starter_ids,
            "reserve_ids": [],
            "waiver_position": 6,
        },
        "rosters": [
            {
                "roster_id": row["roster_id"],
                "manager": row["manager"],
                "player_ids": list(row["player_ids"]),
                "starter_ids": list(row["starter_ids"]),
                "reserve_ids": list(row["reserve_ids"]),
            }
            for row in snapshot["rosters"]
        ],
        "owner_by_player": {
            pid: row["roster_id"]
            for row in snapshot["rosters"]
            for pid in row["player_ids"]
        },
        "current_lineup": lineup,
        "current_lineup_total": 140.9,
        "recent_transactions": copy.deepcopy(snapshot["recent_transactions"]),
    }


def fixture_twelve_team_league() -> tuple[dict, dict]:
    """Build a realistic 192-player live league without external data."""
    snapshot = fixture_snapshot()
    players = {}
    rosters = []
    live_rosters = []
    owner_by_player = {}
    positions = [
        "QB", "RB", "RB", "WR", "WR", "TE", "RB", "WR",
        "K", "DEF", "QB", "RB", "WR", "TE", "WR", "RB",
    ]
    for roster_id in range(1, 13):
        manager = f"Manager {roster_id:02d} With A Realistic Team Name"
        player_ids = []
        for index, position in enumerate(positions, start=1):
            player_id = f"live-{roster_id:02d}-{index:02d}"
            player_ids.append(player_id)
            owner_by_player[player_id] = roster_id
            # Simulate a just-added player whose metadata has not reached the
            # projection snapshot yet. Its live ownership must still survive.
            if roster_id == 12 and index == 16:
                continue
            projection = round(5.0 + roster_id * 0.17 + index * 0.41, 2)
            player = _player(
                player_id,
                f"Synthetic Player {roster_id:02d}-{index:02d}",
                position,
                f"T{(roster_id + index) % 32:02d}",
                roster_id,
                projection,
                projection,
                previous_projection_pg=round(projection - 0.3, 2),
                projection_change_pg=0.3,
            )
            player["owner"] = manager
            player["bye_weeks"] = [((roster_id + index) % 8) + 7]
            if index == 4 and roster_id % 3 == 0:
                player["injury_status"] = "Questionable"
            players[player_id] = player

        roster = {
            "roster_id": roster_id,
            "manager": manager,
            "player_ids": player_ids,
            "starter_ids": player_ids[:10],
            "reserve_ids": [player_ids[-1]],
            "waiver_position": roster_id,
            "wins": roster_id % 4,
            "losses": 3 - (roster_id % 4),
            "ties": 0,
            "players": [
                {
                    "pid": player_id,
                    "name": players.get(player_id, {}).get("name"),
                    "pos": players.get(player_id, {}).get("pos"),
                }
                for player_id in player_ids
            ],
        }
        rosters.append(roster)
        live_rosters.append(
            {
                key: copy.deepcopy(value)
                for key, value in roster.items()
                if key != "players"
            }
        )

    snapshot["players"] = players
    snapshot["rosters"] = rosters
    snapshot["league"]["total_rosters"] = 12
    snapshot["power_rankings"] = [
        {
            "roster_id": roster_id,
            "manager": f"Manager {roster_id:02d} With A Realistic Team Name",
            "rank": roster_id,
            "core_starter_pg": round(135 - roster_id * 1.2, 2),
            "weeks_measured": 17,
            "fallback_assignments": 0,
        }
        for roster_id in range(1, 13)
    ]
    live = {
        "refreshed_at_utc": "2026-09-07T21:00:00+00:00",
        "season": "2026",
        "week": 1,
        "league_name": "Twelve-Team Test League",
        "total_rosters": 12,
        "starter_slots": list(STARTER_SLOTS),
        "roster_positions": list(STARTER_SLOTS) + ["BN"] * 5 + ["IR"],
        "rosters": live_rosters,
        "my_roster": copy.deepcopy(live_rosters[8]),
        "owner_by_player": owner_by_player,
        "projection_by_player": {},
        "current_lineup": [],
        "current_lineup_total": None,
        "recent_transactions": [],
    }
    return snapshot, live


class MatchingAndIntentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = fixture_snapshot()

    def test_full_names_keep_tee_and_jayden_higgins_isolated(self):
        hits = advisor.match_players(
            "Compare Tee Higgins with Jayden Higgins.", self.snapshot
        )
        self.assertEqual([row["name"] for row in hits], ["Tee Higgins", "Jayden Higgins"])

    def test_ambiguous_higgins_surname_does_not_guess(self):
        hits = advisor.match_players("What about Higgins?", self.snapshot)
        self.assertEqual(hits, [])

    def test_intent_routing_covers_supported_advice_modes(self):
        cases = {
            "Compare Travis Etienne and Tee Higgins": "comparison",
            "Rank every team in this league": "league_rankings",
            "Analyze Gridiron Gods and explain how that team can improve": "team_analysis",
            "Show the biggest season projection increases and decreases": "projection_movers",
            "Who are the best trade targets for my team?": "trade_targets",
            "Show the league's recent completed trades": "recent_transactions",
            "Who should I claim off waivers?": "waiver",
            "Show my exact current lineup": "lineup",
            "Should I trade Travis Etienne for Tee Higgins?": "explicit_trade",
            "Drake London for Tee Higgins": "explicit_trade",
            "Tee Higgins for Drake London": "explicit_trade",
            "Who should I trade away?": "roster_surplus_trade_away",
            "Where do I have surplus?": "roster_surplus_trade_away",
            "Who are good buy low targets?": "buy_low_targets",
            "Buy low RBs": "buy_low_targets",
            "Who should I sell high on?": "sell_high_targets",
            "Sell high candidates": "sell_high_targets",
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                self.assertEqual(advisor.classify_intent(question, self.snapshot), expected)

    def test_resolve_trade_from_conversational_phrasing(self):
        # London on roster 9, Higgins on roster 4
        trade1 = advisor.resolve_trade_from_question(self.snapshot, "Drake London for Tee Higgins")
        self.assertIsNotNone(trade1)
        self.assertEqual(trade1["give"], ["Drake London"])
        self.assertEqual(trade1["get"], ["Tee Higgins"])

        # Counterparty first phrasing resolves give from perspective ownership
        trade2 = advisor.resolve_trade_from_question(self.snapshot, "Tee Higgins for Drake London")
        self.assertIsNotNone(trade2)
        self.assertEqual(trade2["give"], ["Drake London"])
        self.assertEqual(trade2["get"], ["Tee Higgins"])

        # Explicit direction prefix
        trade3 = advisor.resolve_trade_from_question(self.snapshot, "give Drake London for Tee Higgins")
        self.assertIsNotNone(trade3)
        self.assertEqual(trade3["give"], ["Drake London"])
        self.assertEqual(trade3["get"], ["Tee Higgins"])

        # Non-trade question returns None
        self.assertIsNone(advisor.resolve_trade_from_question(self.snapshot, "Who should I start for week 2?"))


class LineupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = fixture_snapshot()

    def test_ten_slot_lineup_is_ordered_legal_unique_and_summed(self):
        player_ids = self.snapshot["rosters"][0]["player_ids"]
        result = advisor.optimize_lineup(
            player_ids, self.snapshot, week=1, starter_slots=STARTER_SLOTS
        )
        starters = result["starters"]
        self.assertEqual([row["slot"] for row in starters], STARTER_SLOTS)
        self.assertEqual(len(starters), 10)
        self.assertEqual(len({row["name"] for row in starters}), 10)

        positions = {p["name"]: p["pos"] for p in self.snapshot["players"].values()}
        eligibility = {
            "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"},
            "FLEX": {"RB", "WR", "TE"}, "K": {"K"}, "DEF": {"DEF"},
        }
        for row in starters:
            self.assertIn(positions[row["name"]], eligibility[row["slot"]])
        self.assertEqual([row["slot"] for row in starters[6:8]], ["FLEX", "FLEX"])

        expected_total = round(sum(float(row["points"]) for row in starters), 2)
        self.assertAlmostEqual(result["projected_total"], expected_total, places=2)
        self.assertAlmostEqual(result["projected_total"], 140.9, places=2)

    def test_missing_projection_remains_none_instead_of_becoming_zero(self):
        self.snapshot["players"]["k"]["weekly_points"] = {}
        result = advisor.optimize_lineup(
            self.snapshot["rosters"][0]["player_ids"],
            self.snapshot,
            week=1,
            starter_slots=STARTER_SLOTS,
        )
        kicker = next(row for row in result["starters"] if row["slot"] == "K")
        self.assertIsNone(kicker["points"])

    def test_live_sleeper_lineup_is_preserved_not_reoptimized(self):
        live = fixture_live_context(self.snapshot)
        packet = advisor.build_packet(
            "Show my exact current lineup",
            self.snapshot,
            live_context=live,
            include_market=False,
        )
        self.assertEqual(packet["current_lineup"], live["current_lineup"])
        self.assertEqual([row["slot"] for row in packet["current_lineup"]], STARTER_SLOTS)
        self.assertEqual(
            [row["name"] for row in packet["current_lineup"]],
            [
                "Trevor Lawrence", "Travis Etienne", "Javonte Williams", "Drake London",
                "Davante Adams", "Colston Loveland", "David Montgomery",
                "Jaxon Smith-Njigba", "Jake Bates", "Jacksonville Jaguars",
            ],
        )
        self.assertEqual(packet["current_lineup"][6]["slot"], "FLEX")
        self.assertEqual(packet["current_lineup"][7]["slot"], "FLEX")
        self.assertAlmostEqual(packet["current_lineup_total"], 140.9, places=2)


class TradeSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = fixture_snapshot()
        self.live = fixture_live_context(self.snapshot)

    def _three_week_trade_snapshot(self, reserve_slots: int = 1) -> dict:
        def player(
            pid: str,
            name: str,
            pos: str,
            owner: int,
            points: float,
        ) -> dict:
            row = _player(pid, name, pos, "TST", owner, points, points)
            row["weekly_points"] = {
                str(week): points for week in range(1, 4)
            }
            row["current_week"] = 1
            return row

        players = {
            "my_qb": player("my_qb", "My Quarterback", "QB", 9, 10.0),
            "give": player("give", "Give Runner", "RB", 9, 10.0),
            "give_ir": player("give_ir", "IR Receiver", "WR", 9, 0.0),
            "their_qb": player(
                "their_qb", "Their Quarterback", "QB", 4, 9.0
            ),
            "get": player("get", "Get Receiver", "WR", 4, 12.0),
            "top": player("top", "Premium Runner", "RB", 4, 30.0),
        }
        players["give_ir"]["injury_status"] = "IR"
        players["give_ir"]["status"] = "IR"
        players["my_qb"]["weekly_points"].pop("2")
        players["my_qb"]["bye_weeks"] = [2]
        players["their_qb"]["weekly_points"].pop("3")
        players["their_qb"]["bye_weeks"] = [3]
        return {
            "schema_version": 2,
            "engine": {"version": "v6.3-test"},
            "league": {
                "season": 2026,
                "current_week": 1,
                "season_end_week": 3,
                "starter_slots": ["QB", "FLEX"],
                "roster_positions": ["QB", "FLEX", "BN"],
                "league_settings": {"reserve_slots": reserve_slots},
                "playoff_weeks": [3],
            },
            "players": players,
            "rosters": [
                {
                    "roster_id": 9,
                    "manager": "Reeve",
                    "player_ids": ["my_qb", "give", "give_ir"],
                    "starter_ids": ["my_qb", "give"],
                    "reserve_ids": ["give_ir"],
                },
                {
                    "roster_id": 4,
                    "manager": "Gridiron Gods",
                    "player_ids": ["their_qb", "get", "top"],
                    "starter_ids": ["their_qb", "top"],
                    "reserve_ids": [],
                },
            ],
        }

    @staticmethod
    def _two_for_one_terms() -> dict:
        return {
            "give_ids": ["give", "give_ir"],
            "get_ids": ["get"],
            "give": ["Give Runner", "IR Receiver"],
            "get": ["Get Receiver"],
            "other_rid": 4,
            "terms_explicit": True,
        }

    def test_plain_comparison_never_creates_trade_math(self):
        with mock.patch.object(
            advisor,
            "_pergame_trade",
            side_effect=AssertionError("comparison must not run trade arithmetic"),
            create=True,
        ):
            packet = advisor.build_packet(
                "Compare Travis Etienne and Tee Higgins",
                self.snapshot,
                live_context=self.live,
                include_market=False,
            )
        self.assertEqual(packet["decision_type"], "comparison")
        self.assertEqual(
            [row["name"] for row in packet["focused_players"]],
            ["Travis Etienne", "Tee Higgins"],
        )
        self.assertIsNone(packet.get("exact_engine_decision_math"))

    def test_explicit_two_for_one_resolves_exact_players_and_owner(self):
        trade = advisor.resolve_explicit_trade(
            self.snapshot,
            give_names=["Travis Etienne", "Jayden Higgins"],
            get_names=["Tee Higgins"],
            manager="Gridiron Gods",
        )
        self.assertEqual(trade["give"], ["Travis Etienne", "Jayden Higgins"])
        self.assertEqual(trade["get"], ["Tee Higgins"])
        self.assertEqual(trade["other_rid"], 4)

        fake_math = {
            "give": trade["give"],
            "get": trade["get"],
            "my_before_pg": 124.8,
            "my_after_pg": 125.3,
            "my_delta_pg": 0.5,
        }
        with mock.patch.object(advisor, "evaluate_trade", return_value=fake_math):
            packet = advisor.build_packet(
                "Should I accept this exact two-for-one?",
                self.snapshot,
                explicit_trade=trade,
                live_context=self.live,
                include_market=False,
            )
        self.assertEqual(packet["decision_type"], "explicit_trade")
        self.assertIsNotNone(packet["exact_engine_decision_math"])
        self.assertEqual(
            {row["name"] for row in packet["focused_players"]},
            {"Travis Etienne", "Jayden Higgins", "Tee Higgins"},
        )

    def test_named_friend_trade_uses_that_roster_as_perspective(self):
        trade = advisor.resolve_explicit_trade(
            self.snapshot,
            give_names=["Tee Higgins"],
            get_names=["Malik Nabers"],
            manager="Sunday Scaries",
            perspective_manager="Gridiron Gods",
        )
        self.assertEqual(trade["perspective_rid"], 4)
        self.assertEqual(trade["perspective_manager"], "Gridiron Gods")
        self.assertEqual(trade["other_rid"], 7)
        self.assertEqual(trade["give"], ["Tee Higgins"])
        self.assertEqual(trade["get"], ["Malik Nabers"])

        fake_math = {
            "perspective_before_pg": 100.0,
            "perspective_after_pg": 101.0,
            "perspective_delta_pg": 1.0,
            "counterparty_before_pg": 99.0,
            "counterparty_after_pg": 98.0,
            "counterparty_delta_pg": -1.0,
        }
        with mock.patch.object(advisor, "evaluate_trade", return_value=fake_math):
            packet = advisor.build_packet(
                "Should Gridiron Gods give Tee Higgins for Malik Nabers?",
                self.snapshot,
                explicit_trade=trade,
                live_context=self.live,
                include_market=False,
            )
        self.assertEqual(
            {row["roster_id"] for row in packet["involved_rosters"]},
            {4, 7},
        )
        self.assertNotIn(9, {
            row["roster_id"] for row in packet["involved_rosters"]
        })
        # This fixture has no verified provider timestamps. Perspective
        # resolution must succeed while the new freshness warnings remain.
        self.assertTrue(any("stale" in warning for warning in packet["warnings"]))

    def test_friend_trade_math_uses_neutral_labels_not_my_labels(self):
        snapshot = self._three_week_trade_snapshot()
        terms = {
            "give_ids": ["get"],
            "get_ids": ["give"],
            "give": ["Get Receiver"],
            "get": ["Give Runner"],
            "perspective_rid": 4,
            "other_rid": 9,
            "terms_explicit": True,
        }
        result = advisor.evaluate_trade(snapshot, terms)
        self.assertEqual(result["perspective_roster_id"], 4)
        self.assertEqual(result["counterparty_roster_id"], 9)
        self.assertIsNotNone(result["perspective_delta_pg"])
        self.assertIsNotNone(result["counterparty_delta_pg"])
        self.assertNotIn("my_delta_pg", result)
        self.assertNotIn("their_delta_pg", result)

    def test_trade_rejects_ambiguous_name_wrong_owner_and_free_agent(self):
        with self.assertRaises(ValueError):
            advisor.resolve_explicit_trade(
                self.snapshot, ["Travis Etienne"], ["Higgins"], manager=None
            )
        with self.assertRaises(ValueError):
            advisor.resolve_explicit_trade(
                self.snapshot,
                ["Travis Etienne"],
                ["Tee Higgins", "Malik Nabers"],
                manager=None,
            )
        with self.assertRaises(ValueError):
            advisor.resolve_explicit_trade(
                self.snapshot, ["Travis Etienne"], ["Parker Washington"], manager=None
            )

    def test_byes_are_known_zeroes_and_trade_season_math_is_complete(self):
        snapshot = self._three_week_trade_snapshot()
        bye_points, bye_source = advisor._projection_for_week(
            snapshot["players"]["my_qb"], 2
        )
        self.assertEqual((bye_points, bye_source), (0.0, "bye"))
        missing_player = copy.deepcopy(snapshot["players"]["get"])
        missing_player["weekly_points"].pop("2")
        self.assertEqual(
            advisor._projection_for_week(missing_player, 2),
            (None, "missing"),
        )

        result = advisor.evaluate_trade(snapshot, self._two_for_one_terms())

        for field in (
            "my_before_pg",
            "my_after_pg",
            "my_delta_pg",
            "their_before_pg",
            "their_after_pg",
            "their_delta_pg",
        ):
            self.assertIsNotNone(result[field], field)
        self.assertAlmostEqual(result["my_before_pg"], 16.6667, places=4)
        self.assertAlmostEqual(result["my_after_pg"], 18.6667, places=4)
        self.assertAlmostEqual(result["my_delta_pg"], 2.0, places=4)

    def test_incoming_ir_player_uses_open_reserve_without_forced_drop(self):
        snapshot = self._three_week_trade_snapshot(reserve_slots=1)

        result = advisor.evaluate_trade(snapshot, self._two_for_one_terms())

        self.assertEqual(result["my_forced_drops"], [])
        self.assertEqual(result["their_forced_drops"], [])

    def test_injected_market_anchor_source_surfaces_through_the_existing_interface(self):
        """T4: evaluate_trade needs no changes to report a new source.

        Injecting a "market_anchor" key into weekly_points_by_source is the
        entire wiring mechanism (see advisor.select_projection_source and
        STATUS.md's T4 Decision Log). This proves it two ways: the unmodified
        evaluate_trade's own independent_projection_checks discovers the new
        source on its own, and select_projection_source's substitution for
        the *primary* basis reproduces that same independent-check result
        exactly.
        """
        snapshot = self._three_week_trade_snapshot()
        # Distinct from the existing weekly_points so the injected source is
        # unambiguously the one being measured, not a coincidental match.
        snapshot["players"]["give"]["weekly_points_by_source"] = {
            "market_anchor": {"1": 5.0, "3": 5.0}
        }
        snapshot["players"]["get"]["weekly_points_by_source"] = {
            "market_anchor": {"1": 20.0, "3": 20.0}
        }
        terms = self._two_for_one_terms()

        result = advisor.evaluate_trade(snapshot, terms)
        self.assertIn("market_anchor", result["independent_projection_checks"])
        via_default_call = result["independent_projection_checks"]["market_anchor"]

        primary = advisor.evaluate_trade(
            advisor.select_projection_source(snapshot, "market_anchor"),
            terms,
            source_checks=False,
        )
        for field in ("perspective_delta_pg", "counterparty_delta_pg"):
            self.assertEqual(primary[field], via_default_call[field])
        # And it actually reflects the injected numbers, not the untouched default.
        self.assertNotEqual(
            via_default_call["perspective_delta_pg"], result["perspective_delta_pg"]
        )

    def test_incomplete_drop_objective_preserves_premium_asset(self):
        snapshot = self._three_week_trade_snapshot(reserve_slots=0)
        snapshot["players"]["kicker"] = _player(
            "kicker", "Replaceable Kicker", "K", "TST", 4, 1.0, 1.0
        )
        snapshot["players"]["kicker"]["weekly_points"] = {
            str(week): 1.0 for week in range(1, 4)
        }
        snapshot["league"]["roster_positions"] = [
            "QB", "FLEX", "K", "BN"
        ]
        other = snapshot["rosters"][1]
        over_limit = [
            "their_qb", "top", "give", "give_ir", "kicker"
        ]

        legal, drops = advisor._legalize_roster(
            over_limit,
            other,
            snapshot,
            weeks=[1, 2, 3],
            slots=["TE"],
        )

        self.assertEqual(drops, ["give_ir"])
        self.assertIn("top", legal)
        self.assertIn("kicker", legal)

    def test_incomplete_trade_math_emits_explicit_warning(self):
        snapshot = self._three_week_trade_snapshot()
        snapshot["players"]["my_qb"]["bye_weeks"] = []
        snapshot["players"]["my_qb"]["weekly_points"].pop("3")

        packet = advisor.build_packet(
            "Should I make this trade?",
            snapshot,
            explicit_trade=self._two_for_one_terms(),
            include_market=False,
        )

        self.assertIsNone(
            packet["exact_engine_decision_math"]["my_before_pg"]
        )
        warning = " ".join(packet["warnings"])
        self.assertIn("Trade lineup math is incomplete", warning)
        self.assertIn("Treat any populated partial or playoff delta", warning)

    def test_explicit_trade_packet_includes_sensitivity_and_decision_report(self):
        snapshot = self._three_week_trade_snapshot()
        trade = advisor.resolve_trade_from_question(snapshot, "Give Runner for Get Receiver")
        self.assertIsNotNone(trade)
        self.assertEqual(trade["give"], ["Give Runner"])
        self.assertEqual(trade["get"], ["Get Receiver"])

        packet = advisor.build_packet(
            "Give Runner for Get Receiver",
            snapshot,
            explicit_trade=trade,
            live_context=None,
            include_market=False,
        )
        self.assertEqual(packet["decision_type"], "explicit_trade")
        self.assertEqual(packet["assumption_list"], [])
        self.assertEqual(packet["assumptions"], [])
        math = packet["exact_engine_decision_math"]
        self.assertIsNotNone(math)
        self.assertIn("min_ppg_shift_to_flip", math)
        self.assertIsNotNone(math["perspective_delta_pg"])
        self.assertEqual(math["min_ppg_shift_to_flip"], round(abs(math["perspective_delta_pg"]), 4))
        self.assertEqual(packet["min_ppg_shift_to_flip"], math["min_ppg_shift_to_flip"])
        self.assertIn("decision_report", packet)
        report = packet["decision_report"]
        self.assertEqual(report["weekly_ppg_impact"], math["perspective_delta_pg"])
        self.assertEqual(report["playoff_ppg_impact"], math["perspective_playoff_delta_pg"])
        self.assertEqual(report["min_ppg_shift_to_flip"], math["min_ppg_shift_to_flip"])
# removed prose

        # When projections are incomplete, min_ppg_shift_to_flip is None
        incomplete_trade = advisor.resolve_trade_from_question(self.snapshot, "Drake London for Tee Higgins")
        inc_packet = advisor.build_packet(
            "Drake London for Tee Higgins",
            self.snapshot,
            explicit_trade=incomplete_trade,
            live_context=self.live,
            include_market=False,
        )
        self.assertIsNone(inc_packet["exact_engine_decision_math"]["min_ppg_shift_to_flip"])
        self.assertIsNone(inc_packet["min_ppg_shift_to_flip"])
# removed prose


class PacketAndProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = fixture_snapshot()
        self.live = fixture_live_context(self.snapshot)

    def test_include_market_false_never_calls_a_market_source(self):
        with mock.patch.object(
            advisor,
            "focused_market_packet",
            side_effect=AssertionError("market network path must stay disabled"),
            create=True,
        ):
            packet = advisor.build_packet(
                "Compare Tee Higgins and Travis Etienne",
                self.snapshot,
                live_context=self.live,
                include_market=False,
            )
        self.assertFalse(packet.get("market_evidence"))

    def test_focused_packet_stays_below_hard_size_guard(self):
        packet = advisor.build_packet(
            "Compare Tee Higgins and Travis Etienne",
            self.snapshot,
            live_context=self.live,
            include_market=False,
        )
        encoded = json.dumps(packet, separators=(",", ":"), default=str)
        self.assertLess(len(encoded), 24_000)

    def test_unknown_focused_projection_is_preserved_as_none(self):
        packet = advisor.build_packet(
            "Explain Parker Washington",
            self.snapshot,
            live_context=self.live,
            include_market=False,
        )
        self.assertEqual([row["name"] for row in packet["focused_players"]], ["Parker Washington"])
        parker = packet["focused_players"][0]
        self.assertIsNone(parker["weekly_projection"]["1"])
        self.assertIsNone(parker["engine_value_pg"])

    def test_projection_movers_use_real_baselines_and_absolute_delta_order(self):
        movers = advisor.projection_movers(self.snapshot, limit=2)
        self.assertEqual([row["name"] for row in movers], ["Tee Higgins", "Travis Etienne"])
        self.assertEqual([row["delta_pg"] for row in movers], [3.0, -2.5])
        self.assertNotIn("Parker Washington", [row["name"] for row in movers])


class TradeTargetPacketTests(unittest.TestCase):
    def test_full_live_league_keeps_every_owner_and_player_under_limit(self):
        snapshot, live = fixture_twelve_team_league()
        packet = advisor.build_packet(
            "Who are the best trade targets for my team?",
            snapshot,
            live_context=live,
            include_market=False,
        )

        self.assertEqual(packet["decision_type"], "trade_targets")
        self.assertEqual(len(packet["league_rosters"]), 12)
        fields = packet["league_roster_player_fields"]
        self.assertEqual(
            fields,
            [
                "player_id", "name", "position", "team", "lineup_role",
                "week_projection", "week_projection_state", "ros_projection_pg",
                "projection_change_pg", "status", "bye_weeks",
            ],
        )
        field_index = {name: index for index, name in enumerate(fields)}

        encoded_ownership = {}
        encoded_rows = {}
        for roster in packet["league_rosters"]:
            self.assertEqual(len(roster["players"]), 16)
            for player_row in roster["players"]:
                self.assertEqual(len(player_row), len(fields))
                player_id = player_row[field_index["player_id"]]
                encoded_ownership[player_id] = roster["roster_id"]
                encoded_rows[player_id] = player_row

        self.assertEqual(encoded_ownership, live["owner_by_player"])
        self.assertEqual(len(encoded_rows), 192)
        known = encoded_rows["live-04-03"]
        self.assertEqual(known[field_index["name"]], "Synthetic Player 04-03")
        self.assertEqual(known[field_index["position"]], "RB")
        self.assertIsNotNone(known[field_index["week_projection"]])
        self.assertEqual(known[field_index["week_projection_state"]], "W")

        late_add = encoded_rows["live-12-16"]
        self.assertIsNone(late_add[field_index["name"]])
        self.assertEqual(late_add[field_index["week_projection_state"]], "U")
        self.assertNotIn(
            "Roster player detail was trimmed to respect the packet limit.",
            packet["warnings"],
        )
        actual_size = len(
            json.dumps(packet, separators=(",", ":"), default=str)
        )
        self.assertLess(actual_size, 24_000)


if __name__ == "__main__":
    unittest.main()

