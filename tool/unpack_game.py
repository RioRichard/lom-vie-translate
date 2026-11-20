from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from src.glossary import load_glossary
from src.relationship_matrix import build_matrix_from_flowchart
from src.story_flowchart import extract_story_flowchart_from_mortal_data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Unpack Legend of Mortal Mortal_Data directly (zero-UABEA) into "
            "LeanLocalJson files, StoryFlowchart JSON, and RelationshipMatrix JSON."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-md",
        "--mortal-data-dir",
        required=True,
        help="Path to the Legend of Mortal Mortal_Data directory (read-only).",
    )
    parser.add_argument(
        "-od",
        "--output-json-dir",
        default="Resource/LeanLocalJson",
        help="Output directory for unpacked LeanLanguageCSV JSON files.",
    )
    parser.add_argument(
        "-ff",
        "--flowchart-file",
        default="Resource/story_flowchart.json",
        help="Output path for StoryFlowchart JSON.",
    )
    parser.add_argument(
        "-rf",
        "--relationship-file",
        default="Resource/relationship_matrix.json",
        help="Output path for RelationshipMatrix JSON.",
    )
    parser.add_argument(
        "--language",
        default="ChineseSimplified",
        help="Language table to extract from LeanLanguageCSV assets.",
    )
    parser.add_argument(
        "-gf",
        "--glossary-file",
        default=None,
        help="Optional glossary file to enrich Vietnamese character names in the matrix.",
    )
    parser.add_argument(
        "--skip-json",
        action="store_true",
        help="Skip extracting LeanLocalJson files.",
    )
    parser.add_argument(
        "--skip-flowchart",
        action="store_true",
        help="Skip building story_flowchart.json (also skips relationship matrix unless provided).",
    )
    parser.add_argument(
        "--skip-relationship",
        action="store_true",
        help="Skip building relationship_matrix.json.",
    )
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = build_parser()
    args = parser.parse_args(argv)

    mortal_dir = Path(args.mortal_data_dir)
    if not mortal_dir.is_dir():
        parser.error(f"Mortal_Data directory not found: {mortal_dir}")

    summary: dict[str, Any] = {
        "json_files": [],
        "flowchart_file": None,
        "relationship_file": None,
    }

    if not args.skip_json:
        from src.unity_assets import extract_lean_local_jsons

        extracted = extract_lean_local_jsons(
            mortal_dir,
            args.output_json_dir,
            language=args.language,
        )
        summary["json_files"] = [str(p) for p in extracted]
        print(f"Extracted {len(extracted)} '{args.language}' JSON files to {args.output_json_dir}")

    if not args.skip_flowchart:
        flowchart = extract_story_flowchart_from_mortal_data(mortal_dir)
        flowchart_path = flowchart.to_json_file(args.flowchart_file)
        summary["flowchart_file"] = str(flowchart_path)
        print(
            f"Generated StoryFlowchart at {flowchart_path} "
            f"(characters={len(flowchart.characters)}, scripts={len(flowchart.scripts)})"
        )

        if not args.skip_relationship:
            glossary_map: dict[str, str] | None = None
            if args.glossary_file:
                name_map, orig_map = load_glossary(args.glossary_file)
                glossary_map = {**orig_map, **name_map}
            matrix = build_matrix_from_flowchart(flowchart, glossary_name_map=glossary_map)
            matrix_path = matrix.to_json_file(args.relationship_file)
            summary["relationship_file"] = str(matrix_path)
            print(
                f"Generated RelationshipMatrix at {matrix_path} "
                f"(pairs={len(matrix.pairs)})"
            )

    return summary


def main_cli(argv: list[str] | None = None) -> None:
    main(argv)


if __name__ == "__main__":
    main_cli()
