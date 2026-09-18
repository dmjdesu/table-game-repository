from django.contrib import admin
from .models import Game, GameAction, GameMessage, GamePlayer, Scenario

admin.site.register(Game)
admin.site.register(GamePlayer)
admin.site.register(Scenario)
admin.site.register(GameAction)
admin.site.register(GameMessage)
