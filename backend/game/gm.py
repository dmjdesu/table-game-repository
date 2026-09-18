from dataclasses import dataclass
from typing import Protocol

from .models import Game


@dataclass
class GMReply:
    text: str
    source: str = "rule_based"


class GMProvider(Protocol):
    def answer(self, *, question: str, safe_context: dict) -> GMReply:
        ...


def build_safe_gm_context(game: Game, seat: int, visible_payload: dict) -> dict:
    """
    LLMに渡してよい情報だけをここで確定する。
    Scenario.definition の truth や他プレイヤーの秘密は絶対に入れない。
    """
    return {
        "game_id": str(game.id),
        "game_type": game.game_type,
        "current_phase": visible_payload.get("phase"),
        "public_evidence": visible_payload.get("evidence", []),
        "my_character": visible_payload.get("me"),
        "players": visible_payload.get("players", []),
        "finished": visible_payload.get("finished", False),
        "resolution": visible_payload.get("resolution"),
    }


class RuleBasedGM:
    def answer(self, *, question: str, safe_context: dict) -> GMReply:
        normalized = question.strip().lower()
        phase = safe_context.get("current_phase") or {}
        label = phase.get("label") or "現在のフェーズ"

        if safe_context.get("finished"):
            resolution = safe_context.get("resolution") or {}
            return GMReply(resolution.get("text") or "ゲームは終了しています。")

        if any(word in normalized for word in ["次", "なにすれば", "何すれば", "what next", "help"]):
            instruction = phase.get("instructions")
            if instruction:
                return GMReply(f"現在は「{label}」です。{instruction}")
            return GMReply(f"現在は「{label}」です。公開情報と自分の個別情報を確認し、このフェーズの目的に沿って行動してください。")

        if any(word in normalized for word in ["証拠", "evidence"]):
            evidence = safe_context.get("public_evidence") or []
            if not evidence:
                return GMReply("現在あなたが閲覧できる証拠はありません。")
            titles = "、".join(item.get("title", "") for item in evidence)
            return GMReply(f"現在閲覧できる証拠は「{titles}」です。")

        if any(word in normalized for word in ["秘密", "個別", "自分の情報"]):
            me = safe_context.get("my_character") or {}
            secrets = me.get("secrets") or []
            if not secrets:
                return GMReply("現在あなたに配布されている個別の秘密情報はありません。")
            return GMReply("あなたの個別情報はプレイヤー画面の「秘密」欄で確認できます。")

        return GMReply(f"現在は「{label}」です。GMは公開済み情報と、あなたに許可された個別情報の範囲でのみ回答します。")
