"""Tests for translator engine (DEF-03, rotation, and soft validation)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from lom_translate import config as cfg
from lom_translate.client import LLMClientPool
from lom_translate.translator import translate_text


@pytest.mark.asyncio
async def test_translate_text_success_with_rotation(sample_app_config):
    """Translating text rotates to next model and returns postprocessed translation."""
    cfg.set_config(sample_app_config)
    pool = LLMClientPool.from_task(sample_app_config, "translate")

    # Mock LLM generation
    with (
        patch.object(pool.clients[0], "generate", new_callable=AsyncMock) as mock_gen1,
        patch.object(pool.clients[1], "generate", new_callable=AsyncMock) as mock_gen2,
    ):
        mock_gen1.return_value = "Bản dịch 1[||]Dòng 2"
        mock_gen2.return_value = "Bản dịch 2[||]Dòng 2"

        # First call hits model 0
        t1, dur1, val1 = await translate_text("原文1[||]第二行", "entry_1", "prompt_1", pool)
        assert t1 == "Bản dịch 1\nDòng 2"
        assert val1.is_clean is True
        mock_gen1.assert_called_once()
        mock_gen2.assert_not_called()

        # Second call rotates to model 1
        t2, dur2, val2 = await translate_text("原文2[||]第二行", "entry_2", "prompt_2", pool)
        assert t2 == "Bản dịch 2\nDòng 2"
        mock_gen2.assert_called_once()


@pytest.mark.asyncio
async def test_translate_text_rotates_immediately_on_failure(sample_app_config):
    """If primary model fails, translator rotates immediately to next model in pool."""
    cfg.set_config(sample_app_config)
    pool = LLMClientPool.from_task(sample_app_config, "translate")

    with (
        patch.object(pool.clients[0], "generate", new_callable=AsyncMock) as mock_gen1,
        patch.object(pool.clients[1], "generate", new_callable=AsyncMock) as mock_gen2,
    ):
        # Model 1 raises exception
        mock_gen1.side_effect = RuntimeError("API error on primary")
        # Model 2 succeeds
        mock_gen2.return_value = "Bản dịch thành công"

        t, dur, val = await translate_text("原文", "entry_err", "prompt", pool)
        assert t == "Bản dịch thành công"
        assert mock_gen1.call_count == 1
        assert mock_gen2.call_count == 1


@pytest.mark.asyncio
async def test_translate_text_returns_original_on_total_failure(sample_app_config):
    """If all models exhaust retries, returns original text without crashing."""
    cfg.set_config(sample_app_config)
    pool = LLMClientPool.from_task(sample_app_config, "translate")

    with (
        patch.object(pool.clients[0], "generate", new_callable=AsyncMock) as mock_gen1,
        patch.object(pool.clients[1], "generate", new_callable=AsyncMock) as mock_gen2,
    ):
        mock_gen1.side_effect = RuntimeError("Fatal error 1")
        mock_gen2.side_effect = RuntimeError("Fatal error 2")

        t, dur, val = await translate_text("原文不能翻译", "entry_fatal", "prompt", pool)
        assert t == "原文不能翻译"
