from collections import Counter


def _issue(level: str, code: str, message: str, path: str = "") -> dict:
    return {"level": level, "code": code, "message": message, "path": path}


def validate_scenario(definition: dict) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []

    title = definition.get("title") or definition.get("metadata", {}).get("title")
    if not title:
        errors.append(_issue("error", "missing_title", "タイトルがありません。", "title"))

    players = definition.get("players") or definition.get("metadata", {}).get("players")
    try:
        players = int(players)
    except (TypeError, ValueError):
        errors.append(_issue("error", "invalid_players", "プレイヤー人数を整数で指定してください。", "players"))
        players = 0

    characters = definition.get("characters") or []
    character_ids = [str(item.get("id", "")) for item in characters]
    if any(not cid for cid in character_ids):
        errors.append(_issue("error", "character_id_missing", "全キャラクターにidが必要です。", "characters"))
    duplicate_characters = [cid for cid, count in Counter(character_ids).items() if cid and count > 1]
    if duplicate_characters:
        errors.append(_issue("error", "duplicate_character", f"キャラクターidが重複しています: {duplicate_characters}", "characters"))
    if players and len(characters) != players:
        errors.append(_issue("error", "character_count_mismatch", f"players={players} に対してキャラクターが {len(characters)} 人です。", "characters"))

    truth = definition.get("truth") or {}
    culprit = str(truth.get("culprit", ""))
    if not culprit:
        errors.append(_issue("error", "culprit_missing", "真相に犯人が定義されていません。", "truth.culprit"))
    elif culprit not in character_ids:
        errors.append(_issue("error", "culprit_unknown", f"犯人 {culprit} がキャラクター一覧に存在しません。", "truth.culprit"))

    for index, character in enumerate(characters):
        if not character.get("secrets"):
            warnings.append(_issue("warning", "secret_missing", f"{character.get('name') or character.get('id')} に秘密がありません。", f"characters.{index}.secrets"))
        if not character.get("objectives"):
            warnings.append(_issue("warning", "objective_missing", f"{character.get('name') or character.get('id')} に目的がありません。", f"characters.{index}.objectives"))

    evidence = definition.get("evidence") or []
    evidence_ids = [str(item.get("id", "")) for item in evidence]
    duplicate_evidence = [eid for eid, count in Counter(evidence_ids).items() if eid and count > 1]
    if duplicate_evidence:
        errors.append(_issue("error", "duplicate_evidence", f"証拠idが重複しています: {duplicate_evidence}", "evidence"))
    if not evidence:
        warnings.append(_issue("warning", "no_evidence", "証拠が1件もありません。推理ゲームとして成立するか確認してください。", "evidence"))

    phases = definition.get("phases") or []
    if not phases:
        errors.append(_issue("error", "phase_missing", "フェーズがありません。", "phases"))
    for index, phase in enumerate(phases):
        for evidence_id in phase.get("start_evidence", []) or []:
            if evidence_id not in evidence_ids:
                errors.append(_issue("error", "unknown_phase_evidence", f"フェーズ {phase.get('id')} が未知の証拠 {evidence_id} を参照しています。", f"phases.{index}.start_evidence"))

    events = definition.get("events") or []
    event_ids = [str(item.get("id", "")) for item in events]
    duplicate_events = [eid for eid, count in Counter(event_ids).items() if eid and count > 1]
    if duplicate_events:
        errors.append(_issue("error", "duplicate_event", f"イベントidが重複しています: {duplicate_events}", "events"))
    for index, event in enumerate(events):
        result = event.get("result") or {}
        unlocks = result.get("unlock_evidence", []) or []
        if isinstance(unlocks, str):
            unlocks = [unlocks]
        for evidence_id in unlocks:
            if evidence_id not in evidence_ids:
                errors.append(_issue("error", "unknown_event_evidence", f"イベント {event.get('id')} が未知の証拠 {evidence_id} を解除しようとしています。", f"events.{index}.result"))

    endings = definition.get("endings") or []
    if not endings:
        errors.append(_issue("error", "ending_missing", "エンディングがありません。", "endings"))
    elif not any((ending.get("condition") or {}).get("type") == "default" for ending in endings):
        warnings.append(_issue("warning", "default_ending_missing", "条件に一致しない場合のdefaultエンディングを用意することを推奨します。", "endings"))

    report = {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "players": players,
            "characters": len(characters),
            "evidence": len(evidence),
            "phases": len(phases),
            "events": len(events),
            "endings": len(endings),
        },
    }
    return report
