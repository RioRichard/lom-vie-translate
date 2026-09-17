"""Tests for file pipeline processing (DEF-09, DEF-14)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from lom_translate import config as cfg
from lom_translate.client import LLMClientPool
from lom_translate.glossary import Glossary
from lom_translate.pipeline import run_pipeline


@pytest.mark.asyncio
async def test_pipeline_translates_and_writes_atomically(tmp_path, sample_app_config, sample_schema_a_dict):
    """Pipeline processes file and writes output atomically with correct schema."""
    cfg.set_config(sample_app_config)

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output" / "json"

    # Write input file
    input_file = input_dir / "test_a.json"
    input_file.write_text(json.dumps(sample_schema_a_dict), encoding="utf-8")

    pool = LLMClientPool.from_task(sample_app_config, "translate")
    glossary = Glossary()

    with patch("lom_translate.translator.translate_text", new_callable=AsyncMock) as mock_trans:
        from lom_translate.validation import ValidationResult

        mock_trans.return_value = (
            "Dịch: Nam Cung bá bá\r\nChúc phúc",
            0.1,
            ValidationResult(healed_text="Dịch: Nam Cung bá bá\r\nChúc phúc"),
        )

        stats = await run_pipeline(
            input_dir=input_dir,
            output_dir=output_dir,
            client_pool=pool,
            glossary=glossary,
            mode="translate",
        )

        assert stats["total_entries"] == 2
        assert len(stats["failed_files"]) == 0

        # Check output file exists and preserves Schema A structure
        out_file = output_dir / "test_a.json"
        assert out_file.exists()
        out_data = json.loads(out_file.read_text(encoding="utf-8"))
        assert "entries" in out_data
        assert "Array" in out_data["entries"]
        assert len(out_data["entries"]["Array"]) == 2
        assert out_data["entries"]["Array"][0]["Speaker"] == "HuynhNhi"
        assert out_data["entries"]["Array"][0]["Voice"] == "voice_101.wav"

        # Check artifacts created in sibling directories
        details_file = output_dir.parent / "details" / "translation_details.json"
        assert details_file.exists()
        pairs_file = output_dir.parent / "pairs" / "translation_pairs.txt"
        assert pairs_file.exists()


@pytest.mark.asyncio
async def test_pipeline_skips_non_chinese_simplified(tmp_path, sample_app_config):
    """DEF-09: Files with Language != ChineseSimplified are skipped without error."""
    cfg.set_config(sample_app_config)

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output" / "json"

    file_en = input_dir / "english.json"
    file_en.write_text(json.dumps({"Language": "English", "entries": []}), encoding="utf-8")

    pool = LLMClientPool.from_task(sample_app_config, "translate")
    glossary = Glossary()

    _ = await run_pipeline(
        input_dir=input_dir,
        output_dir=output_dir,
        client_pool=pool,
        glossary=glossary,
        mode="translate",
    )

    assert not (output_dir / "english.json").exists()


@pytest.mark.asyncio
async def test_pipeline_tracks_failed_files(tmp_path, sample_app_config):
    """DEF-14: Corrupted files are captured in stats['failed_files'] instead of aborting the run."""
    cfg.set_config(sample_app_config)

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output" / "json"

    # Malformed JSON file
    corrupt_file = input_dir / "corrupt.json"
    corrupt_file.write_text("{ invalid json here...", encoding="utf-8")

    pool = LLMClientPool.from_task(sample_app_config, "translate")
    glossary = Glossary()

    stats = await run_pipeline(
        input_dir=input_dir,
        output_dir=output_dir,
        client_pool=pool,
        glossary=glossary,
        mode="translate",
    )

    assert len(stats["failed_files"]) == 1
    assert str(corrupt_file) in stats["failed_files"][0]


@pytest.mark.asyncio
async def test_pipeline_passes_preprocessed_text_and_glossary_matches(tmp_path, sample_app_config):
    """Verify pipeline passes [|]/[||] preprocessed text and glossary_matches to translate_text."""
    cfg.set_config(sample_app_config)

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output" / "json"

    # Input file with CRLF linebreaks and glossary term
    schema_a = {
        "Language": "ChineseSimplified",
        "entries": {
            "Array": [
                {
                    "Id": 301,
                    "Name": "Story/BreakTest",
                    "Text": "唐门秘籍。\r\n不可轻传。",
                    "Speaker": "ZhaoHuo",
                }
            ]
        },
    }
    (input_dir / "break_test.json").write_text(json.dumps(schema_a), encoding="utf-8")

    pool = LLMClientPool.from_task(sample_app_config, "translate")
    glossary = Glossary()
    glossary.original_to_translated["唐门"] = "Đường Môn"
    glossary._build_automaton()

    captured_calls = []

    async def mock_translate_text(text, name, prompt, client_pool, glossary_matches=None, soft_max_retries=None):
        captured_calls.append({"text": text, "glossary_matches": glossary_matches})
        from lom_translate.validation import ValidationResult

        return (
            "Đường Môn bí kíp.\r\nKhông thể truyền bừa.",
            0.05,
            ValidationResult(healed_text="Đường Môn bí kíp.[|][||]Không thể truyền bừa."),
        )

    with patch("lom_translate.pipeline.translate_text", side_effect=mock_translate_text):
        stats = await run_pipeline(
            input_dir=input_dir,
            output_dir=output_dir,
            client_pool=pool,
            glossary=glossary,
            mode="translate",
        )

        assert len(captured_calls) == 1
        # 1. Verify text passed to translate_text contains [|] and [||]
        assert "[|]" in captured_calls[0]["text"]
        assert "[||]" in captured_calls[0]["text"]
        assert "唐门秘籍。[|][||]不可轻传。" == captured_calls[0]["text"]

        # 2. Verify glossary_matches was forwarded
        assert captured_calls[0]["glossary_matches"] is not None
        assert any(orig == "唐门" for orig, _ in captured_calls[0]["glossary_matches"])

        # 3. Verify output file restored clean newlines
        out_file = output_dir / "break_test.json"
        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        out_entry = data["entries"]["Array"][0]
        assert "\r\n" in out_entry["Text"] or "\n" in out_entry["Text"]
        assert "[|]" not in out_entry["Text"]


@pytest.mark.asyncio
async def test_pipeline_tracks_soft_validation_warnings(tmp_path, sample_app_config):
    """Verify run_stats['token_warnings'] is incremented when soft warnings occur."""
    cfg.set_config(sample_app_config)

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output" / "json"

    file_data = {
        "Language": "ChineseSimplified",
        "entries": [{"Id": 401, "Name": "Story/CjkWarning", "Text": "简单的句子"}],
    }
    (input_dir / "warn_test.json").write_text(json.dumps(file_data), encoding="utf-8")

    pool = LLMClientPool.from_task(sample_app_config, "translate")
    glossary = Glossary()

    with patch("lom_translate.pipeline.translate_text", new_callable=AsyncMock) as mock_trans:
        from lom_translate.validation import ValidationResult

        # Return candidate that is not clean (soft warning accepted)
        mock_trans.return_value = (
            "Câu dịch còn 世界",
            0.1,
            ValidationResult(healed_text="Câu dịch còn 世界", is_clean=False, has_untranslated_cjk=True),
        )

        stats = await run_pipeline(
            input_dir=input_dir,
            output_dir=output_dir,
            client_pool=pool,
            glossary=glossary,
            mode="translate",
        )

        assert stats["token_warnings"] >= 1
        assert (output_dir / "warn_test.json").exists()


@pytest.mark.asyncio
async def test_pipeline_hard_fallback_preserves_surrounding_entries(tmp_path, sample_app_config):
    """When one entry permanently fails, fallback preserves original text without aborting other entries."""
    cfg.set_config(sample_app_config)

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output" / "json"

    file_data = {
        "Language": "ChineseSimplified",
        "entries": {
            "Array": [
                {"Id": 501, "Name": "Entry_1", "Text": "第一句", "Speaker": "S1"},
                {"Id": 502, "Name": "Entry_2_Fatal", "Text": "致命错误句", "Speaker": "S2"},
                {"Id": 503, "Name": "Entry_3", "Text": "第三句", "Speaker": "S3"},
            ]
        },
    }
    (input_dir / "multi_test.json").write_text(json.dumps(file_data), encoding="utf-8")

    pool = LLMClientPool.from_task(sample_app_config, "translate")
    glossary = Glossary()

    async def mock_translate(text, name, prompt, client_pool, glossary_matches=None, soft_max_retries=None):
        from lom_translate.validation import ValidationResult

        if "Fatal" in name:
            # Fallback returns original text
            return text, 0.1, ValidationResult(healed_text=text, is_clean=False)
        return f"Dịch {name}", 0.05, ValidationResult(healed_text=f"Dịch {name}", is_clean=True)

    with patch("lom_translate.pipeline.translate_text", side_effect=mock_translate):
        stats = await run_pipeline(
            input_dir=input_dir,
            output_dir=output_dir,
            client_pool=pool,
            glossary=glossary,
            mode="translate",
        )

        assert stats["total_entries"] == 3
        out_file = output_dir / "multi_test.json"
        data = json.loads(out_file.read_text(encoding="utf-8"))
        entries = data["entries"]["Array"]

        assert entries[0]["Text"] == "Dịch Entry_1"
        assert entries[1]["Text"] == "致命错误句"  # Preserved original text
        assert entries[2]["Text"] == "Dịch Entry_3"
        # Metadata preserved
        assert entries[1]["Speaker"] == "S2"

