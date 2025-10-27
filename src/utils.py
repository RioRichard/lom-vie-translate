def preprocess_text(text):
    return text.strip().replace("\r", "[|]").replace("\n", "[||]")


def postprocess_text(text, for_json=True):
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
    else:
        # Store as literal \\r and \\n for txt
        return text.replace("\r", "\\r").replace("\n", "\\n")


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
START_PROMPT = "Bạn là một chuyên gia dịch thuật từ Tiếng Trung (Giản thể) sang Tiếng Việt và đã có kinh nghiệm dịch game."

RULES_PROMPT = """
Nhiệm vụ của bạn là:
1. Dịch văn bản trên từ Tiếng Trung (Giản thể) sang Tiếng Việt, đảm bảo câu văn giữ ý nghĩa của văn bản gốc, đồng thời câu văn phải tự nhiên, mượt mà, phù hợp với bối cảnh Kiếm hiệp cổ trang Trung Quốc của game Legend of Mortal
2. Tự động phát hiện và viết hoa đúng các danh từ riêng (tên người, địa danh, tổ chức, v.v.).
3. Trong một số trường hợp, có thể ưu tiên sử dụng thành ngữ, tục ngữ phổ biến của người Việt để dịch, hoặc dịch sao đảm bảo chất thơ của câu.
Ví dụ: (Format: Gốc / Bản dịch Thô / Bản dịch cuối)
    預設 / Giậu đổ bìm leo / Châm dầu vào lửa.
    天下寂寥事，与君阔别时 / Thiên hạ bao chuyện u buồn, chính khi cùng người chia ly / Nhân gian hiu quạnh, xa cách cố nhân
4. Giữ nguyên các kí hiệu đánh dấu đặc biệt như [|], [||], ???, ???, {title}, [{0}], ... và các ký hiệu khác. Đây là các ký hiệu cho code trong game Legend of Mortal.
Ví dụ:
    {title} -> {title}
    捅人伤害+{{0:N0}}  骰子+{{1:N0}} -> Đâm người gây thương tích +{{0:N0}}  Xúc xắc +{{1:N0}}
    南宫伯伯，南宫爷爷，萤儿给您们请安。\\r\\n恭贺爷爷百岁大寿，祝您老人家福如东海，寿比南山。-> Nam Cung bá bá, Nam Cung gia gia, Huỳnh Nhi bái kiến hai vị.\\r\\nChúc gia gia thượng thọ trăm tuổi, nguyện lão nhân gia phúc như Đông Hải, thọ tùng Nam Sơn.
5. Đối với cụm từ ngắn (1-2 chữ), cần xem xét bối cảnh game và ưu tiên dịch theo nghĩa hành động/trạng thái thay vì nghĩa sự vật.
Ví dụ:
    "整装" nên dịch là "chuẩn bị" thay vì "toàn bộ vũ khí"
6. Chỉ trả về phần văn bản đã được dịch dươi định dạng plain text.
7. Đảm bảo bản dịch không còn chứa văn bản tiếng Trung nào.
"""

STORY_CONTEXT_PROMPT = """
Bối cảnh câu chuyện: Legend of Mortal là câu chuyện bối cảnh kiếm hiệp cổ trang diễn ra vào triều Tống tại Trung Quốc đang dần suy yếu.
Nhân vật chính là Triệu Hoạt của Đường Môn. Triệu Hoạt là một con người không có gì - xuất thân mơ hồ, nhan sắc xấu xí, võ công yếu kém
Nhưng đến cuối cùng, số mệnh Đường Môn, hoặc cả võ lâm giang hồ cùng nhà Tống nằm trong tay Triệu Hoạt.
"""
