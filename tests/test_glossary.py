"""Tests for glossary loading and Aho-Corasick matching (DEF-10, DEF-15)."""

from __future__ import annotations

import json

import pytest

from lom_translate.glossary import Glossary


@pytest.mark.asyncio
async def test_dict_glossary_populates_both_maps(tmp_path):
    """DEF-10: Dictionary format glossaries must populate BOTH name and original mapping tables."""
    glossary_file = tmp_path / "dict_glossary.json"
    data = {
        "唐门": "Đường Môn",
        "赵活": "Triệu Hoạt",
        "南宫世家": "Nam Cung Thế Gia",
    }
    glossary_file.write_text(json.dumps(data), encoding="utf-8")

    glossary = Glossary()
    await glossary.load(path=glossary_file)

    assert glossary.get_by_name("唐门") == "Đường Môn"
    assert glossary.get_by_name("赵活") == "Triệu Hoạt"
    assert "唐门" in glossary.original_to_translated
    assert "赵活" in glossary.original_to_translated
    assert glossary.original_to_translated["唐门"] == "Đường Môn"


@pytest.mark.asyncio
async def test_list_glossary_loading(tmp_path):
    """List of objects format populates name and original tables."""
    glossary_file = tmp_path / "list_glossary.json"
    data = [
        {"Name": "Item_Sword", "Original": "重剑", "Translated": "Trọng Kiếm"},
        {"Name": "NPC_Master", "Original": "掌门", "Translated": "Chưởng Môn"},
    ]
    glossary_file.write_text(json.dumps(data), encoding="utf-8")

    glossary = Glossary()
    await glossary.load(path=glossary_file)

    assert glossary.get_by_name("Item_Sword") == "Trọng Kiếm"
    assert glossary.original_to_translated["重剑"] == "Trọng Kiếm"


@pytest.mark.asyncio
async def test_txt_glossary_loading(tmp_path):
    """Text format (key=value) loads properly."""
    glossary_file = tmp_path / "glossary.txt"
    glossary_file.write_text("飞石=Phi Thạch\n毒术=Độc Thuật\n", encoding="utf-8")

    glossary = Glossary()
    await glossary.load(path=glossary_file)

    assert glossary.original_to_translated["飞石"] == "Phi Thạch"
    assert glossary.original_to_translated["毒术"] == "Độc Thuật"


@pytest.mark.asyncio
async def test_aho_corasick_longest_match_deduplication(tmp_path):
    """DEF-15: Longest matches take precedence and shorter substrings within them are deduplicated."""
    glossary_file = tmp_path / "terms.json"
    data = {
        "南宫": "Nam Cung",
        "南宫世家": "Nam Cung Thế Gia",
        "门": "Môn",
        "唐门": "Đường Môn",
    }
    glossary_file.write_text(json.dumps(data), encoding="utf-8")

    glossary = Glossary()
    await glossary.load(path=glossary_file)

    sentence = "唐门弟子拜会南宫世家"
    matches = glossary.find_matches(sentence)
    matched_originals = [m[0] for m in matches]

    # '唐门' matched -> '门' should not be separately matched
    assert "唐门" in matched_originals
    assert "门" not in matched_originals

    # '南宫世家' matched -> '南宫' should not be separately matched
    assert "南宫世家" in matched_originals
    assert "南宫" not in matched_originals
