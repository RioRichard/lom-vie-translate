"""Comprehensive tests for dual-tier validators, auto-healing, and token integrity."""

from __future__ import annotations

import pytest

from lom_translate.validation import (
    ValidationResult,
    auto_heal_tokens,
    soft_validate_translation,
    validate_translation,
)


# =====================================================================
# 1. Auto-Healing Unit Tests
# =====================================================================

def test_auto_heal_spaced_injected_breaks():
    """Auto-healer fixes whitespace injected by LLMs in [||] and [|]."""
    raw = "Câu 1[ || ]Câu 2[ | | ]Câu 3[ | ]Câu 4"
    healed = auto_heal_tokens(raw)
    assert healed == "Câu 1[||]Câu 2[||]Câu 3[|]Câu 4"


def test_auto_heal_spaced_game_tokens():
    """Auto-healer fixes whitespace injected inside {0:N0} and {title}."""
    raw = "Đâm người gây thương tích +{ 0 : N0 } với { title }"
    healed = auto_heal_tokens(raw)
    assert healed == "Đâm người gây thương tích +{0:N0} với {title}"


def test_auto_heal_spaced_closing_tags():
    """Auto-healer fixes whitespace in closing rich text tags like </ color >."""
    raw = "<color=#FF0000>Văn bản</ color >"
    healed = auto_heal_tokens(raw)
    assert healed == "<color=#FF0000>Văn bản</color>"


def test_auto_heal_bracketed_params():
    """Auto-healer fixes whitespace in bracketed parameters [ { 0 } ] and [ 0 ]."""
    raw = "Trang bị [ { 0 } ] và [ {0} ] cùng [ { title } ] hay [ 0 ]"
    healed = auto_heal_tokens(raw)
    assert healed == "Trang bị [{0}] và [{0}] cùng [{title}] hay [0]"


def test_auto_heal_opening_rich_text_tags():
    """Auto-healer fixes whitespace in opening tags with and without attributes."""
    raw = "< color = #FF0000 >Văn bản đỏ</color> và < b >chữ đậm</b> với < size = 20 >chữ to</size>"
    healed = auto_heal_tokens(raw)
    assert healed == "<color=#FF0000>Văn bản đỏ</color> và <b>chữ đậm</b> với <size=20>chữ to</size>"


def test_auto_heal_combined_sentence():
    """Auto-healer correctly heals multiple spaced artifacts in a single sentence."""
    raw = "Sát thương +{ 0 : N0 }[ || ]Nhận < color = #00FF00 >[ { 1 } ]</ color >[ | ]Hết"
    healed = auto_heal_tokens(raw)
    assert healed == "Sát thương +{0:N0}[||]Nhận <color=#00FF00>[{1}]</color>[|]Hết"


# =====================================================================
# 2. Baseline Regression Tests (Preserving Existing Behavior)
# =====================================================================

def test_validate_clean_translation():
    """Valid translation with matching tokens passes cleanly."""
    orig = "造成伤害+{0:N0}，获得[|][||]{title}"
    trans = "Gây sát thương +{ 0 : N0 }, nhận được[ || ][ | ]{ title }"

    res = soft_validate_translation(orig, trans)
    assert res.is_clean is True
    assert res.is_hard_valid is True
    assert res.is_soft_valid is True
    assert len(res.missing_tokens) == 0
    assert len(res.warning_messages) == 0
    assert res.healed_text == "Gây sát thương +{0:N0}, nhận được[||][|]{title}"


def test_validate_detects_missing_injected_breaks():
    """Soft validator detects when an LLM drops [||]."""
    orig = "第一行[||]第二行"
    trans = "Dòng 1 Dòng 2"  # Dropped [||]

    res = soft_validate_translation(orig, trans)
    assert res.is_clean is False
    assert res.is_hard_valid is False
    assert "[||]" in res.missing_tokens
    assert any("Missing required tokens" in w for w in res.warning_messages)


def test_validate_detects_missing_game_engine_token():
    """Soft validator detects when an LLM drops or alters {0:N0}."""
    orig = "伤害+{0:N0}"
    trans = "Sát thương +0"  # Dropped {0:N0}

    res = soft_validate_translation(orig, trans)
    assert res.is_clean is False
    assert res.is_hard_valid is False
    assert "{0:N0}" in res.missing_tokens


def test_validate_detects_lingering_cjk_characters():
    """Soft validator flags lingering untranslated Chinese characters."""
    orig = "你好，世界"
    trans = "Xin chào，世界"  # Left '世界' untranslated

    res = soft_validate_translation(orig, trans)
    assert res.has_untranslated_cjk is True
    assert res.is_clean is False
    assert res.is_soft_valid is False
    assert res.is_hard_valid is True  # Only soft failure
    assert any("untranslated Chinese characters" in w for w in res.warning_messages)


# =====================================================================
# 3. Hard Validator Unit Tests
# =====================================================================

def test_output_existence_empty_and_whitespace():
    """Rejects empty string, whitespace only, or None."""
    orig = "你好"
    res_empty = validate_translation(orig, "")
    assert res_empty.is_hard_valid is False
    assert res_empty.is_clean is False
    assert any(i.category == "output_existence" for i in res_empty.issues)

    res_ws = validate_translation(orig, "   \n\t   ")
    assert res_ws.is_hard_valid is False


@pytest.mark.parametrize("placeholder", ["null", "None", "nil", "undefined", "[empty]", "TODO", "(trống)"])
def test_output_existence_placeholders(placeholder: str):
    """Rejects placeholder tokens as empty outputs."""
    orig = "你好"
    res = validate_translation(orig, placeholder)
    assert res.is_hard_valid is False
    assert any(i.category == "output_existence" for i in res.issues)


def test_token_integrity_non_overlapping_brackets():
    """Verifies that [{0}] does not collide with {0}."""
    orig = "造成伤害[{0}]，附加{0}点"
    # LLM correctly preserved both
    trans_valid = "Gây sát thương [{0}], cộng {0} điểm"
    res_valid = validate_translation(orig, trans_valid)
    assert res_valid.is_hard_valid is True
    assert len(res_valid.missing_tokens) == 0

    # LLM dropped brackets from [{0}], returning '{0}' twice
    trans_missing_bracket = "Gây sát thương {0}, cộng {0} điểm"
    res_invalid = validate_translation(orig, trans_missing_bracket)
    assert res_invalid.is_hard_valid is False
    assert "[{0}]" in res_invalid.missing_tokens
    assert "{0}" not in res_invalid.missing_tokens  # {0} itself was not missing


def test_token_integrity_extra_tokens():
    """Unexpected extra tokens are tracked in extra_tokens."""
    orig = "Xin chào"
    trans = "Xin chào[||]"  # Injected unexpected [||]
    res = validate_translation(orig, trans)
    assert "[||]" in res.extra_tokens
    assert any("Unexpected extra tokens" in w for w in res.warning_messages)


def test_rich_text_unclosed_tag():
    """Flags unclosed rich-text opening tag as Hard error."""
    orig = "<b>Văn bản gốc</b>"
    trans = "<b>Văn bản dịch"  # Missing </b>
    res = validate_translation(orig, trans)
    assert res.is_hard_valid is False
    assert any(i.category == "rich_text_tag_integrity" for i in res.issues)
    assert len(res.corrupted_tags) > 0


def test_rich_text_unmatched_closing_tag():
    """Flags closing rich-text tag without matching opening tag as Hard error."""
    orig = "Văn bản gốc"
    trans = "Văn bản dịch</b>"  # Extra </b>
    res = validate_translation(orig, trans)
    assert res.is_hard_valid is False
    assert any("không có thẻ mở tương ứng" in tag for tag in res.corrupted_tags)


def test_rich_text_mismatched_nesting():
    """Flags mismatched tag nesting order as Hard error."""
    orig = "<b><color=#FF0000>Văn bản gốc</color></b>"
    trans = "<b><color=#FF0000>Văn bản dịch</b></color>"  # Inverted closing tags
    res = validate_translation(orig, trans)
    assert res.is_hard_valid is False
    assert any("không khớp thứ tự lồng" in tag for tag in res.corrupted_tags)


def test_rich_text_missing_or_altered_attribute():
    """Flags missing or modified color attributes as Hard error."""
    orig = "<color=#FF0000>Cảnh báo</color>"
    trans = "<color>Cảnh báo</color>"  # Dropped =#FF0000
    res = validate_translation(orig, trans)
    assert res.is_hard_valid is False
    assert any("Thiếu hoặc sai thuộc tính" in tag for tag in res.corrupted_tags)


def test_rich_text_void_tags_valid():
    """Void / self-closing tags like <sprite> do not require closing tags."""
    orig = "Nhận được <sprite name=gold> vàng"
    trans = "Nhận được <sprite name=gold> vàng"
    res = validate_translation(orig, trans)
    assert res.is_hard_valid is True
    assert len(res.corrupted_tags) == 0


# =====================================================================
# 4. Soft Validator Unit Tests
# =====================================================================

def test_lingering_cjk_extended_blocks():
    """Detects Chinese characters in Extension A (\\u3400-\\u4dbf) and Compatibility (\\uf900-\\ufaff)."""
    orig = "Kiểm tra chữ hiếm"
    trans_ext_a = "Dịch chữ hiếm: \u3400"  # Extension A char
    res_a = validate_translation(orig, trans_ext_a)
    assert res_a.is_soft_valid is False
    assert res_a.has_untranslated_cjk is True

    trans_compat = "Dịch chữ trùng: \uf90e"  # Compatibility char
    res_c = validate_translation(orig, trans_compat)
    assert res_c.is_soft_valid is False
    assert res_c.has_untranslated_cjk is True


def test_verbatim_identity_detection():
    """Echoing Chinese dialogue without translation triggers Soft error."""
    orig = "唐门弟子听令，准备迎敌！"
    trans = "唐门弟子听令，准备迎敌！"
    res = validate_translation(orig, trans)
    assert res.is_soft_valid is False
    assert any(i.category == "verbatim_identity" for i in res.issues)


def test_verbatim_identity_exemption_numeric_ascii():
    """Echoing numeric or ASCII keys is exempted and does not trigger error."""
    orig = "100"
    trans = "100"
    res = validate_translation(orig, trans)
    assert res.is_clean is True
    assert not any(i.category == "verbatim_identity" for i in res.issues)


def test_glossary_compliance_success():
    """Translation containing all injected glossary terms passes."""
    orig = "赵活来到了唐门"
    trans = "Triệu Hoạt đã đến Đường Môn"
    glossary = [("赵活", "Triệu Hoạt"), ("唐门", "Đường Môn")]

    res = validate_translation(orig, trans, glossary_matches=glossary)
    assert res.is_soft_valid is True
    assert len(res.missing_glossary) == 0


def test_glossary_compliance_missing():
    """Translation omitting an injected glossary term fails Soft validation."""
    orig = "赵活来到了唐门"
    trans = "Tiểu Hoạt đã đến phái họ Đường"  # Missed 'Triệu Hoạt' and 'Đường Môn'
    glossary = [("赵活", "Triệu Hoạt"), ("唐门", "Đường Môn")]

    res = validate_translation(orig, trans, glossary_matches=glossary)
    assert res.is_soft_valid is False
    assert any("赵活=Triệu Hoạt" in term for term in res.missing_glossary)
    assert any("唐门=Đường Môn" in term for term in res.missing_glossary)


def test_glossary_compliance_dict_format():
    """Supports glossary matches passed as list of dicts."""
    orig = "南宫伯伯"
    trans = "Nam Cung bá bá"
    glossary = [{"Original": "南宫伯伯", "Translated": "Nam Cung bá bá"}]

    res = validate_translation(orig, trans, glossary_matches=glossary)
    assert res.is_soft_valid is True
    assert len(res.missing_glossary) == 0


def test_glossary_compliance_case_insensitive():
    """Glossary matching is case-insensitive."""
    orig = "唐门"
    trans = "đường môn"  # Lowercase
    glossary = [("唐门", "Đường Môn")]

    res = validate_translation(orig, trans, glossary_matches=glossary)
    assert res.is_soft_valid is True


def test_length_ratio_normal_truncated():
    """Fails Soft validation if translation is severely truncated (ratio < 0.3)."""
    orig = "唐门始建于开元初年，乃是蜀中武林大派，以暗器毒药威震天下。"  # 28 chars
    trans = "Được."  # 5 chars -> ratio = 0.18 < 0.3
    res = validate_translation(orig, trans)
    assert res.is_soft_valid is False
    assert any(i.category == "length_ratio" for i in res.issues)


def test_length_ratio_normal_bloated():
    """Fails Soft validation if translation contains hallucinated commentary (ratio > 6.0)."""
    orig = "你好，掌门。"  # 6 chars
    trans = (
        "Xin chào chưởng môn nhân tôn kính của môn phái. "
        "Đây là lời chào hỏi kính cẩn theo nghi thức võ lâm thời xưa của Trung Quốc, "
        "thể hiện lòng tôn kính sâu sắc đối với người đứng đầu một giáo phái."
    )  # 204 chars -> ratio = 34.0 > 6.0
    res = validate_translation(orig, trans)
    assert res.is_soft_valid is False
    assert any(i.category == "length_ratio" for i in res.issues)


def test_length_ratio_normal_valid():
    """Normal translation length ratio (typically 1.5x - 4.0x) passes cleanly."""
    orig = "唐门始建于开元初年。"  # 10 chars
    trans = "Đường Môn được thành lập vào những năm đầu Khai Nguyên."  # 55 chars -> ratio 5.5
    res = validate_translation(orig, trans)
    assert not any(i.category == "length_ratio" for i in res.issues)


def test_length_ratio_short_phrase_valid():
    """Short phrases (< 6 chars) under 60 chars are not falsely flagged."""
    orig = "走"  # 1 char
    trans = "Đi thôi"  # 7 chars -> ratio 7.0, but <= 60 chars
    res = validate_translation(orig, trans)
    assert not any(i.category == "length_ratio" for i in res.issues)


def test_length_ratio_short_phrase_bloated():
    """Short phrases bloated beyond 60 chars fail Soft validation."""
    orig = "走"
    trans = "Đi thôi, mau mau cất bước rời khỏi nơi nguy hiểm này trước khi kẻ thù ập đến."  # 78 chars
    res = validate_translation(orig, trans)
    assert res.is_soft_valid is False
    assert any(i.category == "length_ratio" for i in res.issues)


# =====================================================================
# 5. Integration, Diagnostics & Backward Compatibility Tests
# =====================================================================

def test_diagnostic_feedback_formatting():
    """Verifies that diagnostic_feedback formats Vietnamese instructions with emojis."""
    orig = "获得技能+{0:N0}，前往唐门"
    trans = "Nhận kỹ năng, đi đến 唐门"  # Missing {0:N0}, missed glossary, untranslated CJK
    glossary = [("唐门", "Đường Môn")]

    res = validate_translation(orig, trans, glossary_matches=glossary)
    feedback = res.diagnostic_feedback

    assert "[LƯU Ý LỖI BẢN DỊCH TRƯỚC VÀ YÊU CẦU SỬA ĐỔI]:" in feedback
    assert "❌ [LỖI KÝ HIỆU HỆ THỐNG]" in feedback
    assert "⚠️ [CẢNH BÁO SÓT CHỮ HÁN]" in feedback
    assert "⚠️ [CẢNH BÁO THUẬT NGỮ BẮT BUỘC]" in feedback
    assert "Vui lòng dịch lại câu thoại trên" in feedback


def test_validation_result_default_instantiation():
    """Verifies ValidationResult can be instantiated with healed_text only for backward compatibility."""
    res = ValidationResult(healed_text="Văn bản dịch")
    assert res.healed_text == "Văn bản dịch"
    assert res.is_hard_valid is True
    assert res.is_soft_valid is True
    assert res.is_clean is True
    assert len(res.missing_tokens) == 0
    assert len(res.warning_messages) == 0
    assert res.diagnostic_feedback == ""
