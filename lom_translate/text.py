"""Text preprocessing, postprocessing, and prompt templates."""

from __future__ import annotations


def preprocess_text(text: str) -> str:
    """Prepare text for LLM injection, encoding linebreaks into code markers."""
    return text.strip().replace("\r", "[|]").replace("\n", "[||]")


def postprocess_text(text: str) -> str:
    """Clean LLM output. DEF-11 FIX: preserves double linebreaks / intentional paragraph breaks."""
    return text.strip().replace("[|]", "\r").replace("[||]", "\n").replace("**", "").replace("Đây là bản dịch:\n", "")


SPECIAL_CHARS = [
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

START_PROMPT = (
    "Bạn là một chuyên gia dịch thuật từ Tiếng Trung (Giản thể) sang Tiếng Việt "
    "và đã có kinh nghiệm bản địa hóa các tựa game từ các thứ tiếng sang Tiếng Việt."
)

RULES_PROMPT = """
Nhiệm vụ của bạn là:
1. Dịch văn bản trên từ Tiếng Trung (Giản thể) sang Tiếng Việt, đảm bảo câu văn giữ ý nghĩa của văn bản gốc, đồng thời câu văn phải tự nhiên, mượt mà, phù hợp với bối cảnh Kiếm hiệp cổ trang Trung Quốc của game Legend of Mortal.
2. Tự động phát hiện và viết hoa đúng các danh từ riêng (tên người, địa danh, tổ chức, v.v.).
3. Trong một số trường hợp, có thể ưu tiên sử dụng thành ngữ, tục ngữ phổ biến của người Việt để dịch, hoặc dịch sao đảm bảo chất thơ của câu.
4. BẮT BUỘC GIỮ NGUYÊN các kí hiệu đánh dấu đặc biệt như [|], [||], ???, {title}, [{0}], {0:N0} ... và các ký hiệu khác. Tuyệt đối không xóa, không dịch nghĩa, không thêm khoảng trắng vào trong ký hiệu.
5. Đối với cụm từ ngắn (1-2 chữ), cần xem xét bối cảnh game và ưu tiên dịch theo nghĩa hành động/trạng thái thay vì nghĩa sự vật.
6. Chỉ trả về phần văn bản đã được dịch dưới định dạng plain text.
7. Đảm bảo bản dịch không còn chứa văn bản tiếng Trung nào.
8. Khi phân vân không biết dịch sao, bạn cứ trả về văn bản mà bạn cho đúng nhất.
"""

STORY_CONTEXT_PROMPT = """
Bối cảnh câu chuyện: Legend of Mortal là câu chuyện bối cảnh kiếm hiệp cổ trang diễn ra vào triều Tống tại Trung Quốc đang dần suy yếu.
Nhân vật chính là Triệu Hoạt - Đệ tử ngoại thất của Đường Môn. Triệu Hoạt là một con người không có gì - xuất thân mơ hồ, nhan sắc xấu xí, võ công yếu kém.
Nhưng đến cuối cùng, số mệnh Đường Môn, hoặc cả võ lâm giang hồ cùng nhà Tống nằm trong tay Triệu Hoạt.
"""
