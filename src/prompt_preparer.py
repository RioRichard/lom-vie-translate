import json
from src.utils import preprocess_text, STORY_CONTEXT_PROMPT, RULES_PROMPT, START_PROMPT
from src.glossary import find_original_matches
from src.logger import logger


async def prepare_prompt_data(
    original_file_path,
    original_data,
    translated_file_content=None,
    original_to_translated=None,
):
    """
    Prepare translation prompts using:
    - name (key) and text from original file
    - glossary matches for the text
    - existing translations from translated files if available
    """
    # Load original file
    # original_data is already loaded in process_json_file

    # Extract entries from original
    entries = original_data.get("entries", [])
    if isinstance(entries, dict) and "Array" in entries:
        original_entries = entries["Array"]
    else:
        original_entries = entries

    logger.debug(f"Original entries for {original_file_path.name}: {original_entries}")

    # If translated_file_content provided, parse it
    translated_data = None
    if translated_file_content:
        try:
            translated_data = json.loads(translated_file_content)
        except json.JSONDecodeError:
            logger.error(
                f"Could not parse translated file content for {original_file_path.name}"
            )

    translated_file_entries = None
    if translated_data:
        entries = translated_data.get("entries", [])
        if isinstance(entries, dict) and "Array" in entries:
            translated_file_entries = entries["Array"]
        else:
            translated_file_entries = entries

    prompt_data = []
    for entry in original_entries:
        # Get key name and original text
        name = entry.get("key", "") or entry.get("Name", "")
        text = entry.get("value", "") or entry.get("Text", "")
        text = preprocess_text(text.strip())

        # Find glossary matches for the text
        glossary_matches = find_original_matches(text, original_to_translated)

        # Check if we have a raw translation by name
        raw_translation = None
        if translated_file_entries:
            for trans_entry in translated_file_entries:
                trans_name = trans_entry.get("key", "") or trans_entry.get("Name", "")
                if trans_name == name:
                    raw_translation = trans_entry.get("value", "") or trans_entry.get(
                        "Text", ""
                    )
                    break
        prompt = []
        prompt.append(f"{START_PROMPT}\n{STORY_CONTEXT_PROMPT}\n{RULES_PROMPT}\n")

        # Select and build the appropriate prompt template
        if raw_translation:
            # Template for improving existing translation
            prompt.append("""
8. Sử dụng bản dịch thô để THAM KHẢO về xưng hô cũng như mối quan hệ giữa các nhân vật.
""")
            if glossary_matches:
                prompt.append("\nMột số thuật ngữ/cụm từ cần giữ nguyên:")
                for orig, trans in glossary_matches:
                    prompt.append(f"\n- {orig}={trans}")
            prompt.append(f"\nVăn bản cần được dịch: \n{text}")
            prompt.append(f"\nBản dịch thô để tham khảo: \n{raw_translation}")

        else:
            # Template for fresh translation
            if glossary_matches:
                prompt.append("\nMột số thuật ngữ/cụm từ cần giữ nguyên:")
                for orig, trans in glossary_matches:
                    prompt.append(f"\n- {orig}={trans}")
            prompt.append(f"\nVăn bản cần dịch: {text}")

        # Store the data
        prompt_data.append(
            {
                "name": name,
                "original_text": text,
                "glossary_matches": glossary_matches,
                "raw_translation": raw_translation,
                "prompt": "\n".join(prompt),
            }
        )

    logger.debug(f"Generated prompt data list: {prompt_data}")
    return prompt_data, translated_file_entries
