import json
import time
from pathlib import Path
import aiofiles
import asyncio
from tqdm.asyncio import tqdm as async_tqdm
from src.translator import translate_text
from src.prompt_preparer import prepare_prompt_data
from src.config import MAX_CONCURRENT, OUTPUT_DIR
from src.utils import SPECIAL_CHARS
from src.logger import logger


async def process_entry(entry, thread_idx=None, mode='translate', prompt_data=None, glossary_text=None, translation_cache=None, run_stats=None):
    """Process a single entry for translation or improvement

    Args:
        entry: The entry to process (dict with 'Name' and 'Text' keys)
        thread_idx: Thread index for concurrent processing
        mode: 'translate' for fresh translation or 'improve' for improving existing translations
        prompt_data: Pre-prepared prompt data containing context and templates, including raw_translation for improve mode
        glossary_text (dict, optional): Glossary map from original text to translated text.
        translation_cache (dict, optional): Cache of previously translated text.
        run_stats (dict, optional): Dictionary to store run statistics.

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
        if run_stats:
            run_stats["empty"] += 1
        return entry

    # Skip special characters
    if original_text in SPECIAL_CHARS:
        logger.debug(f"Skipping special character: {original_text}")
        if run_stats:
            run_stats["special_chars"] += 1
        return {
            'Name': name,
            'Text': original_text
        }

    # 1. Check for old translation (cache) first for performance
    if translation_cache:
        cached_translation = translation_cache.get(original_text)
        if cached_translation:
            logger.info(f"Reusing old translation for original text: '{original_text}' -> '{cached_translation}'")
            if run_stats:
                run_stats["from_cache"] += 1
            return {
                'Name': name,
                'Text': cached_translation
            }

    # 2. Check for existing translation in glossary (can also act as a cache)
    if glossary_text:
        existing_translation = glossary_text.get(original_text)
        if existing_translation:
            logger.info(f"Reusing glossary for original text: '{original_text}' -> '{existing_translation}'")
            if run_stats:
                run_stats["from_glossary"] += 1
            return {
                'Name': name,
                'Text': existing_translation
            }

    # Start translation
    line_start = time.time()

    translated_text = await translate_text(
        text=original_text,
        thread_idx=thread_idx,
        name=name,
        prompt_data=prompt_data,
        original_to_translated=glossary_text
    )

    # await asyncio.sleep(RATE_LIMIT_DELAY)
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

async def process_json_file(file_path, file_content, translated_file_content, all_data_dict, translation_pairs, mode='translate', translated_dir=None, json_output_dir=None, glossary_text=None, translation_cache=None, run_stats=None):
    """Process a JSON file for translation or improvement

    Args:
        file_path: Path to the input JSON file
        file_content: Content of the input JSON file
        translated_file_content: Content of the raw translated JSON file (for improve mode)
        all_data_dict: Dictionary to store detailed translation data including original and raw translations
        translation_pairs: List to store original=translation pairs for txt output
        mode: 'translate' for fresh translation or 'improve' for improving existing translations
        translated_dir: Directory containing existing translations (required for improve mode)
        json_output_dir: Directory for individual translated JSON files (defaults to OUTPUT_DIR/json)
        glossary_text (dict, optional): Glossary map from original text to translated text.
        translation_cache (dict, optional): Cached translations from previous runs.
        run_stats (dict, optional): Dictionary to store run statistics.

    Raises:
        ValueError: If mode is invalid or if translated_dir is missing in improve mode
    """


    if mode == 'improve' and not translated_dir:
        raise ValueError("translated_dir is required when using improve mode")

    file_name = file_path.name
    json_output_dir = Path(json_output_dir if json_output_dir else OUTPUT_DIR)
    json_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = json_output_dir / file_name

    try:
        file_start = time.time()

        data = json.loads(file_content) # Parse JSON once

        # Prepare prompts with appropriate templates and context
        prompt_data_list, old_translated_file_data = await prepare_prompt_data(
            original_file_path=file_path,
            original_data=data,
            translated_file_content=translated_file_content if mode == 'improve' else None,
            original_to_translated=glossary_text
        )
        entries_list, is_array_format = _parse_json_entries(data)
        # Process all entries concurrently
        logger.concurrent_info(len(entries_list), MAX_CONCURRENT)

        tasks = _create_translation_tasks(entries_list, prompt_data_list)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        pbar = async_tqdm(total=len(tasks), desc=f"Entries in {file_name}", leave=False, mininterval=0.1)

        async def safe_process_entry_with_delay(args):
            entry, idx, prompt = args
            async with semaphore:
                result = await process_entry(
                    entry=entry,
                    thread_idx=idx,
                    mode=mode,
                    prompt_data=prompt,
                    glossary_text=glossary_text,
                    translation_cache=translation_cache,
                    run_stats=run_stats
                )
                pbar.update(1)
                return result

        # Process all entries concurrently with tqdm progress bar
        translations = await asyncio.gather(*[safe_process_entry_with_delay(task) for task in tasks])
        pbar.close()

        if is_array_format:
            data['entries']['Array'] = translations
        else:
            data['entries'] = translations
        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))

        await _process_and_store_results(
            file_name=file_name,
            translations=translations,
            original_entries=entries_list,
            all_data_dict=all_data_dict,
            translation_pairs=translation_pairs,
            mode=mode,
            translated_file_content=translated_file_content
        )

        file_end = time.time()
        logger.info(f"Completed {file_name} - {len(translations)} translations in {file_end - file_start:.2f}s")
    except Exception as e:
        logger.error(f"Error processing {file_name}: {str(e)}")

def _parse_json_entries(data):
    entries = data.get('entries', [])
    if isinstance(entries, dict) and 'Array' in entries:
        entries_list = entries['Array']
        is_array_format = True
    else:
        entries_list = entries
        is_array_format = False
    return entries_list, is_array_format

def _create_translation_tasks(entries_list, prompt_data_list):
    if len(prompt_data_list) != len(entries_list):
        logger.warning(f"Number of prompts ({len(prompt_data_list)}) doesn't match number of entries ({len(entries_list)})")
        logger.debug(f"Entries list: {entries_list}")
        logger.debug(f"Prompt data list: {prompt_data_list}")

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
    return tasks

async def _process_and_store_results(file_name, translations, original_entries, all_data_dict, translation_pairs, mode, translated_file_content):
    raw_translation_data = None
    if translated_file_content:
        try:
            raw_translation_data = json.loads(translated_file_content)
        except json.JSONDecodeError:
            logger.error(f"Could not parse raw translated file content for {file_name}")

    for entry, original_entry in zip(translations, original_entries):
        name = entry.get('Name')
        original_text = original_entry.get('Text', '').strip()
        final_text = entry.get('Text', '').strip()

        if name and original_text and final_text:
            entry_details = {
                'Name': name,
                'Original': original_text,
                'Translated': final_text
            }

            if mode == 'improve' and raw_translation_data:
                for trans_entry in raw_translation_data.get('entries', {}).get('Array', []):
                    if trans_entry.get('Name') == name:
                        entry_details['Raw'] = trans_entry.get('Text', '').strip()
                        break

            all_data_dict.append(entry_details)

            escaped_original = original_text.replace('\r', '\\r').replace('\n', '\\n')
            escaped_final = final_text.replace('\r', '\\r').replace('\n', '\\n')
            if escaped_original not in translation_pairs:
                translation_pairs[escaped_original] = escaped_final
