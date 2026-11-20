from __future__ import annotations

import argparse
from pathlib import Path

from src.story_flowchart import StoryFlowchart, extract_story_flowchart_from_mortal_data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build StoryFlowchart JSON from Legend of Mortal game data (Mortal_Data).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-md",
        "--mortal-data-dir",
        required=True,
        help="Path to the Legend of Mortal Mortal_Data directory.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="Resource/story_flowchart.json",
        help="Output path for the generated story_flowchart.json file.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write minified JSON without indentation.",
    )
    return parser


def main(argv: list[str] | None = None) -> StoryFlowchart:
    parser = build_parser()
    args = parser.parse_args(argv)

    mortal_dir = Path(args.mortal_data_dir)
    if not mortal_dir.is_dir():
        parser.error(f"Mortal_Data directory not found: {mortal_dir}")

    flowchart = extract_story_flowchart_from_mortal_data(mortal_dir)
    indent = None if args.compact else 2
    out_path = flowchart.to_json_file(args.output, indent=indent)

    total_lines = sum(len(script.lines) for script in flowchart.scripts.values())
    total_deltas = sum(len(script.relationship_deltas) for script in flowchart.scripts.values())
    total_endings = sum(len(script.ending_ids) for script in flowchart.scripts.values())

    print(
        f"StoryFlowchart written to {out_path} "
        f"(characters={len(flowchart.characters)}, scripts={len(flowchart.scripts)}, "
        f"lines={total_lines}, relationship_deltas={total_deltas}, endings={total_endings})"
    )
    return flowchart


def main_cli(argv: list[str] | None = None) -> None:
    main(argv)


if __name__ == "__main__":
    main_cli()
