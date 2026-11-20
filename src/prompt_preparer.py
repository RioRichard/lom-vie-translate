import json
from pathlib import Path
from typing import Any

from src.glossary import find_original_matches
from src.logger import logger
from src.utils import build_translation_prompt, parse_json_entries, preprocess_text


def _get_character_info(char_id: str, flowchart: Any) -> Any | None:
    characters = getattr(flowchart, "characters", None)
    if isinstance(characters, dict):
        return characters.get(char_id)
    return None


def _format_character_label(
    char_id: str,
    flowchart: Any,
    custom_name: str | None = None,
    include_title: bool = False,
) -> str:
    if not char_id or char_id == "narrative":
        if custom_name and custom_name.strip():
            return custom_name.strip()
        return "Dẫn truyện"

    char_info = _get_character_info(char_id, flowchart)
    vi_name = (getattr(char_info, "vi_name", "") or "").strip() if char_info else ""
    zh_name = (getattr(char_info, "zh_name", "") or "").strip() if char_info else ""
    zh_title = (getattr(char_info, "zh_title", "") or "").strip() if char_info else ""

    if custom_name and custom_name.strip():
        c_name = custom_name.strip()
        base = f"{vi_name} [{c_name}]" if vi_name and c_name != vi_name else c_name
    elif vi_name and zh_name and vi_name != zh_name:
        base = f"{vi_name} ({zh_name})"
    else:
        base = vi_name or zh_name or char_id

    if include_title and zh_title:
        return f"{base} [{zh_title}]"
    return base


def _format_pronoun_rule(speaker_label: str, listener_label: str, rule: Any) -> str | None:
    if rule is None:
        return None
    self_p = (getattr(rule, "self_pronoun", "") or "").strip()
    target_p = (getattr(rule, "target_pronoun", "") or "").strip()
    third_p = (getattr(rule, "third_person", "") or "").strip()
    tone = (getattr(rule, "tone", "") or "").strip()
    stage_id = (getattr(rule, "stage_id", "") or "").strip()

    parts: list[str] = []
    if self_p or target_p:
        parts.append(f"tự xưng '{self_p}' / gọi '{target_p}'")
    if third_p:
        parts.append(f"ngôi 3: '{third_p}'")
    if tone:
        parts.append(f"giọng điệu: {tone}")
    if stage_id:
        parts.append(f"giai đoạn: {stage_id}")
    if not parts:
        return None
    return f"- {speaker_label} -> {listener_label}: {', '.join(parts)}"


def _build_story_context(
    name: str,
    flowchart: Any | None,
    relationship_matrix: Any | None,
    dialogue_window: int,
) -> dict[str, Any]:
    empty_context: dict[str, Any] = {
        "prev_keys": [],
        "next_keys": [],
        "prev_speakers": {},
        "next_speakers": {},
        "speaker_label": None,
        "script_id": None,
        "story_context_header": None,
    }
    if flowchart is None or not name:
        return empty_context

    line_ctx = flowchart.get_line_context(name, window=dialogue_window, lookahead=1)
    if line_ctx is None:
        return empty_context

    script = getattr(line_ctx, "script", None)
    line = getattr(line_ctx, "line", None)
    if line is None:
        return empty_context

    script_id = (getattr(script, "script_id", None) or "").strip() or None if script else None
    title_zh = (getattr(script, "title_zh", "") or "").strip() if script else ""
    ending_ids = (
        [str(e) for e in (getattr(script, "ending_ids", None) or []) if e] if script else []
    )

    branch_path = (getattr(line, "branch_path", None) or "main").strip() or "main"
    speaker_id = (getattr(line, "speaker_id", None) or "narrative").strip() or "narrative"
    custom_name = getattr(line, "speaker_custom_name", None)
    line_type = (getattr(line, "line_type", None) or "dialogue").strip() or "dialogue"
    mood = (getattr(line, "portrait_mood", None) or "").strip()
    listeners = [str(lid) for lid in (getattr(line, "listeners_on_stage", None) or []) if lid]

    speaker_label = _format_character_label(speaker_id, flowchart, custom_name=custom_name)
    speaker_display = _format_character_label(
        speaker_id, flowchart, custom_name=custom_name, include_title=True
    )

    header_lines: list[str] = []
    scene_parts: list[str] = []
    if script_id:
        scene_parts.append(f"Cảnh: {script_id}" + (f" ({title_zh})" if title_zh else ""))
    elif title_zh:
        scene_parts.append(f"Cảnh: {title_zh}")
    if branch_path != "main":
        scene_parts.append(f"Nhánh: {branch_path}")
    if ending_ids:
        scene_parts.append(f"Kết cục: {', '.join(ending_ids)}")
    if scene_parts:
        header_lines.append(" | ".join(scene_parts))

    meta_parts = [line_type]
    if mood:
        meta_parts.append(f"biểu cảm: {mood}")
    header_lines.append(f"Người nói: {speaker_display} [{', '.join(meta_parts)}]")

    if listeners:
        listener_labels = [_format_character_label(lid, flowchart) for lid in listeners]
        header_lines.append(f"Nhân vật trên sân khấu: {', '.join(listener_labels)}")

    if relationship_matrix is not None and speaker_id != "narrative":
        rule_lines: list[str] = []
        for listener_id in listeners:
            if listener_id in (speaker_id, "narrative"):
                continue
            rule = relationship_matrix.resolve_pair(
                speaker_id,
                listener_id,
                script_id=script_id,
                branch_path=branch_path,
            )
            listener_label = _format_character_label(listener_id, flowchart)
            formatted = _format_pronoun_rule(speaker_label, listener_label, rule)
            if formatted:
                rule_lines.append(formatted)
        if rule_lines:
            header_lines.append("Quy tắc xưng hô:\n" + "\n".join(rule_lines))

    prev_lines = list(getattr(line_ctx, "prev_lines", None) or [])
    next_lines = list(getattr(line_ctx, "next_lines", None) or [])

    prev_keys: list[str] = []
    prev_speakers: dict[str, str] = {}
    for prev_line in prev_lines:
        p_key = str(getattr(prev_line, "key", "") or "")
        if p_key:
            prev_keys.append(p_key)
            prev_speakers[p_key] = _format_character_label(
                str(getattr(prev_line, "speaker_id", "") or "narrative"),
                flowchart,
                custom_name=getattr(prev_line, "speaker_custom_name", None),
            )

    next_keys: list[str] = []
    next_speakers: dict[str, str] = {}
    for next_line in next_lines:
        n_key = str(getattr(next_line, "key", "") or "")
        if n_key:
            next_keys.append(n_key)
            next_speakers[n_key] = _format_character_label(
                str(getattr(next_line, "speaker_id", "") or "narrative"),
                flowchart,
                custom_name=getattr(next_line, "speaker_custom_name", None),
            )

    return {
        "prev_keys": prev_keys,
        "next_keys": next_keys,
        "prev_speakers": prev_speakers,
        "next_speakers": next_speakers,
        "speaker_label": speaker_label,
        "script_id": script_id,
        "story_context_header": "\n".join(header_lines) if header_lines else None,
    }


async def prepare_prompt_data(
    original_file_path: str | Path,
    original_data: dict[str, Any],
    translated_file_content: str | None = None,
    original_to_translated: dict[str, str] | None = None,
    flowchart: Any | None = None,
    relationship_matrix: Any | None = None,
    dialogue_window: int = 4,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """Prepare translation prompts using original entries, glossary matches, raw translations, and story context."""
    file_name = Path(original_file_path).name
    original_entries, _ = parse_json_entries(original_data)
    logger.debug(f"Original entries for {file_name}: {original_entries}")

    translated_file_entries: list[dict[str, Any]] | None = None
    if translated_file_content:
        try:
            translated_data = json.loads(translated_file_content)
        except json.JSONDecodeError:
            logger.error(f"Could not parse translated file content for {file_name}")
        else:
            translated_file_entries, _ = parse_json_entries(translated_data)

    raw_by_name: dict[str, str] = {}
    if translated_file_entries:
        for trans_entry in translated_file_entries:
            if not isinstance(trans_entry, dict):
                continue
            trans_name = trans_entry.get("key") or trans_entry.get("Name") or ""
            if trans_name and trans_name not in raw_by_name:
                raw_by_name[trans_name] = str(
                    trans_entry.get("value") or trans_entry.get("Text") or ""
                )

    prompt_data: list[dict[str, Any]] = []
    for entry in original_entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("key") or entry.get("Name") or ""
        raw_text = entry.get("value") or entry.get("Text") or ""
        text = preprocess_text(str(raw_text).strip())

        glossary_matches = find_original_matches(text, original_to_translated)
        raw_val = raw_by_name.get(name)
        raw_translation = (
            preprocess_text(raw_val.strip()) if raw_val and raw_val.strip() else None
        )

        story_ctx = _build_story_context(
            name=name,
            flowchart=flowchart,
            relationship_matrix=relationship_matrix,
            dialogue_window=dialogue_window,
        )
        story_context_header = story_ctx["story_context_header"]

        prompt = build_translation_prompt(
            original_text=text,
            raw_translation=raw_translation,
            glossary_matches=glossary_matches,
            story_context=story_context_header,
        )

        prompt_data.append(
            {
                "name": name,
                "original_text": text,
                "glossary_matches": glossary_matches,
                "raw_translation": raw_translation,
                "prev_keys": story_ctx["prev_keys"],
                "next_keys": story_ctx["next_keys"],
                "prev_speakers": story_ctx["prev_speakers"],
                "next_speakers": story_ctx["next_speakers"],
                "speaker_label": story_ctx["speaker_label"],
                "script_id": story_ctx["script_id"],
                "story_context_header": story_context_header,
                "prompt": prompt,
            }
        )

    logger.debug(f"Generated prompt data list: {prompt_data}")
    return prompt_data, translated_file_entries
