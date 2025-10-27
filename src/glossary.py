import json
import aiofiles
from pathlib import Path
from src.config import GLOSSARY_DIR
from src.logger import logger


async def load_glossary_async(glossary_file_path=None):
    """Asynchronously load glossary data from JSON or TXT files."""
    name_to_translated = {}
    original_to_translated = {}
    files_to_process = []

    if glossary_file_path:
        file_path = Path(glossary_file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Glossary file not found: {glossary_file_path}")
        files_to_process.append(file_path)
    else:
        glossary_path = Path(GLOSSARY_DIR)
        if glossary_path.exists():
            files_to_process.extend(list(glossary_path.glob("*.json")))
        else:
            logger.warning(f"Glossary directory not found: {GLOSSARY_DIR}")

    if not files_to_process:
        logger.warning(f"No glossary files found in {GLOSSARY_DIR}")
        return name_to_translated, original_to_translated

    for file in files_to_process:
        try:
            async with aiofiles.open(file, "r", encoding="utf-8") as f:
                content = await f.read()
                if file.suffix == ".json":
                    data = json.loads(content)
                    if isinstance(data, list):
                        for entry in data:
                            name = entry.get("Name", "").strip()
                            original = entry.get("Original", "").strip()
                            translated = entry.get("Translated", "").strip()
                            if name and translated:
                                name_to_translated[name] = translated
                            if original and translated:
                                original_to_translated[original] = translated
                    elif isinstance(data, dict):
                        for k, v in data.items():
                            if k.strip() and str(v).strip():
                                name_to_translated[k.strip()] = str(v).strip()
                elif file.suffix == ".txt":
                    for line in content.splitlines():
                        if "=" in line:
                            original, translated = line.split("=", 1)
                            original, translated = original.strip(), translated.strip()
                            if original and translated:
                                original_to_translated[original] = translated
                                name_to_translated[original] = translated
        except Exception as e:
            logger.error(f"Failed to process glossary file {file}: {str(e)}")
    return name_to_translated, original_to_translated


async def load_old_translations_async(input_dir, translated_dir):
    """Asynchronously load old translations by comparing input and translated directories."""
    old_translations_map = {}
    input_path = Path(input_dir)
    translated_path = Path(translated_dir)

    if not translated_path.exists():
        logger.warning(f"Translated directory not found: {translated_dir}")
        return old_translations_map

    def _parse_entries(data):
        entries = data.get("entries", [])
        return (
            entries["Array"]
            if isinstance(entries, dict) and "Array" in entries
            else (entries if isinstance(entries, list) else [])
        )

    for t_file in translated_path.glob("*.json"):
        o_file = input_path / t_file.name
        if not o_file.exists():
            continue
        try:
            async with aiofiles.open(o_file, "r", encoding="utf-8") as f:
                o_data = json.loads(await f.read())
            async with aiofiles.open(t_file, "r", encoding="utf-8") as f:
                t_data = json.loads(await f.read())

            o_entries, t_entries = _parse_entries(o_data), _parse_entries(t_data)
            t_map = {
                (e.get("key") or e.get("Name")): (e.get("value") or e.get("Text", ""))
                for e in t_entries
            }

            for o_entry in o_entries:
                name = o_entry.get("key") or o_entry.get("Name")
                original_text = (
                    o_entry.get("value") or o_entry.get("Text", "")
                ).strip()
                if name in t_map:
                    translated_text = t_map[name].strip()
                    if original_text and translated_text:
                        old_translations_map[original_text] = translated_text
        except Exception as e:
            logger.error(
                f"Failed to process old translation file pair ({o_file.name}, {t_file.name}): {e}"
            )
    return old_translations_map


def load_glossary(glossary_file_path=None):
    """Load glossary data from JSON or TXT files.

    Args:
        glossary_file_path (str, optional): Absolute path to a specific glossary file (.json or .txt).

    Returns:
        Tuple of (name_to_translated, original_to_translated) dictionaries

    Raises:
        FileNotFoundError: If a specified glossary file is not found.
        json.JSONDecodeError: If a glossary JSON file is invalid.
    """
    name_to_translated = {}
    original_to_translated = {}

    files_to_process = []

    if glossary_file_path:
        file_path = Path(glossary_file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Glossary file not found: {glossary_file_path}")
        files_to_process.append(file_path)
    else:
        glossary_path = Path(GLOSSARY_DIR)
        if not glossary_path.exists():
            logger.warning(f"Glossary directory not found: {GLOSSARY_DIR}")
            return name_to_translated, original_to_translated
        files_to_process.extend(list(glossary_path.glob("*.json")))
        if not files_to_process:
            logger.warning(f"No glossary files found in {GLOSSARY_DIR}")
            return name_to_translated, original_to_translated

    for file in files_to_process:
        try:
            if file.suffix == ".json":
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, list):
                    for entry in data:
                        name = entry.get("Name", "").strip()
                        original = entry.get("Original", "").strip()
                        translated = entry.get("Translated", "").strip()

                        if name and translated:
                            name_to_translated[name] = translated
                        if original and translated:
                            original_to_translated[original] = translated

                elif isinstance(data, dict):
                    # fallback for dict format
                    for k, v in data.items():
                        if k.strip() and str(v).strip():
                            name_to_translated[k.strip()] = str(v).strip()

            elif file.suffix == ".txt":
                with open(file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if "=" in line:
                            original, translated = line.split("=", 1)
                            original = original.strip()
                            translated = translated.strip()
                            if original and translated:
                                original_to_translated[original] = translated
                                # For TXT, we don't have a 'Name' field, so we'll use original for name_to_translated if needed
                                name_to_translated[original] = translated

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in glossary file {file}: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to process glossary file {file}: {str(e)}")
    return name_to_translated, original_to_translated


def load_old_translations(input_dir, translated_dir):
    """Load old translations by comparing input and translated directories."""
    old_translations_map = {}
    input_path = Path(input_dir)
    translated_path = Path(translated_dir)

    if not translated_path.exists():
        logger.warning(f"Translated directory not found: {translated_dir}")
        return old_translations_map

    def _parse_entries(data):
        entries = data.get("entries", [])
        if isinstance(entries, dict) and "Array" in entries:
            return entries["Array"]
        return entries if isinstance(entries, list) else []

    for t_file in translated_path.glob("*.json"):
        o_file = input_path / t_file.name
        if not o_file.exists():
            continue

        try:
            with open(o_file, "r", encoding="utf-8") as f:
                o_data = json.load(f)
            with open(t_file, "r", encoding="utf-8") as f:
                t_data = json.load(f)

            o_entries = _parse_entries(o_data)
            t_entries = _parse_entries(t_data)

            t_map = {
                (e.get("key") or e.get("Name")): (e.get("value") or e.get("Text", ""))
                for e in t_entries
            }

            for o_entry in o_entries:
                name = o_entry.get("key") or o_entry.get("Name")
                original_text = (
                    o_entry.get("value") or o_entry.get("Text", "")
                ).strip()
                if name in t_map:
                    translated_text = t_map[name].strip()
                    if original_text and translated_text:
                        old_translations_map[original_text] = translated_text
        except json.JSONDecodeError as e:
            logger.error(
                f"Invalid JSON in old translation file pair ({o_file.name}, {t_file.name}): {e}"
            )
        except Exception as e:
            logger.error(
                f"Failed to process old translation file pair ({o_file.name}, {t_file.name}): {e}"
            )

    return old_translations_map


def get_translated_by_name(name, name_to_translated):
    return name_to_translated.get(name)


def find_original_matches(text, original_to_translated):
    """Find all glossary terms that appear in the given text

    Args:
        text: The text to search in
        original_to_translated: Dictionary mapping original terms to translations

    Returns:
        List of (original, translation) tuples for matches found
    """
    if not text or not original_to_translated:
        return []

    matches = [
        (orig, trans)
        for orig, trans in original_to_translated.items()
        if orig and orig in text
    ]
    return sorted(
        matches, key=lambda x: len(x[0]), reverse=True
    )  # Longest matches first
