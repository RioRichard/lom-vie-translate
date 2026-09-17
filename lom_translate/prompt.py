"""Contextual prompt generation with hash-map indexing."""

from __future__ import annotations

from typing import Any

from lom_translate.glossary import Glossary
from lom_translate.models import LocalizationEntry
from lom_translate.text import RULES_PROMPT, START_PROMPT, STORY_CONTEXT_PROMPT, preprocess_text


def build_prompts(
    entries: list[LocalizationEntry],
    glossary: Glossary,
    raw_entries: list[LocalizationEntry] | None = None,
) -> list[dict[str, Any]]:
    """Build prompts for all entries in a file.

    DEF-15 FIX: raw translations pre-indexed into a dict for O(1) matching instead of O(N*M).
    """
    raw_map: dict[str, str] = {e.Name: e.Text for e in raw_entries} if raw_entries else {}

    prompts: list[dict[str, Any]] = []
    for entry in entries:
        text = preprocess_text(entry.Text.strip())
        matches = glossary.find_matches(text)
        raw = raw_map.get(entry.Name)

        parts = [f"{START_PROMPT}\n{STORY_CONTEXT_PROMPT}\n{RULES_PROMPT}\n"]
        if raw:
            parts.append("8. Sử dụng bản dịch thô để THAM KHẢO về xưng hô và quan hệ nhân vật.\n")
        if matches:
            parts.append("\nMột số thuật ngữ/cụm từ cần giữ nguyên:")
            for orig, trans in matches:
                parts.append(f"\n- {orig}={trans}")
        parts.append(f"\nVăn bản cần dịch: {text}")
        if raw:
            parts.append(f"\nBản dịch thô để tham khảo: {raw}")

        prompts.append(
            {
                "name": entry.Name,
                "original_text": text,
                "glossary_matches": matches,
                "raw_translation": raw,
                "prompt": "\n".join(parts),
            }
        )
    return prompts
