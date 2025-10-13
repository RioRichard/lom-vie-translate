from pathlib import Path
import json
import re
import argparse
import time
import asyncio
import aiofiles
from collections import OrderedDict
from tqdm.asyncio import tqdm as async_tqdm
from src.file_processor import process_json_file
from src.config import INPUT_DIR, OUTPUT_DIR, MAX_CONCURRENT_FILE_OPENS, VALID_MODES
from src.logger import logger
from src.glossary import load_glossary_async, load_old_translations_async

async def file_producer(file_paths, queue, semaphore, progress_bar, mode, translated_dir):
    translated_files_map = {}
    if mode == 'improve' and translated_dir:
        for t_file_path in translated_dir.glob("*.json"):
            translated_files_map[t_file_path.name] = t_file_path

    async def read_file_and_put_in_queue(original_file_path):
        async with semaphore:
            progress_bar.set_description(f"Queuing file: {original_file_path.name} (Queue size: {queue.qsize()})")

            original_content = None
            translated_content = None
            translated_file_path = None

            async with aiofiles.open(original_file_path, 'r', encoding='utf-8') as f:
                initial_chunk = await f.read(4096)
                if not re.search(r'"Language":\s*"ChineseSimplified"', initial_chunk):
                    progress_bar.write(f"Skipping file {original_file_path.name}: Not 'ChineseSimplified' or language field not found in initial chunk.")
                    progress_bar.update(1)
                    return
                original_content = initial_chunk + await f.read()
                async_tqdm.write(f"Queued file: {original_file_path.name}")

            if mode == 'improve':
                translated_file_path = translated_files_map.get(original_file_path.name)
                if translated_file_path:
                    async with aiofiles.open(translated_file_path, 'r', encoding='utf-8') as f:
                        translated_content = await f.read()
                        async_tqdm.write(f"Queued raw translated file: {translated_file_path.name}")

                else:
                    progress_bar.write(f"Warning: No raw translated file found for {original_file_path.name} in improve mode. Processing original only.")

            await queue.put((original_file_path, original_content, translated_file_path, translated_content))

    tasks = [read_file_and_put_in_queue(file_path) for file_path in file_paths]
    await asyncio.gather(*tasks)
async def file_consumer(queue, all_data_dict, translation_pairs, mode, translated_dir, json_output_dir, original_to_translated, translation_cache, progress_bar, run_stats):
    while True:
        original_file_path, original_content, _, translated_content = await queue.get()
        try:
            progress_bar.set_description(f"Processing file: {original_file_path.name}")
            await process_json_file(
                file_path=original_file_path,
                file_content=original_content,
                translated_file_content=translated_content,
                all_data_dict=all_data_dict,
                translation_pairs=translation_pairs,
                mode=mode,
                translated_dir=translated_dir,
                json_output_dir=json_output_dir,
                glossary_text=original_to_translated,
                translation_cache=translation_cache,
                run_stats=run_stats
            )
            progress_bar.update(1) # Update after file is fully processed
        finally:
            queue.task_done()

async def main_async():
    parser = argparse.ArgumentParser(
        description='Chinese to Vietnamese translation tool',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Mode selection
    parser.add_argument('--mode', choices=VALID_MODES, required=True, help='Operation mode')

    # Directory configuration
    parser.add_argument('--input-dir', default=INPUT_DIR, help='Input directory')
    parser.add_argument('--output-dir', default=OUTPUT_DIR, help='Base output directory')
    parser.add_argument('--raw-dir', help='Directory with raw translations for "improve" mode')
    parser.add_argument('--json-output-dir', help='Directory for translated JSONs (default: output-dir/json)')
    parser.add_argument('--details-output-dir', help='Directory for translation details (default: output-dir/details)')
    parser.add_argument('--pairs-output-dir', help='Directory for translation pairs (default: output-dir/pairs)')

    # Glossary and Cache configuration
    parser.add_argument('--glossary-file', help='Path to a specific glossary file (optional)')
    parser.add_argument('--old-dir', help='Directory with old translations for caching (optional)')
    parser.add_argument('--old-file', help='A single file with old translations for caching (optional)')

    args = parser.parse_args()

    # --- Argument Validation ---
    if args.mode == 'improve' and not args.raw_dir:
        parser.error("--raw-dir is required for --mode=improve")
    if args.old_dir and args.old_file:
        parser.error("Provide either --old-dir or --old-file for caching, not both.")

    json_dir = Path(args.input_dir)
    if not json_dir.is_dir() or not any(json_dir.glob("*.json")):
        parser.error(f"Input directory not found or contains no JSON files: {json_dir}")

    raw_dir = Path(args.raw_dir) if args.raw_dir else None
    if raw_dir and not raw_dir.is_dir():
        parser.error(f"Raw translations directory not found: {raw_dir}")

    # --- Setup Output Directories ---
    base_output_dir = Path(args.output_dir)
    json_output_dir = Path(args.json_output_dir or base_output_dir / "json")
    details_output_dir = Path(args.details_output_dir or base_output_dir / "details")
    pairs_output_dir = Path(args.pairs_output_dir or base_output_dir / "pairs")
    for dir_path in [json_output_dir, details_output_dir, pairs_output_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)

    # --- Logging ---
    logger.info(f"Starting translation in '{args.mode}' mode.")
    logger.info(f"Input directory: {json_dir}")
    logger.info(f"Output directories: {base_output_dir}/(json, details, pairs)")
    if raw_dir:
        logger.info(f"Improve mode raw translations directory: {raw_dir}")
    if args.glossary_file:
        logger.info(f"Using glossary file: {args.glossary_file}")
    if args.old_dir:
        logger.info(f"Using old translations cache directory: {args.old_dir}")
    if args.old_file:
        logger.info(f"Using old translations cache file: {args.old_file}")

    run_start = time.time()

    # --- Asynchronous Data Loading ---
    tasks = {
        "glossary": load_glossary_async(args.glossary_file),
        "translation_cache": None
    }
    if args.old_dir:
        tasks["translation_cache"] = load_old_translations_async(args.input_dir, args.old_dir)
    elif args.old_file:
        # Assuming old-file has a glossary-like format
        tasks["translation_cache"] = load_glossary_async(args.old_file)

    results = await asyncio.gather(*[task for task in tasks.values() if task])

    # Process results
    _, glossary_text = results[0]
    translation_cache = {}
    if len(results) > 1:
        if args.old_file:
            _, translation_cache = results[1] # From load_glossary_async
        else:
            translation_cache = results[1] # From load_old_translations_async

    if glossary_text:
        logger.info(f"Loaded {len(glossary_text)} glossary entries.")
    if translation_cache:
        logger.info(f"Loaded {len(translation_cache)} old translation pairs for cache.")

    # --- File Processing Pipeline ---
    all_data_dict = []
    translation_pairs = OrderedDict()
    run_stats = {"from_cache": 0, "from_glossary": 0, "special_chars": 0, "empty": 0}
    file_paths = list(json_dir.glob("*.json"))
    total_files = len(file_paths)
    logger.info(f"Total files to process: {total_files}")

    queue = asyncio.Queue()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FILE_OPENS)

    with async_tqdm(total=total_files, desc="Initializing...", mininterval=0, miniters=1) as progress_bar:
        producer_task = asyncio.create_task(file_producer(file_paths, queue, semaphore, progress_bar, args.mode, raw_dir))
        consumer_task = asyncio.create_task(file_consumer(
            queue, all_data_dict, translation_pairs, args.mode, raw_dir,
            json_output_dir, glossary_text, translation_cache, progress_bar, run_stats
        ))

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
        await f.write("\n".join([f"{original}={translated}" for original, translated in translation_pairs.items()]))

    # --- Final Summary ---
    run_end = time.time()
    logger.run_summary(
        files_processed=len(file_paths),
        total_translations=len(all_data_dict),
        total_time=run_end - run_start,
        from_cache=run_stats["from_cache"],
        from_glossary=run_stats["from_glossary"],
        empty_lines=run_stats["empty"],
        special_chars=run_stats["special_chars"]
    )
    logger.info("Results saved to:")
    logger.info(f"  - Individual JSON files: {json_output_dir}")
    logger.info(f"  - Translation details: {details_file}")
    logger.info(f"  - Translation pairs: {pairs_file}")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
