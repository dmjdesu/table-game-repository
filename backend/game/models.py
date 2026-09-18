import uuid
from django.db import models


class Scenario(models.Model):
    class GameType(models.TextChoices):
        MURDER_MYSTERY = "murder_mystery", "Murder Mystery"
        TRPG = "trpg", "TRPG"
        ESCAPE = "escape", "Escape"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        READY = "ready", "Ready"
        INVALID = "invalid", "Invalid"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=160)
    game_type = models.CharField(
        max_length=32,
        choices=GameType.choices,
        default=GameType.MURDER_MYSTERY,
    )
    source_format = models.CharField(max_length=16, default="yaml")
    raw_text = models.TextField(blank=True)
    definition = models.JSONField(default=dict)
    validation_report = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Game(models.Model):
    class Status(models.TextChoices):
        LOBBY = "lobby", "Lobby"
        PLAYING = "playing", "Playing"
        FINISHED = "finished", "Finished"

    class GameType(models.TextChoices):
        WEREWOLF = "werewolf", "Werewolf"
        MURDER_MYSTERY = "murder_mystery", "Murder Mystery"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80, default="JINROID Village")
    game_type = models.CharField(
        max_length=32,
        choices=GameType.choices,
        default=GameType.WEREWOLF,
    )
    scenario = models.ForeignKey(
        Scenario,
        related_name="games",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.LOBBY)
    player_count = models.PositiveSmallIntegerField()
    ai_count = models.PositiveSmallIntegerField(default=0)
    config = models.JSONField(default=dict)
    abstract_state = models.JSONField(default=dict)
    strategy_profile = models.JSONField(default=dict)
    state = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class GamePlayer(models.Model):
    game = models.ForeignKey(Game, related_name="players", on_delete=models.CASCADE)
    seat = models.PositiveSmallIntegerField()
    display_name = models.CharField(max_length=40)
    role = models.CharField(max_length=32)
    is_ai = models.BooleanField(default=False)
    ai_profile = models.JSONField(default=dict, blank=True)
    character_id = models.CharField(max_length=64, blank=True, default="")
    known_information = models.JSONField(default=list, blank=True)
    runtime_state = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["game", "seat"], name="unique_game_seat")
        ]
        ordering = ["seat"]


class GameAction(models.Model):
    game = models.ForeignKey(Game, related_name="actions", on_delete=models.CASCADE)
    actor_seat = models.PositiveSmallIntegerField(null=True, blank=True)
    action_type = models.CharField(max_length=48)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class GameMessage(models.Model):
    game = models.ForeignKey(Game, related_name="messages", on_delete=models.CASCADE)
    player = models.ForeignKey(GamePlayer, related_name="messages", on_delete=models.CASCADE)
    phase_key = models.CharField(max_length=80, blank=True, default="")
    content = models.CharField(max_length=400)
    ap_cost = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
