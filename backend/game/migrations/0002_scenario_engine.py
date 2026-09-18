from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("game", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Scenario",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=160)),
                ("game_type", models.CharField(choices=[("murder_mystery", "Murder Mystery"), ("trpg", "TRPG"), ("escape", "Escape")], default="murder_mystery", max_length=32)),
                ("source_format", models.CharField(default="yaml", max_length=16)),
                ("raw_text", models.TextField(blank=True)),
                ("definition", models.JSONField(default=dict)),
                ("validation_report", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("ready", "Ready"), ("invalid", "Invalid")], default="draft", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name="game",
            name="game_type",
            field=models.CharField(choices=[("werewolf", "Werewolf"), ("murder_mystery", "Murder Mystery")], default="werewolf", max_length=32),
        ),
        migrations.AddField(
            model_name="game",
            name="scenario",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="games", to="game.scenario"),
        ),
        migrations.AddField(
            model_name="game",
            name="state",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="gameplayer",
            name="character_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="gameplayer",
            name="known_information",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.CreateModel(
            name="GameAction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actor_seat", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("action_type", models.CharField(max_length=48)),
                ("payload", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("game", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="actions", to="game.game")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
    ]
