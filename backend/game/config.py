ROLE_LABELS = {
    "villager": "村人",
    "wolf": "人狼",
    "seer": "占い師",
    "medium": "霊媒師",
    "guard": "狩人",
    "madman": "狂人",
}

ROLE_TEAMS = {
    "villager": "village",
    "wolf": "wolf",
    "seer": "village",
    "medium": "village",
    "guard": "village",
    "madman": "wolf_support",
}

PRESETS = {
    "6_standard": {
        "id": "6_standard",
        "label": "6人 スピード村",
        "description": "短時間で遊べる小規模構成。狂人入りで情報戦が早い。",
        "player_count": 6,
        "roles": {"villager": 3, "wolf": 1, "seer": 1, "madman": 1},
        "first_day_divination": True,
        "consecutive_guard": False,
        "role_missing": False,
        "revote": True,
        "speech_limit": 8,
        "ai_count": 3,
        "ai_difficulty": "standard",
        "ai_count_visibility": "range",
    },
    "8_standard": {
        "id": "8_standard",
        "label": "8人 王道村",
        "description": "2狼・占い・霊媒・狩人。MVPの基準構成。",
        "player_count": 8,
        "roles": {"villager": 3, "wolf": 2, "seer": 1, "medium": 1, "guard": 1},
        "first_day_divination": True,
        "consecutive_guard": False,
        "role_missing": False,
        "revote": True,
        "speech_limit": 8,
        "ai_count": 4,
        "ai_difficulty": "standard",
        "ai_count_visibility": "range",
    },
    "10_standard": {
        "id": "10_standard",
        "label": "10人 推理村",
        "description": "狂人を含む標準的な中規模構成。ライン考察が増える。",
        "player_count": 10,
        "roles": {"villager": 4, "wolf": 2, "seer": 1, "medium": 1, "guard": 1, "madman": 1},
        "first_day_divination": True,
        "consecutive_guard": False,
        "role_missing": False,
        "revote": True,
        "speech_limit": 8,
        "ai_count": 5,
        "ai_difficulty": "standard",
        "ai_count_visibility": "range",
    },
}

AI_DIFFICULTIES = {"casual", "standard", "expert"}
AI_VISIBILITIES = {"exact", "range", "hidden"}
