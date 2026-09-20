"""Configurable team mystery. All secret-bearing data stays server-side."""
import copy
from collections import Counter
from django.db import transaction
from rest_framework import serializers as s
from .models import Game, GameAction


class Option(s.Serializer):
    id = s.CharField(max_length=64)
    label = s.CharField()


class Question(s.Serializer):
    id = s.CharField(max_length=64)
    prompt = s.CharField()
    options = Option(many=True, allow_empty=False)
    answer = s.CharField(max_length=64)
    points = s.IntegerField(min_value=0, default=1)
    evidence_any = s.ListField(child=s.CharField(), default=list)
    evidence_points = s.IntegerField(min_value=0, default=0)


class Draw(s.Serializer):
    eligible = s.CharField(default="all")  # all, previous_winners, or a team id
    per_player = s.IntegerField(min_value=1, max_value=100, default=1)


class Round(s.Serializer):
    id = s.CharField(max_length=64)
    label = s.CharField()
    discussion_seconds = s.IntegerField(min_value=0, default=0)
    questions = Question(many=True, allow_empty=False)
    draw = Draw(required=False)
    max_evidence = s.IntegerField(min_value=0, default=2)
    discussion_instructions = s.CharField(default="個別情報とカードをもとに自由に議論してください。")
    meeting_instructions = s.CharField(default="陣営で相談し、代表者が回答を確定してください。確定後は変更できません。")


class Card(s.Serializer):
    id = s.CharField(max_length=64)
    title = s.CharField()
    target = s.CharField()
    content = s.CharField()
    interpretations = s.DictField(child=s.CharField(), default=dict)


class CampaignDefinition(s.Serializer):
    teams = Option(many=True, allow_empty=False)
    role_teams = s.DictField(child=s.CharField())
    rounds = Round(many=True, allow_empty=False)
    cards = Card(many=True, allow_empty=True)
    introduction = s.CharField()
    speech_ap_per_phase = s.IntegerField(min_value=1, default=1000)
    successor_label = s.CharField(default="記録を引き継いだ代理人")
    ending_text = s.CharField()


def normalize(config):
    serializer = CampaignDefinition(data=config)
    serializer.is_valid(raise_exception=True)
    value = dict(serializer.validated_data)
    def ids(rows):
        result = [r["id"] for r in rows]
        if len(set(result)) != len(result):
            raise ValueError("連動シナリオのIDが重複しています。")
        return set(result)
    teams, cards = ids(value["teams"]), ids(value["cards"])
    ids(value["rounds"])
    if teams & {"all", "previous_winners"}:
        raise ValueError("allとprevious_winnersは陣営IDに使用できません。")
    if len(teams) < 2 or not value["role_teams"] or not set(value["role_teams"].values()) <= teams:
        raise ValueError("2陣営以上と、陣営に対応した役職を設定してください。")
    for row in value["rounds"]:
        ids(row["questions"])
        if row.get("draw", {}).get("eligible", "all") not in teams | {"all", "previous_winners"}:
            raise ValueError("カード取得の対象陣営が不正です。")
        for q in row["questions"]:
            if q["answer"] not in ids(q["options"]) or not set(q["evidence_any"]) <= cards:
                raise ValueError("会議の正答または根拠カードが存在しません。")
            if q["evidence_points"] and (not q["evidence_any"] or not row["max_evidence"]):
                raise ValueError("根拠点には正答カードと1枚以上の根拠提出枠が必要です。")
    return value


def phases(config):
    result = []
    for row in config["rounds"]:
        common = {"duration_seconds": 0, "start_evidence": []}
        result.extend([
            {**common, "id": row["id"] + "_discussion", "type": "discussion", "round_id": row["id"],
             "label": row["label"] + "前の議論", "instructions": row["discussion_instructions"],
             "duration_seconds": row["discussion_seconds"]},
            {**common, "id": row["id"] + "_meeting", "type": "meeting", "round_id": row["id"],
             "label": row["label"], "instructions": row["meeting_instructions"]},
        ])
        if row.get("draw"):
            result.append({**common, "id": row["id"] + "_draw", "type": "card_draw", "round_id": row["id"],
                           "label": row["label"] + "後の調査", "instructions": "対象者は未取得のカードから選んでください。"})
    return result


class OutcomePlayer(s.Serializer):
    seat = s.IntegerField(min_value=1)
    display_name = s.CharField(max_length=40)
    role = s.CharField(max_length=32)
    alive = s.BooleanField()
    character_id = s.CharField(max_length=64, required=False)


class Outcome(s.Serializer):
    winner_team = s.CharField(max_length=64)
    players = OutcomePlayer(many=True, allow_empty=False)
    source_label = s.CharField(max_length=200, default="前の人狼")


def validate_outcome(definition, raw):
    serializer = Outcome(data=raw)
    serializer.is_valid(raise_exception=True)
    value = dict(serializer.validated_data)
    config = definition["campaign"]
    teams = {t["id"] for t in config["teams"]}
    players = value["players"]
    if value["winner_team"] not in teams or sorted(p["seat"] for p in players) != list(range(1, definition["players"] + 1)):
        raise ValueError("勝利陣営と、1から人数分の座席を確認してください。")
    assigned = []
    for p in players:
        if p["role"] not in config["role_teams"]:
            raise ValueError("前ゲームに未対応の役職があります。role_teamsを設定してください。")
        p["team"] = config["role_teams"][p["role"]]
        if p.get("character_id"):
            assigned.append(p["character_id"])
    character_ids = {c["id"] for c in definition["characters"]}
    if len(set(assigned)) != len(assigned) or not set(assigned) <= character_ids:
        raise ValueError("引継ぎキャラクターIDが重複しているか、存在しません。")
    if {p["team"] for p in players} != teams:
        raise ValueError("各陣営に1人以上必要です。")
    counts = Counter(p["team"] for p in players)
    needed = 0
    for row in config["rounds"]:
        draw = row.get("draw")
        if draw:
            team = draw["eligible"]
            n = len(players) if team == "all" else counts[value["winner_team"] if team == "previous_winners" else team]
            needed += n * draw["per_player"]
    if needed > len(config["cards"]):
        raise ValueError(f"取得予定{needed}枚に対しカードが不足しています。")
    return value


def current(game):
    config = game.scenario.definition["campaign"]
    phase = game.scenario.definition["phases"][game.state["current_phase_index"]]
    row = next(r for r in config["rounds"] if r["id"] == phase["round_id"])
    return config, phase, row


def eligible(game, row):
    rule = row.get("draw", {}).get("eligible")
    if rule == "previous_winners":
        rule = game.legacy["winner_team"]
    return [p["seat"] for p in game.legacy["players"] if rule == "all" or p["team"] == rule]


def remaining(game, row, seat):
    if seat not in eligible(game, row):
        return 0
    taken = game.state.get("card_owners", {}).values()
    used = sum(v["seat"] == seat and v["round_id"] == row["id"] for v in taken)
    return max(0, row["draw"]["per_player"] - used)


def can_advance(game):
    config, phase, row = current(game)
    if phase["type"] == "meeting":
        return len(game.state.get("submissions", {}).get(row["id"], {})) == len(config["teams"])
    if phase["type"] == "card_draw":
        return all(remaining(game, row, seat) == 0 for seat in eligible(game, row))
    return True


def public_payload(game, seat):
    config, phase, row = current(game)
    person = next((p for p in game.legacy["players"] if p["seat"] == seat), None)
    owners = game.state.get("card_owners", {})
    player = next((p for p in game.players.all() if p.seat == seat), None)
    character = next((c for c in game.scenario.definition["characters"] if player and c["id"] == player.character_id), {})
    owned = []
    for card in config["cards"]:
        if owners.get(card["id"], {}).get("seat") == seat:
            owned.append({k: card[k] for k in ("id", "title", "target", "content")})
            owned[-1]["interpretation"] = card["interpretations"].get(character.get("id"), "")
    submissions = game.state.get("submissions", {}).get(row["id"], {})
    return {
        "introduction": config["introduction"], "teams": config["teams"],
        "previous_winner": game.legacy["winner_team"],
        "team": person["team"] if person else None,
        "identity": ("本人" if person["alive"] else config["successor_label"]) if person else None,
        "skill": character.get("skill", ""),
        "team_members": [{"seat": p["seat"], "display_name": p["display_name"]} for p in game.legacy["players"] if person and p["team"] == person["team"]],
        "rounds": [{"id": r["id"], "label": r["label"]} for r in config["rounds"]],
        "round_id": row["id"],
        "max_evidence": row["max_evidence"],
        "my_history": [{"round_id": r["id"], "label": r["label"], "answers": [
            {"question": q["prompt"], "label": next(o["label"] for o in q["options"] if o["id"] == sub["answers"][q["id"]])}
            for q in r["questions"]], "evidence": sub["evidence"]}
            for r in config["rounds"]
            if person and (sub := game.state.get("submissions", {}).get(r["id"], {}).get(person["team"]))],
        "catalogue": [{"id": c["id"], "title": c["title"], "target": c["target"], "taken": c["id"] in owners} for c in config["cards"]],
        "owned_cards": owned,
        "remaining_picks": remaining(game, row, seat) if phase["type"] == "card_draw" and not game.state.get("finished") else 0,
        "questions": [{k: q[k] for k in ("id", "prompt", "options", "points", "evidence_points")} for q in row["questions"]] if phase["type"] == "meeting" else [],
        "submitted_teams": list(submissions),
        "my_submission": submissions.get(person["team"]) if person else None,
        "can_advance": can_advance(game) and not game.state.get("finished"),
        "results": game.state.get("campaign_results") if game.state.get("finished") else None,
    }


@transaction.atomic
def act(game_id, seat, action, data):
    # Lock the session before checking ownership/quota. PostgreSQL serializes competing picks.
    game = Game.objects.select_for_update().select_related("scenario").get(id=game_id)
    if not game.scenario.definition.get("campaign") or game.state.get("finished"):
        raise ValueError("この操作は受け付けられません。")
    person = next((p for p in game.legacy["players"] if p["seat"] == seat), None)
    if not person:
        raise ValueError("座席が存在しません。")
    config, phase, row = current(game)
    state = copy.deepcopy(game.state)
    if action == "pick":
        card = data.get("card_id")
        if phase["type"] != "card_draw" or remaining(game, row, seat) <= 0:
            raise ValueError("現在この座席には取得権がありません。")
        if not isinstance(card, str) or card not in {c["id"] for c in config["cards"]} or card in state.get("card_owners", {}):
            raise ValueError("このカードは取得できません。")
        state.setdefault("card_owners", {})[card] = {"seat": seat, "round_id": row["id"]}
    elif action == "submit":
        if phase["type"] != "meeting" or person["team"] in state.get("submissions", {}).get(row["id"], {}):
            raise ValueError("会議中ではないか、陣営の回答が既に確定しています。")
        answers = data.get("answers")
        evidence = data.get("evidence", [])
        if not isinstance(answers, dict) or set(answers) != {q["id"] for q in row["questions"]}:
            raise ValueError("全てのお題に回答してください。")
        if any(not isinstance(answers[q["id"]], str) or answers[q["id"]] not in {o["id"] for o in q["options"]} for q in row["questions"]):
            raise ValueError("回答の選択肢が不正です。")
        if not isinstance(evidence, list) or any(not isinstance(e, str) or e not in state.get("card_owners", {}) for e in evidence):
            raise ValueError("根拠には取得済みカードを指定してください。")
        if len(set(evidence)) > row["max_evidence"]:
            raise ValueError(f"根拠カードは{row['max_evidence']}枚までです。")
        state.setdefault("submissions", {}).setdefault(row["id"], {})[person["team"]] = {
            "answers": answers, "evidence": list(dict.fromkeys(evidence)), "submitted_by": seat,
        }
    else:
        raise ValueError("未対応の操作です。")
    game.state = state
    game.save(update_fields=["state"])
    GameAction.objects.create(game=game, actor_seat=seat, action_type="campaign_" + action, payload={"round_id": row["id"]})
    return game


def finish_locked(game):
    config = game.scenario.definition["campaign"]
    scores = {t["id"]: 0 for t in config["teams"]}
    rounds = []
    for row in config["rounds"]:
        submissions = game.state["submissions"][row["id"]]
        for team, sub in submissions.items():
            for q in row["questions"]:
                correct = sub["answers"][q["id"]] == q["answer"]
                score = q["points"] if correct else 0
                if correct and set(sub["evidence"]) & set(q["evidence_any"]):
                    score += q["evidence_points"]
                scores[team] += score
                labels = {o["id"]: o["label"] for o in q["options"]}
                rounds.append({"round_id": row["id"], "round_label": row["label"], "team": team,
                               "question": q["prompt"], "answer": q["answer"], "answer_label": labels[q["answer"]],
                               "submitted_label": labels[sub["answers"][q["id"]]], "submission": sub, "score": score})
    game.state.update(finished=True, ending_id="campaign_end", phase_ends_at=None,
                      campaign_results={"scores": scores, "winners": [t for t, v in scores.items() if v == max(scores.values())], "rounds": rounds})
    game.status = Game.Status.FINISHED
    game.save(update_fields=["state", "status"])
