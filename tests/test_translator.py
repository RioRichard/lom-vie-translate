"""Comprehensive tests for translator engine: dual-budget state machine, loop prevention, and rotation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from lom_translate import config as cfg
from lom_translate.client import LLMClientPool
from lom_translate.models import AppConfig, ModelConfig, Settings
from lom_translate.translator import translate_text


@pytest.fixture
def translator_test_config() -> AppConfig:
    """Config with two models with max_retries=2 each for testing bounded retries."""
    return AppConfig(
        models=[
            ModelConfig(
                id="model-primary",
                url="http://localhost:8000/v1",
                api_key="test-key-1",
                model_name="test-llm-1",
                max_retries=2,
                limit_per_minute=60,
                rate_limit_delay=0.001,
                rate_limit_if_quota_exceeded=0.01,
            ),
            ModelConfig(
                id="model-secondary",
                url="http://localhost:8001/v1",
                api_key="test-key-2",
                model_name="test-llm-2",
                max_retries=2,
                limit_per_minute=60,
                rate_limit_delay=0.001,
                rate_limit_if_quota_exceeded=0.01,
            ),
        ],
        task_assignments={
            "translate": ["model-primary", "model-secondary"],
        },
        settings=Settings(
            max_concurrent=2,
            max_concurrent_files=2,
            max_global_retries=1,
            soft_validation_max_retries=2,
        ),
    )


# =====================================================================
# Baseline Regression Tests
# =====================================================================

@pytest.mark.asyncio
async def test_translate_text_success_with_rotation(sample_app_config):
    """Translating text rotates to next model and returns postprocessed translation."""
    cfg.set_config(sample_app_config)
    pool = LLMClientPool.from_task(sample_app_config, "translate")

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
        mock_gen1.side_effect = RuntimeError("API error on primary")
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


# =====================================================================
# Dual-Budget & State Machine Execution Tests
# =====================================================================

@pytest.mark.asyncio
async def test_translate_text_clean_pass_immediately(translator_test_config):
    """Path 1: Clean output passes immediately on first call without rotation or retries."""
    cfg.set_config(translator_test_config)
    pool = LLMClientPool.from_task(translator_test_config, "translate")

    with (
        patch.object(pool.clients[0], "generate", new_callable=AsyncMock) as mock_gen1,
        patch.object(pool.clients[1], "generate", new_callable=AsyncMock) as mock_gen2,
    ):
        mock_gen1.return_value = "Xin chào đại hiệp[||]Chúc phúc"
        mock_gen2.return_value = "Never called"

        translated, duration, val = await translate_text(
            text="你好大侠[||]祝福",
            name="Dialog/Clean",
            prompt="Base prompt",
            client_pool=pool,
        )

        assert translated == "Xin chào đại hiệp\nChúc phúc"
        assert val.is_clean is True
        assert val.is_hard_valid is True
        assert val.is_soft_valid is True
        assert mock_gen1.call_count == 1
        assert mock_gen2.call_count == 0


@pytest.mark.asyncio
async def test_translate_text_soft_failure_two_retries_then_accept(translator_test_config):
    """Path 2: Soft failure (lingering CJK) re-prompts 2 times, then accepts with warnings."""
    cfg.set_config(translator_test_config)
    pool = LLMClientPool.from_task(translator_test_config, "translate")

    with (
        patch.object(pool.clients[0], "generate", new_callable=AsyncMock) as mock_gen1,
        patch.object(pool.clients[1], "generate", new_callable=AsyncMock) as mock_gen2,
    ):
        # Model 0 produces CJK on call 1 and call 3; Model 1 produces CJK on call 2
        mock_gen1.side_effect = ["Xin chào 世界", "Xin chào 世界 lần 3"]
        mock_gen2.side_effect = ["Xin chào 世界 lần 2"]

        translated, duration, val = await translate_text(
            text="你好世界",
            name="Dialog/SoftCjk",
            prompt="Translate this",
            client_pool=pool,
            soft_max_retries=2,
        )

        # Total calls across pool: exactly 3 (1 initial + 2 soft retries)
        assert mock_gen1.call_count == 2
        assert mock_gen2.call_count == 1
        # Accepted translation contains healed text, but flags warning
        assert "Xin chào 世界" in translated
        assert val.has_untranslated_cjk is True
        assert val.is_clean is False


@pytest.mark.asyncio
async def test_translate_text_soft_failure_recovers_on_retry(translator_test_config):
    """Path 3: Soft failure receives corrective feedback and recovers on second attempt."""
    cfg.set_config(translator_test_config)
    pool = LLMClientPool.from_task(translator_test_config, "translate")

    with (
        patch.object(pool.clients[0], "generate", new_callable=AsyncMock) as mock_gen1,
        patch.object(pool.clients[1], "generate", new_callable=AsyncMock) as mock_gen2,
    ):
        # Call 1 on model 0 has lingering CJK
        mock_gen1.return_value = "Xin chào 世界"
        # Call 2 rotates to model 1 and returns clean translation
        mock_gen2.return_value = "Xin chào thế giới"

        translated, duration, val = await translate_text(
            text="你好世界",
            name="Dialog/Recover",
            prompt="Translate this",
            client_pool=pool,
            soft_max_retries=2,
        )

        assert translated == "Xin chào thế giới"
        assert val.is_clean is True
        assert mock_gen1.call_count == 1
        assert mock_gen2.call_count == 1

        # Verify model 2 received corrective feedback prompt
        call_prompt = mock_gen2.call_args[0][0]
        assert "BẢN DỊCH" in call_prompt or "LỖI" in call_prompt or "CHỮ HÁN" in call_prompt


@pytest.mark.asyncio
async def test_translate_text_hard_failure_rotation(translator_test_config):
    """Path 4: Hard failure (dropped token {0:N0}) rotates model with diagnostic prompt and recovers."""
    cfg.set_config(translator_test_config)
    pool = LLMClientPool.from_task(translator_test_config, "translate")

    with (
        patch.object(pool.clients[0], "generate", new_callable=AsyncMock) as mock_gen1,
        patch.object(pool.clients[1], "generate", new_callable=AsyncMock) as mock_gen2,
    ):
        # Model 0 dropped {0:N0}
        mock_gen1.return_value = "Sát thương +100"
        # Model 1 restores {0:N0}
        mock_gen2.return_value = "Sát thương +{0:N0}"

        translated, duration, val = await translate_text(
            text="伤害+{0:N0}",
            name="Skill/Damage",
            prompt="Translate skill",
            client_pool=pool,
        )

        assert translated == "Sát thương +{0:N0}"
        assert val.is_hard_valid is True
        assert len(val.missing_tokens) == 0
        assert mock_gen1.call_count == 1
        assert mock_gen2.call_count == 1


@pytest.mark.asyncio
async def test_translate_text_hard_failure_exhaustion_fallback(translator_test_config):
    """Path 5: Hard failure on all models exhausts retry budget; safely falls back to original text."""
    cfg.set_config(translator_test_config)
    pool = LLMClientPool.from_task(translator_test_config, "translate")

    with (
        patch.object(pool.clients[0], "generate", new_callable=AsyncMock) as mock_gen1,
        patch.object(pool.clients[1], "generate", new_callable=AsyncMock) as mock_gen2,
    ):
        # Both models repeatedly drop required tokens
        mock_gen1.return_value = "Bản dịch thiếu token"
        mock_gen2.return_value = "Bản dịch cũng thiếu token"

        original = "原始技能：{title} + {0:N0}"
        translated, duration, val = await translate_text(
            text=original,
            name="Skill/Fatal",
            prompt="Translate",
            client_pool=pool,
        )

        # Fallback returns original text without throwing exceptions
        assert translated == original
        # Both models exhausted their max_retries (2 each = 4 calls total)
        assert mock_gen1.call_count == 2
        assert mock_gen2.call_count == 2


@pytest.mark.asyncio
async def test_translate_text_empty_response_triggers_hard_rotation(translator_test_config):
    """Path 6: Empty response is treated as hard failure, rotating to next model."""
    cfg.set_config(translator_test_config)
    pool = LLMClientPool.from_task(translator_test_config, "translate")

    with (
        patch.object(pool.clients[0], "generate", new_callable=AsyncMock) as mock_gen1,
        patch.object(pool.clients[1], "generate", new_callable=AsyncMock) as mock_gen2,
    ):
        mock_gen1.return_value = ""  # Empty output
        mock_gen2.return_value = "Đã dịch thành công"

        translated, duration, val = await translate_text(
            text="原文",
            name="Dialog/Empty",
            prompt="Translate",
            client_pool=pool,
        )

        assert translated == "Đã dịch thành công"
        assert mock_gen1.call_count == 1
        assert mock_gen2.call_count == 1


@pytest.mark.asyncio
async def test_translate_text_zero_infinite_loops_adversarial_alternating(translator_test_config):
    """Path 7: Alternating Hard/Soft failures strictly terminate within total pool budget."""
    cfg.set_config(translator_test_config)
    pool = LLMClientPool.from_task(translator_test_config, "translate")

    with (
        patch.object(pool.clients[0], "generate", new_callable=AsyncMock) as mock_gen1,
        patch.object(pool.clients[1], "generate", new_callable=AsyncMock) as mock_gen2,
    ):
        # Model 0 returns Hard fail (drops {0:N0})
        # Model 1 returns Soft fail (keeps {0:N0} but leaves CJK)
        mock_gen1.return_value = "Bản dịch thiếu token"
        mock_gen2.return_value = "Bản dịch {0:N0} có 世界"

        translated, duration, val = await translate_text(
            text="伤害+{0:N0}",
            name="Dialog/LoopCheck",
            prompt="Translate",
            client_pool=pool,
            soft_max_retries=2,
        )

        total_calls = mock_gen1.call_count + mock_gen2.call_count
        max_allowed = sum(c.config.max_retries for c in pool.clients)
        # Total calls must never exceed pool capacity
        assert total_calls <= max_allowed
        # Must terminate deterministically
        assert isinstance(translated, str)


@pytest.mark.asyncio
async def test_translate_text_configurable_soft_retries_zero(translator_test_config):
    """Path 8: soft_max_retries=0 accepts soft failures on first attempt without retrying."""
    cfg.set_config(translator_test_config)
    pool = LLMClientPool.from_task(translator_test_config, "translate")

    with (
        patch.object(pool.clients[0], "generate", new_callable=AsyncMock) as mock_gen1,
        patch.object(pool.clients[1], "generate", new_callable=AsyncMock) as mock_gen2,
    ):
        mock_gen1.return_value = "Xin chào 世界"

        translated, duration, val = await translate_text(
            text="你好世界",
            name="Dialog/ZeroSoft",
            prompt="Translate",
            client_pool=pool,
            soft_max_retries=0,
        )

        assert mock_gen1.call_count == 1
        assert mock_gen2.call_count == 0
        assert val.has_untranslated_cjk is True
