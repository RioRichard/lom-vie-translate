import json
from src.glossary import find_original_matches
from src.logger import logger

async def prepare_prompt_data(original_file_path, original_data, translated_file_content=None, original_to_translated=None):
    """
    Prepare translation prompts using:
    - name (key) and text from original file
    - glossary matches for the text
    - existing translations from translated files if available
    """
    # Load original file
    # original_data is already loaded in process_json_file

    # Extract entries from original
    entries = original_data.get('entries', [])
    if isinstance(entries, dict) and 'Array' in entries:
        original_entries = entries['Array']
    else:
        original_entries = entries

    logger.debug(f"Original entries for {original_file_path.name}: {original_entries}")

    # If translated_file_content provided, parse it
    translated_data = None
    if translated_file_content:
        try:
            translated_data = json.loads(translated_file_content)
        except json.JSONDecodeError:
            logger.error(f"Could not parse translated file content for {original_file_path.name}")

    translated_file_entries = None
    if translated_data:
        entries = translated_data.get('entries', [])
        if isinstance(entries, dict) and 'Array' in entries:
            translated_file_entries = entries['Array']
        else:
            translated_file_entries = entries

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
        if translated_file_entries:
            for trans_entry in translated_file_entries:
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
                    prompt.append(f"\n- {orig}={trans}")
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
                    prompt.append(f"\n- {orig}={trans}")
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
    return prompt_data, translated_file_entries
