import argparse
import json
from pathlib import Path
import asyncio

from src.glossary import find_original_matches
from src.logger import logger

from src.translator import translate_text
from src.config import RATE_LIMIT_DELAY, MAX_CONCURRENT
from tqdm import tqdm


async def improve_glossary_prompts(glossary_file_path):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    """
    Prepare improvement prompts for glossary entries.
    """
    logger.info(f"Processing glossary file: {glossary_file_path}")

    with open(glossary_file_path, "r", encoding="utf-8") as f:
        glossary_data = json.load(f)

    tasks = []
    # Assuming glossary_data is a list of dictionaries or a dictionary with entries
    entries = (
        glossary_data.get("entries", [])
        if isinstance(glossary_data, dict)
        else glossary_data
    )

    for entry in entries:
        original_text = entry.get("Original", "").strip()
        raw_translation = entry.get("Translated", "").strip()
        name = (
            entry.get("Name", "") or original_text
        )  # Use original_text as name if Name is not present

        if not original_text or not raw_translation:
            logger.warning(
                f"Skipping entry due to missing original or translated text: {entry}"
            )
            continue

        # Find glossary matches (if any, though for glossary improvement, this might be less relevant)
        # For now, we'll pass an empty original_to_translated as we are improving the glossary itself
        glossary_matches = find_original_matches(original_text, {})

        # Template for improving existing translation
        prompt_parts = []
        prompt_parts.append("""Bạn là một chuyên gia dịch thuật từ Tiếng Trung (Giản thể) sang Tiếng Việt và đã có kinh nghiệm dịch game.
Đây là một phần của câu chuyện trong tựa game Legend of Mortal có bối cảnh kiếm hiệp cổ trang Trung Quốc mà cần bạn dịch
Nhiệm vụ của bạn là:
1. Dịch văn bản trên từ Tiếng Trung (Giản thể) sang Tiếng Việt, đảm bảo câu văn giữ ý nghĩa của văn bản gốc, đồng thời câu văn phải tự nhiên, mượt mà, phù hợp với bối cảnh Kiếm hiệp cổ trang Trung Quốc của game Legend of Mortal
2. Tự động phát hiện và viết hoa đúng các danh từ riêng (tên người, địa danh, tổ chức, v.v.).
3. Giữ nguyên các kí hiệu đánh dấu đặc biệt như [|], [||], ???, ???, {{title}}, [{{0}}], [{0}], ... và các ký hiệu khác. Đây là các ký hiệu cho code trong game Legend of Mortal.
Ví dụ:
    {title} -> {title}
    捅人伤害+{0:N0}  骰子+{1:N0} -> Đâm người gây thương tích +{0:N0}  Xúc xắc +{1:N0}
    南宫伯伯，南宫爷爷，萤儿给您们请安。\r\n恭贺爷爷百岁大寿，祝您老人家福如 Đông Hải,寿比南山。-> Nam Cung bá bá, Nam Cung gia gia, Huỳnh Nhi bái kiến hai vị.\r\nChúc gia gia thượng thọ trăm tuổi, nguyện lão nhân gia phúc như Đông Hải, thọ tùng Nam Sơn.
4. Đối với cụm từ ngắn (1-2 chữ), cần xem xét bối cảnh game và ưu tiên dịch theo nghĩa hành động/trạng thái thay vì nghĩa sự vật.
Ví dụ:
    "整装" nên dịch là "chuẩn bị" thay vì "toàn bộ vũ khí"
5. Chỉ trả về phần văn bản đã được dịch dươi định dạng plain text.
6. Sử dụng bản dịch thô để THAM KHẢO về xưng hô cũng như mối quan hệ giữa các nhân vật.
7. Đảm bảo bản dịch không còn chứa văn bản tiếng Trung nào.""")
        if glossary_matches:
            prompt_parts.append("\nMột số thuật ngữ/cụm từ cần giữ nguyên:")
            for orig, trans in glossary_matches:
                prompt_parts.append(f"\n- {orig}={trans}")
        prompt_parts.append(f"\nVăn bản cần được dịch: \n{original_text}")
        prompt_parts.append(f"\nBản dịch thô để tham khảo: \n{raw_translation}")
        prompt = "\n".join(prompt_parts)

        tasks.append((semaphore, name, original_text, raw_translation, prompt))
    pbar = tqdm(total=len(tasks), desc="Processing entries", mininterval=0.1)

    async def safe_run_with_delay(args):
        semaphore, name, original_text, raw_translation, prompt = args
        async with semaphore:
            await asyncio.sleep(RATE_LIMIT_DELAY)
            improvement_glossary = await translate_text(
                text=original_text, name=name, prompt_data=prompt
            )

            result = {
                "Name": name,
                "Original": original_text,
                "RawTranslated": raw_translation,
                "Translated": improvement_glossary,
            }
        tqdm.write(f"Processed entry: {result}")
        pbar.update(1)
        return result

    improved_translations = await asyncio.gather(
        *[safe_run_with_delay(task) for task in tasks]
    )
    pbar.close()

    return improved_translations


async def main():
    parser = argparse.ArgumentParser(
        description="Prepare improvement prompts for glossary entries."
    )
    parser.add_argument(
        "-gf",
        "--glossary-file",
        type=str,
        required=True,
        help="Path to the input glossary JSON file.",
    )
    parser.add_argument(
        "-od",
        "--output-dir",
        type=str,
        required=True,
        help="Directory to save the output JSON file.",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    prompts = await improve_glossary_prompts(Path(args.glossary_file))

    output_file_path = (
        output_dir / f"improved_glossary_prompts_{Path(args.glossary_file).stem}.json"
    )
    with open(output_file_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=4)
    logger.info(f"Improvement prompts saved to: {output_file_path}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
