import random
from django.db import transaction
from .models import Game, GamePlayer
from .strategy import build_abstract_state, build_strategy_profile


AI_PERSONAS = [
    {"name": "logical", "logic": 85, "talkativeness": 45, "memory": 75, "deception": 55},
    {"name": "actor", "logic": 65, "talkativeness": 75, "memory": 60, "deception": 88},
    {"name": "cautious", "logic": 72, "talkativeness": 32, "memory": 82, "deception": 62},
    {"name": "emotional", "logic": 48, "talkativeness": 84, "memory": 52, "deception": 68},
]


def _role_deck(roles: dict) -> list[str]:
    deck = []
    for role, count in roles.items():
        deck.extend([role] * count)
    return deck


def _ai_presence_hint(ai_count: int, player_count: int, visibility: str) -> str:
    if visibility == "exact":
        return f"AIプレイヤーは{ai_count}人参加します。"
    if visibility == "hidden":
        return "AIプレイヤーの人数は非公開です。"
    low = max(0, ai_count - 1)
    high = min(player_count, ai_count + 1)
    return f"AIプレイヤーは{low}〜{high}人参加している可能性があります。"


@transaction.atomic
def create_game(validated_config: dict, name: str = "JINROID Village") -> Game:
    config = dict(validated_config)
    config.setdefault("discussion_duration_seconds", 300)
    config.setdefault("vote_duration_seconds", 90)
    config.setdefault("night_duration_seconds", 90)
    config.setdefault("speech_ap_per_phase", config.get("speech_limit", 8))
    state = build_abstract_state(config)
    strategy = build_strategy_profile(state)

    game = Game.objects.create(
        name=name,
        game_type=Game.GameType.WEREWOLF,
        status=Game.Status.PLAYING,
        player_count=config["player_count"],
        ai_count=config["ai_count"],
        config=config,
        abstract_state=state,
        strategy_profile=strategy,
        state={"phase": "day_discussion", "day": 1},
    )

    seats = list(range(1, config["player_count"] + 1))
    roles = _role_deck(config["roles"])
    random.SystemRandom().shuffle(roles)
    ai_seats = set(random.SystemRandom().sample(seats, k=config["ai_count"]))

    for index, seat in enumerate(seats):
        is_ai = seat in ai_seats
        profile = random.SystemRandom().choice(AI_PERSONAS) if is_ai else {}
        if is_ai:
            profile = {**profile, "difficulty": config["ai_difficulty"]}
        GamePlayer.objects.create(
            game=game,
            seat=seat,
            display_name=f"Player {seat}",
            role=roles[index],
            is_ai=is_ai,
            ai_profile=profile,
        )

    from .realtime import initialize_realtime

    initialize_realtime(game.id)
    game.refresh_from_db()
    return game


def public_game_payload(game: Game) -> dict:
    visibility = game.config.get("ai_count_visibility", "range")
    return {
        "id": str(game.id),
        "name": game.name,
        "game_type": game.game_type,
        "status": game.status,
        "player_count": game.player_count,
        "ai_presence_hint": _ai_presence_hint(game.ai_count, game.player_count, visibility),
        "public_config": {
            "roles": {role: count for role, count in game.config.get("roles", {}).items()},
            "first_day_divination": game.config.get("first_day_divination", True),
            "consecutive_guard": game.config.get("consecutive_guard", False),
            "role_missing": game.config.get("role_missing", False),
            "revote": game.config.get("revote", True),
            "speech_limit": game.config.get("speech_limit", 8),
        },
        "players": [
            {"seat": player.seat, "display_name": player.display_name}
            for player in game.players.all()
        ],
        "abstract_state": game.abstract_state,
        "strategy_profile": game.strategy_profile,
        "created_at": game.created_at.isoformat(),
    }
