import json
import time
from pathlib import Path
import concurrent.futures
from src.translator import translate_text
from src.prompt_preparer import prepare_prompt_data
from src.config import RATE_LIMIT_DELAY, MAX_CONCURRENT, INPUT_DIR, OUTPUT_DIR
from src.logger import logger

def process_entry(entry, thread_idx=None, mode='translate', prompt_data=None):
    """Process a single entry for translation or improvement

    Args:
        entry: The entry to process (dict with 'Name' and 'Text' keys)
        thread_idx: Thread index for concurrent processing
        mode: 'translate' for fresh translation or 'improve' for improving existing translations
        prompt_data: Pre-prepared prompt data containing context and templates, including raw_translation for improve mode

    Returns:
        dict: The processed entry with translated text
    """
    # Ensure we have the required fields
    if 'Name' not in entry or 'Text' not in entry:
        logger.warning(f"Entry missing required fields: {entry}")
        return entry

    name = entry['Name']
    original_text = entry['Text'].strip()

    # Skip empty text
    if not original_text:
        logger.debug(f"Skipping empty text for entry: {name}")
        return entry

    # Start translation
    line_start = time.time()

    translated_text = translate_text(
        text=original_text,
        thread_idx=thread_idx,
        name=name,
        prompt_data=prompt_data
    )

    time.sleep(RATE_LIMIT_DELAY)
    line_end = time.time()

    # Log the translation with raw translation if available in improve mode
    raw_translation = prompt_data.get('raw_translation') if prompt_data else None

    logger.translation_detail(
        name=name,
        original=original_text,
        translated=translated_text,
        duration=line_end - line_start,
        raw_translation=raw_translation,
        mode=mode
    )

    # Return entry with same structure but translated text
    return {
        'Name': name,
        'Text': translated_text
    }

def process_json_file(file_path, all_data_dict, translation_pairs, mode='translate', translated_dir=None, json_output_dir=None):
    """Process a JSON file for translation or improvement

    Args:
        file_path: Path to the input JSON file
        all_data_dict: Dictionary to store detailed translation data including original and raw translations
        translation_pairs: List to store original=translation pairs for txt output
        mode: 'translate' for fresh translation or 'improve' for improving existing translations
        translated_dir: Directory containing existing translations (required for improve mode)
        json_output_dir: Directory for individual translated JSON files (defaults to OUTPUT_DIR/json)

    Raises:
        ValueError: If mode is invalid or if translated_dir is missing in improve mode
    """
    from src.config import VALID_MODES

    if mode not in VALID_MODES:
        raise ValueError(f"Invalid mode: {mode}. Must be one of {VALID_MODES}")

    if mode == 'improve' and not translated_dir:
        raise ValueError("translated_dir is required when using improve mode")

    file_name = file_path.name
    json_output_dir = Path(json_output_dir if json_output_dir else OUTPUT_DIR)
    json_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = json_output_dir / file_name

    logger.file_start(file_name)

    # Prepare prompts with appropriate templates and context
    prompt_data_list = prepare_prompt_data(
        original_file_path=file_path,
        translated_dir=translated_dir if mode == 'improve' else None
    )
    try:
        file_start = time.time()
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        language = data.get('Language')
        if language != 'ChineseSimplified':
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Skipped non-ChineseSimplified file: {file_name} (Language: {language})")
            return
        entries = data.get('entries', [])
        if isinstance(entries, dict) and 'Array' in entries:
            entries_list = entries['Array']
            is_array_format = True
        else:
            entries_list = entries
            is_array_format = False
        # Process all entries concurrently
        logger.concurrent_info(len(entries_list), MAX_CONCURRENT)
        file_line_start = time.time()

        def safe_process_entry_with_delay(args):
            entry, idx, prompt = args
            return process_entry(
                entry=entry,
                thread_idx=idx,
                mode=mode,
                prompt_data=prompt
            )

        # Create list of tasks with their corresponding prompts
        if len(prompt_data_list) != len(entries_list):
            logger.warning(f"Number of prompts ({len(prompt_data_list)}) doesn't match number of entries ({len(entries_list)})")

        tasks = []
        for idx, entry in enumerate(entries_list):
            prompt = prompt_data_list[idx] if idx < len(prompt_data_list) else {
                'name': entry.get('key', '') or entry.get('Name', ''),
                'original_text': entry.get('value', '') or entry.get('Text', '').strip(),
                'glossary_matches': [],
                'raw_translation': None,
                'prompt': None  # Will use default prompt in translator
            }
            tasks.append((entry, idx, prompt))

        # Process all entries concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
            translations = list(executor.map(safe_process_entry_with_delay, tasks))
        if is_array_format:
            data['entries']['Array'] = translations
        else:
            data['entries'] = translations
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # Store translation data
        for entry, original_entry in zip(translations, entries_list):
            name = entry.get('Name')
            original_text = original_entry.get('Text', '').strip()
            final_text = entry.get('Text', '').strip()

            if name and original_text and final_text:
                # Store in all_data_dict with full details
                all_data_dict[name] = {
                    'original': original_text,
                    'final': final_text
                }

                if mode == 'improve' and translated_dir:
                    # Find raw translation if in improve mode
                    raw_translation = None
                    trans_path = Path(translated_dir) / file_name
                    if trans_path.exists():
                        with open(trans_path, 'r', encoding='utf-8') as f:
                            trans_data = json.load(f)
                            trans_entries = trans_data.get('entries', {}).get('Array', [])
                            for trans_entry in trans_entries:
                                if trans_entry.get('Name') == name:
                                    raw_translation = trans_entry.get('Text', '').strip()
                                    break
                    if raw_translation:
                        all_data_dict[name]['raw'] = raw_translation

                # Store as original=translation pair for txt output, escaping newlines
                escaped_original = original_text.replace('\r', '\\r').replace('\n', '\\n')
                escaped_final = final_text.replace('\r', '\\r').replace('\n', '\\n')
                translation_pairs.append(f"{escaped_original}={escaped_final}")
        file_end = time.time()
        logger.file_end(file_name, len(translations), file_end - file_start)
    except Exception as e:
        logger.error(f"Error processing {file_name}: {str(e)}", exc_info=True)
