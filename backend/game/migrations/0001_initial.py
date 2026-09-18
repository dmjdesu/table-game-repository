from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Game",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(default="JINROID Village", max_length=80)),
                ("status", models.CharField(choices=[("lobby", "Lobby"), ("playing", "Playing"), ("finished", "Finished")], default="lobby", max_length=16)),
                ("player_count", models.PositiveSmallIntegerField()),
                ("ai_count", models.PositiveSmallIntegerField(default=0)),
                ("config", models.JSONField(default=dict)),
                ("abstract_state", models.JSONField(default=dict)),
                ("strategy_profile", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="GamePlayer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("seat", models.PositiveSmallIntegerField()),
                ("display_name", models.CharField(max_length=40)),
                ("role", models.CharField(max_length=32)),
                ("is_ai", models.BooleanField(default=False)),
                ("ai_profile", models.JSONField(blank=True, default=dict)),
                ("game", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="players", to="game.game")),
            ],
            options={"ordering": ["seat"]},
        ),
        migrations.AddConstraint(
            model_name="gameplayer",
            constraint=models.UniqueConstraint(fields=("game", "seat"), name="unique_game_seat"),
        ),
    ]
