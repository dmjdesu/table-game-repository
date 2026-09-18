import asyncio
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import Game, GamePlayer
from .realtime import (
    advance_game_phase,
    post_chat_message,
    realtime_snapshot,
)


@database_sync_to_async
def _seat_exists(game_id, seat: int) -> bool:
    return GamePlayer.objects.filter(game_id=game_id, seat=seat).exists()


@database_sync_to_async
def _game_exists(game_id) -> bool:
    return Game.objects.filter(id=game_id).exists()


@database_sync_to_async
def _snapshot(game_id, seat: int):
    return realtime_snapshot(game_id, seat)


@database_sync_to_async
def _post_message(game_id, seat: int, content: str):
    return post_chat_message(game_id, seat, content)


@database_sync_to_async
def _advance(game_id, require_expired: bool = False):
    return advance_game_phase(game_id, require_expired=require_expired)


class GameConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.game_id = self.scope["url_route"]["kwargs"]["game_id"]
        query = parse_qs(self.scope.get("query_string", b"").decode("utf-8"))
        try:
            self.seat = int((query.get("seat") or ["0"])[0])
        except ValueError:
            self.seat = 0

        if not await _game_exists(self.game_id):
            await self.close(code=4404)
            return
        if self.seat < 1 or not await _seat_exists(self.game_id, self.seat):
            await self.close(code=4403)
            return

        self.group_name = f"game_{self.game_id}"
        self.phase_event = asyncio.Event()

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_snapshot(reason="connected")
        self.timer_task = asyncio.create_task(self.phase_watch_loop())

    async def disconnect(self, close_code):
        timer_task = getattr(self, "timer_task", None)
        if timer_task:
            timer_task.cancel()
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        event_type = content.get("type")

        if event_type == "chat.send":
            try:
                result = await _post_message(
                    self.game_id,
                    self.seat,
                    str(content.get("content") or ""),
                )
            except (ValueError, GamePlayer.DoesNotExist) as exc:
                await self.send_json({"type": "error", "code": "chat_rejected", "message": str(exc)})
                return

            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "game.chat_message",
                    "message": result["message"],
                },
            )
            # 送信者だけAPが減るので即座に自分のsnapshotを更新。
            await self.send_snapshot(reason="chat.sent")
            return

        if event_type == "phase.advance":
            if self.seat != 1:
                await self.send_json({
                    "type": "error",
                    "code": "host_only",
                    "message": "MVPではSeat 1のみ手動でフェーズを進められます。",
                })
                return
            changed = await _advance(self.game_id, False)
            if changed:
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        "type": "game.state_changed",
                        "reason": "phase.manual",
                    },
                )
            return

        if event_type == "state.refresh":
            await self.send_snapshot(reason="refresh")
            return

        await self.send_json({
            "type": "error",
            "code": "unknown_event",
            "message": f"未対応のWebSocketイベントです: {event_type}",
        })

    async def game_chat_message(self, event):
        await self.send_json({
            "type": "chat.message",
            "message": event["message"],
        })

    async def game_state_changed(self, event):
        self.phase_event.set()
        await self.send_snapshot(reason=event.get("reason", "state.changed"))

    async def send_snapshot(self, reason: str):
        try:
            payload = await _snapshot(self.game_id, self.seat)
        except Game.DoesNotExist:
            await self.close(code=4404)
            return
        await self.send_json({
            "type": "snapshot",
            "reason": reason,
            **payload,
        })

    async def phase_watch_loop(self):
        try:
            while True:
                payload = await _snapshot(self.game_id, self.seat)
                timer = payload["realtime"]["phase_timer"]
                remaining = timer.get("remaining_seconds")
                if remaining is None:
                    self.phase_event.clear()
                    await self.phase_event.wait()
                    continue

                self.phase_event.clear()
                try:
                    await asyncio.wait_for(
                        self.phase_event.wait(),
                        timeout=max(0.25, float(remaining) + 0.25),
                    )
                    continue
                except asyncio.TimeoutError:
                    pass

                changed = await _advance(self.game_id, True)
                if changed:
                    await self.channel_layer.group_send(
                        self.group_name,
                        {
                            "type": "game.state_changed",
                            "reason": "phase.timer",
                        },
                    )
                else:
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            return
