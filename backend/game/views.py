from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .config import PRESETS, ROLE_LABELS
from .gm import RuleBasedGM, build_safe_gm_context
from .models import Game, GamePlayer, Scenario
from .mystery import (
    cast_vote,
    create_mystery_game,
    mystery_payload,
    process_action,
)
from .realtime import advance_game_phase, broadcast_game_update, realtime_snapshot
from .scenario_parser import parse_scenario
from .scenario_validator import validate_scenario
from .serializers import (
    GMHelpSerializer,
    MysteryActionSerializer,
    MysteryGameCreateSerializer,
    MysteryVoteSerializer,
    ScenarioImportSerializer,
    VillageConfigSerializer,
)
from .services import create_game, public_game_payload
from .strategy import build_abstract_state, build_strategy_profile


@api_view(["GET"])
def presets(request):
    return Response({
        "roles": ROLE_LABELS,
        "presets": list(PRESETS.values()),
    })


@api_view(["POST"])
def validate_config(request):
    serializer = VillageConfigSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    state = build_abstract_state(serializer.validated_data)
    return Response({
        "valid": True,
        "abstract_state": state,
        "strategy_profile": build_strategy_profile(state),
    })


@api_view(["POST"])
def strategy_preview(request):
    serializer = VillageConfigSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    state = build_abstract_state(serializer.validated_data)
    return Response({
        "abstract_state": state,
        "strategy_profile": build_strategy_profile(state),
    })


@api_view(["POST"])
def games(request):
    payload = request.data.copy()
    name = payload.pop("name", "JINROID Village")
    serializer = VillageConfigSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    game = create_game(serializer.validated_data, name=name)
    return Response(public_game_payload(game), status=status.HTTP_201_CREATED)


@api_view(["GET"])
def game_detail(request, game_id):
    game = get_object_or_404(Game.objects.prefetch_related("players"), id=game_id)
    if game.game_type == Game.GameType.MURDER_MYSTERY:
        seat = request.query_params.get("seat")
        return Response(mystery_payload(game, seat=int(seat) if seat else None))
    return Response(public_game_payload(game))


@api_view(["GET"])
def game_realtime(request, game_id):
    seat = request.query_params.get("seat")
    seat_value = int(seat) if seat else None
    get_object_or_404(Game, id=game_id)
    if seat_value is not None and not GamePlayer.objects.filter(game_id=game_id, seat=seat_value).exists():
        return Response({"detail": "その座席は存在しません。"}, status=status.HTTP_400_BAD_REQUEST)
    return Response(realtime_snapshot(game_id, seat_value))


def _scenario_payload(scenario: Scenario, include_definition: bool = False) -> dict:
    payload = {
        "id": str(scenario.id),
        "title": scenario.title,
        "game_type": scenario.game_type,
        "source_format": scenario.source_format,
        "status": scenario.status,
        "validation_report": scenario.validation_report,
        "created_at": scenario.created_at.isoformat(),
    }
    if include_definition:
        payload["definition"] = scenario.definition
    return payload


@api_view(["POST"])
def import_scenario(request):
    serializer = ScenarioImportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    raw_text = serializer.validated_data["raw_text"]
    source_format = serializer.validated_data["source_format"]

    try:
        definition = parse_scenario(raw_text, source_format)
    except Exception as exc:
        return Response(
            {
                "detail": "シナリオを構造化できませんでした。",
                "parser_error": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    report = validate_scenario(definition)
    scenario = Scenario.objects.create(
        title=definition.get("title") or "Untitled Scenario",
        game_type=Scenario.GameType.MURDER_MYSTERY,
        source_format=source_format,
        raw_text=raw_text,
        definition=definition,
        validation_report=report,
        status=Scenario.Status.READY if report["valid"] else Scenario.Status.INVALID,
    )
    # import直後は作者本人が確認する前提なのでdefinitionを返す。
    # 保存済みシナリオの通常GETではtruth/secretsを含むdefinitionは返さない。
    return Response(_scenario_payload(scenario, include_definition=True), status=status.HTTP_201_CREATED)


@api_view(["GET"])
def scenario_detail(request, scenario_id):
    scenario = get_object_or_404(Scenario, id=scenario_id)
    return Response(_scenario_payload(scenario, include_definition=False))


@api_view(["POST"])
def mystery_games(request):
    serializer = MysteryGameCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    scenario = get_object_or_404(Scenario, id=data["scenario_id"])

    try:
        game = create_mystery_game(
            scenario,
            name=data.get("name") or scenario.title,
            player_names=data.get("player_names") or [],
            ai_count=data.get("ai_count", 0),
            ai_count_visibility=data.get("ai_count_visibility", "range"),
            previous_result=data.get("previous_result"),
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(mystery_payload(game), status=status.HTTP_201_CREATED)


def _mystery_game_or_404(game_id):
    return get_object_or_404(
        Game.objects.select_related("scenario").prefetch_related("players"),
        id=game_id,
        game_type=Game.GameType.MURDER_MYSTERY,
    )


@api_view(["GET"])
def mystery_game_detail(request, game_id):
    game = _mystery_game_or_404(game_id)
    seat = request.query_params.get("seat")
    return Response(mystery_payload(game, seat=int(seat) if seat else None))


@api_view(["POST"])
def mystery_advance(request, game_id):
    game = _mystery_game_or_404(game_id)
    if game.scenario.definition.get("campaign") and request.data.get("seat") != 1:
        return Response({"detail": "進行操作はホスト（座席1）が行ってください。"}, status=403)
    changed = advance_game_phase(game.id)
    game.refresh_from_db()
    if not changed and game.scenario.definition.get("campaign") and not game.state.get("finished"):
        return Response({"detail": "カード取得または陣営の回答が完了するまで進めません。"}, status=409)
    if changed:
        broadcast_game_update(game.id, "phase.http")
    seat = request.data.get("seat")
    return Response(mystery_payload(game, seat=int(seat) if seat else None))


@api_view(["POST"])
def mystery_action(request, game_id):
    game = _mystery_game_or_404(game_id)
    serializer = MysteryActionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    result = process_action(
        game,
        actor_seat=data["seat"],
        action=data["action"],
        target=data.get("target", ""),
    )
    game.refresh_from_db()
    broadcast_game_update(game.id, "action.http")
    return Response({
        "result": result,
        "game": mystery_payload(game, seat=data["seat"]),
    })


@api_view(["POST"])
def mystery_vote(request, game_id):
    game = _mystery_game_or_404(game_id)
    serializer = MysteryVoteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        cast_vote(
            game,
            voter_seat=data["seat"],
            target_character_id=data["target_character_id"],
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    game.refresh_from_db()
    broadcast_game_update(game.id, "vote.http")
    return Response(mystery_payload(game, seat=data["seat"]))


@api_view(["POST"])
def mystery_gm_help(request, game_id):
    game = _mystery_game_or_404(game_id)
    serializer = GMHelpSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    visible = mystery_payload(game, seat=data["seat"])
    if visible.get("me") is None:
        return Response({"detail": "その座席は存在しません。"}, status=status.HTTP_400_BAD_REQUEST)

    safe_context = build_safe_gm_context(game, data["seat"], visible)
    reply = RuleBasedGM().answer(question=data["question"], safe_context=safe_context)
    return Response({
        "text": reply.text,
        "source": reply.source,
        "safe_context": safe_context,
    })


@api_view(["GET"])
def scenario_sample(request):
    """Author download, intentionally includes the complete scenario and solution."""
    from pathlib import Path
    from django.http import FileResponse
    kind = request.query_params.get("kind", "scenario")
    filename = "previous_result.example.json" if kind == "result" else "neet_recording.yaml"
    path = Path(__file__).parent / "scenarios" / filename
    return FileResponse(path.open("rb"), as_attachment=True, filename=filename,
                        content_type="application/json" if kind == "result" else "application/yaml")


@api_view(["POST"])
def scenario_structure(request):
    from rest_framework import serializers
    from .scenario_ai import generate_yaml
    class Input(serializers.Serializer):
        text = serializers.CharField(min_length=1, max_length=50000)
    data = Input(data=request.data)
    data.is_valid(raise_exception=True)
    try:
        result = generate_yaml(data.validated_data["text"])
    except RuntimeError as exc:
        return Response({"detail": str(exc)}, status=503)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=422)
    except Exception:
        # Do not expose provider credentials, prompts or transport diagnostics.
        return Response({"detail": "AI構造化に失敗しました。時間を置いて再試行してください。"}, status=502)
    return Response(result)


@api_view(["POST"])
def campaign_action(request, game_id):
    from rest_framework import serializers
    from .campaign import act
    class Input(serializers.Serializer):
        seat = serializers.IntegerField(min_value=1)
        action = serializers.ChoiceField(choices=["pick", "submit"])
        card_id = serializers.CharField(required=False)
        answers = serializers.DictField(child=serializers.CharField(), required=False)
        evidence = serializers.ListField(child=serializers.CharField(), required=False)
    _mystery_game_or_404(game_id)
    serializer = Input(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        game = act(game_id, data["seat"], data["action"], data)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    broadcast_game_update(game.id, "campaign.http")
    return Response(mystery_payload(game, seat=data["seat"]))
