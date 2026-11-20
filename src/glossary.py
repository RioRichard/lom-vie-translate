import json
from pathlib import Path
from typing import Any

import aiofiles

from src.logger import logger
from src.utils import parse_json_entries


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
