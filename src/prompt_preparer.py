import json
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
        text = text.strip()

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

        # Select and build the appropriate prompt template
        if raw_translation:
            # Template for improving existing translation
            prompt = []
            prompt.append("""Bạn là một chuyên gia dịch thuật từ Tiếng Trung (Giản thể) sang Tiếng Việt và đã có kinh nghiệm dịch game.
Đây là một phần của câu chuyện trong tựa game Legend of Mortal có bối cảnh kiếm hiệp cổ trang Trung Quốc mà cần bạn dịch
Nhiệm vụ của bạn là:
1. Dịch văn bản trên từ Tiếng Trung (Giản thể) sang Tiếng Việt, đảm bảo câu văn giữ ý nghĩa của văn bản gốc, đồng thời câu văn phải tự nhiên, mượt mà, phù hợp với bối cảnh Kiếm hiệp cổ trang Trung Quốc của game Legend of Mortal
2. Tự động phát hiện và viết hoa đúng các danh từ riêng (tên người, địa danh, tổ chức, v.v.).
3. Trong một số trường hợp, có thể ưu tiên sử dụng thành ngữ, tục ngữ phổ biến của người Việt để dịch, hoặc dịch sao đảm bảo chất thơ của câu.
Ví dụ: (Format: Gốc / Bản dịch Thô / Bản dịch cuối)
    預設 / Giậu đổ bìm leo / Châm dầu vào lửa.
    天下寂寥事，与君阔别时 / Thiên hạ bao chuyện u buồn, chính khi cùng người chia ly / Nhân gian hiu quạnh, xa cách cố nhân
4. Giữ nguyên các kí hiệu đánh dấu đặc biệt như [|], [||], ???, ???, {{title}}, [{{0}}], [{0}], ... và các ký hiệu khác. Đây là các ký hiệu cho code trong game Legend of Mortal.
Ví dụ:
    {title} -> {title}
    捅人伤害+{0:N0}  骰子+{1:N0} -> Đâm người gây thương tích +{0:N0}  Xúc xắc +{1:N0}
    南宫伯伯，南宫爷爷，萤儿给您们请安。\\r\\n恭贺爷爷百岁大寿，祝您老人家福如东海，寿比南山。-> Nam Cung bá bá, Nam Cung gia gia, Huỳnh Nhi bái kiến hai vị.\\r\\nChúc gia gia thượng thọ trăm tuổi, nguyện lão nhân gia phúc như Đông Hải, thọ tùng Nam Sơn.
5. Đối với cụm từ ngắn (1-2 chữ), cần xem xét bối cảnh game và ưu tiên dịch theo nghĩa hành động/trạng thái thay vì nghĩa sự vật.
Ví dụ:
    "整装" nên dịch là "chuẩn bị" thay vì "toàn bộ vũ khí"
6. Chỉ trả về phần văn bản đã được dịch dươi định dạng plain text.
7. Sử dụng bản dịch thô để THAM KHẢO về xưng hô cũng như mối quan hệ giữa các nhân vật.
8. Đảm bảo bản dịch không còn chứa văn bản tiếng Trung nào.""")
            if glossary_matches:
                prompt.append("\nMột số thuật ngữ/cụm từ cần giữ nguyên:")
                for orig, trans in glossary_matches:
                    prompt.append(f"\n- {orig}={trans}")
            prompt.append(f"\nVăn bản cần được dịch: \n{text}")
            prompt.append(f"\nBản dịch thô để tham khảo: \n{raw_translation}")

        else:
            # Template for fresh translation
            prompt = []
            prompt.append("""Bạn là một chuyên gia dịch thuật từ Tiếng Trung (Giản thể) sang Tiếng Việt và đã có kinh nghiệm dịch game.
Đây là một phần của câu chuyện trong tựa game Legend of Mortal có bối cảnh kiếm hiệp cổ trang Trung Quốc mà cần bạn dịch
Nhiệm vụ của bạn là:
1. Dịch văn bản trên từ Tiếng Trung (Giản thể) sang Tiếng Việt, đảm bảo câu văn giữ ý nghĩa của văn bản gốc, đồng thời câu văn phải tự nhiên, mượt mà, phù hợp với bối cảnh Kiếm hiệp cổ trang Trung Quốc của game Legend of Mortal
2. Tự động phát hiện và viết hoa đúng các danh từ riêng (tên người, địa danh, tổ chức, v.v.).
3. Trong một số trường hợp, có thể ưu tiên sử dụng thành ngữ, tục ngữ phổ biến của người Việt để dịch, hoặc dịch sao đảm bảo chất thơ của câu.
Ví dụ: (Format: Gốc -> Bản dịch)
    預設 / Châm dầu vào lửa.
    天下寂寥事，与君阔别时 / Nhân gian hiu quạnh, xa cách cố nhân
4. Giữ nguyên các kí hiệu đánh dấu đặc biệt như [|], [||], ???, ???, {{title}}, [{{0}}], [{0}], ... và các ký hiệu khác. Đây là các ký hiệu cho code trong game Legend of Mortal.
Ví dụ: (Format: Gốc -> Bản dịch)
    {title} -> {title}
    捅人伤害+{0:N0}  骰子+{1:N0} -> Đâm người gây thương tích +{0:N0}  Xúc xắc +{1:N0}
    南宫伯伯，南宫爷爷，萤儿给您们请安。\\r\\n恭贺爷爷百岁大寿，祝您老人家福如东海，寿比南山。-> Nam Cung bá bá, Nam Cung gia gia, Huỳnh Nhi bái kiến hai vị.\\r\\nChúc gia gia thượng thọ trăm tuổi, nguyện lão nhân gia phúc như Đông Hải, thọ tùng Nam Sơn.
5. Đối với cụm từ ngắn (1-2 chữ), cần xem xét bối cảnh game và ưu tiên dịch theo nghĩa hành động/trạng thái thay vì nghĩa sự vật.
Ví dụ:
    "整装" nên dịch là "chuẩn bị" thay vì "toàn bộ vũ khí"
6. Chỉ trả về phần văn bản đã được dịch dươi định dạng plain text.
7. Đảm bảo bản dịch không còn chứa văn bản tiếng Trung nào.""")
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
