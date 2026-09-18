import json

from django.test import TestCase
from rest_framework.test import APIClient

from .models import GamePlayer
from .realtime import advance_game_phase, message_ap_cost, post_chat_message, realtime_snapshot


SCENARIO_YAML = """
title: 雪山荘の惨劇
players: 3

characters:
  - id: a
    name: 秋山
    role: 医師
    public_profile: 被害者の主治医
    secrets:
      - 被害者と金銭トラブルがあった
    objectives:
      - 犯人を特定する
      - 金銭トラブルを隠す
  - id: b
    name: 美月
    role: 記者
    secrets:
      - 21時に書斎付近で物音を聞いた
    objectives:
      - 特ダネを持ち帰る
  - id: c
    name: 千堂
    role: 実業家
    secrets:
      - あなたが犯人である
    objectives:
      - 自分への投票を避ける

truth:
  culprit: c
  crime_time: "22:15"
  crime_scene: 書斎
  weapon: ナイフ
  solution: 千堂は停電中に書斎へ入り犯行に及んだ。

evidence:
  - id: corpse
    title: 遺体
    content: 胸部に刺創がある。
  - id: diary
    title: 被害者の日記
    content: 千堂との口論について書かれている。

phases:
  - id: introduction
    label: 導入
    type: discussion
    duration: 5分
    start_evidence:
      - corpse
    instructions: 自己紹介と公開情報の確認を行ってください。
  - id: investigation
    label: 第一調査
    type: investigation
    duration: 20分
    instructions: 調べたい場所を選んでください。
  - id: voting
    label: 投票
    type: voting
    duration: 5分
    instructions: 最も犯人だと思う人物へ投票してください。

events:
  - id: discover_diary
    trigger:
      action: investigate
      target: desk
    conditions:
      phase: investigation
    result:
      unlock_evidence:
        - diary
      message: 机の引き出しから日記を発見した。

endings:
  - id: true_end
    label: 真相解明
    condition:
      type: culprit_votes_max
    text: 村は真犯人を突き止めた。
  - id: bad_end
    label: 迷宮入り
    condition:
      type: default
    text: 真犯人は逃げ切った。
"""


class WerewolfApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.config = {
            "player_count": 8,
            "roles": {"villager": 3, "wolf": 2, "seer": 1, "medium": 1, "guard": 1},
            "first_day_divination": True,
            "consecutive_guard": False,
            "role_missing": False,
            "revote": True,
            "speech_limit": 8,
            "ai_count": 4,
            "ai_difficulty": "standard",
            "ai_count_visibility": "range",
        }

    def test_presets(self):
        response = self.client.get("/api/presets/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["presets"]), 3)

    def test_rejects_role_total_mismatch(self):
        bad = {**self.config, "roles": {"villager": 2, "wolf": 2}}
        response = self.client.post("/api/config/validate/", bad, format="json")
        self.assertEqual(response.status_code, 400)

    def test_game_creation_hides_ai_identity_and_roles(self):
        response = self.client.post("/api/games/", {"name": "Test", **self.config}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(GamePlayer.objects.filter(is_ai=True).count(), 4)
        for player in response.data["players"]:
            self.assertNotIn("is_ai", player)
            self.assertNotIn("role", player)

    def test_strategy_cache_key_is_present(self):
        response = self.client.post("/api/strategy/preview/", self.config, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("cache_key", response.data["strategy_profile"])

    def test_realtime_chat_uses_ap_and_private_role(self):
        response = self.client.post("/api/games/", {"name": "Realtime", **self.config}, format="json")
        game_id = response.data["id"]

        snapshot = realtime_snapshot(game_id, 1)
        self.assertEqual(snapshot["realtime"]["speech_ap_remaining"], 8)
        self.assertIsNotNone(snapshot["game"]["me"]["role"])

        result = post_chat_message(game_id, 1, "短い発言")
        self.assertEqual(result["message"]["ap_cost"], 1)
        after = realtime_snapshot(game_id, 1)
        self.assertEqual(after["realtime"]["speech_ap_remaining"], 7)
        self.assertEqual(len(after["realtime"]["messages"]), 1)

    def test_message_cost_and_phase_reset(self):
        self.assertEqual(message_ap_cost("a" * 20), 1)
        self.assertEqual(message_ap_cost("a" * 80), 2)
        self.assertEqual(message_ap_cost("a" * 200), 3)

        response = self.client.post("/api/games/", {"name": "Phase", **self.config}, format="json")
        game_id = response.data["id"]
        post_chat_message(game_id, 1, "a" * 80)
        self.assertEqual(realtime_snapshot(game_id, 1)["realtime"]["speech_ap_remaining"], 6)

        self.assertTrue(advance_game_phase(game_id))
        updated = realtime_snapshot(game_id, 1)
        self.assertEqual(updated["realtime"]["speech_ap_remaining"], 8)
        self.assertIn("day_vote", updated["realtime"]["phase_timer"]["phase_key"])


class MysteryEngineTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def import_scenario(self):
        response = self.client.post(
            "/api/scenarios/import/",
            {"source_format": "yaml", "raw_text": SCENARIO_YAML},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "ready")
        return response.data

    def create_session(self, ai_count=1):
        scenario = self.import_scenario()
        response = self.client.post(
            "/api/mystery/games/",
            {
                "scenario_id": scenario["id"],
                "name": "テスト雪山荘",
                "player_names": ["P1", "P2", "P3"],
                "ai_count": ai_count,
                "ai_count_visibility": "range",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        return response.data

    def test_import_and_validation(self):
        scenario = self.import_scenario()
        self.assertTrue(scenario["validation_report"]["valid"])
        self.assertEqual(scenario["definition"]["truth"]["culprit"], "c")
        self.assertEqual(scenario["validation_report"]["summary"]["phases"], 3)

    def test_player_payload_hides_truth_ai_and_other_secrets(self):
        game = self.create_session(ai_count=1)
        self.assertNotIn("truth", game)
        for player in game["players"]:
            self.assertNotIn("is_ai", player)
            self.assertNotIn("secrets", player)

        response = self.client.get(f"/api/mystery/games/{game['id']}/?seat=1")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data["me"])
        self.assertIn("secrets", response.data["me"])
        self.assertIsNone(response.data["resolution"])

    def test_phase_action_unlocks_evidence(self):
        game = self.create_session(ai_count=0)
        self.assertEqual([item["id"] for item in game["evidence"]], ["corpse"])

        response = self.client.post(
            f"/api/mystery/games/{game['id']}/advance/",
            {"seat": 1},
            format="json",
        )
        self.assertEqual(response.data["phase"]["id"], "investigation")

        action = self.client.post(
            f"/api/mystery/games/{game['id']}/actions/",
            {"seat": 1, "action": "investigate", "target": "desk"},
            format="json",
        )
        evidence_ids = [item["id"] for item in action.data["game"]["evidence"]]
        self.assertIn("diary", evidence_ids)
        self.assertEqual(action.data["result"]["triggered"][0]["event_id"], "discover_diary")

    def test_votes_resolve_and_only_then_reveal_truth(self):
        game = self.create_session(ai_count=0)
        for seat in [1, 2, 3]:
            response = self.client.post(
                f"/api/mystery/games/{game['id']}/vote/",
                {"seat": seat, "target_character_id": "c"},
                format="json",
            )

        self.assertTrue(response.data["finished"])
        self.assertEqual(response.data["resolution"]["ending_id"], "true_end")
        self.assertEqual(response.data["resolution"]["truth"]["culprit"], "c")

    def test_gm_context_is_server_filtered(self):
        game = self.create_session(ai_count=0)
        response = self.client.post(
            f"/api/mystery/games/{game['id']}/gm/help/",
            {"seat": 1, "question": "次は何すればいい？"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("truth", response.data["safe_context"])
        self.assertNotIn("definition", response.data["safe_context"])
        self.assertIn("current_phase", response.data["safe_context"])

    def test_invalid_scenario_cannot_start(self):
        invalid = SCENARIO_YAML.replace("  culprit: c\n", "")
        imported = self.client.post(
            "/api/scenarios/import/",
            {"source_format": "yaml", "raw_text": invalid},
            format="json",
        )
        self.assertEqual(imported.data["status"], "invalid")

        started = self.client.post(
            "/api/mystery/games/",
            {"scenario_id": imported.data["id"], "ai_count": 0},
            format="json",
        )
        self.assertEqual(started.status_code, 400)
