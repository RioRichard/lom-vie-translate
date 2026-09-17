"""Tests for text preprocessing and postprocessing (DEF-11)."""

from __future__ import annotations

from lom_translate.text import postprocess_text, preprocess_text


def test_preprocess_encodes_crlf():
    """Preprocessing replaces \\r with [|] and \\n with [||]."""
    raw = "Line 1\r\nLine 2\nLine 3"
    pre = preprocess_text(raw)
    assert pre == "Line 1[|][||]Line 2[||]Line 3"


def test_postprocess_restores_linebreaks():
    """Postprocessing restores [|] to \\r and [||] to \\n."""
    encoded = "Dòng 1[|][||]Dòng 2[||]Dòng 3"
    post = postprocess_text(encoded)
    assert post == "Dòng 1\r\nDòng 2\nDòng 3"


def test_postprocess_preserves_paragraph_breaks():
    """DEF-11: Double newlines (paragraph breaks) must NOT be collapsed into single newlines."""
    text_with_paragraphs = "Đoạn văn 1.\n\nĐoạn văn 2.\n\nĐoạn văn 3."
    post = postprocess_text(text_with_paragraphs)
    assert "\n\n" in post
    assert post.count("\n\n") == 2


def test_postprocess_strips_markdown_bold_and_prefix():
    """Postprocessing removes markdown asterisks and model commentary prefix."""
    raw = "**Đây là bản dịch:\n**Nam Cung gia gia"
    cleaned = postprocess_text(raw)
    assert cleaned == "Nam Cung gia gia"
    assert "**" not in cleaned
