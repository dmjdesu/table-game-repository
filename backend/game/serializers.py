from rest_framework import serializers
from .config import AI_DIFFICULTIES, AI_VISIBILITIES, ROLE_LABELS


class VillageConfigSerializer(serializers.Serializer):
    player_count = serializers.IntegerField(min_value=5, max_value=15)
    roles = serializers.DictField(child=serializers.IntegerField(min_value=0, max_value=15))
    first_day_divination = serializers.BooleanField(default=True)
    consecutive_guard = serializers.BooleanField(default=False)
    role_missing = serializers.BooleanField(default=False)
    revote = serializers.BooleanField(default=True)
    speech_limit = serializers.IntegerField(min_value=3, max_value=20, default=8)
    ai_count = serializers.IntegerField(min_value=0)
    ai_difficulty = serializers.ChoiceField(choices=sorted(AI_DIFFICULTIES), default="standard")
    ai_count_visibility = serializers.ChoiceField(choices=sorted(AI_VISIBILITIES), default="range")

    def validate_roles(self, roles):
        unknown = set(roles) - set(ROLE_LABELS)
        if unknown:
            raise serializers.ValidationError(f"未対応の役職: {', '.join(sorted(unknown))}")
        if roles.get("wolf", 0) < 1:
            raise serializers.ValidationError("人狼を1人以上設定してください。")
        return roles

    def validate(self, attrs):
        player_count = attrs["player_count"]
        role_total = sum(attrs["roles"].values())
        if role_total != player_count:
            raise serializers.ValidationError({
                "roles": f"役職人数の合計({role_total})と参加人数({player_count})を一致させてください。"
            })
        if attrs["ai_count"] > player_count:
            raise serializers.ValidationError({"ai_count": "AI人数は参加人数以下にしてください。"})

        wolves = attrs["roles"].get("wolf", 0)
        if wolves * 2 >= player_count:
            raise serializers.ValidationError({
                "roles": "開始時点で人狼陣営が即時勝利に近すぎます。人狼人数を減らしてください。"
            })
        return attrs


class ScenarioImportSerializer(serializers.Serializer):
    raw_text = serializers.CharField(min_length=1)
    source_format = serializers.ChoiceField(
        choices=["yaml", "yml", "json", "markdown", "md", "txt"],
        default="yaml",
    )


class MysteryGameCreateSerializer(serializers.Serializer):
    scenario_id = serializers.UUIDField()
    name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    ai_count = serializers.IntegerField(min_value=0, default=0)
    ai_count_visibility = serializers.ChoiceField(
        choices=["exact", "range", "hidden"],
        default="range",
    )
    player_names = serializers.ListField(
        child=serializers.CharField(max_length=40),
        required=False,
        allow_empty=True,
    )


class MysteryActionSerializer(serializers.Serializer):
    seat = serializers.IntegerField(min_value=1)
    action = serializers.CharField(max_length=48)
    target = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")


class MysteryVoteSerializer(serializers.Serializer):
    seat = serializers.IntegerField(min_value=1)
    target_character_id = serializers.CharField(max_length=64)


class GMHelpSerializer(serializers.Serializer):
    seat = serializers.IntegerField(min_value=1)
    question = serializers.CharField(min_length=1, max_length=1000)
