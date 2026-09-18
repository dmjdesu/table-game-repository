from math import floor


def _band(value: float, low: float, high: float) -> str:
    if value < low:
        return "low"
    if value > high:
        return "high"
    return "standard"


def build_abstract_state(config: dict) -> dict:
    roles = config["roles"]
    player_count = config["player_count"]
    wolves = roles.get("wolf", 0)
    madmen = roles.get("madman", 0)
    information_roles = roles.get("seer", 0) + roles.get("medium", 0)
    guards = roles.get("guard", 0)
    village_side = player_count - wolves - madmen

    if player_count <= 7:
        population_bucket = "small"
    elif player_count <= 10:
        population_bucket = "medium"
    else:
        population_bucket = "large"

    wolf_ratio = wolves / player_count
    info_ratio = information_roles / player_count
    guard_ratio = guards / player_count
    deception_ratio = (wolves + madmen) / player_count
    mislynch_budget = max(0, floor((village_side - wolves - 1) / 2))

    return {
        "population_bucket": population_bucket,
        "wolf_pressure": _band(wolf_ratio, 0.16, 0.28),
        "information_density": _band(info_ratio, 0.10, 0.25),
        "protection_level": _band(guard_ratio, 0.05, 0.16),
        "deception_layer": _band(deception_ratio, 0.20, 0.36),
        "mislynch_budget": mislynch_budget,
        "first_day_information": "present" if config.get("first_day_divination") else "limited",
        "guard_pattern": "repeatable" if config.get("consecutive_guard") else "non_repeatable",
        "speech_budget": config.get("speech_limit", 8),
    }


def build_cache_key(state: dict) -> str:
    keys = [
        "population_bucket",
        "wolf_pressure",
        "information_density",
        "protection_level",
        "deception_layer",
        "first_day_information",
        "guard_pattern",
    ]
    return "|".join(f"{key}:{state[key]}" for key in keys)


def build_strategy_profile(state: dict) -> dict:
    village = ["公開情報を増やし、投票理由の矛盾を比較する"]
    wolf = ["処刑回避と情報撹乱を優先し、仲間との距離を固定しすぎない"]

    if state["information_density"] == "high":
        village.append("能力者COの整合性と結果の衝突を中心に見る")
        wolf.append("能力者の信用差を利用し、確定情報を作らせすぎない")
    elif state["information_density"] == "low":
        village.append("発言・投票履歴を重く評価する")
        wolf.append("情報不足を利用して複数の疑い先を維持する")

    if state["protection_level"] == "high":
        village.append("護衛価値の高い役職を早期に露出させすぎない")
        wolf.append("襲撃候補を分散し、護衛読みを外す")

    if state["deception_layer"] == "high":
        village.append("役職COを真偽二択で即断せず、陣営利得まで見る")
        wolf.append("騙りと潜伏の役割を分け、同じ論調に寄せすぎない")

    if state["mislynch_budget"] <= 1:
        village.append("誤処刑余裕が少ないため、雰囲気投票を避ける")
        wolf.append("一度の誤処刑が重いため、最有力候補への便乗を慎重に使う")

    return {
        "cache_key": build_cache_key(state),
        "village_priorities": village,
        "wolf_priorities": wolf,
        "decision_layers": ["team", "role", "situation", "personality", "memory"],
    }
