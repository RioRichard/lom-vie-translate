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
from src.config import INPUT_DIR, OUTPUT_DIR, MAX_CONCURRENT_FILE_OPENS
from src.logger import logger
from src.glossary import load_glossary, load_old_translations

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
async def file_consumer(queue, all_data_dict, translation_pairs, mode, translated_dir, json_output_dir, original_to_translated, old_translations, progress_bar):
    while True:
        original_file_path, original_content, translated_file_path, translated_content = await queue.get()
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
                original_to_translated=original_to_translated,
                old_translations=old_translations
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
    parser.add_argument(
        '--mode',
        choices=['translate', 'improve'],
        required=True,
        help='Operation mode: translate (fresh translation) or improve (improve existing translations)'
    )

    # Directory configuration
    parser.add_argument(
        '--input-dir',
        default=INPUT_DIR,
        help='Input directory containing JSON files'
    )

    parser.add_argument(
        '--output-dir',
        default=OUTPUT_DIR,
        help='Base output directory for all files'
    )

    parser.add_argument(
        '--translated-dir',
        help='Directory containing existing raw translations (required for improve mode)'
    )

    parser.add_argument(
        '--json-output-dir',
        help='Directory for individual translated JSON files (defaults to output-dir/json)'
    )

    parser.add_argument(
        '--details-output-dir',
        help='Directory for translation details JSON (defaults to output-dir/details)'
    )

    parser.add_argument(
        '--pairs-output-dir',
        help='Directory for translation pairs text file (defaults to output-dir/pairs)'
    )

    parser.add_argument(
        '--glossary-file',
        help='Path to a specific glossary file (.json or .txt) to use (optional)'
    )

    args = parser.parse_args()

    # Validate arguments and directories
    if args.mode == 'improve' and not args.translated_dir:
        parser.error("--translated-dir is required when using --mode=improve")
    # Allow translated_dir in translate mode for checking old translations
    if args.mode == 'translate' and args.translated_dir:
        async_tqdm.write(f"Using existing translations directory for lookup: {args.translated_dir}")

    json_dir = Path(args.input_dir)
    if not json_dir.exists():
        parser.error(f"Input directory does not exist: {json_dir}")
    if not any(json_dir.glob("*.json")):
        parser.error(f"No JSON files found in input directory: {json_dir}")

    translated_dir = None
    if args.translated_dir:
        translated_dir = Path(args.translated_dir)
        if not translated_dir.exists():
            parser.error(f"Translated directory does not exist: {translated_dir}")

    # Setup output directories
    base_output_dir = Path(args.output_dir)
    base_output_dir.mkdir(parents=True, exist_ok=True)

    # Setup specific output directories with defaults
    json_output_dir = Path(args.json_output_dir) if args.json_output_dir else base_output_dir / "json"
    details_output_dir = Path(args.details_output_dir) if args.details_output_dir else base_output_dir / "details"
    pairs_output_dir = Path(args.pairs_output_dir) if args.pairs_output_dir else base_output_dir / "pairs"

    # Create all output directories
    for dir_path in [json_output_dir, details_output_dir, pairs_output_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)

    all_data_dict = []

    async_tqdm.write(f"Starting translation in {args.mode} mode")
    async_tqdm.write(f"Input directory: {json_dir}")
    async_tqdm.write(f"JSON output directory: {json_output_dir}")
    async_tqdm.write(f"Details output directory: {details_output_dir}")
    async_tqdm.write(f"Pairs output directory: {pairs_output_dir}")
    if translated_dir:
        async_tqdm.write(f"Existing translations directory: {translated_dir}")

    run_start = time.time()

    # Dictionary to store all unique translation pairs for txt output
    translation_pairs = OrderedDict()

    # Load glossary once
    _, original_to_translated = load_glossary(args.glossary_file)

    # Load old translations if translated_dir is provided
    old_translations = {}
    if args.translated_dir:
        logger.info(f"Loading old translations from {args.translated_dir}...")
        old_translations = load_old_translations(args.input_dir, args.translated_dir)
        if old_translations:
            logger.info(f"Loaded {len(old_translations)} old translation pairs.")

    file_paths = list(json_dir.glob("*.json"))
    total_files = len(file_paths)
    async_tqdm.write(f"Total files to process: {total_files}")

    queue = asyncio.Queue()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FILE_OPENS)

    with async_tqdm(total=total_files, desc="Initializing...", mininterval=0, miniters=1) as progress_bar:
        producer_task = asyncio.create_task(file_producer(file_paths, queue, semaphore, progress_bar, args.mode, translated_dir))
        consumer_task = asyncio.create_task(file_consumer(
            queue,
            all_data_dict,
            translation_pairs,
            args.mode,
            translated_dir,
            json_output_dir,
            original_to_translated,
            old_translations,
            progress_bar
        ))

        await producer_task
        await queue.join()
        consumer_task.cancel()
        await asyncio.gather(consumer_task, return_exceptions=True)

    # Save consolidated JSON with full translation details
    details_file = details_output_dir / "translation_details.json"
    async with aiofiles.open(details_file, "w", encoding="utf-8") as f:
        await f.write(json.dumps(all_data_dict, ensure_ascii=False, indent=2))

    # Save translation pairs to txt file
    pairs_file = pairs_output_dir / "translation_pairs.txt"
    async with aiofiles.open(pairs_file, "w", encoding="utf-8") as f:
        await f.write("\n".join([f"{original}={translated}" for original, translated in translation_pairs.items()]))

    run_end = time.time()
    files_processed = len(file_paths)
    total_translations = len(all_data_dict)

    logger.run_summary(
        files_processed=files_processed,
        total_translations=total_translations,
        total_time=run_end - run_start
    )

    async_tqdm.write("Results saved to:")
    async_tqdm.write(f"  - Individual JSON files: {json_output_dir}")
    async_tqdm.write(f"  - Translation details: {details_file}")
    async_tqdm.write(f"  - Translation pairs: {pairs_file}")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
