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
