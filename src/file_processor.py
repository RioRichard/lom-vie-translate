import json
import time
from pathlib import Path
import aiofiles
from tqdm.asyncio import tqdm as async_tqdm
from src.translator import translate_text
from src.prompt_preparer import prepare_prompt_data
from src.config import MAX_CONCURRENT, OUTPUT_DIR



async def process_entry(entry, thread_idx=None, mode='translate', prompt_data=None, name_to_translated=None, original_to_translated=None):
    """Process a single entry for translation or improvement

    Args:
        entry: The entry to process (dict with 'Name' and 'Text' keys)
        thread_idx: Thread index for concurrent processing
        mode: 'translate' for fresh translation or 'improve' for improving existing translations
        prompt_data: Pre-prepared prompt data containing context and templates, including raw_translation for improve mode
        name_to_translated (dict, optional): Glossary map from name to translated text.
        original_to_translated (dict, optional): Glossary map from original text to translated text.

    Returns:
        dict: The processed entry with translated text
    """
    # Ensure we have the required fields
    if 'Name' not in entry or 'Text' not in entry:
        async_tqdm.write(f"[WARNING] Entry missing required fields: {entry}")
        return entry

    name = entry['Name']
    original_text = entry['Text'].strip()

    # Skip empty text
    if not original_text:
        async_tqdm.write(f"[DEBUG] Skipping empty text for entry: {name}")
        return entry

    # Check for glossary match by Original text
    if original_to_translated:
        glossary_translated_by_original = original_to_translated.get(original_text)
        if glossary_translated_by_original:
            async_tqdm.write(f"[INFO] Reusing glossary translation for original text: '{original_text}' -> '{glossary_translated_by_original}'")
            return {
                'Name': name,
                'Text': glossary_translated_by_original
            }

    # Start translation
    line_start = time.time()

    async_tqdm.write(f"[DEBUG] Type of prompt_data in process_entry: {type(prompt_data)}")
    async_tqdm.write(f"[DEBUG] Content of prompt_data in process_entry: {prompt_data}")

    translated_text = translate_text(
        text=original_text,
        thread_idx=thread_idx,
        name=name,
        prompt_data=prompt_data,
        name_to_translated=name_to_translated,
        original_to_translated=original_to_translated
    )

    # await asyncio.sleep(RATE_LIMIT_DELAY)
    line_end = time.time()

    # Log the translation with raw translation if available in improve mode
    raw_translation = prompt_data.get('raw_translation') if prompt_data else None

    action = "Translation" if mode == 'translate' else "Improvement"
    message = (
        f"{action} completed in {line_end - line_start:.2f}s\n"
        f"    Name: {name}\n"
        f"    Original: {original_text}\n"
    )

    if mode == 'improve' and raw_translation:
        message += f"    Raw Translation: {raw_translation}\n"

    message += f"    Final Output: {translated_text}"

    async_tqdm.write(message)

    # Return entry with same structure but translated text
    return {
        'Name': name,
        'Text': translated_text
    }

async def process_json_file(file_path, file_content, all_data_dict, translation_pairs, mode='translate', translated_dir=None, json_output_dir=None, name_to_translated=None, original_to_translated=None):
    """Process a JSON file for translation or improvement

    Args:
        file_path: Path to the input JSON file
        file_content: Content of the input JSON file
        all_data_dict: Dictionary to store detailed translation data including original and raw translations
        translation_pairs: List to store original=translation pairs for txt output
        mode: 'translate' for fresh translation or 'improve' for improving existing translations
        translated_dir: Directory containing existing translations (required for improve mode)
        json_output_dir: Directory for individual translated JSON files (defaults to OUTPUT_DIR/json)
        old_version_dir (Path, optional): Directory containing old version translations for reuse.
        glossary_file_path (str, optional): Path to a specific glossary file to use.

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

    try:
        file_start = time.time()
        data = json.loads(file_content)
        language = data.get('Language')
        if language != 'ChineseSimplified':
            async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            async_tqdm.write(f"Skipped non-ChineseSimplified file: {file_name} (Language: {language})") # Use tqdm.write
            return

        # Prepare prompts with appropriate templates and context
        prompt_data_list, old_translated_file_data = await prepare_prompt_data(
            original_file_path=file_path,
            original_data=data,
            translated_dir=translated_dir if mode == 'improve' else None,
            original_to_translated=original_to_translated
        )
        entries = data.get('entries', [])
        if isinstance(entries, dict) and 'Array' in entries:
            entries_list = entries['Array']
            is_array_format = True
        else:
            entries_list = entries
            is_array_format = False
        # Process all entries concurrently
        async_tqdm.write(f"[INFO] Processing {len(entries_list)} entries with {MAX_CONCURRENT} concurrent workers")

        async def safe_process_entry_with_delay(args):
            entry, idx, prompt = args
            return await process_entry(
                entry=entry,
                thread_idx=idx,
                mode=mode,
                prompt_data=prompt,
                name_to_translated=name_to_translated,
                original_to_translated=original_to_translated
            )

        # Create list of tasks with their corresponding prompts
        if len(prompt_data_list) != len(entries_list):
            async_tqdm.write(f"[WARNING] Number of prompts ({len(prompt_data_list)}) doesn't match number of entries ({len(entries_list)})")
            async_tqdm.write(f"[DEBUG] Entries list: {entries_list}")
            async_tqdm.write(f"[DEBUG] Prompt data list: {prompt_data_list}")

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

        # Process all entries sequentially with tqdm progress bar
        translations = []
        for idx, task in enumerate(async_tqdm(tasks, desc=f"Entries in {file_name}", leave=False, mininterval=0.1)):
            translations.append(await safe_process_entry_with_delay(task))

        if is_array_format:
            data['entries']['Array'] = translations
        else:
            data['entries'] = translations
        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        # Store translation data
        for entry, original_entry in zip(translations, entries_list):
            name = entry.get('Name')
            original_text = original_entry.get('Text', '').strip()
            final_text = entry.get('Text', '').strip()

            if name and original_text and final_text:
                # Create a dictionary for the current entry
                entry_details = {
                    'Name': name,
                    'Original': original_text,
                    'Translated': final_text
                }

                if mode == 'improve' and translated_dir:
                    # Find raw translation if in improve mode
                    raw_translation = None
                    trans_path = Path(translated_dir) / file_name
                    if trans_path.exists():
                        async with aiofiles.open(trans_path, 'r', encoding='utf-8') as f:
                            trans_data = json.loads(await f.read())
                            trans_entries = trans_data.get('entries', {}).get('Array', [])
                            for trans_entry in trans_entries:
                                if trans_entry.get('Name') == name:
                                    raw_translation = trans_entry.get('Text', '').strip()
                                    break
                    if raw_translation:
                        entry_details['Raw'] = raw_translation

                # Append the entry details to the all_data_dict list
                all_data_dict.append(entry_details)

                # Store as original=translation pair for txt output, escaping newlines
                escaped_original = original_text.replace('\r', '\\r').replace('\n', '\\n')
                escaped_final = final_text.replace('\r', '\\r').replace('\n', '\\n')
                if escaped_original not in translation_pairs:
                    translation_pairs[escaped_original] = escaped_final
        file_end = time.time()
        async_tqdm.write(f"[INFO] Completed {file_name} - {len(translations)} translations in {file_end - file_start:.2f}s")
    except Exception as e:
        async_tqdm.write(f"[ERROR] Error processing {file_name}: {str(e)}", exc_info=True)
