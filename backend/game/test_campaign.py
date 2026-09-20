import copy
import importlib.util
import json
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient
from .campaign import act
from .gm import build_safe_gm_context
from .models import Scenario
from .mystery import create_mystery_game, mystery_payload, cast_vote
from .realtime import advance_game_phase, realtime_snapshot
from .scenario_parser import parse_scenario
from .scenario_validator import validate_scenario

SAMPLES = Path(__file__).parent / "scenarios"


class CampaignTests(TestCase):
    def setUp(self):
        self.definition = parse_scenario((SAMPLES / "neet_recording.yaml").read_text(), "yaml")
        self.outcome = json.loads((SAMPLES / "previous_result.example.json").read_text())
        self.client = APIClient()

    def create(self, definition=None, outcome=None):
        definition = definition or self.definition
        report = validate_scenario(definition)
        self.assertTrue(report["valid"], report)
        scenario = Scenario.objects.create(title=definition["title"], definition=definition, validation_report=report, status="ready")
        return create_mystery_game(scenario, previous_result=outcome or self.outcome)

    def submit(self, game, row):
        for seat in (1, 2):
            act(game.id, seat, "submit", {"answers": {q["id"]: q["answer"] for q in row["questions"]}, "evidence": []})

    def walk(self, game):
        for row in game.scenario.definition["campaign"]["rounds"]:
            self.assertTrue(advance_game_phase(game.id))
            self.assertFalse(advance_game_phase(game.id))
            self.submit(game, row)
            self.assertTrue(advance_game_phase(game.id))
            if "draw" in row:
                game.refresh_from_db()
                from .campaign import eligible
                for seat in eligible(game, row):
                    for _ in range(row["draw"]["per_player"]):
                        game.refresh_from_db()
                        card = next(c for c in self.definition["campaign"]["cards"] if c["id"] not in game.state.get("card_owners", {}))
                        act(game.id, seat, "pick", {"card_id": card["id"]})
                self.assertTrue(advance_game_phase(game.id))
        game.refresh_from_db()
        self.assertTrue(game.state["finished"])

    def test_full_game_both_winner_outcomes(self):
        for winner, count in [("village", 15), ("wolves", 12)]:
            with self.subTest(winner=winner):
                outcome = copy.deepcopy(self.outcome)
                outcome["winner_team"] = winner
                game = self.create(outcome=outcome)
                self.walk(game)
                self.assertEqual(len(game.state["card_owners"]), count)
                self.assertEqual(game.state["campaign_results"]["scores"], {"village": 8, "wolves": 8})
                self.assertIsNotNone(mystery_payload(game, seat=1)["resolution"])
                with self.assertRaises(ValueError):
                    act(game.id, 1, "pick", {"card_id": "card15"})

    def test_private_visibility_and_frozen_answers(self):
        game = self.create()
        advance_game_phase(game.id)
        row = self.definition["campaign"]["rounds"][0]
        act(game.id, 1, "submit", {"answers": {"voice": "recording"}})
        with self.assertRaises(ValueError):
            act(game.id, 1, "submit", {"answers": {"voice": "live"}})
        other = realtime_snapshot(game.id, 2)["game"]
        self.assertIsNone(other["campaign"]["my_submission"])
        self.assertNotIn('"answer":', json.dumps(other))
        act(game.id, 2, "submit", {"answers": {"voice": "live"}})
        advance_game_phase(game.id)
        act(game.id, 1, "pick", {"card_id": "card01"})
        game.refresh_from_db()
        mine = mystery_payload(game, seat=1)
        other = mystery_payload(game, seat=2)
        observer = mystery_payload(game)
        self.assertEqual(len(mine["campaign"]["owned_cards"]), 1)
        content = self.definition["campaign"]["cards"][0]["content"]
        self.assertNotIn(content, json.dumps(other, ensure_ascii=False))
        self.assertNotIn(content, json.dumps(observer, ensure_ascii=False))
        self.assertNotIn(content, json.dumps(build_safe_gm_context(game, 2, other), ensure_ascii=False))
        with self.assertRaises(ValueError):
            act(game.id, 2, "pick", {"card_id": "card01"})
        with self.assertRaises(ValueError):
            act(game.id, 1, "pick", {"card_id": "card02"})
        with self.assertRaises(ValueError):
            cast_vote(game, voter_seat=1, target_character_id=game.players.first().character_id)

    def test_loser_cannot_draw_but_dead_winner_can(self):
        game = self.create()
        for row in self.definition["campaign"]["rounds"][:2]:
            advance_game_phase(game.id)
            self.submit(game, row)
            advance_game_phase(game.id)
            if row["id"] == "r1":
                for seat in range(1, 10):
                    act(game.id, seat, "pick", {"card_id": f"card{seat:02}"})
                advance_game_phase(game.id)
        with self.assertRaises(ValueError):
            act(game.id, 2, "pick", {"card_id": "card10"})
        act(game.id, 4, "pick", {"card_id": "card10"})
        game.refresh_from_db()
        self.assertIn("代理人", mystery_payload(game, seat=4)["campaign"]["identity"])

    def test_variable_rounds_player_count_and_draw_quota(self):
        definition = copy.deepcopy(self.definition)
        definition["players"] = 4
        definition["characters"] = definition["characters"][:4]
        for card in definition["campaign"]["cards"]:
            card["interpretations"] = {}
        definition["campaign"]["rounds"] = definition["campaign"]["rounds"][:2]
        definition["campaign"]["rounds"][0]["draw"]["per_player"] = 2
        definition["campaign"]["rounds"][1].pop("draw")
        definition = parse_scenario(json.dumps(definition), "json")
        outcome = copy.deepcopy(self.outcome)
        outcome["players"] = outcome["players"][:4]
        game = self.create(definition, outcome)
        self.walk(game)
        self.assertEqual(len(game.state["card_owners"]), 8)
        self.assertEqual(len(game.scenario.definition["phases"]), 5)

    def test_fixed_character_independent_of_role(self):
        outcome = copy.deepcopy(self.outcome)
        outcome["players"][0]["character_id"] = "audio"
        outcome["players"][1]["character_id"] = "planner"
        game = self.create(outcome=outcome)
        self.assertEqual(game.players.get(seat=1).character_id, "audio")
        self.assertEqual(game.players.get(seat=2).character_id, "planner")

    def test_invalid_source_and_card_shortage(self):
        for mutate in [lambda x: x.update(winner_team="unknown"), lambda x: x["players"][0].update(seat=2), lambda x: x["players"][0].update(role="unknown")]:
            outcome = copy.deepcopy(self.outcome); mutate(outcome)
            with self.assertRaises(ValueError):
                self.create(outcome=outcome)
        definition = copy.deepcopy(self.definition)
        definition["campaign"]["rounds"][0]["draw"]["per_player"] = 2
        with self.assertRaises(ValueError):
            self.create(definition=definition)

    def test_download_reimport_and_api_rejections(self):
        response = self.client.get("/api/scenarios/sample/")
        self.assertIn("attachment", response["Content-Disposition"])
        raw = b"".join(response.streaming_content).decode()
        imported = self.client.post("/api/scenarios/import/", {"raw_text": raw}, format="json")
        self.assertEqual(imported.status_code, 201)
        self.assertEqual(imported.data["status"], "ready")
        created = self.client.post("/api/mystery/games/", {"scenario_id": imported.data["id"], "previous_result": self.outcome}, format="json")
        self.assertEqual(created.status_code, 201)
        url = f'/api/mystery/games/{created.data["id"]}'
        self.assertEqual(self.client.post(url + "/advance/", {"seat": 2}, format="json").status_code, 403)
        self.assertEqual(self.client.post(url + "/campaign/", {"seat": 99, "action": "pick", "card_id": "card01"}, format="json").status_code, 400)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "", "SCENARIO_AI_MODEL": ""})
    def test_ai_not_configured_does_not_block_yaml(self):
        response = self.client.post("/api/scenarios/structure/", {"text": "9人の事件"}, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertTrue(validate_scenario(self.definition)["valid"])

    @skipUnless(importlib.util.find_spec("langgraph"), "Optional AI dependencies not installed")
    def test_langgraph_repairs_and_stops_at_limit(self):
        from .scenario_ai import build_graph
        calls = []
        def repair(source, previous, report):
            calls.append(report)
            return "invalid json" if len(calls) == 1 else json.dumps(self.definition)
        result = build_graph(repair).invoke({"source": "test", "attempts": 0})
        self.assertTrue(result["report"]["valid"])
        self.assertEqual(result["attempts"], 2)
        failed = build_graph(lambda *_: "invalid", max_attempts=2).invoke({"source": "test", "attempts": 0})
        self.assertFalse(failed["report"]["valid"])
        self.assertEqual(failed["attempts"], 2)

    def test_evidence_limit_history_and_scoring_labels(self):
        game = self.create()
        advance_game_phase(game.id)
        self.submit(game, self.definition["campaign"]["rounds"][0])
        advance_game_phase(game.id)
        for seat in range(1, 10):
            act(game.id, seat, "pick", {"card_id": f"card{seat:02}"})
        advance_game_phase(game.id)
        advance_game_phase(game.id)
        with self.assertRaises(ValueError):
            act(game.id, 1, "submit", {"answers": {"mechanism": "test"}, "evidence": ["card01", "card02", "card03"]})
        game.refresh_from_db()
        mine = mystery_payload(game, seat=1)["campaign"]
        self.assertEqual(len(mine["team_members"]), 6)
        self.assertEqual(mine["my_history"][0]["answers"][0]["label"], "以前の録音の予約再生")
        self.assertIsNone(mystery_payload(game)["campaign"]["my_submission"])
        self.assertEqual(mystery_payload(game)["campaign"]["my_history"], [])
        self.assertEqual(mystery_payload(game)["campaign"]["team_members"], [])

    def test_invalid_campaign_rules_and_stale_round_actions(self):
        for mutate in [
            lambda c: c["cards"].append(copy.deepcopy(c["cards"][0])),
            lambda c: c["rounds"][0]["draw"].update(eligible="missing"),
            lambda c: c["rounds"][0]["questions"][0].update(answer="missing"),
            lambda c: c["teams"][0].update(id="all"),
            lambda c: c["rounds"][0]["questions"][0].update(evidence_points=1),
        ]:
            definition = copy.deepcopy(self.definition)
            mutate(definition["campaign"])
            with self.assertRaises(ValueError):
                parse_scenario(json.dumps(definition), "json")
        game = self.create()
        with self.assertRaises(ValueError):
            act(game.id, 1, "submit", {"answers": {"voice": "recording"}})
        with self.assertRaises(ValueError):
            act(game.id, 1, "pick", {"card_id": "card01"})

    @skipUnless(importlib.util.find_spec("langgraph"), "Optional AI dependencies not installed")
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-placeholder", "SCENARIO_AI_MODEL": "test-model"})
    def test_ai_endpoint_returns_reimportable_yaml_without_starting_game(self):
        from types import SimpleNamespace
        from .models import Game
        with patch("langchain_openai.ChatOpenAI") as model:
            model.return_value.bind.return_value.invoke.return_value = SimpleNamespace(content=json.dumps(self.definition))
            response = self.client.post("/api/scenarios/structure/", {"text": "9人、3会議で撮影中の事件を調べる。"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["validation_report"]["valid"])
        self.assertTrue(validate_scenario(parse_scenario(response.data["yaml"], "yaml"))["valid"])
        self.assertEqual(Scenario.objects.count(), 0)
        self.assertEqual(Game.objects.count(), 0)
