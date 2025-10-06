import os
import json
from pathlib import Path
from src.config import GROSSARY_DIR
from src.logger import logger

def load_grossary(glossary_file_path=None):
    """Load glossary data from JSON or TXT files.

    Args:
        glossary_file_path (str, optional): Absolute path to a specific glossary file (.json or .txt).

    Returns:
        Tuple of (name_to_translated, original_to_translated) dictionaries

    Raises:
        FileNotFoundError: If glossary directory doesn't exist or specified file not found.
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
        grossary_path = Path(GROSSARY_DIR)
        if not grossary_path.exists():
            raise FileNotFoundError(f"Glossary directory not found: {GROSSARY_DIR}")
        files_to_process.extend(list(grossary_path.glob('*.json')))
        if not files_to_process:
            logger.warning(f"No glossary files found in {GROSSARY_DIR}")
            return name_to_translated, original_to_translated

    for file in files_to_process:
        try:
            if file.suffix == '.json':
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if isinstance(data, list):
                    for entry in data:
                        name = entry.get('Name', '').strip()
                        original = entry.get('Original', '').strip()
                        translated = entry.get('Translated', '').strip()

                        if name and translated:
                            name_to_translated[name] = translated
                        if original and translated:
                            original_to_translated[original] = translated

                elif isinstance(data, dict):
                    # fallback for dict format
                    for k, v in data.items():
                        if k.strip() and str(v).strip():
                            name_to_translated[k.strip()] = str(v).strip()

            elif file.suffix == '.txt':
                with open(file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if '=' in line:
                            original, translated = line.split('=', 1)
                            original = original.strip()
                            translated = translated.strip()
                            if original and translated:
                                original_to_translated[original] = translated
                                # For TXT, we don't have a 'Name' field, so we'll use original for name_to_translated if needed
                                name_to_translated[original] = translated

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in glossary file {file}: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to process glossary file {file}: {str(e)}", exc_info=True)
    return name_to_translated, original_to_translated

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

    matches = [(orig, trans) for orig, trans in original_to_translated.items()
               if orig and orig in text]
    return sorted(matches, key=lambda x: len(x[0]), reverse=True)  # Longest matches first
