from __future__ import annotations

from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Game, GameAction, GameMessage, GamePlayer


WEREWOLF_PHASES = ("day_discussion", "day_vote", "night")


def _now():
    return timezone.now()


def _iso(value):
    return value.isoformat() if value else None


def _parse_time(value):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def get_phase_key(game: Game) -> str:
    if game.game_type == Game.GameType.MURDER_MYSTERY and game.scenario:
        phases = game.scenario.definition.get("phases", [])
        index = int(game.state.get("current_phase_index", 0))
        if 0 <= index < len(phases):
            return str(phases[index].get("id") or f"phase-{index + 1}")
        return "finished"
    day = int(game.state.get("day", 1))
    return f"day-{day}:{game.state.get('phase', 'day_discussion')}"


def get_phase_duration_seconds(game: Game) -> int:
    if game.game_type == Game.GameType.MURDER_MYSTERY and game.scenario:
        phases = game.scenario.definition.get("phases", [])
        index = int(game.state.get("current_phase_index", 0))
        if 0 <= index < len(phases):
            return max(0, int(phases[index].get("duration_seconds") or 0))
        return 0

    phase = game.state.get("phase", "day_discussion")
    if phase == "day_vote":
        return int(game.config.get("vote_duration_seconds", 90))
    if phase == "night":
        return int(game.config.get("night_duration_seconds", 90))
    return int(game.config.get("discussion_duration_seconds", 300))


def get_speech_budget(game: Game) -> int:
    return max(
        1,
        int(
            game.config.get(
                "speech_ap_per_phase",
                game.config.get("speech_limit", 8),
            )
        ),
    )


def message_ap_cost(content: str) -> int:
    length = len("".join(content.split()))
    if length <= 40:
        return 1
    if length <= 120:
        return 2
    return 3


def _reset_runtime_locked(game: Game, *, start_timer: bool = True) -> None:
    budget = get_speech_budget(game)
    now = _now()
    duration = get_phase_duration_seconds(game)
    state = dict(game.state)
    state["phase_started_at"] = _iso(now)
    state["phase_ends_at"] = _iso(now + timedelta(seconds=duration)) if start_timer and duration > 0 else None
    state["phase_key"] = get_phase_key(game)
    game.state = state
    game.save(update_fields=["state"])

    GamePlayer.objects.filter(game=game).update(
        runtime_state={
            "speech_ap_total": budget,
            "speech_ap_remaining": budget,
            "phase_key": state["phase_key"],
        }
    )


@transaction.atomic
def initialize_realtime(game_id) -> Game:
    game = (
        Game.objects.select_for_update()
        .select_related("scenario")
        .get(id=game_id)
    )
    _reset_runtime_locked(game)
    return game


def phase_timer_payload(game: Game) -> dict:
    now = _now()
    ends_at = _parse_time(game.state.get("phase_ends_at"))
    remaining = None
    if ends_at:
        remaining = max(0, int((ends_at - now).total_seconds()))
    return {
        "phase_key": game.state.get("phase_key") or get_phase_key(game),
        "started_at": game.state.get("phase_started_at"),
        "ends_at": game.state.get("phase_ends_at"),
        "remaining_seconds": remaining,
        "server_now": _iso(now),
    }


def serialize_message(message: GameMessage) -> dict:
    return {
        "id": message.id,
        "seat": message.player.seat,
        "display_name": message.player.display_name,
        "content": message.content,
        "ap_cost": message.ap_cost,
        "phase_key": message.phase_key,
        "created_at": message.created_at.isoformat(),
    }


def recent_messages(game: Game, limit: int = 100) -> list[dict]:
    rows = list(
        GameMessage.objects.filter(game=game)
        .select_related("player")
        .order_by("-id")[:limit]
    )
    rows.reverse()
    return [serialize_message(row) for row in rows]


@transaction.atomic
def post_chat_message(game_id, seat: int, content: str) -> dict:
    content = str(content or "").strip()
    if not content:
        raise ValueError("発言内容が空です。")
    if len(content) > 400:
        raise ValueError("1発言は400文字以内にしてください。")

    player = (
        GamePlayer.objects.select_for_update()
        .select_related("game", "game__scenario")
        .get(game_id=game_id, seat=seat)
    )
    game = player.game
    if game.status == Game.Status.FINISHED or game.state.get("finished"):
        raise ValueError("終了済みのゲームでは発言できません。")

    budget = get_speech_budget(game)
    runtime = dict(player.runtime_state or {})
    current_key = get_phase_key(game)
    if runtime.get("phase_key") != current_key:
        runtime = {
            "speech_ap_total": budget,
            "speech_ap_remaining": budget,
            "phase_key": current_key,
        }

    cost = message_ap_cost(content)
    remaining = int(runtime.get("speech_ap_remaining", budget))
    if cost > remaining:
        raise ValueError(f"発言APが不足しています。残り{remaining}APです。")

    runtime["speech_ap_remaining"] = remaining - cost
    player.runtime_state = runtime
    player.save(update_fields=["runtime_state"])

    message = GameMessage.objects.create(
        game=game,
        player=player,
        phase_key=current_key,
        content=content,
        ap_cost=cost,
    )
    GameAction.objects.create(
        game=game,
        actor_seat=seat,
        action_type="chat_message",
        payload={"message_id": message.id, "ap_cost": cost},
    )
    return {
        "message": serialize_message(message),
        "runtime": runtime,
    }


def _advance_mystery_locked(game: Game) -> bool:
    definition = game.scenario.definition
    phases = definition.get("phases", [])
    index = int(game.state.get("current_phase_index", 0))
    if index + 1 >= len(phases):
        state = dict(game.state)
        state["phase_ends_at"] = None
        game.state = state
        game.save(update_fields=["state"])
        return False

    state = dict(game.state)
    next_index = index + 1
    state["current_phase_index"] = next_index
    unlocked = list(state.get("unlocked_evidence", []))
    for evidence_id in phases[next_index].get("start_evidence", []) or []:
        if evidence_id not in unlocked:
            unlocked.append(evidence_id)
    state["unlocked_evidence"] = unlocked
    game.state = state
    game.save(update_fields=["state"])
    GameAction.objects.create(
        game=game,
        action_type="phase_advanced",
        payload={"phase": phases[next_index].get("id")},
    )
    _reset_runtime_locked(game)
    return True


def _advance_werewolf_locked(game: Game) -> bool:
    state = dict(game.state)
    phase = state.get("phase", "day_discussion")
    day = int(state.get("day", 1))

    if phase == "day_discussion":
        state["phase"] = "day_vote"
    elif phase == "day_vote":
        state["phase"] = "night"
    else:
        state["phase"] = "day_discussion"
        state["day"] = day + 1

    game.state = state
    game.status = Game.Status.PLAYING
    game.save(update_fields=["state", "status"])
    GameAction.objects.create(
        game=game,
        action_type="phase_advanced",
        payload={"phase": state["phase"], "day": state.get("day", day)},
    )
    _reset_runtime_locked(game)
    return True


@transaction.atomic
def advance_game_phase(game_id, *, require_expired: bool = False) -> bool:
    game = (
        Game.objects.select_for_update()
        .select_related("scenario")
        .get(id=game_id)
    )
    if game.status == Game.Status.FINISHED or game.state.get("finished"):
        return False

    if require_expired:
        ends_at = _parse_time(game.state.get("phase_ends_at"))
        if not ends_at or _now() < ends_at:
            return False

    if game.game_type == Game.GameType.MURDER_MYSTERY:
        return _advance_mystery_locked(game)
    return _advance_werewolf_locked(game)


def private_game_payload(game: Game, seat: int | None) -> dict:
    if game.game_type == Game.GameType.MURDER_MYSTERY:
        from .mystery import mystery_payload

        return mystery_payload(game, seat=seat)

    from .services import public_game_payload

    payload = public_game_payload(game)
    if seat is None:
        payload["me"] = None
        return payload

    player = next((row for row in game.players.all() if row.seat == seat), None)
    if not player:
        payload["me"] = None
        return payload

    me = {
        "seat": player.seat,
        "display_name": player.display_name,
        "role": player.role,
    }
    if player.role == "wolf":
        me["known_allies"] = [
            {
                "seat": ally.seat,
                "display_name": ally.display_name,
            }
            for ally in game.players.all()
            if ally.role == "wolf" and ally.seat != seat
        ]
    payload["me"] = me
    return payload


def realtime_snapshot(game_id, seat: int | None = None) -> dict:
    game = (
        Game.objects.select_related("scenario")
        .prefetch_related("players")
        .get(id=game_id)
    )
    player = next((row for row in game.players.all() if row.seat == seat), None) if seat else None
    runtime = dict(player.runtime_state or {}) if player else {}
    budget = get_speech_budget(game)

    return {
        "game": private_game_payload(game, seat),
        "realtime": {
            "phase_timer": phase_timer_payload(game),
            "speech_ap_total": int(runtime.get("speech_ap_total", budget)),
            "speech_ap_remaining": int(runtime.get("speech_ap_remaining", budget)),
            "messages": recent_messages(game),
        },
    }


def broadcast_game_update(game_id, reason: str = "state.updated") -> None:
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    async_to_sync(channel_layer.group_send)(
        f"game_{game_id}",
        {
            "type": "game.state_changed",
            "reason": reason,
        },
    )
