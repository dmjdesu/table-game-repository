from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from jinroid_api.asgi import application

from .services import create_game


class RealtimeWebsocketTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.config = {
            "player_count": 6,
            "roles": {
                "villager": 3,
                "wolf": 1,
                "seer": 1,
                "madman": 1,
            },
            "first_day_divination": True,
            "consecutive_guard": False,
            "role_missing": False,
            "revote": True,
            "speech_limit": 5,
            "ai_count": 2,
            "ai_difficulty": "standard",
            "ai_count_visibility": "range",
        }
        self.game = create_game(self.config, name="Socket Test")

    async def test_connect_chat_and_snapshot(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/games/{self.game.id}/?seat=1",
            headers=[
                (b"host", b"testserver"),
                (b"origin", b"http://testserver"),
            ],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        first = await communicator.receive_json_from(timeout=2)
        self.assertEqual(first["type"], "snapshot")
        self.assertEqual(first["realtime"]["speech_ap_remaining"], 5)
        self.assertEqual(first["game"]["me"]["seat"], 1)

        await communicator.send_json_to({
            "type": "chat.send",
            "content": "今日は誰から見ようか",
        })

        received = [
            await communicator.receive_json_from(timeout=2),
            await communicator.receive_json_from(timeout=2),
        ]
        by_type = {item["type"]: item for item in received}
        self.assertIn("chat.message", by_type)
        self.assertIn("snapshot", by_type)
        self.assertEqual(by_type["chat.message"]["message"]["seat"], 1)
        self.assertEqual(
            by_type["snapshot"]["realtime"]["speech_ap_remaining"],
            4,
        )

        await communicator.disconnect()

    async def test_non_host_cannot_advance_phase(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/games/{self.game.id}/?seat=2",
            headers=[
                (b"host", b"testserver"),
                (b"origin", b"http://testserver"),
            ],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_json_from(timeout=2)

        await communicator.send_json_to({"type": "phase.advance"})
        event = await communicator.receive_json_from(timeout=2)
        self.assertEqual(event["type"], "error")
        self.assertEqual(event["code"], "host_only")

        await communicator.disconnect()
