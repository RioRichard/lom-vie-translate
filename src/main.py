import argparse
import asyncio
import json
import re
import time
from collections import OrderedDict
from pathlib import Path

import aiofiles
from tqdm.asyncio import tqdm as async_tqdm

from src.config import VALID_MODES, load_config
from src.file_processor import process_json_file
from src.glossary import (
    autocheck_and_sync_glossary,
    load_glossary_async,
    load_old_translations_async,
)
from src.logger import logger
from src.translator import TranslationEngine
from src.utils import postprocess_text


async def file_producer(
    file_paths,
    queue,
    semaphore,
    progress_bar,
    mode,
    translated_dir,
):
    translated_files_map: dict[str, Path] = {}
    if mode == "improve" and translated_dir:
        for t_file_path in Path(translated_dir).glob("*.json"):
            translated_files_map[t_file_path.name] = t_file_path

    async def read_file_and_put_in_queue(original_file_path):
        original_file_path = Path(original_file_path)
        async with semaphore:
            if progress_bar is not None:
                progress_bar.set_description(
                    f"Queuing file: {original_file_path.name} (Queue size: {queue.qsize()})"
                )

            original_content = None
            translated_content = None
            translated_file_path = None

            async with aiofiles.open(original_file_path, encoding="utf-8") as f:
                initial_chunk = await f.read(4096)
                if re.search(r'"Language"\s*:\s*"ChineseSimplified"', initial_chunk):
                    original_content = initial_chunk + await f.read()
                elif re.search(r'"Language"\s*:\s*"([^"]+)"', initial_chunk):
                    if progress_bar is not None:
                        progress_bar.write(
                            f"Skipping file {original_file_path.name}: Not 'ChineseSimplified'."
                        )
                        progress_bar.update(1)
                    return
                else:
                    full_content = initial_chunk + await f.read()
                    try:
                        data = json.loads(full_content)
                    except json.JSONDecodeError as exc:
                        if progress_bar is not None:
                            progress_bar.write(
                                f"Skipping file {original_file_path.name}: Invalid JSON ({exc})."
                            )
                            progress_bar.update(1)
                        return
                    if not isinstance(data, dict) or data.get("Language") != "ChineseSimplified":
                        if progress_bar is not None:
                            progress_bar.write(
                                f"Skipping file {original_file_path.name}: Not 'ChineseSimplified'."
                            )
                            progress_bar.update(1)
                        return
                    original_content = full_content

                async_tqdm.write(f"Queued file: {original_file_path.name}")

            if mode == "improve":
                translated_file_path = translated_files_map.get(original_file_path.name)
                if translated_file_path:
                    async with aiofiles.open(translated_file_path, encoding="utf-8") as f:
                        translated_content = await f.read()
                        async_tqdm.write(
                            f"Queued raw translated file: {translated_file_path.name}"
                        )
                elif progress_bar is not None:
                    progress_bar.write(
                        f"Warning: No raw translated file found for {original_file_path.name} in improve mode. Processing original only."
                    )

            await queue.put(
                (
                    original_file_path,
                    original_content,
                    translated_file_path,
                    translated_content,
                )
            )

    tasks = [read_file_and_put_in_queue(file_path) for file_path in file_paths]
    await asyncio.gather(*tasks)


async def file_consumer(
    queue,
    all_data_dict,
    translation_pairs,
    engine,
    mode,
    translated_dir,
    json_output_dir,
    original_to_translated,
    translation_cache,
    progress_bar,
    run_stats,
    max_concurrent=5,
    override_provider=None,
    override_tier=None,
    override_model=None,
    flowchart=None,
    relationship_matrix=None,
    dialogue_window=4,
):
    while True:
        original_file_path, original_content, _, translated_content = await queue.get()
        try:
            if progress_bar is not None:
                progress_bar.set_description(f"Processing file: {original_file_path.name}")
            await process_json_file(
                file_path=original_file_path,
                file_content=original_content,
                translated_file_content=translated_content,
                all_data_dict=all_data_dict,
                translation_pairs=translation_pairs,
                engine=engine,
                mode=mode,
                translated_dir=translated_dir,
                json_output_dir=json_output_dir,
                glossary_text=original_to_translated,
                translation_cache=translation_cache,
                run_stats=run_stats,
                max_concurrent=max_concurrent,
                override_provider=override_provider,
                override_tier=override_tier,
                override_model=override_model,
                flowchart=flowchart,
                relationship_matrix=relationship_matrix,
                dialogue_window=dialogue_window,
            )
            if progress_bar is not None:
                progress_bar.update(1)
        finally:
            queue.task_done()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Chinese to Vietnamese translation tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--config-file",
        "-c",
        default=None,
        help="Path to TOML configuration file (defaults to LOM_CONFIG_FILE or config.toml)",
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=VALID_MODES,
        default=None,
        help="Operation mode (overrides [run].mode in config.toml)",
    )
    parser.add_argument(
        "--input-dir",
        "-id",
        default=None,
        help="Input directory (overrides [run].input_dir)",
    )
    parser.add_argument(
        "--output-dir",
        "-od",
        default=None,
        help="Base output directory (overrides [run].output_dir)",
    )
    parser.add_argument(
        "--raw-dir",
        "-rd",
        default=None,
        help='Directory with raw translations for "improve" mode',
    )
    parser.add_argument(
        "--json-output-dir",
        "-jod",
        default=None,
        help="Directory for translated JSONs (default: output-dir/json)",
    )
    parser.add_argument(
        "--details-output-dir",
        "-dod",
        default=None,
        help="Directory for translation details (default: output-dir/details)",
    )
    parser.add_argument(
        "--pairs-output-dir",
        "-pod",
        default=None,
        help="Directory for translation pairs (default: output-dir/pairs)",
    )
    parser.add_argument(
        "--glossary-file",
        "-gf",
        default=None,
        help="Path to a specific glossary file (optional)",
    )
    parser.add_argument(
        "--no-auto-glossary",
        action="store_true",
        help="Skip automatic pre-flight glossary check and sync before translate/improve runs",
    )
    parser.add_argument(
        "--old-dir",
        "-old",
        default=None,
        help="Directory with old translations for caching (optional)",
    )
    parser.add_argument(
        "--old-file",
        "-olf",
        default=None,
        help="A single file with old translations for caching (optional)",
    )
    parser.add_argument(
        "--flowchart-file",
        "-ff",
        default=None,
        help="Path to story_flowchart.json for story dialogue context (optional)",
    )
    parser.add_argument(
        "--relationship-file",
        "-rf",
        default=None,
        help="Path to relationship_matrix.json for character pronoun rules (optional)",
    )
    parser.add_argument(
        "--dialogue-window",
        "-dw",
        type=int,
        default=None,
        help="Number of preceding dialogue turns in context window (overrides [run].dialogue_window)",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Override primary provider for the selected task",
    )
    parser.add_argument(
        "--tier",
        default=None,
        help="Override primary tier for the selected task",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override primary model for the selected task",
    )
    return parser


async def main_async(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config_file)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))

    run_cfg = config.run
    mode = args.mode if args.mode is not None else run_cfg.mode
    input_dir = args.input_dir if args.input_dir is not None else run_cfg.input_dir
    output_dir = args.output_dir if args.output_dir is not None else run_cfg.output_dir
    raw_dir_arg = args.raw_dir if args.raw_dir is not None else run_cfg.raw_dir
    json_output_dir_arg = (
        args.json_output_dir if args.json_output_dir is not None else run_cfg.json_output_dir
    )
    details_output_dir_arg = (
        args.details_output_dir
        if args.details_output_dir is not None
        else run_cfg.details_output_dir
    )
    pairs_output_dir_arg = (
        args.pairs_output_dir if args.pairs_output_dir is not None else run_cfg.pairs_output_dir
    )
    glossary_file = (
        args.glossary_file if args.glossary_file is not None else run_cfg.glossary_file
    )
    old_dir = args.old_dir if args.old_dir is not None else run_cfg.old_dir
    old_file = args.old_file if args.old_file is not None else run_cfg.old_file
    flowchart_file_arg = (
        args.flowchart_file if args.flowchart_file is not None else run_cfg.flowchart_file
    )
    relationship_file_arg = (
        args.relationship_file
        if args.relationship_file is not None
        else run_cfg.relationship_file
    )
    dialogue_window = (
        args.dialogue_window if args.dialogue_window is not None else run_cfg.dialogue_window
    )

    # --- Argument & Route Validation ---
    if not mode or mode not in VALID_MODES:
        parser.error("--mode is required. Please specify it via command-line or config.toml.")
    if mode == "improve" and not raw_dir_arg:
        parser.error("--raw-dir is required for --mode=improve")
    if old_dir and old_file:
        parser.error("Provide either --old-dir or --old-file for caching, not both.")
    if dialogue_window < 0:
        parser.error("--dialogue-window must be >= 0.")
    if args.flowchart_file is not None and not Path(args.flowchart_file).is_file():
        parser.error(f"Flowchart file not found: {args.flowchart_file}")
    if args.relationship_file is not None and not Path(args.relationship_file).is_file():
        parser.error(f"Relationship matrix file not found: {args.relationship_file}")

    json_dir = Path(input_dir)
    if not json_dir.is_dir() or not any(json_dir.glob("*.json")):
        parser.error(f"Input directory not found or contains no JSON files: {json_dir}")

    raw_dir = Path(raw_dir_arg) if (raw_dir_arg and mode != "glossary") else None
    if raw_dir and not raw_dir.is_dir():
        parser.error(f"Raw translations directory not found: {raw_dir}")

    route_task = (
        ("improve_glossary" if "improve_glossary" in config.tasks else "translate")
        if mode == "glossary"
        else mode
    )
    try:
        routes, _ = config.resolve_task_routes(
            route_task,
            provider=args.provider,
            tier=args.tier,
            model=args.model,
        )
    except ValueError as exc:
        parser.error(f"Invalid route configuration for task '{route_task}': {exc}")

    if not routes:
        parser.error(f"No routes configured for task '{route_task}'.")

    auto_sync_active = mode == "glossary" or (
        run_cfg.auto_sync_glossary and not args.no_auto_glossary
    )
    glossary_task = (
        "improve_glossary"
        if "improve_glossary" in config.tasks
        else ("translate" if "translate" in config.tasks else mode)
    )
    glossary_max_concurrent = routes[0].max_concurrent
    if auto_sync_active:
        if glossary_task == route_task:
            glossary_routes = routes
        else:
            try:
                glossary_routes, _ = config.resolve_task_routes(
                    glossary_task,
                    provider=args.provider,
                    tier=args.tier,
                    model=args.model,
                )
            except ValueError:
                glossary_task = route_task
                glossary_routes = routes
        if glossary_routes:
            glossary_max_concurrent = glossary_routes[0].max_concurrent

    # Enable file logging only after CLI parsing and validation succeed
    logger.enable_file_logging()

    # --- Setup Output Directories (skipped in glossary-only mode) ---
    base_output_dir = Path(output_dir)
    json_output_dir = Path(json_output_dir_arg or base_output_dir / "json")
    details_output_dir = Path(details_output_dir_arg or base_output_dir / "details")
    pairs_output_dir = Path(pairs_output_dir_arg or base_output_dir / "pairs")
    if mode != "glossary":
        for dir_path in [json_output_dir, details_output_dir, pairs_output_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

    # --- Logging ---
    if mode == "glossary":
        logger.info("Starting glossary check and sync in 'glossary' mode.")
        logger.info(
            f"Task '{route_task}' routes: {', '.join(route.route_label for route in routes)}"
        )
        logger.info(f"Input directory: {json_dir}")
    else:
        logger.info(f"Starting translation in '{mode}' mode.")
        logger.info(
            f"Task '{route_task}' routes: {', '.join(route.route_label for route in routes)}"
        )
        logger.info(f"Input directory: {json_dir}")
        logger.info(f"Output directories: {base_output_dir}/(json, details, pairs)")
        if raw_dir:
            logger.info(f"Improve mode raw translations directory: {raw_dir}")
    if glossary_file:
        logger.info(f"Using glossary file: {glossary_file}")
    else:
        logger.info(f"Using glossary directory: {run_cfg.glossary_dir}")
    if mode != "glossary":
        if old_dir:
            logger.info(f"Using old translations cache directory: {old_dir}")
        if old_file:
            logger.info(f"Using old translations cache file: {old_file}")

    flowchart = None
    if flowchart_file_arg:
        flowchart_path = Path(flowchart_file_arg)
        if flowchart_path.is_file():
            try:
                from src.story_flowchart import StoryFlowchart

                flowchart = StoryFlowchart.from_json_file(flowchart_path)
                logger.info(
                    f"Loaded story flowchart ({len(getattr(flowchart, 'scripts', {}))} scripts, "
                    f"{len(getattr(flowchart, 'characters', {}))} characters) from: {flowchart_path}"
                )
            except Exception as exc:
                if args.flowchart_file is not None:
                    parser.error(f"Failed to load flowchart file '{flowchart_path}': {exc}")
                logger.warning(
                    f"Failed to load configured flowchart file '{flowchart_path}': {exc}. "
                    "Proceeding without story flowchart."
                )
        else:
            logger.warning(
                f"Configured flowchart file not found: {flowchart_path}. "
                "Proceeding without story flowchart."
            )

    relationship_matrix = None
    if relationship_file_arg:
        relationship_path = Path(relationship_file_arg)
        if relationship_path.is_file():
            try:
                from src.relationship_matrix import RelationshipMatrix

                relationship_matrix = RelationshipMatrix.from_json_file(relationship_path)
                logger.info(
                    f"Loaded relationship matrix ({len(getattr(relationship_matrix, 'pairs', {}))} pairs) "
                    f"from: {relationship_path}"
                )
            except Exception as exc:
                if args.relationship_file is not None:
                    parser.error(
                        f"Failed to load relationship matrix file '{relationship_path}': {exc}"
                    )
                logger.warning(
                    f"Failed to load configured relationship matrix file '{relationship_path}': {exc}. "
                    "Proceeding without relationship matrix."
                )
        else:
            logger.warning(
                f"Configured relationship matrix file not found: {relationship_path}. "
                "Proceeding without relationship matrix."
            )

    run_start = time.time()

    engine = TranslationEngine(config)
    glossary_text: dict[str, str] = {}
    translation_cache: dict[str, str] = {}

    if auto_sync_active:
        logger.info(
            f"Running pre-flight glossary check & sync (task '{glossary_task}', "
            f"max_concurrent={glossary_max_concurrent})..."
        )
        _, synced_orig_to_translated, sync_stats = await autocheck_and_sync_glossary(
            input_dir=json_dir,
            glossary_file_path=glossary_file,
            glossary_dir=run_cfg.glossary_dir,
            engine=engine,
            flowchart=flowchart,
            flowchart_file=flowchart_file_arg,
            relationship_matrix=relationship_matrix,
            relationship_file=relationship_file_arg,
            task_name=glossary_task,
            override_provider=args.provider,
            override_tier=args.tier,
            override_model=args.model,
            max_concurrent=glossary_max_concurrent,
        )
        glossary_text = synced_orig_to_translated
        logger.info(
            "Glossary sync summary: "
            f"candidates={sync_stats['total_candidates']}, "
            f"in_sync={sync_stats['in_sync']}, "
            f"reused={sync_stats['reused']}, "
            f"outdated_updated={sync_stats['outdated_updated']}, "
            f"new_translated={sync_stats['new_translated']}, "
            f"failed={sync_stats['failed']}, "
            f"flowchart_updated={sync_stats['flowchart_updated']}, "
            f"matrix_updated={sync_stats['matrix_updated']}"
        )

        if mode == "glossary":
            run_end = time.time()
            target_glossary = glossary_file or str(Path(run_cfg.glossary_dir) / "glossary.json")
            logger.info(
                f"Glossary mode completed in {run_end - run_start:.2f}s. "
                f"Active glossary terms: {len(glossary_text)} (target: {target_glossary})."
            )
            return

    # --- Asynchronous Data Loading ---
    data_tasks = []
    if not auto_sync_active:
        data_tasks.append(
            ("glossary", load_glossary_async(glossary_file, glossary_dir=run_cfg.glossary_dir))
        )
    if old_dir:
        data_tasks.append(("old_dir", load_old_translations_async(input_dir, old_dir)))
    elif old_file:
        data_tasks.append(
            ("old_file", load_glossary_async(old_file, glossary_dir=run_cfg.glossary_dir))
        )

    if data_tasks:
        results = await asyncio.gather(*[coro for _, coro in data_tasks])
        for (key, _), result in zip(data_tasks, results, strict=True):
            if key == "glossary":
                _, glossary_text = result
            elif key == "old_file":
                _, translation_cache = result
            elif key == "old_dir":
                translation_cache = result

    if not auto_sync_active and glossary_text:
        logger.info(f"Loaded {len(glossary_text)} glossary entries.")
    if translation_cache:
        logger.info(f"Loaded {len(translation_cache)} old translation pairs for cache.")

    # --- File Processing Pipeline ---
    all_data_dict = []
    translation_pairs: OrderedDict[str, str] = OrderedDict()
    run_stats = {
        "from_cache": 0,
        "from_glossary": 0,
        "special_chars": 0,
        "empty": 0,
        "from_pairs": 0,
        "failed": 0,
    }
    file_paths = sorted(json_dir.glob("*.json"))
    total_files = len(file_paths)
    logger.info(f"Total files to process: {total_files}")

    queue: asyncio.Queue = asyncio.Queue()
    semaphore = asyncio.Semaphore(run_cfg.max_concurrent_file_opens)

    with async_tqdm(
        total=total_files, desc="Initializing...", mininterval=0, miniters=1
    ) as progress_bar:
        producer_task = asyncio.create_task(
            file_producer(file_paths, queue, semaphore, progress_bar, mode, raw_dir)
        )
        consumer_task = asyncio.create_task(
            file_consumer(
                queue=queue,
                all_data_dict=all_data_dict,
                translation_pairs=translation_pairs,
                engine=engine,
                mode=mode,
                translated_dir=raw_dir,
                json_output_dir=json_output_dir,
                original_to_translated=glossary_text,
                translation_cache=translation_cache,
                progress_bar=progress_bar,
                run_stats=run_stats,
                max_concurrent=routes[0].max_concurrent,
                override_provider=args.provider,
                override_tier=args.tier,
                override_model=args.model,
                flowchart=flowchart,
                relationship_matrix=relationship_matrix,
                dialogue_window=dialogue_window,
            )
        )

        await producer_task
        await queue.join()
        consumer_task.cancel()
        await asyncio.gather(consumer_task, return_exceptions=True)

    # --- Save Results ---
    details_file = details_output_dir / "translation_details.json"
    async with aiofiles.open(details_file, "w", encoding="utf-8") as f:
        await f.write(json.dumps(all_data_dict, ensure_ascii=False, indent=2))

    pairs_file = pairs_output_dir / "translation_pairs.txt"
    async with aiofiles.open(pairs_file, "w", encoding="utf-8") as f:
        await f.write(
            "\n".join(
                f"{postprocess_text(original, for_json=False)}={postprocess_text(translated, for_json=False)}"
                for original, translated in translation_pairs.items()
            )
        )

    # --- Final Summary ---
    run_end = time.time()
    logger.run_summary(
        files_processed=len(file_paths),
        total_translations=len(all_data_dict),
        total_time=run_end - run_start,
        from_cache=run_stats["from_cache"],
        from_reuse_translation=run_stats["from_pairs"],
        from_glossary=run_stats["from_glossary"],
        empty_lines=run_stats["empty"],
        special_chars=run_stats["special_chars"],
        failed=run_stats["failed"],
    )
    logger.info("Results saved to:")
    logger.info(f"  - Individual JSON files: {json_output_dir}")
    logger.info(f"  - Translation details: {details_file}")
    logger.info(f"  - Translation pairs: {pairs_file}")


def main(argv: list[str] | None = None) -> None:
    asyncio.run(main_async(argv))


if __name__ == "__main__":
    main()
