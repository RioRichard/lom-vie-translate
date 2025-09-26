from pathlib import Path
import json
import argparse
import time
from src.file_processor import process_json_file
from src.config import INPUT_DIR, OUTPUT_DIR
from src.logger import logger

def main():
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
        '--translated-dir',
        help='Directory containing existing translations (required for improve mode)'
    )

    args = parser.parse_args()

    # Validate arguments and directories
    if args.mode == 'improve' and not args.translated_dir:
        parser.error("--translated-dir is required when using --mode=improve")

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

    all_data_dict = {}

    logger.info(f"Starting translation in {args.mode} mode")
    logger.info(f"Input directory: {json_dir}")
    logger.info(f"JSON output directory: {json_output_dir}")
    logger.info(f"Details output directory: {details_output_dir}")
    logger.info(f"Pairs output directory: {pairs_output_dir}")
    if translated_dir:
        logger.info(f"Existing translations directory: {translated_dir}")

    run_start = time.time()

    # List to store all translation pairs for txt output
    translation_pairs = []

    # Process all files
    for file_path in json_dir.glob("*.json"):
        process_json_file(
            file_path=file_path,
            all_data_dict=all_data_dict,
            translation_pairs=translation_pairs,
            mode=args.mode,
            translated_dir=translated_dir,
            json_output_dir=json_output_dir
        )

    # Save consolidated JSON with full translation details
    details_file = details_output_dir / "translation_details.json"
    with open(details_file, "w", encoding="utf-8") as f:
        json.dump(all_data_dict, f, ensure_ascii=False, indent=2)

    # Save translation pairs to txt file
    pairs_file = pairs_output_dir / "translation_pairs.txt"
    with open(pairs_file, "w", encoding="utf-8") as f:
        f.write("\n".join(translation_pairs))

    run_end = time.time()
    files_processed = len(list(json_dir.glob("*.json")))
    total_translations = len(all_data_dict)

    logger.run_summary(
        files_processed=files_processed,
        total_translations=total_translations,
        total_time=run_end - run_start
    )

    logger.info("Results saved to:")
    logger.info(f"  - Individual JSON files: {json_output_dir}")
    logger.info(f"  - Translation details: {details_file}")
    logger.info(f"  - Translation pairs: {pairs_file}")

if __name__ == "__main__":
    main()
