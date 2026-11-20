import argparse
import json
from pathlib import Path
from typing import Any

from src.config import load_config
from src.glossary import find_original_matches, load_glossary
from src.utils import parse_json_entries


def load_entries(json_path: str | Path) -> list[dict[str, Any]]:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    entries_list, _ = parse_json_entries(data)
    return entries_list


def map_translation_context(
    json_path: str | Path,
    glossary_file_path: str | Path | None = None,
    glossary_dir: str | Path = "Resource/glossary",
) -> list[dict[str, Any]]:
    entries = load_entries(json_path)
    _, original_to_translated = load_glossary(
        glossary_file_path,
        glossary_dir=glossary_dir,
    )
    mapped: list[dict[str, Any]] = []
    for entry in entries:
        original_text = entry.get("value") or entry.get("Text", "")
        raw_translated_text = (
            entry.get("TranslatedText")
            or entry.get("translated")
            or entry.get("Text", "")
        )
        glossary_matches = find_original_matches(original_text, original_to_translated)
        mapped.append(
            {
                "original_text": original_text,
                "raw_translated_text": raw_translated_text,
                "glossary_matches": glossary_matches,
            }
        )
    return mapped


def map_all_files(
    input_dir: str | Path,
    glossary_file_path: str | Path | None = None,
    glossary_dir: str | Path = "Resource/glossary",
) -> dict[str, list[dict[str, Any]]]:
    json_dir = Path(input_dir)
    all_mapped: dict[str, list[dict[str, Any]]] = {}
    for file_path in sorted(json_dir.glob("*.json")):
        all_mapped[file_path.name] = map_translation_context(
            file_path,
            glossary_file_path=glossary_file_path,
            glossary_dir=glossary_dir,
        )
    return all_mapped


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Map JSON translation entries to their glossary matches."
    )
    parser.add_argument(
        "-c",
        "--config-file",
        default=None,
        help="Path to TOML configuration file (used when --input-dir is omitted).",
    )
    parser.add_argument(
        "--input-dir",
        default=None,
        help="Directory containing input JSON files (no config.toml needed when provided).",
    )
    parser.add_argument(
        "--glossary-file",
        default=None,
        help="Path to a specific glossary file (optional).",
    )

    args = parser.parse_args(argv)

    glossary_dir: str | Path = "Resource/glossary"
    glossary_file = args.glossary_file

    if args.input_dir is not None and args.config_file is None:
        input_dir = args.input_dir
    else:
        try:
            config = load_config(args.config_file)
        except (FileNotFoundError, ValueError) as exc:
            parser.error(str(exc))
        input_dir = args.input_dir if args.input_dir is not None else config.run.input_dir
        glossary_dir = config.run.glossary_dir
        if glossary_file is None:
            glossary_file = config.run.glossary_file

    input_path = Path(input_dir)
    if not input_path.is_dir():
        parser.error(f"Input directory not found: {input_path}")

    result = map_all_files(
        input_dir=input_path,
        glossary_file_path=glossary_file,
        glossary_dir=glossary_dir,
    )
    for fname, entries in result.items():
        print(f"--- {fname} ---")
        for entry in entries:
            print(entry)


if __name__ == "__main__":
    main()
