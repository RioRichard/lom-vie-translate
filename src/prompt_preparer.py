import json
import time
from pathlib import Path
from src.grossary import load_grossary, find_original_matches
from src.config import INPUT_DIR
from src.logger import logger

def prepare_prompt_data(original_file_path, translated_dir=None):
    """
    Prepare translation prompts using:
    - name (key) and text from original file
    - glossary matches for the text
    - existing translations from translated files if available
    """
    # Load original file
    with open(original_file_path, 'r', encoding='utf-8') as f:
        original_data = json.load(f)

    # Extract entries from original
    entries = original_data.get('entries', [])
    if isinstance(entries, dict) and 'Array' in entries:
        original_entries = entries['Array']
    else:
        original_entries = entries

    # Load glossary mapping
    name_to_translated, original_to_translated = load_grossary()

    # If translated_dir provided, try to find existing translations
    translated_file = None
    if translated_dir:
        file_name = Path(original_file_path).name
        trans_path = Path(translated_dir) / file_name
        if trans_path.exists():
            with open(trans_path, 'r', encoding='utf-8') as f:
                translated_data = json.load(f)
                entries = translated_data.get('entries', [])
                if isinstance(entries, dict) and 'Array' in entries:
                    translated_file = entries['Array']
                else:
                    translated_file = entries

    prompt_data = []
    for entry in original_entries:
        # Get key name and original text
        name = entry.get('key', '') or entry.get('Name', '')
        text = entry.get('value', '') or entry.get('Text', '')
        text = text.strip()

        # Find glossary matches for the text
        glossary_matches = find_original_matches(text, original_to_translated)

        # Check if we have a raw translation by name
        raw_translation = None
        if translated_file:
            for trans_entry in translated_file:
                trans_name = trans_entry.get('key', '') or trans_entry.get('Name', '')
                if trans_name == name:
                    raw_translation = trans_entry.get('value', '') or trans_entry.get('Text', '')
                    break

        # Select and build the appropriate prompt template
        if raw_translation:
            # Template for improving existing translation
            prompt = []
            prompt.append("""Bạn là một chuyên gia hiệu chỉnh văn bản đã dịch từ Tiếng Trung (Giản thể) sang Tiếng Việt. Nhiệm vụ của bạn là:
1. Cải thiện bản dịch hiện có dựa trên văn bản gốc.
2. Đảm bảo câu văn tự nhiên, mượt mà và đúng ngữ pháp.
3. Tự động phát hiện và viết hoa đúng các danh từ riêng (tên người, địa danh, tổ chức, v.v.).
4. Giữ nguyên ý nghĩa ban đầu. Không thêm giải thích.
5. Văn phong bản dịch theo phong cách kiếm hiệp.
6. Giữ nguyên các kí hiệu đánh dấu đặc biệt như [|], [||], ???, ???, {{title}}, [{{0}}], ……。 và các ký hiệu khác.
7. Đối với cụm từ ngắn (1-2 chữ), cần xem xét bối cảnh game và ưu tiên dịch theo nghĩa hành động/trạng thái thay vì nghĩa sự vật (ví dụ: "整装" nên dịch là "chuẩn bị" thay vì "toàn bộ vũ khí").
8. Chỉ trả về phần văn bản đã được cải thiện.""")
            if glossary_matches:
                prompt.append("\nThuật ngữ cần giữ nguyên hoặc dịch đặc biệt:")
                for orig, trans in glossary_matches:
                    prompt.append(f"- {orig}={trans}")
            prompt.append(f"\nVăn bản gốc: {text}")
            prompt.append(f"\nBản dịch hiện tại: {raw_translation}")

        else:
            # Template for fresh translation
            prompt = []
            prompt.append("""Bạn là một chuyên gia dịch thuật từ Tiếng Trung (Giản thể) sang Tiếng Việt. Nhiệm vụ của bạn là:
1. Làm cho câu văn trở nên tự nhiên, mượt mà và đúng ngữ pháp.
2. Tự động phát hiện và viết hoa đúng các danh từ riêng (tên người, địa danh, tổ chức, v.v.).
3. Giữ nguyên ý nghĩa ban đầu. Không thêm giải thích.
4. Văn phong bản dịch theo phong cách kiếm hiệp.
5. Giữ nguyên các kí hiệu đánh dấu đặc biệt như [|], [||], ???, ???, {{title}}, [{{0}}], ……。 và các ký hiệu khác
6. Trong trường hợp văn bản gốc chỉ có dấu đặc biệt hoặc rỗng, trả về y hệt.
7. Đối với cụm từ ngắn (1-2 chữ), cần xem xét bối cảnh game và ưu tiên dịch theo nghĩa hành động/trạng thái thay vì nghĩa sự vật (ví dụ: "整装" nên dịch là "chuẩn bị" thay vì "toàn bộ vũ khí").
8. Chỉ trả về phần văn bản đã được dịch.""")
            if glossary_matches:
                prompt.append("\nThuật ngữ cần giữ nguyên hoặc dịch đặc biệt:")
                for orig, trans in glossary_matches:
                    prompt.append(f"- {orig}={trans}")
            prompt.append(f"\nVăn bản cần dịch: {text}")


        # Store the data
        prompt_data.append({
            'name': name,
            'original_text': text,
            'glossary_matches': glossary_matches,
            'raw_translation': raw_translation,
            'prompt': '\n'.join(prompt)
        })

    return prompt_data, translated_file

def prepare_all_files(original_dir, translated_dir=None):
    """
    Process all original JSON files and prepare translation prompts

    Args:
        original_dir (str): Directory containing original JSON files
        translated_dir (str, optional): Directory containing translated JSON files for reference
    """
    json_dir = Path(original_dir)
    all_prompts = {}
    run_start = time.time()

    for file_path in json_dir.glob('*.json'):
        file_start = time.time()
        logger.info(f"Preparing prompts for {file_path.name}")

        try:
            prompts = prepare_prompt_data(str(file_path), translated_dir)
            all_prompts[file_path.name] = prompts

            file_end = time.time()
            logger.info(f"✓ Prepared {len(prompts)} prompts for {file_path.name} in {file_end-file_start:.2f}s")
        except Exception as e:
            logger.error(f"✗ Error processing {file_path.name}: {str(e)}", exc_info=True)
            continue

    run_end = time.time()
    logger.info(f"Prompt preparation completed in {run_end-run_start:.2f}s")
    logger.info(f"Successfully processed {len(all_prompts)} files")
    return all_prompts

# Example usage:
# result = prepare_all_files()
# for fname, entries in result.items():
#     for entry in entries:
#         print(entry)
