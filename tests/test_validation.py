"""Tests for soft validators and token integrity."""

from __future__ import annotations

from lom_translate.validation import auto_heal_tokens, soft_validate_translation


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


def test_validate_clean_translation():
    """Valid translation with matching tokens passes cleanly."""
    orig = "造成伤害+{0:N0}，获得[|][||]{title}"
    trans = "Gây sát thương +{ 0 : N0 }, nhận được[ || ][ | ]{ title }"

    res = soft_validate_translation(orig, trans)
    assert res.is_clean is True
    assert len(res.missing_tokens) == 0
    assert len(res.warning_messages) == 0
    assert res.healed_text == "Gây sát thương +{0:N0}, nhận được[||][|]{title}"


def test_validate_detects_missing_injected_breaks():
    """Soft validator detects when an LLM drops [||]."""
    orig = "第一行[||]第二行"
    trans = "Dòng 1 Dòng 2"  # Dropped [||]

    res = soft_validate_translation(orig, trans)
    assert res.is_clean is False
    assert "[||]" in res.missing_tokens
    assert any("Missing required tokens" in w for w in res.warning_messages)


def test_validate_detects_missing_game_engine_token():
    """Soft validator detects when an LLM drops or alters {0:N0}."""
    orig = "伤害+{0:N0}"
    trans = "Sát thương +0"  # Dropped {0:N0}

    res = soft_validate_translation(orig, trans)
    assert res.is_clean is False
    assert "{0:N0}" in res.missing_tokens


def test_validate_detects_lingering_cjk_characters():
    """Soft validator flags lingering untranslated Chinese characters."""
    orig = "你好，世界"
    trans = "Xin chào，世界"  # Left '世界' untranslated

    res = soft_validate_translation(orig, trans)
    assert res.has_untranslated_cjk is True
    assert res.is_clean is False
    assert any("untranslated Chinese characters" in w for w in res.warning_messages)
