import asyncio
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import aiofiles

from src.logger import logger
from src.relationship_matrix import RelationshipMatrix, sync_matrix_characters
from src.story_flowchart import (
    ANONYMOUS_CHARACTER_NAMES,
    CURATED_CHARACTERS,
    StoryFlowchart,
    sync_characters_from_glossary,
)
from src.utils import SPECIAL_CHARS, parse_json_entries


def _resolve_glossary_files(
    glossary_file_path: str | Path | None,
    glossary_dir: str | Path,
) -> list[Path]:
    """Resolve the list of glossary files to load."""
    if glossary_file_path:
        file_path = Path(glossary_file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Glossary file not found: {glossary_file_path}")
        return [file_path]

    glossary_path = Path(glossary_dir)
    if not glossary_path.exists():
        logger.warning(f"Glossary directory not found: {glossary_dir}")
        return []

    files = sorted(glossary_path.glob("*.json"))
    if not files:
        logger.warning(f"No glossary files found in {glossary_dir}")
    return files


def _parse_glossary_content(
    content: str,
    suffix: str,
    name_to_translated: dict[str, str],
    original_to_translated: dict[str, str],
) -> None:
    """Parse glossary file content (.json or .txt) into lookup dictionaries."""
    ext = suffix.lower()
    if ext == ".json":
        data = json.loads(content)
        if isinstance(data, list):
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("Name") or "").strip()
                original = str(entry.get("Original") or "").strip()
                translated = str(entry.get("Translated") or "").strip()
                if name and translated:
                    name_to_translated[name] = translated
                if original and translated:
                    original_to_translated[original] = translated
        elif isinstance(data, dict):
            for key, value in data.items():
                k = str(key).strip() if key is not None else ""
                v = str(value).strip() if value is not None else ""
                if k and v:
                    name_to_translated[k] = v
                    original_to_translated[k] = v
    elif ext == ".txt":
        for line in content.splitlines():
            stripped = line.strip()
            if "=" in stripped:
                original, translated = stripped.split("=", 1)
                original = original.strip()
                translated = translated.strip()
                if original and translated:
                    original_to_translated[original] = translated
                    name_to_translated[original] = translated


def _extract_old_pairs(
    original_data: dict[str, Any],
    translated_data: dict[str, Any],
) -> dict[str, str]:
    """Extract original_text -> translated_text pairs from aligned JSON files."""
    o_entries, _ = parse_json_entries(original_data)
    t_entries, _ = parse_json_entries(translated_data)

    t_map: dict[str, str] = {}
    for entry in t_entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("key") or entry.get("Name")
        if name:
            t_map[str(name)] = str(entry.get("value") or entry.get("Text") or "")

    pairs: dict[str, str] = {}
    for o_entry in o_entries:
        if not isinstance(o_entry, dict):
            continue
        name = o_entry.get("key") or o_entry.get("Name")
        original_text = str(o_entry.get("value") or o_entry.get("Text") or "").strip()
        if name and str(name) in t_map:
            translated_text = t_map[str(name)].strip()
            if original_text and translated_text:
                pairs[original_text] = translated_text

    return pairs


async def load_glossary_async(
    glossary_file_path: str | Path | None = None,
    glossary_dir: str | Path = "Resource/glossary",
) -> tuple[dict[str, str], dict[str, str]]:
    """Asynchronously load glossary data from JSON or TXT files."""
    name_to_translated: dict[str, str] = {}
    original_to_translated: dict[str, str] = {}

    files_to_process = _resolve_glossary_files(glossary_file_path, glossary_dir)
    for file in files_to_process:
        try:
            async with aiofiles.open(file, encoding="utf-8") as f:
                content = await f.read()
            _parse_glossary_content(content, file.suffix, name_to_translated, original_to_translated)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in glossary file {file}: {e}")
        except Exception as e:
            logger.error(f"Failed to process glossary file {file}: {e}")

    return name_to_translated, original_to_translated


def load_glossary(
    glossary_file_path: str | Path | None = None,
    glossary_dir: str | Path = "Resource/glossary",
) -> tuple[dict[str, str], dict[str, str]]:
    """Load glossary data from JSON or TXT files."""
    name_to_translated: dict[str, str] = {}
    original_to_translated: dict[str, str] = {}

    files_to_process = _resolve_glossary_files(glossary_file_path, glossary_dir)
    for file in files_to_process:
        try:
            with open(file, encoding="utf-8") as f:
                content = f.read()
            _parse_glossary_content(content, file.suffix, name_to_translated, original_to_translated)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in glossary file {file}: {e}")
        except Exception as e:
            logger.error(f"Failed to process glossary file {file}: {e}")

    return name_to_translated, original_to_translated


async def load_old_translations_async(
    input_dir: str | Path,
    translated_dir: str | Path,
) -> dict[str, str]:
    """Asynchronously load old translations by comparing input and translated directories."""
    old_translations_map: dict[str, str] = {}
    input_path = Path(input_dir)
    translated_path = Path(translated_dir)

    if not translated_path.exists():
        logger.warning(f"Translated directory not found: {translated_dir}")
        return old_translations_map

    for t_file in sorted(translated_path.glob("*.json")):
        o_file = input_path / t_file.name
        if not o_file.exists():
            continue
        try:
            async with aiofiles.open(o_file, encoding="utf-8") as f:
                o_data = json.loads(await f.read())
            async with aiofiles.open(t_file, encoding="utf-8") as f:
                t_data = json.loads(await f.read())
            old_translations_map.update(_extract_old_pairs(o_data, t_data))
        except json.JSONDecodeError as e:
            logger.error(
                f"Invalid JSON in old translation file pair ({o_file.name}, {t_file.name}): {e}"
            )
        except Exception as e:
            logger.error(
                f"Failed to process old translation file pair ({o_file.name}, {t_file.name}): {e}"
            )

    return old_translations_map


def load_old_translations(
    input_dir: str | Path,
    translated_dir: str | Path,
) -> dict[str, str]:
    """Load old translations by comparing input and translated directories."""
    old_translations_map: dict[str, str] = {}
    input_path = Path(input_dir)
    translated_path = Path(translated_dir)

    if not translated_path.exists():
        logger.warning(f"Translated directory not found: {translated_dir}")
        return old_translations_map

    for t_file in sorted(translated_path.glob("*.json")):
        o_file = input_path / t_file.name
        if not o_file.exists():
            continue
        try:
            with open(o_file, encoding="utf-8") as f:
                o_data = json.load(f)
            with open(t_file, encoding="utf-8") as f:
                t_data = json.load(f)
            old_translations_map.update(_extract_old_pairs(o_data, t_data))
        except json.JSONDecodeError as e:
            logger.error(
                f"Invalid JSON in old translation file pair ({o_file.name}, {t_file.name}): {e}"
            )
        except Exception as e:
            logger.error(
                f"Failed to process old translation file pair ({o_file.name}, {t_file.name}): {e}"
            )

    return old_translations_map


def get_translated_by_name(name: str, name_to_translated: dict[str, str]) -> str | None:
    return name_to_translated.get(name)


def find_original_matches(
    text: str,
    original_to_translated: dict[str, str] | None,
) -> list[tuple[str, str]]:
    """Find all glossary terms that appear in the given text (longest matches first)."""
    if not text or not original_to_translated:
        return []

    matches = [
        (orig, trans)
        for orig, trans in original_to_translated.items()
        if orig and orig in text
    ]
    return sorted(matches, key=lambda item: len(item[0]), reverse=True)


_CANDIDATE_PREFIX_RULES: tuple[tuple[str, str], ...] = (
    # characters
    ("Character/", "characters"),
    ("CharacterTitle/", "characters"),
    ("CombatCharacter/Name/", "characters"),
    ("CombatCharacter/Title/", "characters"),
    ("PlayerInfo/Lover/", "characters"),
    ("PlayerInfo/Title/", "characters"),
    ("EnemyTeam/", "characters"),
    # martial_arts
    ("Book/Name/", "martial_arts"),
    ("CombatSkill/Name/", "martial_arts"),
    ("BattleSkill/Name/", "martial_arts"),
    ("BattleSkill/Brother1/", "martial_arts"),
    ("PlayerTalent/Name/", "martial_arts"),
    # locations
    ("Position/Name/", "locations"),
    ("Position/title/", "locations"),
    ("MapPosition/Name/", "locations"),
    ("Facility/Name/", "locations"),
    ("Facility/Title/", "locations"),
    # items_lore
    ("Equip/Name/", "items_lore"),
    ("Misc/Name/", "items_lore"),
    ("_Misc/Name/", "items_lore"),
    ("Special/Name/", "items_lore"),
    ("Library/Title/", "items_lore"),
    ("Flag/Name/", "items_lore"),
)

_DESC_PREFIX_BY_NAME_PREFIX: dict[str, tuple[str, ...]] = {
    "Book/Name/": ("Book/Desc/",),
    "CombatSkill/Name/": ("CombatSkill/Desc/",),
    "BattleSkill/Name/": ("BattleSkill/Desc/",),
    "BattleSkill/Brother1/": ("BattleSkill/Desc/",),
    "PlayerTalent/Name/": ("PlayerTalent/Desc/",),
    "MapPosition/Name/": ("MapPosition/Desc/", "MapPosition/desc/"),
    "Equip/Name/": ("Equip/Desc/",),
    "Misc/Name/": ("Misc/Desc/",),
    "_Misc/Name/": ("_Misc/Desc/",),
    "Special/Name/": ("Special/Desc/",),
    "Library/Title/": ("Library/Desc/",),
    "Flag/Name/": ("Flag/Desc/",),
}

_CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "characters": "Tên nhân vật, danh hiệu, xưng hô hoặc tên môn phái/phe phái",
    "martial_arts": "Tên võ công, bí kíp, tuyệt chiêu hoặc thiên phú võ học",
    "locations": "Địa danh, bản đồ, kiến trúc hoặc cơ sở môn phái",
    "items_lore": "Trang bị, vật phẩm, dược phẩm, điển cố hoặc mục lục thư viện",
}


def _should_skip_candidate(text: str) -> bool:
    """Return True if candidate text is empty, anonymous, placeholder-only, or non-letter."""
    cleaned = text.strip()
    if not cleaned:
        return True
    if cleaned in SPECIAL_CHARS or cleaned in ANONYMOUS_CHARACTER_NAMES:
        return True
    if "{title}" in cleaned or "{{title}}" in cleaned:
        return True
    without_placeholders = re.sub(r"\{+[^{}]*\}+", "", cleaned)
    return not any(unicodedata.category(ch).startswith("L") for ch in without_placeholders)


def _clean_context_text(raw: str) -> str:
    """Normalize linebreaks and repeated whitespace in context snippets."""
    return " ".join(raw.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").split())


def _build_character_context(
    prefix: str,
    item_id: str,
    all_entries: dict[str, str],
    flowchart: Any | None,
) -> str:
    """Build paired biography, companion name/title, and flowchart context for characters."""
    parts: list[str] = []

    if prefix in ("Character/", "CombatCharacter/Name/"):
        title = (
            all_entries.get(f"CharacterTitle/{item_id}")
            or all_entries.get(f"CombatCharacter/Title/{item_id}")
            or ""
        )
        if title and not _should_skip_candidate(title):
            parts.append(f"Danh hiệu: {_clean_context_text(title)}")
    elif prefix in ("CharacterTitle/", "CombatCharacter/Title/"):
        char_name = (
            all_entries.get(f"Character/{item_id}")
            or all_entries.get(f"CombatCharacter/Name/{item_id}")
            or ""
        )
        if char_name and not _should_skip_candidate(char_name):
            parts.append(f"Nhân vật: {_clean_context_text(char_name)}")

    intros = [
        _clean_context_text(all_entries[f"CharacterIntro{i}/{item_id}"])
        for i in range(5)
        if all_entries.get(f"CharacterIntro{i}/{item_id}", "").strip()
    ]
    if intros:
        parts.append(f"Tiểu sử: {' | '.join(intros)}")

    fc_chars = getattr(flowchart, "characters", None) if flowchart is not None else None
    cinfo = fc_chars.get(item_id) if isinstance(fc_chars, dict) else None
    if cinfo is not None:
        zh_title = (getattr(cinfo, "zh_title", "") or "").strip()
        if (
            prefix in ("Character/", "CombatCharacter/Name/")
            and zh_title
            and not _should_skip_candidate(zh_title)
            and not any(p.startswith("Danh hiệu:") for p in parts)
        ):
            parts.append(f"Danh hiệu: {_clean_context_text(zh_title)}")

        gender = (getattr(cinfo, "gender", "") or "").strip()
        if gender:
            parts.append(f"Giới tính: {gender}")

        aliases = [
            str(alias).strip()
            for alias in (getattr(cinfo, "aliases", None) or [])
            if str(alias).strip()
        ]
        if aliases:
            parts.append(f"Biệt danh: {', '.join(aliases)}")

        traits = (getattr(cinfo, "traits", "") or "").strip()
        if traits and not intros:
            parts.append(f"Đặc điểm: {_clean_context_text(traits)}")

    return "\n".join(parts)


def _build_candidate_context(
    prefix: str,
    category: str,
    item_id: str,
    all_entries: dict[str, str],
    lower_entries: dict[str, str],
    facility_effects: dict[str, list[str]],
    flowchart: Any | None,
) -> str:
    """Build paired description or character context for a glossary candidate."""
    if category == "characters":
        if prefix in (
            "Character/",
            "CharacterTitle/",
            "CombatCharacter/Name/",
            "CombatCharacter/Title/",
        ):
            return _build_character_context(prefix, item_id, all_entries, flowchart)
        return ""

    if prefix in ("Position/Name/", "Position/title/"):
        parts: list[str] = []
        if prefix == "Position/Name/":
            companion = (
                all_entries.get(f"Position/title/{item_id}")
                or lower_entries.get(f"position/title/{item_id.lower()}")
                or ""
            )
            if companion and not _should_skip_candidate(companion):
                parts.append(f"Hoạt động/Tiêu đề: {_clean_context_text(companion)}")
        else:
            companion = (
                all_entries.get(f"Position/Name/{item_id}")
                or lower_entries.get(f"position/name/{item_id.lower()}")
                or ""
            )
            if companion and not _should_skip_candidate(companion):
                parts.append(f"Địa điểm: {_clean_context_text(companion)}")

        desc = (
            all_entries.get(f"Position/desc/{item_id}")
            or lower_entries.get(f"position/desc/{item_id.lower()}")
            or ""
        )
        if desc.strip():
            parts.append(f"Mô tả: {_clean_context_text(desc)}")
        return "\n".join(parts)

    if prefix in ("Facility/Name/", "Facility/Title/"):
        raw_effects = list(facility_effects.get(item_id, []))
        direct = all_entries.get(f"Facility/Effect/{item_id}")
        if direct:
            raw_effects.insert(0, direct)
        cleaned_effects = list(
            dict.fromkeys(
                eff_clean
                for eff in raw_effects
                if (eff_clean := _clean_context_text(eff)) and eff_clean != "【效果】"
            )
        )
        if cleaned_effects:
            return f"Hiệu quả: {' | '.join(cleaned_effects)}"
        return ""

    for desc_prefix in _DESC_PREFIX_BY_NAME_PREFIX.get(prefix, ()):
        desc = all_entries.get(f"{desc_prefix}{item_id}", "")
        if not desc and prefix == "BattleSkill/Brother1/":
            desc = all_entries.get("BattleSkill/Desc/brother1", "")
        if desc.strip():
            return f"Mô tả: {_clean_context_text(desc)}"
    return ""


def extract_game_glossary_candidates(
    input_dir: str | Path,
    flowchart: Any | None = None,
) -> list[dict[str, str]]:
    """Extract structured glossary candidates with paired context from ChineseSimplified JSONs."""
    input_path = Path(input_dir)
    all_entries: dict[str, str] = {}
    lower_entries: dict[str, str] = {}
    facility_effects: dict[str, list[str]] = {}
    ordered_items: list[tuple[str, str]] = []
    seen_entry_names: set[str] = set()

    if input_path.is_dir():
        for json_file in sorted(input_path.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(f"Skipping unreadable JSON file {json_file.name}: {exc}")
                continue
            if not isinstance(data, dict) or data.get("Language") != "ChineseSimplified":
                continue

            entries, _ = parse_json_entries(data)
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("Name") or entry.get("key") or "").strip()
                text = str(entry.get("Text") or entry.get("value") or "").strip()
                if not name:
                    continue

                if name not in all_entries or (not all_entries[name] and text):
                    all_entries[name] = text
                lower_key = name.lower()
                if lower_key not in lower_entries or (not lower_entries[lower_key] and text):
                    lower_entries[lower_key] = text

                if name.startswith("Facility/Effect/") and text:
                    eff_id = name.removeprefix("Facility/Effect/")
                    facility_effects.setdefault(eff_id, []).append(text)
                    base_eff_id = eff_id.split("_", 1)[0]
                    if base_eff_id != eff_id:
                        facility_effects.setdefault(base_eff_id, []).append(text)

                if name not in seen_entry_names:
                    seen_entry_names.add(name)
                    ordered_items.append((name, text))

    candidates: list[dict[str, str]] = []
    emitted_names: set[str] = set()

    for name, raw_text in ordered_items:
        matched_rule = next(
            ((pfx, cat) for pfx, cat in _CANDIDATE_PREFIX_RULES if name.startswith(pfx)),
            None,
        )
        if matched_rule is None or _should_skip_candidate(raw_text):
            continue

        prefix, category = matched_rule
        item_id = name.removeprefix(prefix)
        context = _build_candidate_context(
            prefix=prefix,
            category=category,
            item_id=item_id,
            all_entries=all_entries,
            lower_entries=lower_entries,
            facility_effects=facility_effects,
            flowchart=flowchart,
        )
        emitted_names.add(name)
        candidates.append(
            {
                "Name": name,
                "Original": raw_text,
                "Category": category,
                "Context": context,
            }
        )

    fc_chars = getattr(flowchart, "characters", None) if flowchart is not None else None
    if isinstance(fc_chars, dict):
        for cid, cinfo in fc_chars.items():
            if cid == "narrative":
                continue
            zh_name = (getattr(cinfo, "zh_name", "") or "").strip()
            char_key = f"Character/{cid}"
            if char_key not in emitted_names and not _should_skip_candidate(zh_name):
                emitted_names.add(char_key)
                ctx = _build_character_context("Character/", cid, all_entries, flowchart)
                candidates.append(
                    {
                        "Name": char_key,
                        "Original": zh_name,
                        "Category": "characters",
                        "Context": ctx,
                    }
                )

            zh_title = (getattr(cinfo, "zh_title", "") or "").strip()
            title_key = f"CharacterTitle/{cid}"
            if (
                title_key not in emitted_names
                and f"CombatCharacter/Title/{cid}" not in emitted_names
                and not _should_skip_candidate(zh_title)
            ):
                emitted_names.add(title_key)
                ctx = _build_character_context("CharacterTitle/", cid, all_entries, flowchart)
                candidates.append(
                    {
                        "Name": title_key,
                        "Original": zh_title,
                        "Category": "characters",
                        "Context": ctx,
                    }
                )

    return candidates


def build_glossary_term_prompt(
    original_text: str,
    category: str,
    context: str = "",
    glossary_matches: list[tuple[str, str]] | None = None,
) -> str:
    """Build a domain-aware Chinese->Vietnamese prompt for translating a single glossary term."""
    cat_desc = _CATEGORY_DESCRIPTIONS.get(
        category,
        "Thuật ngữ bản địa hóa game kiếm hiệp cổ trang",
    )
    sections = [
        (
            "Bạn là chuyên gia bản địa hóa game kiếm hiệp cổ trang Legend of Mortal "
            "(Tiếng Trung Giản thể -> Tiếng Việt).\n"
            f"Loại thuật ngữ: {category} ({cat_desc}).\n"
            "Quy tắc bắt buộc:\n"
            "1. Dịch chuẩn xác theo văn phong kiếm hiệp cổ trang / Hán-Việt "
            "(viết hoa đúng danh từ riêng, tên nhân vật, môn phái, võ công, địa danh).\n"
            "2. Giữ nguyên các kí hiệu đặc biệt hoặc placeholder code nếu có ({0:0}, [|], v.v.).\n"
            "3. Chỉ trả về DUY NHẤT bản dịch tiếng Việt ở dạng plain text, "
            "không giải thích thêm, không ngoặc kép thừa, không giữ lại chữ tiếng Trung."
        )
    ]

    cleaned_ctx = context.strip()
    if cleaned_ctx:
        sections.append(f"Ngữ cảnh đi kèm:\n{cleaned_ctx}")

    if glossary_matches:
        match_lines = ["Thuật ngữ thành phần đã chuẩn hóa (bắt buộc giữ nhất quán):"]
        for orig, trans in glossary_matches:
            match_lines.append(f"- {orig}={trans}")
        sections.append("\n".join(match_lines))

    sections.append(f"Thuật ngữ cần dịch:\n{original_text}")
    return "\n\n".join(sections)


def _resolve_sync_target_paths(
    glossary_file_path: str | Path | None,
    glossary_dir: str | Path,
) -> tuple[Path, Path, Path | None]:
    """Resolve target ``(json_path, txt_path, explicit_txt_seed)`` for glossary syncing."""
    if glossary_file_path:
        given = Path(glossary_file_path)
        suffix = given.suffix.lower()
        if suffix == ".txt":
            return given.with_suffix(".json"), given, given
        if suffix == ".json":
            return given, given.with_suffix(".txt"), None
        return given.with_suffix(".json"), given.with_suffix(".txt"), None

    g_dir = Path(glossary_dir)
    return g_dir / "glossary.json", g_dir / "glossary.txt", None


def _load_existing_glossary_entries(
    target_json_path: Path,
    target_txt_path: Path,
    explicit_txt_seed: Path | None,
    glossary_dir: str | Path,
    using_default_dir: bool,
) -> tuple[
    dict[str, dict[str, str]],
    list[dict[str, str]],
    dict[str, str],
    dict[str, str],
    bool,
]:
    """Load existing glossary entries and auxiliary maps without failing on missing files."""
    entries_by_name: dict[str, dict[str, str]] = {}
    nameless_entries: list[dict[str, str]] = []
    extra_name_map: dict[str, str] = {}
    extra_orig_map: dict[str, str] = {}
    format_migrated = False

    if target_json_path.is_file():
        try:
            raw_data = json.loads(target_json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error(f"Invalid JSON in glossary file {target_json_path}: {exc}")
            raw_data = []

        if isinstance(raw_data, list):
            for item in raw_data:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("Name") or "").strip()
                original = str(item.get("Original") or "").strip()
                translated = str(item.get("Translated") or "").strip()
                if name:
                    entries_by_name[name] = {
                        "Name": name,
                        "Original": original,
                        "Translated": translated,
                    }
                elif original and translated:
                    nameless_entries.append(
                        {"Name": "", "Original": original, "Translated": translated}
                    )
        elif isinstance(raw_data, dict):
            format_migrated = True
            if "entries" in raw_data:
                parsed_entries, _ = parse_json_entries(raw_data)
                for item in parsed_entries:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("Name") or item.get("key") or "").strip()
                    translated = str(item.get("Text") or item.get("value") or "").strip()
                    if name and translated:
                        entries_by_name[name] = {
                            "Name": name,
                            "Original": "",
                            "Translated": translated,
                        }
            else:
                for key, value in raw_data.items():
                    k_str = str(key).strip() if key is not None else ""
                    v_str = str(value).strip() if value is not None else ""
                    if k_str and v_str:
                        orig_val = "" if "/" in k_str else k_str
                        entries_by_name[k_str] = {
                            "Name": k_str,
                            "Original": orig_val,
                            "Translated": v_str,
                        }
                        extra_name_map[k_str] = v_str
                        if "/" not in k_str:
                            extra_orig_map[k_str] = v_str
    else:
        txt_seed = explicit_txt_seed if explicit_txt_seed is not None else target_txt_path
        if txt_seed.is_file():
            try:
                _parse_glossary_content(
                    txt_seed.read_text(encoding="utf-8"),
                    ".txt",
                    extra_name_map,
                    extra_orig_map,
                )
            except OSError as exc:
                logger.error(f"Failed to read seed glossary TXT {txt_seed}: {exc}")

    if using_default_dir:
        g_dir_path = Path(glossary_dir)
        if g_dir_path.is_dir():
            for other_json in sorted(g_dir_path.glob("*.json")):
                if other_json.resolve() == target_json_path.resolve():
                    continue
                try:
                    _parse_glossary_content(
                        other_json.read_text(encoding="utf-8"),
                        ".json",
                        extra_name_map,
                        extra_orig_map,
                    )
                except (OSError, json.JSONDecodeError) as exc:
                    logger.error(f"Failed to read auxiliary glossary file {other_json}: {exc}")

    return entries_by_name, nameless_entries, extra_name_map, extra_orig_map, format_migrated


def _match_curated_character(
    name: str,
    curr_orig: str,
    curated_base_zh: dict[str, str],
) -> str | None:
    """Resolve curated Vietnamese character name while guarding anonymous & variant IDs."""
    if curr_orig in ANONYMOUS_CHARACTER_NAMES:
        return None

    if name.startswith("Character/"):
        cid = name.removeprefix("Character/")
    elif name.startswith("CombatCharacter/Name/"):
        cid = name.removeprefix("CombatCharacter/Name/")
    else:
        return None

    if cid == "narrative":
        return None

    if cid in CURATED_CHARACTERS:
        base_zh = curated_base_zh.get(cid)
        if base_zh and curr_orig != base_zh:
            return None
        vi_name = CURATED_CHARACTERS[cid].get("vi_name", "").strip()
        return vi_name if vi_name and vi_name != curr_orig else None

    if "_" in cid:
        base_id = cid.split("_", 1)[0]
        if base_id in CURATED_CHARACTERS and base_id != "narrative":
            base_zh = curated_base_zh.get(base_id)
            if base_zh and curr_orig == base_zh:
                vi_name = CURATED_CHARACTERS[base_id].get("vi_name", "").strip()
                return vi_name if vi_name and vi_name != curr_orig else None

    return None


def _resolve_engine_task_name(engine: Any, requested_task: str) -> str:
    cfg = getattr(engine, "config", None)
    tasks = getattr(cfg, "tasks", None)
    if isinstance(tasks, dict) and requested_task not in tasks and "translate" in tasks:
        return "translate"
    return requested_task


def _escape_txt_field(text: str) -> str:
    return text.replace("\r", "\\r").replace("\n", "\\n")


def _build_curated_base_zh(
    candidates: list[dict[str, str]],
    flowchart: Any | None,
) -> dict[str, str]:
    """Map curated character IDs to their canonical Simplified Chinese names."""
    curated_base_zh: dict[str, str] = {}
    fc_chars = getattr(flowchart, "characters", None) if flowchart is not None else None
    for cid in CURATED_CHARACTERS:
        for cand in candidates:
            if cand["Name"] in (f"Character/{cid}", f"CombatCharacter/Name/{cid}"):
                curated_base_zh[cid] = cand["Original"]
                break
        if cid not in curated_base_zh and isinstance(fc_chars, dict):
            cinfo = fc_chars.get(cid)
            if cinfo is not None:
                zh_val = (getattr(cinfo, "zh_name", "") or "").strip()
                if zh_val:
                    curated_base_zh[cid] = zh_val
    return curated_base_zh


def _build_active_glossary_maps(
    entries_by_name: dict[str, dict[str, str]],
    nameless_entries: list[dict[str, str]],
    extra_name_map: dict[str, str],
    extra_orig_map: dict[str, str],
    outdated_names: set[str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Build active lookup maps excluding invalidated outdated entries."""
    name_to_translated: dict[str, str] = dict(extra_name_map)
    original_to_translated: dict[str, str] = {
        orig: trans for orig, trans in extra_orig_map.items() if orig and trans and trans != orig
    }
    for entry in nameless_entries:
        orig, trans = entry["Original"], entry["Translated"]
        if orig and trans and trans != orig:
            original_to_translated[orig] = trans
    for name, entry in entries_by_name.items():
        if name in outdated_names:
            continue
        orig = entry.get("Original", "")
        trans = entry.get("Translated", "")
        if trans and (not orig or trans != orig):
            name_to_translated[name] = trans
            if orig:
                original_to_translated[orig] = trans
    return name_to_translated, original_to_translated


async def _translate_glossary_wave(
    wave: list[dict[str, str]],
    engine: Any | None,
    resolved_task: str,
    semaphore: asyncio.Semaphore,
    entries_by_name: dict[str, dict[str, str]],
    name_to_translated: dict[str, str],
    original_to_translated: dict[str, str],
    outdated_names: set[str],
    stats: dict[str, int],
    override_provider: str | None,
    override_tier: str | None,
    override_model: str | None,
) -> bool:
    """Translate a wave of deduplicated missing/outdated glossary terms via ``engine``."""
    grouped: dict[str, list[dict[str, str]]] = {}
    changed = False

    for cand in wave:
        orig_text = cand["Original"]
        existing_trans = original_to_translated.get(orig_text)
        if existing_trans and existing_trans != orig_text:
            cname = cand["Name"]
            entries_by_name[cname] = {
                "Name": cname,
                "Original": orig_text,
                "Translated": existing_trans,
            }
            name_to_translated[cname] = existing_trans
            if cname in outdated_names:
                stats["outdated_updated"] += 1
            else:
                stats["reused"] += 1
            changed = True
            continue
        grouped.setdefault(orig_text, []).append(cand)

    if not grouped:
        return changed

    if engine is None:
        unresolved_count = sum(len(items) for items in grouped.values())
        logger.warning(
            "No TranslationEngine provided; skipping LLM translation for "
            f"{unresolved_count} glossary candidates."
        )
        stats["failed"] += unresolved_count
        return changed

    async def translate_group(
        orig_text: str,
        cands_for_orig: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]], str | None]:
        rep = next((c for c in cands_for_orig if c.get("Context")), cands_for_orig[0])
        sub_matches = [
            m
            for m in find_original_matches(orig_text, original_to_translated)
            if m[0] != orig_text
        ]
        prompt = build_glossary_term_prompt(
            original_text=orig_text,
            category=rep["Category"],
            context=rep["Context"],
            glossary_matches=sub_matches,
        )
        async with semaphore:
            try:
                result = await engine.translate_text(
                    text=orig_text,
                    task_name=resolved_task,
                    name=rep["Name"],
                    prompt_data={"prompt": prompt},
                    override_provider=override_provider,
                    override_tier=override_tier,
                    override_model=override_model,
                )
            except Exception as exc:
                logger.error(f"Glossary translation failed for '{orig_text}': {exc}")
                return orig_text, cands_for_orig, None

        if not getattr(result, "succeeded", False):
            logger.warning(
                f"Glossary translation failed for '{orig_text}': "
                f"{getattr(result, 'error', None) or 'unknown error'}"
            )
            return orig_text, cands_for_orig, None

        translated = str(getattr(result, "text", "") or "").strip()
        return (orig_text, cands_for_orig, translated) if translated else (orig_text, cands_for_orig, None)

    wave_results = await asyncio.gather(
        *[translate_group(orig_text, items) for orig_text, items in grouped.items()]
    )

    for orig_text, cands_for_orig, translated in wave_results:
        if not translated:
            stats["failed"] += len(cands_for_orig)
            continue
        original_to_translated[orig_text] = translated
        for cand in cands_for_orig:
            cname = cand["Name"]
            entries_by_name[cname] = {
                "Name": cname,
                "Original": orig_text,
                "Translated": translated,
            }
            name_to_translated[cname] = translated
            if cname in outdated_names:
                stats["outdated_updated"] += 1
            else:
                stats["new_translated"] += 1
            changed = True

    return changed


async def _persist_synced_glossary(
    target_json_path: Path,
    target_txt_path: Path,
    final_entries: list[dict[str, str]],
    changed: bool,
) -> None:
    """Write synced glossary JSON list and deduplicated TXT when changed or missing."""
    if changed or not target_json_path.is_file():
        async with aiofiles.open(target_json_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(final_entries, ensure_ascii=False, indent=2))

    if changed or not target_txt_path.is_file():
        txt_lines = list(
            dict.fromkeys(
                f"{_escape_txt_field(entry['Original'])}={_escape_txt_field(entry['Translated'])}"
                for entry in final_entries
                if entry.get("Original") and entry.get("Translated")
            )
        )
        async with aiofiles.open(target_txt_path, "w", encoding="utf-8") as f:
            await f.write("\n".join(txt_lines))


async def autocheck_and_sync_glossary(
    input_dir: str | Path,
    glossary_file_path: str | Path | None = None,
    glossary_dir: str | Path = "Resource/glossary",
    engine: Any | None = None,
    flowchart: Any | None = None,
    flowchart_file: str | Path | None = None,
    relationship_matrix: Any | None = None,
    relationship_file: str | Path | None = None,
    task_name: str = "improve_glossary",
    override_provider: str | None = None,
    override_tier: str | None = None,
    override_model: str | None = None,
    max_concurrent: int = 5,
) -> tuple[dict[str, str], dict[str, str], dict[str, int]]:
    """Verify, update, translate, and persist the game glossary, then sync character names."""
    target_json_path, target_txt_path, explicit_txt_seed = _resolve_sync_target_paths(
        glossary_file_path, glossary_dir
    )
    target_json_path.parent.mkdir(parents=True, exist_ok=True)

    (
        entries_by_name,
        nameless_entries,
        extra_name_map,
        extra_orig_map,
        changed,
    ) = _load_existing_glossary_entries(
        target_json_path=target_json_path,
        target_txt_path=target_txt_path,
        explicit_txt_seed=explicit_txt_seed,
        glossary_dir=glossary_dir,
        using_default_dir=not bool(glossary_file_path),
    )

    if flowchart is None and flowchart_file and Path(flowchart_file).is_file():
        flowchart = StoryFlowchart.from_json_file(flowchart_file)

    if relationship_matrix is None and relationship_file and Path(relationship_file).is_file():
        relationship_matrix = RelationshipMatrix.from_json_file(relationship_file)

    candidates = extract_game_glossary_candidates(input_dir, flowchart=flowchart)
    stats: dict[str, int] = {
        "total_candidates": len(candidates),
        "in_sync": 0,
        "reused": 0,
        "outdated_updated": 0,
        "new_translated": 0,
        "failed": 0,
        "flowchart_updated": 0,
        "matrix_updated": 0,
    }

    # 1) Outdated check: invalidate stale entries whose source Chinese text changed
    outdated_names: set[str] = set()
    for cand in candidates:
        name = cand["Name"]
        curr_orig = cand["Original"]
        existing = entries_by_name.get(name)
        if existing is not None:
            old_orig = existing.get("Original", "")
            if old_orig and old_orig != curr_orig:
                outdated_names.add(name)
                existing["Original"] = curr_orig
                existing["Translated"] = ""
                changed = True

    name_to_translated, original_to_translated = _build_active_glossary_maps(
        entries_by_name,
        nameless_entries,
        extra_name_map,
        extra_orig_map,
        outdated_names,
    )
    curated_base_zh = _build_curated_base_zh(candidates, flowchart)

    # 2) In-sync & deterministic reuse checks
    pending_candidates: list[dict[str, str]] = []
    for cand in candidates:
        name = cand["Name"]
        curr_orig = cand["Original"]
        existing = entries_by_name.get(name)

        if (
            name not in outdated_names
            and existing is not None
            and existing.get("Original") == curr_orig
            and existing.get("Translated")
            and existing.get("Translated") != curr_orig
        ):
            stats["in_sync"] += 1
            continue

        reused_trans = original_to_translated.get(curr_orig)
        if reused_trans and reused_trans != curr_orig:
            entries_by_name[name] = {
                "Name": name,
                "Original": curr_orig,
                "Translated": reused_trans,
            }
            name_to_translated[name] = reused_trans
            stats["reused"] += 1
            changed = True
            continue

        curated_vi = _match_curated_character(name, curr_orig, curated_base_zh)
        if curated_vi:
            entries_by_name[name] = {
                "Name": name,
                "Original": curr_orig,
                "Translated": curated_vi,
            }
            name_to_translated[name] = curated_vi
            original_to_translated[curr_orig] = curated_vi
            stats["reused"] += 1
            changed = True
            continue

        pending_candidates.append(cand)

    # 3) Missing / Outdated LLM translation (characters first so compound items see consistent names)
    if pending_candidates:
        waves = [
            [c for c in pending_candidates if c["Category"] == "characters"],
            [c for c in pending_candidates if c["Category"] != "characters"],
        ]
        semaphore = asyncio.Semaphore(max(max_concurrent, 1))
        resolved_task = (
            _resolve_engine_task_name(engine, task_name) if engine is not None else task_name
        )
        for wave in waves:
            if not wave:
                continue
            wave_changed = await _translate_glossary_wave(
                wave=wave,
                engine=engine,
                resolved_task=resolved_task,
                semaphore=semaphore,
                entries_by_name=entries_by_name,
                name_to_translated=name_to_translated,
                original_to_translated=original_to_translated,
                outdated_names=outdated_names,
                stats=stats,
                override_provider=override_provider,
                override_tier=override_tier,
                override_model=override_model,
            )
            changed = changed or wave_changed

    final_entries = [
        entry for entry in entries_by_name.values() if entry.get("Translated")
    ] + nameless_entries
    await _persist_synced_glossary(target_json_path, target_txt_path, final_entries, changed)

    if flowchart is not None:
        fc_updated = sync_characters_from_glossary(
            flowchart, name_to_translated, original_to_translated
        )
        stats["flowchart_updated"] = fc_updated
        if fc_updated > 0 and flowchart_file and hasattr(flowchart, "to_json_file"):
            flowchart.to_json_file(flowchart_file)

    if relationship_matrix is not None:
        rm_updated = sync_matrix_characters(
            relationship_matrix, flowchart, name_to_translated, original_to_translated
        )
        stats["matrix_updated"] = rm_updated
        if (
            rm_updated > 0
            and relationship_file
            and hasattr(relationship_matrix, "to_json_file")
        ):
            relationship_matrix.to_json_file(relationship_file)

    return name_to_translated, original_to_translated, stats
