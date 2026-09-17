"""Main command-line interface."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any


def create_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Legend of Mortal: Chinese → Vietnamese translation pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("-m", "--mode", choices=["translate", "improve"], required=True, help="Mode")
    p.add_argument("-c", "--config", default="config.json", help="Path to config.json")
    p.add_argument("-id", "-i", "--input-dir", help="Input directory containing game JSON files")  # DEF-16 FIX
    p.add_argument("-od", "--output-dir", help="Base output directory")
    p.add_argument("-rd", "--raw-dir", help="Raw translations directory (required for improve mode)")
    p.add_argument("-gf", "--glossary-file", help="Specific glossary file (.json or .txt)")
    p.add_argument("-old", "--old-dir", help="Old translations directory for caching")
    p.add_argument("-olf", "--old-file", help="Old translations single file for caching")
    return p


async def main_async() -> None:
    from lom_translate import config as cfg
    from lom_translate.client import LLMClientPool
    from lom_translate.glossary import Glossary, load_old_translations
    from lom_translate.logger import logger
    from lom_translate.pipeline import run_pipeline

    args = create_parser().parse_args()

    # Load configuration
    app_config = cfg.load(args.config)
    logger.initialize()
    s = app_config.settings

    # Initialize client pool from task assignments
    pool = LLMClientPool.from_task(app_config, args.mode)

    # Load glossary
    glossary = Glossary()
    await glossary.load(path=args.glossary_file, glossary_dir=s.glossary_dir)

    # Initialize caches
    caches: dict[str, Any] = {
        "from_glossary": glossary.original_to_translated,
        "from_pairs": {},
        "from_cache": {},
    }

    input_dir = Path(args.input_dir or s.input_dir)
    if args.old_dir:
        caches["from_cache"] = await load_old_translations(input_dir, args.old_dir)
        logger.info(f"Loaded {len(caches['from_cache'])} old translations from {args.old_dir}")

    output_dir = Path(args.output_dir or s.output_dir) / "json"
    raw_dir = Path(args.raw_dir) if args.raw_dir else None

    if args.mode == "improve" and not raw_dir:
        logger.critical("--raw-dir / -rd is required when using improve mode.")
        return

    stats = await run_pipeline(
        input_dir=input_dir,
        output_dir=output_dir,
        client_pool=pool,
        glossary=glossary,
        mode=args.mode,
        raw_dir=raw_dir,
        caches=caches,
    )

    total_entries = stats.get("total_entries", 0)
    logger.run_summary(
        files_processed=len(list(input_dir.glob("*.json"))),
        total_translations=total_entries,
        total_time=stats.get("total_time", 0.0),
        from_cache=stats.get("from_cache", 0),
        from_glossary=stats.get("from_glossary", 0),
        from_pairs=len(caches.get("from_pairs", {})),
        empty_lines=stats.get("empty", 0),
        special_chars=stats.get("special_chars", 0),
        failed_files=stats.get("failed_files", []),
        token_warnings=stats.get("token_warnings", 0),
    )


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
