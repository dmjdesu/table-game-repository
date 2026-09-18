from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("game", "0002_scenario_engine")]

    operations = [
        migrations.AddField(
            model_name="gameplayer",
            name="runtime_state",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.CreateModel(
            name="GameMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phase_key", models.CharField(blank=True, default="", max_length=80)),
                ("content", models.CharField(max_length=400)),
                ("ap_cost", models.PositiveSmallIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("game", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="game.game")),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="game.gameplayer")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
    ]
