from django.urls import path
from . import views

urlpatterns = [
    path("presets/", views.presets, name="presets"),
    path("config/validate/", views.validate_config, name="validate-config"),
    path("strategy/preview/", views.strategy_preview, name="strategy-preview"),
    path("games/", views.games, name="games"),
    path("games/<uuid:game_id>/", views.game_detail, name="game-detail"),
    path("games/<uuid:game_id>/realtime/", views.game_realtime, name="game-realtime"),

    path("scenarios/import/", views.import_scenario, name="scenario-import"),
    path("scenarios/<uuid:scenario_id>/", views.scenario_detail, name="scenario-detail"),

    path("mystery/games/", views.mystery_games, name="mystery-games"),
    path("mystery/games/<uuid:game_id>/", views.mystery_game_detail, name="mystery-game-detail"),
    path("mystery/games/<uuid:game_id>/advance/", views.mystery_advance, name="mystery-advance"),
    path("mystery/games/<uuid:game_id>/actions/", views.mystery_action, name="mystery-action"),
    path("mystery/games/<uuid:game_id>/vote/", views.mystery_vote, name="mystery-vote"),
    path("mystery/games/<uuid:game_id>/gm/help/", views.mystery_gm_help, name="mystery-gm-help"),
]
