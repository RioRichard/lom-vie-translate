import json
import time
from pathlib import Path
import aiofiles
import asyncio
from src.grossary import find_original_matches
from src.logger import logger

async def prepare_prompt_data(original_file_path, translated_dir=None, name_to_translated=None, original_to_translated=None):
    """
    Prepare translation prompts using:
    - name (key) and text from original file
    - glossary matches for the text
    - existing translations from translated files if available
    """
    # Load original file
    async with aiofiles.open(original_file_path, 'r', encoding='utf-8') as f:
        content = await f.read()
        original_data = json.loads(content)

    # Extract entries from original
    entries = original_data.get('entries', [])
    if isinstance(entries, dict) and 'Array' in entries:
        original_entries = entries['Array']
    else:
        original_entries = entries

    logger.debug(f"Original entries for {original_file_path.name}: {original_entries}")

    # If translated_dir provided, try to find existing translations
    translated_file = None
    if translated_dir:
        file_name = Path(original_file_path).name
        trans_path = Path(translated_dir) / file_name
        if trans_path.exists():
            async with aiofiles.open(trans_path, 'r', encoding='utf-8') as f:
                trans_content = await f.read()
                translated_data = json.loads(trans_content)
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
            prompt.append("""Bạn là một chuyên gia hiệu chỉnh các bản dịch từ Tiếng Trung (Giản thể) sang Tiếng Việt.
Đây là một phần của câu chuyện trong tựa game Legend of Mortal có bối cảnh kiếm hiệp cổ trang Trung Quốc.
Nhiệm vụ của bạn là:
1. Cải thiện bản dịch hiện có dựa trên văn bản gốc.
2. Đảm bảo câu văn tự nhiên, mượt mà, đúng ngữ pháp và phù hợp với nội dung của game Legend of Mortal.
3. Tự động phát hiện và viết hoa đúng các danh từ riêng (tên người, địa danh, tổ chức, v.v.).
4. Giữ nguyên ý nghĩa ban đầu. Không thêm giải thích.
5. Sử dụng phong cách kiếm hiệp cổ trang Trung Quốc.
6. Giữ nguyên các kí hiệu đánh dấu đặc biệt như [|], [||], ???, ???, {{title}}, [{{0}}], ... và các ký hiệu khác.
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
            prompt.append("""Bạn là một chuyên gia dịch thuật từ Tiếng Trung (Giản thể) sang Tiếng Việt.
Đây là một phần của câu chuyện trong tựa game Legend of Mortal có bối cảnh kiếm hiệp cổ trang Trung Quốc.
Nhiệm vụ của bạn là:
1. Dịch từ Tiếng Trung (Giản thể) sang Tiếng Việt.
2. Đảm bảo câu văn tự nhiên, mượt mà, đúng ngữ pháp và phù hợp với nội dung của game Legend of Mortal.
3. Tự động phát hiện và viết hoa đúng các danh từ riêng (tên người, địa danh, tổ chức, v.v.)....
4. Giữ nguyên ý nghĩa ban đầu của câu văn. Không cần phải giải thích thêm ý nghĩa của câu văn.
5. Sử dụng phong cách kiếm hiệp cổ trang Trung Quốc.
6. Giữ nguyên các kí hiệu đánh dấu đặc biệt như [|], [||], ???, ???, {{title}}, [{{0}}], v.v....
7. Trong trường hợp văn bản gốc chỉ có dấu đặc biệt hoặc rỗng, trả về y hệt và không giải thích hay yêu cầu gì thêm.
8. Đối với cụm từ ngắn (1-2 chữ), cần xem xét bối cảnh game và ưu tiên dịch theo nghĩa hành động/trạng thái thay vì nghĩa sự vật (ví dụ: "整装" nên dịch là "chuẩn bị" thay vì "toàn bộ vũ khí").
9. Chỉ trả về phần văn bản đã được dịch.""")
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

    logger.debug(f"Generated prompt data list: {prompt_data}")
    return prompt_data, translated_file

async def prepare_all_files(original_dir, translated_dir=None, name_to_translated=None, original_to_translated=None):
    """
    Process all original JSON files and prepare translation prompts

    Args:
        original_dir (str): Directory containing original JSON files
        translated_dir (str, optional): Directory containing translated JSON files for reference
        glossary_file_path (str, optional): Path to a specific glossary file to use.
    """
    json_dir = Path(original_dir)
    all_prompts = {}
    run_start = time.time()

    tasks = []
    for file_path in json_dir.glob('*.json'):
        tasks.append(prepare_prompt_data(str(file_path), translated_dir, name_to_translated, original_to_translated))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for file_path, result in zip(json_dir.glob('*.json'), results):
        if isinstance(result, Exception):
            logger.error(f"✗ Error processing {file_path.name}: {str(result)}", exc_info=True)
        else:
            prompts, translated_file = result
            all_prompts[file_path.name] = prompts
            logger.info(f"✓ Prepared {len(prompts)} prompts for {file_path.name}")

    run_end = time.time()
    logger.info(f"Prompt preparation completed in {run_end-run_start:.2f}s")
    logger.info(f"Successfully processed {len(all_prompts)} files")
    return all_prompts

# Example usage:
# result = prepare_all_files()
# for fname, entries in result.items():
#     for entry in entries:
#         print(entry)
