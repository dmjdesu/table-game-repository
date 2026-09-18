import hashlib
import json
import re
from typing import Any

import yaml


def _stable_id(value: str, prefix: str = "item") -> str:
    value = str(value or "").strip()
    ascii_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    if ascii_id:
        return ascii_id
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{digest}"


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _duration_seconds(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip().lower()
    minute = re.search(r"(\d+)\s*(?:分|min|minutes?)", text)
    if minute:
        return int(minute.group(1)) * 60
    second = re.search(r"(\d+)\s*(?:秒|sec|seconds?)", text)
    if second:
        return int(second.group(1))
    number = re.search(r"\d+", text)
    return int(number.group(0)) if number else 0


def _normalize_definition(data: dict) -> dict:
    scenario_meta = data.get("scenario") if isinstance(data.get("scenario"), dict) else {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}

    title = data.get("title") or scenario_meta.get("title") or metadata.get("title") or "Untitled Scenario"
    players = data.get("players") or scenario_meta.get("players") or metadata.get("players") or 0

    characters = []
    for index, raw in enumerate(data.get("characters") or []):
        raw = raw or {}
        cid = str(raw.get("id") or _stable_id(raw.get("name") or f"character-{index+1}", "character"))
        characters.append({
            "id": cid,
            "name": raw.get("name") or cid,
            "role": raw.get("role") or "",
            "public_profile": raw.get("public_profile") or raw.get("profile") or "",
            "secrets": [str(v) for v in _as_list(raw.get("secrets") or raw.get("secret"))],
            "objectives": [str(v) for v in _as_list(raw.get("objectives") or raw.get("objective"))],
        })

    evidence = []
    for index, raw in enumerate(data.get("evidence") or []):
        raw = raw or {}
        eid = str(raw.get("id") or _stable_id(raw.get("title") or f"evidence-{index+1}", "evidence"))
        evidence.append({
            "id": eid,
            "title": raw.get("title") or eid,
            "content": raw.get("content") or raw.get("description") or "",
            "visibility": raw.get("visibility") or "public",
        })

    phases = []
    for index, raw in enumerate(data.get("phases") or []):
        raw = raw or {}
        pid = str(raw.get("id") or _stable_id(raw.get("label") or f"phase-{index+1}", "phase"))
        phases.append({
            "id": pid,
            "label": raw.get("label") or raw.get("name") or pid,
            "type": raw.get("type") or "discussion",
            "duration_seconds": _duration_seconds(raw.get("duration_seconds") or raw.get("duration") or 0),
            "start_evidence": [str(v) for v in _as_list(raw.get("start_evidence") or raw.get("evidence"))],
            "instructions": raw.get("instructions") or "",
        })

    events = []
    for index, raw in enumerate(data.get("events") or []):
        raw = raw or {}
        trigger = raw.get("trigger") or {}
        conditions = raw.get("conditions") or {}
        result = raw.get("result") or {}
        unlocks = result.get("unlock_evidence") or []
        events.append({
            "id": str(raw.get("id") or f"event-{index+1}"),
            "trigger": {
                "action": trigger.get("action") or raw.get("action") or "",
                "target": trigger.get("target") or raw.get("target") or "",
            },
            "conditions": {
                "phase": conditions.get("phase") or raw.get("phase") or "",
            },
            "result": {
                "unlock_evidence": [str(v) for v in _as_list(unlocks)],
                "set_flags": result.get("set_flags") or {},
                "message": result.get("message") or "",
            },
        })

    endings = []
    for index, raw in enumerate(data.get("endings") or []):
        raw = raw or {}
        condition = raw.get("condition") or {}
        if isinstance(condition, str):
            condition = {"type": condition}
        endings.append({
            "id": str(raw.get("id") or f"ending-{index+1}"),
            "label": raw.get("label") or raw.get("name") or str(raw.get("id") or f"Ending {index+1}"),
            "condition": condition,
            "text": raw.get("text") or raw.get("content") or "",
        })

    truth = data.get("truth") or {}
    return {
        "title": str(title),
        "players": int(players or 0),
        "characters": characters,
        "truth": truth,
        "evidence": evidence,
        "phases": phases,
        "events": events,
        "endings": endings,
    }


def _split_markdown(text: str) -> tuple[dict[str, list[str]], dict[str, dict[str, list[str]]]]:
    top: dict[str, list[str]] = {}
    subs: dict[str, dict[str, list[str]]] = {}
    current_top = ""
    current_sub = ""

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("# "):
            current_top = line[2:].strip().lower()
            current_sub = ""
            top.setdefault(current_top, [])
            subs.setdefault(current_top, {})
        elif line.startswith("## ") and current_top:
            current_sub = line[3:].strip()
            subs[current_top].setdefault(current_sub, [])
        elif current_top:
            if current_sub:
                subs[current_top][current_sub].append(line)
            else:
                top[current_top].append(line)
    return top, subs


def _fields(lines: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_list_key = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("- ") and current_list_key:
            if not isinstance(result.get(current_list_key), list):
                result[current_list_key] = []
            result[current_list_key].append(line[2:].strip())
            continue
        if ":" in line or "：" in line:
            delimiter = ":" if ":" in line else "："
            key, value = line.split(delimiter, 1)
            key = key.strip().lower()
            value = value.strip()
            if value:
                result[key] = value
                current_list_key = None
            else:
                result[key] = []
                current_list_key = key
    return result


def _find_section(mapping: dict, *names: str):
    names = {name.lower() for name in names}
    for key, value in mapping.items():
        if key.lower() in names:
            return value
    return {} if mapping and isinstance(next(iter(mapping.values()), {}), dict) else []


def _parse_markdown(text: str) -> dict:
    fenced = re.search(r"```(yaml|yml|json)\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return parse_scenario(fenced.group(2), "json" if fenced.group(1).lower() == "json" else "yaml")

    top, subs = _split_markdown(text)
    basic = _fields(_find_section(top, "基本情報", "basic", "metadata"))
    title = basic.get("タイトル") or basic.get("title") or "Untitled Scenario"
    players = basic.get("プレイヤー人数") or basic.get("players") or 0

    character_section = _find_section(subs, "登場人物", "characters")
    characters = []
    character_refs = {}
    for heading, lines in character_section.items():
        fields = _fields(lines)
        cid = _stable_id(heading, "character")
        character_refs[heading] = cid
        character_refs[heading.lower()] = cid
        characters.append({
            "id": cid,
            "name": fields.get("名前") or fields.get("name") or heading,
            "role": fields.get("役割") or fields.get("role") or "",
            "public_profile": fields.get("公開情報") or fields.get("public_profile") or "",
            "secrets": _as_list(fields.get("秘密") or fields.get("secrets")),
            "objectives": _as_list(fields.get("目的") or fields.get("objectives")),
        })

    truth_fields = _fields(_find_section(top, "真相", "truth"))
    culprit_raw = str(truth_fields.get("犯人") or truth_fields.get("culprit") or "")
    truth = {
        "culprit": character_refs.get(culprit_raw, character_refs.get(culprit_raw.lower(), _stable_id(culprit_raw, "character") if culprit_raw else "")),
        "crime_time": truth_fields.get("犯行時刻") or truth_fields.get("crime_time") or "",
        "crime_scene": truth_fields.get("犯行場所") or truth_fields.get("crime_scene") or "",
        "weapon": truth_fields.get("凶器") or truth_fields.get("weapon") or "",
        "solution": truth_fields.get("解説") or truth_fields.get("solution") or "",
    }

    evidence_section = _find_section(subs, "証拠", "evidence")
    evidence = []
    evidence_refs = {}
    for heading, lines in evidence_section.items():
        fields = _fields(lines)
        eid = _stable_id(heading, "evidence")
        evidence_refs[heading] = eid
        evidence_refs[heading.lower()] = eid
        evidence_refs[eid] = eid
        title_value = fields.get("タイトル") or fields.get("title") or heading
        evidence_refs[str(title_value)] = eid
        evidence.append({
            "id": eid,
            "title": title_value,
            "content": fields.get("内容") or fields.get("content") or fields.get("説明") or "",
            "visibility": fields.get("公開範囲") or fields.get("visibility") or "public",
        })

    phase_section = _find_section(subs, "フェーズ", "phases")
    phases = []
    pending_evidence_names = []
    for heading, lines in phase_section.items():
        fields = _fields(lines)
        raw_evidence = _as_list(fields.get("開始時公開") or fields.get("start_evidence") or fields.get("追加証拠"))
        pending_evidence_names.extend(raw_evidence)
        phase_type = fields.get("type") or fields.get("種類")
        if not phase_type:
            phase_type = "voting" if "投票" in heading else "investigation" if "調査" in heading else "discussion"
        phases.append({
            "id": _stable_id(heading, "phase"),
            "label": heading,
            "type": phase_type,
            "duration_seconds": _duration_seconds(fields.get("時間") or fields.get("duration") or 0),
            "start_evidence": raw_evidence,
            "instructions": fields.get("指示") or fields.get("instructions") or "",
        })

    # Markdownに証拠本文がなく、フェーズで名前だけ参照されている場合もプレースホルダー化する。
    for raw_name in pending_evidence_names:
        if raw_name not in evidence_refs and str(raw_name).lower() not in evidence_refs:
            eid = _stable_id(raw_name, "evidence")
            evidence_refs[str(raw_name)] = eid
            evidence_refs[str(raw_name).lower()] = eid
            evidence_refs[eid] = eid
            evidence.append({
                "id": eid,
                "title": str(raw_name),
                "content": str(raw_name),
                "visibility": "public",
            })

    for phase in phases:
        phase["start_evidence"] = [
            evidence_refs.get(str(ref), evidence_refs.get(str(ref).lower(), str(ref)))
            for ref in phase["start_evidence"]
        ]

    ending_section = _find_section(subs, "エンディング", "endings")
    endings = []
    for heading, lines in ending_section.items():
        fields = _fields(lines)
        condition_raw = fields.get("条件") or fields.get("condition") or "default"
        condition_type = str(condition_raw)
        endings.append({
            "id": _stable_id(heading, "ending"),
            "label": heading,
            "condition": {"type": condition_type},
            "text": fields.get("本文") or fields.get("text") or "",
        })

    event_section = _find_section(subs, "イベント", "events")
    events = []
    for heading, lines in event_section.items():
        fields = _fields(lines)
        unlocks = _as_list(fields.get("証拠解放") or fields.get("unlock_evidence"))
        events.append({
            "id": _stable_id(heading, "event"),
            "trigger": {
                "action": fields.get("action") or fields.get("行動") or "",
                "target": fields.get("target") or fields.get("対象") or "",
            },
            "conditions": {"phase": fields.get("phase") or fields.get("フェーズ") or ""},
            "result": {
                "unlock_evidence": [
                    evidence_refs.get(str(ref), evidence_refs.get(str(ref).lower(), str(ref)))
                    for ref in unlocks
                ],
                "set_flags": {},
                "message": fields.get("メッセージ") or fields.get("message") or "",
            },
        })

    return _normalize_definition({
        "title": title,
        "players": players,
        "characters": characters,
        "truth": truth,
        "evidence": evidence,
        "phases": phases,
        "events": events,
        "endings": endings,
    })


def parse_scenario(raw_text: str, source_format: str) -> dict:
    source_format = (source_format or "yaml").lower()
    if source_format in {"yaml", "yml"}:
        loaded = yaml.safe_load(raw_text)
    elif source_format == "json":
        loaded = json.loads(raw_text)
    elif source_format in {"markdown", "md", "txt"}:
        return _parse_markdown(raw_text)
    else:
        raise ValueError(f"未対応のシナリオ形式です: {source_format}")

    if not isinstance(loaded, dict):
        raise ValueError("シナリオのルートはオブジェクト形式にしてください。")
    return _normalize_definition(loaded)
