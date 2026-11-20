from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from src.unity_assets import build_patched_assets, install_patch, restore_backup


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser for tool.patch_game."""
    parser = argparse.ArgumentParser(
        description="Build, install, or restore Legend of Mortal Unity asset localization patches.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["build", "install", "restore"],
        default="build",
        help="Patch action: build standalone patch folder/zip, install directly, or restore .bak backups.",
    )
    parser.add_argument(
        "--mortal-data-dir",
        "-md",
        required=True,
        help="Path to the game's Mortal_Data directory.",
    )
    parser.add_argument(
        "--json-dir",
        "-jd",
        default="translated_output/json",
        help="Directory containing translated JSON files.",
    )
    parser.add_argument(
        "--output-patch-dir",
        "-opd",
        default="patch_output",
        help="Output directory for generated patch assets, scripts, and optional zip.",
    )
    parser.add_argument(
        "--patch-dir",
        "-pd",
        default=None,
        help="Existing patch directory (containing Mortal_Data/) to install in install mode.",
    )
    parser.add_argument(
        "--zip",
        action="store_true",
        help="Bundle output patch directory into lom_vietnamese_patch.zip (build mode).",
    )
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Execute the patch_game CLI workflow and return the operation summary."""
    parser = build_parser()
    args = parser.parse_args(argv)

    mortal_dir = Path(args.mortal_data_dir)
    if not mortal_dir.is_dir():
        parser.error(f"Mortal_Data directory not found: {mortal_dir}")

    if args.mode == "build":
        json_dir = Path(args.json_dir)
        if not json_dir.is_dir():
            parser.error(f"Translated JSON directory not found: {json_dir}")
        result = build_patched_assets(
            mortal_data_dir=mortal_dir,
            translated_json_dir=json_dir,
            output_patch_dir=args.output_patch_dir,
            create_zip=args.zip,
        )
        print(
            f"Built patch in {result['output_patch_dir']}: "
            f"assets={result['patched_assets']}, "
            f"objects={result['patched_objects']}, "
            f"entries_modified={result['patched_entries']}"
        )
        if result["zip_path"]:
            print(f"Created patch archive: {result['zip_path']}")
        return result

    if args.mode == "install":
        if args.patch_dir is not None:
            patch_path = Path(args.patch_dir)
            if not patch_path.is_dir():
                parser.error(f"Patch directory not found: {patch_path}")
            result = install_patch(
                mortal_data_dir=mortal_dir,
                patch_dir=patch_path,
                backup=True,
            )
        else:
            json_dir = Path(args.json_dir)
            if not json_dir.is_dir():
                parser.error(f"Translated JSON directory not found: {json_dir}")
            result = install_patch(
                mortal_data_dir=mortal_dir,
                translated_json_dir=json_dir,
                backup=True,
            )
        print(
            f"Installed patch into {result['mortal_data_dir']}: "
            f"installed={result['installed_assets']}, "
            f"backups_created={result['backups_created']}"
        )
        return result

    result = restore_backup(mortal_data_dir=mortal_dir)
    print(
        f"Restored backups in {result['mortal_data_dir']}: "
        f"restored={result['restored_assets']}"
    )
    return result


def main_cli(argv: list[str] | None = None) -> None:
    """Console script entry point for lom-patch-game."""
    main(argv)


if __name__ == "__main__":
    main_cli()
