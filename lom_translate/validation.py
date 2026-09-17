"""Soft validator engine for injected characters and game engine tokens."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Patterns matching game tokens and injected formatting
TOKEN_INTERPOLATION = re.compile(r"\{[^}]*\}")
TOKEN_INJECTED_BREAKS = re.compile(r"\[\|+\]")
TOKEN_BRACKETED_PARAMS = re.compile(r"\[\{*\d+\}*\]")
RICH_TEXT_TAGS = re.compile(r"</?[a-zA-Z0-9_]+(?:=[^>]+)?>")
CJK_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")

# Auto-healing patterns (LLM space insertion artifacts)
HEAL_INJECTED_DOUBLE = re.compile(r"\[\s*\|\s*\|\s*\]")
HEAL_INJECTED_SINGLE = re.compile(r"\[\s*\|\s*\]")
HEAL_BRACKET_SPACES = re.compile(r"\{\s*([a-zA-Z0-9_]+)\s*\}")
HEAL_FORMATTED_SPACES = re.compile(r"\{\s*(\d+)\s*:\s*([a-zA-Z0-9_]+)\s*\}")
HEAL_TAG_SPACES = re.compile(r"<\s*/\s*([a-zA-Z0-9_]+)\s*>")


@dataclass
class ValidationResult:
    """Outcome of soft validation on translated text."""

    healed_text: str
    is_clean: bool = True
    missing_tokens: list[str] = field(default_factory=list)
    extra_tokens: list[str] = field(default_factory=list)
    has_untranslated_cjk: bool = False
    warning_messages: list[str] = field(default_factory=list)


def auto_heal_tokens(text: str) -> str:
    """Stage 1: Normalize common spacing flaws introduced by LLMs without reprompting."""
    if not text:
        return text

    # Heal [||] and [|] spacing
    text = HEAL_INJECTED_DOUBLE.sub("[||]", text)
    text = HEAL_INJECTED_SINGLE.sub("[|]", text)

    # Heal { 0 : N0 } -> {0:N0}
    text = HEAL_FORMATTED_SPACES.sub(r"{\1:\2}", text)

    # Heal { title } -> {title}
    text = HEAL_BRACKET_SPACES.sub(r"{\1}", text)

    # Heal </ color > -> </color>
    text = HEAL_TAG_SPACES.sub(r"</\1>", text)

    return text


def extract_all_tokens(text: str) -> list[str]:
    """Extract all tokens that must be preserved."""
    tokens: list[str] = []
    tokens.extend(TOKEN_INJECTED_BREAKS.findall(text))
    tokens.extend(TOKEN_INTERPOLATION.findall(text))
    tokens.extend(TOKEN_BRACKETED_PARAMS.findall(text))
    tokens.extend(RICH_TEXT_TAGS.findall(text))
    return tokens


def soft_validate_translation(original_text: str, raw_translation: str) -> ValidationResult:
    """Execute Stage 1 auto-healing and Stage 2 discrepancy analysis."""
    # 1. Auto-heal
    healed = auto_heal_tokens(raw_translation)

    orig_tokens = extract_all_tokens(original_text)
    trans_tokens = extract_all_tokens(healed)

    orig_counts: dict[str, int] = {}
    for t in orig_tokens:
        orig_counts[t] = orig_counts.get(t, 0) + 1

    trans_counts: dict[str, int] = {}
    for t in trans_tokens:
        trans_counts[t] = trans_counts.get(t, 0) + 1

    missing: list[str] = []
    for token, count in orig_counts.items():
        if trans_counts.get(token, 0) < count:
            diff = count - trans_counts.get(token, 0)
            missing.extend([token] * diff)

    extra: list[str] = []
    for token, count in trans_counts.items():
        if orig_counts.get(token, 0) < count:
            diff = count - orig_counts.get(token, 0)
            extra.extend([token] * diff)

    # Lingering CJK check
    cjk_matches = CJK_CHAR_PATTERN.findall(healed)
    has_cjk = len(cjk_matches) > 0

    warnings: list[str] = []
    if missing:
        warnings.append(f"Missing required tokens: {sorted(set(missing))}")
    if extra:
        warnings.append(f"Unexpected extra tokens: {sorted(set(extra))}")
    if has_cjk:
        warnings.append(f"Contains {len(cjk_matches)} untranslated Chinese characters")

    is_clean = len(missing) == 0 and not has_cjk

    return ValidationResult(
        healed_text=healed,
        is_clean=is_clean,
        missing_tokens=missing,
        extra_tokens=extra,
        has_untranslated_cjk=has_cjk,
        warning_messages=warnings,
    )
