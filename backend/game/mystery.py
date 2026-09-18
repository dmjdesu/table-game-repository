import random
from collections import Counter

from django.db import transaction

from .models import Game, GameAction, GamePlayer, Scenario


def _character_map(definition: dict) -> dict:
    return {item["id"]: item for item in definition.get("characters", [])}


def _evidence_map(definition: dict) -> dict:
    return {item["id"]: item for item in definition.get("evidence", [])}


def _current_phase(game: Game) -> dict | None:
    phases = game.scenario.definition.get("phases", []) if game.scenario else []
    index = int(game.state.get("current_phase_index", 0))
    return phases[index] if 0 <= index < len(phases) else None


def _initial_state(definition: dict) -> dict:
    phases = definition.get("phases", [])
    first_phase = phases[0] if phases else {}
    return {
        "current_phase_index": 0,
        "unlocked_evidence": list(first_phase.get("start_evidence", []) or []),
        "triggered_events": [],
        "votes": {},
        "flags": {},
        "finished": False,
        "ending_id": None,
    }


def _ai_presence_hint(ai_count: int, player_count: int, visibility: str) -> str:
    if visibility == "exact":
        return f"AIプレイヤーは{ai_count}人参加します。"
    if visibility == "hidden":
        return "AIプレイヤーの人数は非公開です。"
    low = max(0, ai_count - 1)
    high = min(player_count, ai_count + 1)
    return f"AIプレイヤーは{low}〜{high}人参加している可能性があります。"


@transaction.atomic
def create_mystery_game(
    scenario: Scenario,
    *,
    name: str | None = None,
    player_names: list[str] | None = None,
    ai_count: int = 0,
    ai_count_visibility: str = "range",
) -> Game:
    if scenario.status != Scenario.Status.READY:
        raise ValueError("検証済みのシナリオだけゲーム開始できます。")

    definition = scenario.definition
    characters = list(definition.get("characters", []))
    player_count = int(definition.get("players") or len(characters))
    if len(characters) != player_count:
        raise ValueError("キャラクター人数とプレイヤー人数が一致していません。")
    if not 0 <= ai_count <= player_count:
        raise ValueError("AI人数が不正です。")

    names = list(player_names or [])
    names += [f"Player {index}" for index in range(len(names) + 1, player_count + 1)]
    names = names[:player_count]

    shuffled = characters[:]
    random.SystemRandom().shuffle(shuffled)
    seats = list(range(1, player_count + 1))
    ai_seats = set(random.SystemRandom().sample(seats, k=ai_count))

    game = Game.objects.create(
        name=name or scenario.title,
        game_type=Game.GameType.MURDER_MYSTERY,
        scenario=scenario,
        status=Game.Status.PLAYING,
        player_count=player_count,
        ai_count=ai_count,
        config={
            "ai_count_visibility": ai_count_visibility,
            "source_format": scenario.source_format,
            "speech_ap_per_phase": 12,
        },
        state=_initial_state(definition),
        abstract_state={
            "game_type": "murder_mystery",
            "players": player_count,
            "phases": len(definition.get("phases", [])),
            "evidence": len(definition.get("evidence", [])),
            "branch_events": len(definition.get("events", [])),
        },
        strategy_profile={
            "gm_policy": "rule_engine_first",
            "information_policy": "server_side_visibility",
        },
    )

    for index, seat in enumerate(seats):
        character = shuffled[index]
        known_information = [
            *[{"type": "secret", "text": text} for text in character.get("secrets", [])],
            *[{"type": "objective", "text": text} for text in character.get("objectives", [])],
        ]
        GamePlayer.objects.create(
            game=game,
            seat=seat,
            display_name=names[index],
            role="character",
            is_ai=seat in ai_seats,
            ai_profile={"kind": "gm_player"} if seat in ai_seats else {},
            character_id=character["id"],
            known_information=known_information,
        )

    GameAction.objects.create(game=game, action_type="game_started", payload={"phase": _current_phase(game)})

    from .realtime import initialize_realtime

    initialize_realtime(game.id)
    game.refresh_from_db()
    return game


def _visible_evidence(game: Game) -> list[dict]:
    evidence_by_id = _evidence_map(game.scenario.definition)
    result = []
    for evidence_id in game.state.get("unlocked_evidence", []):
        evidence = evidence_by_id.get(evidence_id)
        if evidence:
            result.append({
                "id": evidence["id"],
                "title": evidence.get("title", evidence["id"]),
                "content": evidence.get("content", ""),
            })
    return result


def mystery_payload(game: Game, *, seat: int | None = None) -> dict:
    definition = game.scenario.definition
    characters = _character_map(definition)
    current_phase = _current_phase(game)
    player_rows = []
    me = None

    for player in game.players.all():
        character = characters.get(player.character_id, {})
        public_player = {
            "seat": player.seat,
            "display_name": player.display_name,
            "character_id": player.character_id,
            "character_name": character.get("name", player.character_id),
            "role": character.get("role", ""),
            "public_profile": character.get("public_profile", ""),
        }
        player_rows.append(public_player)
        if seat == player.seat:
            me = {
                **public_player,
                "secrets": [item["text"] for item in player.known_information if item.get("type") == "secret"],
                "objectives": [item["text"] for item in player.known_information if item.get("type") == "objective"],
            }

    resolution = None
    if game.state.get("finished"):
        ending_id = game.state.get("ending_id")
        ending = next((item for item in definition.get("endings", []) if item.get("id") == ending_id), None)
        resolution = {
            "ending_id": ending_id,
            "label": (ending or {}).get("label", ""),
            "text": (ending or {}).get("text", ""),
            "truth": definition.get("truth", {}),
        }

    return {
        "id": str(game.id),
        "name": game.name,
        "game_type": game.game_type,
        "status": game.status,
        "ai_presence_hint": _ai_presence_hint(
            game.ai_count,
            game.player_count,
            game.config.get("ai_count_visibility", "range"),
        ),
        "players": player_rows,
        "me": me,
        "phase": current_phase,
        "evidence": _visible_evidence(game),
        "votes_cast": len(game.state.get("votes", {})),
        "finished": bool(game.state.get("finished")),
        "resolution": resolution,
    }


@transaction.atomic
def advance_phase(game: Game) -> Game:
    if game.state.get("finished"):
        return game
    definition = game.scenario.definition
    phases = definition.get("phases", [])
    index = int(game.state.get("current_phase_index", 0))
    if index + 1 >= len(phases):
        return game

    state = dict(game.state)
    state["current_phase_index"] = index + 1
    unlocked = list(state.get("unlocked_evidence", []))
    for evidence_id in phases[index + 1].get("start_evidence", []) or []:
        if evidence_id not in unlocked:
            unlocked.append(evidence_id)
    state["unlocked_evidence"] = unlocked
    game.state = state
    game.save(update_fields=["state"])
    GameAction.objects.create(
        game=game,
        action_type="phase_advanced",
        payload={"phase": phases[index + 1].get("id")},
    )
    return game


@transaction.atomic
def process_action(game: Game, *, actor_seat: int, action: str, target: str = "") -> dict:
    if game.state.get("finished"):
        return {"triggered": [], "message": "ゲームは終了しています。"}

    definition = game.scenario.definition
    phase = _current_phase(game) or {}
    state = dict(game.state)
    triggered_ids = list(state.get("triggered_events", []))
    unlocked = list(state.get("unlocked_evidence", []))
    flags = dict(state.get("flags", {}))
    matched = []

    for event in definition.get("events", []):
        if event.get("id") in triggered_ids:
            continue
        trigger = event.get("trigger") or {}
        conditions = event.get("conditions") or {}
        if trigger.get("action") and trigger.get("action") != action:
            continue
        if trigger.get("target") and trigger.get("target") != target:
            continue
        if conditions.get("phase") and conditions.get("phase") != phase.get("id"):
            continue

        result = event.get("result") or {}
        for evidence_id in result.get("unlock_evidence", []) or []:
            if evidence_id not in unlocked:
                unlocked.append(evidence_id)
        flags.update(result.get("set_flags") or {})
        triggered_ids.append(event.get("id"))
        matched.append({
            "event_id": event.get("id"),
            "message": result.get("message") or "",
        })

    state["triggered_events"] = triggered_ids
    state["unlocked_evidence"] = unlocked
    state["flags"] = flags
    game.state = state
    game.save(update_fields=["state"])
    GameAction.objects.create(
        game=game,
        actor_seat=actor_seat,
        action_type=action,
        payload={"target": target, "triggered": matched},
    )
    return {"triggered": matched, "evidence": _visible_evidence(game)}


def _resolve_ending(game: Game) -> None:
    definition = game.scenario.definition
    votes = game.state.get("votes", {})
    counter = Counter(votes.values())
    culprit = str((definition.get("truth") or {}).get("culprit", ""))
    culprit_is_unique_max = False

    if counter and culprit:
        max_votes = max(counter.values())
        top = [candidate for candidate, count in counter.items() if count == max_votes]
        culprit_is_unique_max = top == [culprit]

    selected = None
    for ending in definition.get("endings", []):
        condition_type = (ending.get("condition") or {}).get("type")
        if condition_type == "culprit_votes_max" and culprit_is_unique_max:
            selected = ending
            break
    if not selected:
        selected = next(
            (ending for ending in definition.get("endings", []) if (ending.get("condition") or {}).get("type") == "default"),
            None,
        )
    if not selected and definition.get("endings"):
        selected = definition["endings"][0]

    state = dict(game.state)
    state["finished"] = True
    state["ending_id"] = selected.get("id") if selected else None
    game.state = state
    game.status = Game.Status.FINISHED
    game.save(update_fields=["state", "status"])
    GameAction.objects.create(game=game, action_type="game_resolved", payload={"ending_id": state["ending_id"]})


@transaction.atomic
def cast_vote(game: Game, *, voter_seat: int, target_character_id: str) -> Game:
    if game.state.get("finished"):
        return game
    character_ids = set(_character_map(game.scenario.definition))
    if target_character_id not in character_ids:
        raise ValueError("投票先のキャラクターが存在しません。")
    if not game.players.filter(seat=voter_seat).exists():
        raise ValueError("投票者の座席が存在しません。")

    state = dict(game.state)
    votes = dict(state.get("votes", {}))
    votes[str(voter_seat)] = target_character_id
    state["votes"] = votes
    game.state = state
    game.save(update_fields=["state"])
    GameAction.objects.create(
        game=game,
        actor_seat=voter_seat,
        action_type="vote",
        payload={"target_character_id": target_character_id},
    )
    if len(votes) >= game.player_count:
        _resolve_ending(game)
        game.refresh_from_db()
    return game
