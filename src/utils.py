from typing import Any


def preprocess_text(text: str) -> str:
    return text.strip().replace("\r", "[|]").replace("\n", "[||]")


def postprocess_text(text: str, for_json: bool = True) -> str:
    text = (
        text.strip()
        .replace("[|]", "\r")
        .replace("[||]", "\n")
        .replace("**", "")
        .replace("\n\n", "\n")
        .replace("\\n\\n", "\\n")
        .replace("Đây là bản dịch:\n", "")
    )
    if for_json:
        # Keep real \r and \n characters
        return text.replace("\\r", "\r").replace("\\n", "\n")
    # Store as literal \\r and \\n for txt
    return text.replace("\r", "\\r").replace("\n", "\\n")


def parse_json_entries(data: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """Extract entry list and format flag from supported JSON schemas.

    Supports both ``{"entries": {"Array": [...]}}`` (``is_array_format=True``)
    and ``{"entries": [...]}`` (``is_array_format=False``). Returns ``([], False)``
    when ``entries`` is missing or invalid.
    """
    if not isinstance(data, dict):
        return [], False
    entries = data.get("entries")
    if isinstance(entries, dict):
        array = entries.get("Array")
        if isinstance(array, list):
            return array, True
        return [], False
    if isinstance(entries, list):
        return entries, False
    return [], False


SPECIAL_CHARS: list[str] = [
    "？？？",
    "{{title}}",
    "???",
    "[{{0}}]",
    "[{0}]",
    "[|]",
    "[||]",
    "……。",
    "……！",
]

START_PROMPT = "Bạn là một chuyên gia dịch thuật từ Tiếng Trung (Giản thể) sang Tiếng Việt và đã có kinh nghiệm bản địa hóa các tựa game từ các thứ tiếng sang Tiếng Việt."

RULES_PROMPT = """
Nhiệm vụ của bạn là:
1. Dịch văn bản trên từ Tiếng Trung (Giản thể) sang Tiếng Việt, đảm bảo câu văn giữ ý nghĩa của văn bản gốc, đồng thời câu văn phải tự nhiên, mượt mà, phù hợp với bối cảnh Kiếm hiệp cổ trang Trung Quốc của game Legend of Mortal
2. Tự động phát hiện và viết hoa đúng các danh từ riêng (tên người, địa danh, tổ chức, v.v.).
3. Trong một số trường hợp, có thể ưu tiên sử dụng thành ngữ, tục ngữ phổ biến của người Việt để dịch, hoặc dịch sao đảm bảo chất thơ của câu.
Ví dụ: (Format: Gốc / Bản dịch Thô / Bản dịch cuối)
    天下寂寥事，与君阔别时 / Thiên hạ bao chuyện u buồn, chính khi cùng người chia ly / Nhân gian buồn hiu quạnh, khi xa cách cố nhân
4. Giữ nguyên các kí hiệu đánh dấu đặc biệt như [|], [||], ???, ???, {title}, [{0}], ... và các ký hiệu khác. Đây là các ký hiệu cho code trong game Legend of Mortal.
Ví dụ:
    捅人伤害+{{0:N0}}  骰子+{{1:N0}} -> Đâm người gây thương tích +{{0:N0}}  Xúc xắc +{{1:N0}}
5. Đối với cụm từ ngắn (1-2 chữ), cần xem xét bối cảnh game và ưu tiên dịch theo nghĩa hành động/trạng thái thay vì nghĩa sự vật.
Ví dụ:
    "整装" nên dịch là "chuẩn bị" thay vì "toàn bộ vũ khí"
6. Chỉ trả về phần văn bản đã được dịch dưới định dạng plain text.
7. Đảm bảo bản dịch không còn chứa văn bản tiếng Trung nào.
8. Khi phân vân không biết dịch sao, bạn cứ trả về văn bản mà bạn cho đúng nhất.
"""

IMPROVE_RULE_PROMPT = (
    "9. Sử dụng bản dịch thô để THAM KHẢO về xưng hô cũng như mối quan hệ giữa các nhân vật."
)

CONTEXT_AWARE_IMPROVE_RULE_PROMPT = (
    "9. Ưu tiên tuyệt đối Ngữ cảnh cốt truyện và Quy tắc xưng hô (Relationship Matrix) được cung cấp ở trên để dịch đúng xưng hô, vai vế và cảm xúc nhân vật; chỉ dùng bản dịch thô để tham khảo ý nghĩa và PHẢI sửa lại xưng hô nếu bản dịch thô bị sai."
)

STORY_CONTEXT_PROMPT = """
Bối cảnh câu chuyện: Legend of Mortal là câu chuyện bối cảnh kiếm hiệp cổ trang diễn ra vào triều Tống tại Trung Quốc đang dần suy yếu.
Nhân vật chính là Triệu Hoạt - Đệ tử ngoại thất của Đường Môn. Triệu Hoạt là một con người không có gì - xuất thân mơ hồ, nhan sắc xấu xí, võ công yếu kém
Nhưng đến cuối cùng, số mệnh Đường Môn, hoặc cả võ lâm giang hồ cùng nhà Tống nằm trong tay Triệu Hoạt.
"""


def build_translation_prompt(
    original_text: str,
    raw_translation: str | None = None,
    glossary_matches: list[tuple[str, str]] | None = None,
    story_context: str | None = None,
) -> str:
    """Build a translation or improvement prompt for Legend of Mortal game text."""
    normalized_context = story_context.strip() if isinstance(story_context, str) else ""
    header = f"{START_PROMPT}\n{STORY_CONTEXT_PROMPT}\n{RULES_PROMPT.rstrip()}"
    if raw_translation:
        improve_rule = (
            CONTEXT_AWARE_IMPROVE_RULE_PROMPT if normalized_context else IMPROVE_RULE_PROMPT
        )
        header = f"{header}\n{improve_rule}"

    sections: list[str] = [header]

    if normalized_context:
        sections.append(
            f"Thông tin ngữ cảnh & xưng hô trong cảnh hiện tại:\n{normalized_context}"
        )

    if glossary_matches:
        glossary_lines = ["Một số thuật ngữ/cụm từ cần giữ nguyên:"]
        for orig, trans in glossary_matches:
            glossary_lines.append(f"- {orig}={trans}")
        sections.append("\n".join(glossary_lines))

    sections.append(f"Văn bản cần được dịch:\n{original_text}")

    if raw_translation:
        sections.append(f"Bản dịch thô để tham khảo:\n{raw_translation}")

    return "\n\n".join(sections)
