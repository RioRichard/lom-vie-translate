"""Tests for contextual prompt generation, diagnostic feedback, and corrective re-prompting."""

from __future__ import annotations

from lom_translate.glossary import Glossary
from lom_translate.models import LocalizationEntry
from lom_translate.prompt import (
    CANONICAL_SYSTEM_PROMPT,
    build_corrective_prompt,
    build_entry_prompt,
    build_improve_prompt,
    build_prompts,
    build_system_prompt,
    build_translate_prompt,
    format_diagnostic_feedback,
)
from lom_translate.validation import ValidationResult


def test_build_system_prompt_contains_core_sections():
    """System prompt must contain persona, story context, and translation rules."""
    prompt = build_system_prompt()
    assert prompt == CANONICAL_SYSTEM_PROMPT
    assert "chuyên gia dịch thuật" in prompt
    assert "Legend of Mortal" in prompt
    assert "BẮT BUỘC GIỮ NGUYÊN các kí hiệu" in prompt


def test_build_prompts_backward_compatibility():
    """Existing build_prompts preserves exact output schema and content structure."""
    entries = [
        LocalizationEntry(Name="e1", Text="你好世界"),
        LocalizationEntry(Name="e2", Text="造成伤害+{0:N0}"),
    ]
    glossary = Glossary()
    prompts = build_prompts(entries, glossary)

    assert len(prompts) == 2
    for p in prompts:
        assert "name" in p
        assert "original_text" in p
        assert "glossary_matches" in p
        assert "raw_translation" in p
        assert "prompt" in p
        assert "Văn bản cần dịch:" in p["prompt"]
        assert "chuyên gia dịch thuật" in p["prompt"]

    assert prompts[0]["name"] == "e1"
    assert prompts[0]["original_text"] == "你好世界"
    assert prompts[1]["name"] == "e2"
    assert prompts[1]["original_text"] == "造成伤害+{0:N0}"


def test_build_prompts_with_raw_entries_improve_mode():
    """When raw_entries provided, build_prompts includes reference instructions and mapping."""
    entries = [LocalizationEntry(Name="e1", Text="掌门，大事不好了！")]
    raw_entries = [LocalizationEntry(Name="e1", Text="Chưởng môn, việc lớn không tốt!")]
    glossary = Glossary()

    prompts = build_prompts(entries, glossary, raw_entries=raw_entries)
    assert len(prompts) == 1
    assert prompts[0]["raw_translation"] == "Chưởng môn, việc lớn không tốt!"
    assert "Bản dịch thô để tham khảo:" in prompts[0]["prompt"]
    assert "Chưởng môn, việc lớn không tốt!" in prompts[0]["prompt"]


def test_build_prompts_separate_system_prompt():
    """When separate_system_prompt=True, prompt dict includes separated system_prompt."""
    entries = [LocalizationEntry(Name="e1", Text="测试文本")]
    glossary = Glossary()

    prompts = build_prompts(entries, glossary, separate_system_prompt=True)
    assert len(prompts) == 1
    assert "system_prompt" in prompts[0]
    assert prompts[0]["system_prompt"] == CANONICAL_SYSTEM_PROMPT
    assert "Văn bản cần dịch: 测试文本" in prompts[0]["prompt"]


def test_build_translate_and_improve_prompts():
    """Convenience single-entry builders construct expected prompts."""
    trans_p = build_translate_prompt(
        text="你好[||]世界",
        glossary_matches=[("世界", "thế giới")],
        include_system_prompt=False,
    )
    assert "Văn bản cần dịch: 你好[||]世界" in trans_p
    assert "- 世界 => thế giới" in trans_p

    improve_p = build_improve_prompt(
        text="你好[||]世界",
        raw_translation="Xin chào thế giới",
        include_system_prompt=False,
    )
    assert "Bản dịch thô để tham khảo: Xin chào thế giới" in improve_p


def test_format_diagnostic_feedback_clean():
    """A clean validation result produces an empty diagnostic string."""
    res = ValidationResult(healed_text="Bản dịch chuẩn xác", is_clean=True)
    feedback = format_diagnostic_feedback(res)
    assert feedback == ""

    assert format_diagnostic_feedback(None) == ""


def test_format_diagnostic_feedback_missing_tokens():
    """Detects missing tokens and formats engine warning with exact rule."""
    res = ValidationResult(
        healed_text="Sát thương +0",
        is_clean=False,
        missing_tokens=["{0:N0}", "[||]"],
    )
    feedback = format_diagnostic_feedback(res)
    assert "❌ [LỖI KÝ HIỆU HỆ THỐNG]" in feedback
    assert "{0:N0}" in feedback
    assert "[||]" in feedback
    assert "Quy tắc:" in feedback


def test_format_diagnostic_feedback_corrupted_tags():
    """Detects corrupted tags in warning messages and formats tag error directive."""
    res = ValidationResult(
        healed_text="<color=#FF0000>Văn bản",
        is_clean=False,
        warning_messages=["Tag <color=#FF0000> is unclosed"],
    )
    feedback = format_diagnostic_feedback(res)
    assert "❌ [LỖI THẺ ĐỊNH DẠNG]" in feedback
    assert "Unity Rich Text" in feedback
    assert "<color" in feedback


def test_format_diagnostic_feedback_empty_output():
    """Empty or whitespace-only healed output produces empty content error."""
    res = ValidationResult(healed_text="   ", is_clean=False)
    feedback = format_diagnostic_feedback(res)
    assert "❌ [LỖI NỘI DUNG RỖNG]" in feedback


def test_format_diagnostic_feedback_lingering_cjk():
    """Flags untranslated CJK characters and lists sample characters."""
    res = ValidationResult(
        healed_text="Xin chào 世界",
        is_clean=False,
        has_untranslated_cjk=True,
    )
    feedback = format_diagnostic_feedback(res)
    assert "⚠️ [CẢNH BÁO SÓT CHỮ HÁN]" in feedback
    assert "'世'" in feedback or "'界'" in feedback


def test_format_diagnostic_feedback_missing_glossary():
    """Flags missing mandatory glossary translations."""
    res = ValidationResult(
        healed_text="Bá bá và đệ tử Đường Môn",
        is_clean=False,
    )
    glossary_matches = [("南宫伯伯", "Nam Cung bá bá"), ("唐门", "Đường Môn")]
    feedback = format_diagnostic_feedback(res, glossary_matches=glossary_matches)
    assert "⚠️ [CẢNH BÁO THUẬT NGỮ BẮT BUỘC]" in feedback
    assert "'南宫伯伯' bắt buộc dịch là 'Nam Cung bá bá'" in feedback
    # 'Đường Môn' is present, so it should NOT be flagged
    assert "'唐门' bắt buộc dịch là 'Đường Môn'" not in feedback


def test_format_diagnostic_feedback_verbatim_identity():
    """Flags identical verbatim copying of CJK source text."""
    orig = "掌门，大事不好了！"
    res = ValidationResult(healed_text=orig, is_clean=False)
    feedback = format_diagnostic_feedback(res, original_text=orig)
    assert "⚠️ [CẢNH BÁO TRÙNG LẶP NGUYÊN BẢN]" in feedback


def test_format_diagnostic_feedback_length_anomaly():
    """Flags severe dialogue truncation."""
    orig = "这是一段很长的剧情文本，详细叙述了唐门三师兄在江陵之战中的英勇事迹与惨烈牺牲。"
    trans = "Tốt."
    res = ValidationResult(healed_text=trans, is_clean=False)
    feedback = format_diagnostic_feedback(res, original_text=orig)
    assert "⚠️ [CẢNH BÁO ĐỘ DÀI]" in feedback


def test_format_diagnostic_feedback_multiple_errors():
    """Combines multiple errors into a coherent multi-category diagnostic message."""
    res = ValidationResult(
        healed_text="Gây sát thương 50 điểm với 世界",
        is_clean=False,
        missing_tokens=["{0:N0}"],
        has_untranslated_cjk=True,
    )
    glossary_matches = [("伤害", "sát thương"), ("唐门", "Đường Môn")]
    feedback = format_diagnostic_feedback(res, glossary_matches=glossary_matches)

    assert "❌ [LỖI KÝ HIỆU HỆ THỐNG]" in feedback
    assert "⚠️ [CẢNH BÁO SÓT CHỮ HÁN]" in feedback
    assert "⚠️ [CẢNH BÁO THUẬT NGỮ BẮT BUỘC]" in feedback


def test_build_corrective_prompt_structure():
    """Verifies Anchor-and-Patch corrective prompt structure and components."""
    orig = "造成伤害+{0:N0}，获得[|][||]{title}"
    cand = "Gây sát thương +0, nhận được danh hiệu"
    res = ValidationResult(
        healed_text=cand,
        is_clean=False,
        missing_tokens=["{0:N0}", "[|]", "[||]", "{title}"],
    )

    prompt = build_corrective_prompt(
        original_text=orig,
        failed_translation=cand,
        val_result=res,
    )

    assert "--- VĂN BẢN GỐC (TIẾNG TRUNG) ---" in prompt
    assert orig in prompt
    assert "--- BẢN DỊCH HIỆN TẠI CỦA BẠN (CẦN SỬA) ---" in prompt
    assert cand in prompt
    assert "--- DANH SÁCH LỖI CẦN SỬA ---" in prompt
    assert "❌ [LỖI KÝ HIỆU HỆ THỐNG]" in prompt
    assert "--- HƯỚNG DẪN ĐIỀU CHỈNH (ANCHOR-AND-PATCH) ---" in prompt
    assert "Giữ nguyên văn phong, cấu trúc câu" in prompt
    assert "Tuyệt đối KHÔNG thêm lời giải thích" in prompt


def test_build_corrective_prompt_with_raw_and_glossary():
    """Corrective prompt includes raw translation and glossary tables when provided."""
    orig = "南宫伯伯来到了唐门"
    cand = "Bác Nam Cung đến Đường Gia"
    res = ValidationResult(healed_text=cand, is_clean=False)

    prompt = build_corrective_prompt(
        original_text=orig,
        failed_translation=cand,
        val_result=res,
        glossary_matches=[("南宫伯伯", "Nam Cung bá bá"), ("唐门", "Đường Môn")],
        raw_translation="Nam Cung đại thúc tới Đường môn",
    )

    assert "--- BẢN DỊCH THÔ THAM KHẢO ---" in prompt
    assert "Nam Cung đại thúc tới Đường môn" in prompt
    assert "--- BẢNG THUẬT NGỮ BẮT BUỘC ---" in prompt
    assert "- 南宫伯伯 => Nam Cung bá bá" in prompt


def test_build_corrective_prompt_empty_candidate_fallback():
    """Empty candidate translation renders fallback placeholder text."""
    orig = "测试文本"
    prompt = build_corrective_prompt(
        original_text=orig,
        failed_translation="",
        diagnostic_messages=["Bản dịch trả về bị rỗng."],
    )
    assert "(Không có phản hồi / nội dung rỗng)" in prompt
    assert "Bản dịch trả về bị rỗng." in prompt
