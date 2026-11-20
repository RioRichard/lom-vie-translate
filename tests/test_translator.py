from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.config import (
    AppConfig,
    ModelConfig,
    ProviderConfig,
    RouteRef,
    TaskConfig,
    TierConfig,
)
from src.translator import TranslationEngine
from src.utils import build_translation_prompt


def _make_response(content: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _build_engine_config(
    *,
    primary: RouteRef,
    fallbacks: list[RouteRef] | None = None,
    max_global_retries: int = 0,
    local_max_retries: int | None = 2,
    local_cooldown: float = 5.0,
    gemini_max_retries: int | None = None,
    gemini_cooldown: float = 12.0,
    openrouter_cooldown: float = 15.0,
) -> AppConfig:
    return AppConfig(
        providers={
            "local_openai": ProviderConfig(
                api_base="http://localhost:1234/v1",
                timeout=180.0,
                default_api_key="local-no-key",
                tiers={
                    "local": TierConfig(
                        api_key_env="LOCAL_OPENAI_API_KEYS",
                        max_concurrent=2,
                        rate_limit_delay=0.0,
                        quota_cooldown=local_cooldown,
                        max_retries=local_max_retries,
                    ),
                },
                models={
                    "qwen3-14b": ModelConfig(
                        model_id="openai/qwen3-14b",
                        temperature=0.1,
                        max_tokens=1500,
                    ),
                },
            ),
            "gemini": ProviderConfig(
                timeout=60.0,
                tiers={
                    "free": TierConfig(
                        api_key_env="GEMINI_FREE_API_KEYS",
                        max_concurrent=5,
                        rate_limit_delay=0.0,
                        quota_cooldown=gemini_cooldown,
                        max_retries=gemini_max_retries,
                    ),
                },
                models={
                    "gemma-3-27b": ModelConfig(
                        model_id="gemini/gemma-3-27b-it",
                    ),
                },
            ),
            "openrouter": ProviderConfig(
                timeout=90.0,
                tiers={
                    "free": TierConfig(
                        api_key_env="OPENROUTER_FREE_API_KEYS",
                        max_concurrent=3,
                        rate_limit_delay=0.0,
                        quota_cooldown=openrouter_cooldown,
                        model_suffix=":free",
                    ),
                },
                models={
                    "deepseek-v3": ModelConfig(
                        model_id="openrouter/deepseek/deepseek-chat-v3-0324",
                    ),
                },
            ),
        },
        tasks={
            "translate": TaskConfig(
                primary=primary,
                fallbacks=fallbacks or [],
                max_global_retries=max_global_retries,
            ),
        },
    )


async def test_universal_multi_key_rotation_local_and_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1. Local OpenAI-compatible provider with multiple keys rotates round-robin
    monkeypatch.setenv("LOCAL_OPENAI_API_KEYS", "local-key-1, local-key-2, local-key-3")
    local_cfg = _build_engine_config(
        primary=RouteRef(provider="local_openai", tier="local", model="qwen3-14b")
    )
    local_engine = TranslationEngine(local_cfg)

    local_mock = AsyncMock(return_value=_make_response("Xin chào"))
    monkeypatch.setattr("src.translator.litellm.acompletion", local_mock)

    for _ in range(4):
        res = await local_engine.translate_text("你好", task_name="translate")
        assert res.succeeded is True
        assert res.text == "Xin chào"

    local_keys_used = [call.kwargs["api_key"] for call in local_mock.call_args_list]
    assert local_keys_used == ["local-key-1", "local-key-2", "local-key-3", "local-key-1"]

    # 2. Gemini free tier with multiple keys also rotates round-robin
    monkeypatch.setenv("GEMINI_FREE_API_KEYS", "gem-key-a, gem-key-b")
    gemini_cfg = _build_engine_config(
        primary=RouteRef(provider="gemini", tier="free", model="gemma-3-27b")
    )
    gemini_engine = TranslationEngine(gemini_cfg)

    gemini_mock = AsyncMock(return_value=_make_response("Đường Môn"))
    monkeypatch.setattr("src.translator.litellm.acompletion", gemini_mock)

    for _ in range(3):
        res = await gemini_engine.translate_text("唐门", task_name="translate")
        assert res.succeeded is True
        assert res.text == "Đường Môn"

    gemini_keys_used = [call.kwargs["api_key"] for call in gemini_mock.call_args_list]
    assert gemini_keys_used == ["gem-key-a", "gem-key-b", "gem-key-a"]


async def test_keyless_local_provider_uses_api_base_and_default_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOCAL_OPENAI_API_KEYS", raising=False)
    cfg = _build_engine_config(
        primary=RouteRef(provider="local_openai", tier="local", model="qwen3-14b")
    )
    engine = TranslationEngine(cfg)

    mock_completion = AsyncMock(return_value=_make_response("Triệu Hoạt"))
    monkeypatch.setattr("src.translator.litellm.acompletion", mock_completion)

    result = await engine.translate_text("赵活", task_name="translate", name="Hero/Name")

    assert result.succeeded is True
    assert result.text == "Triệu Hoạt"
    assert result.route_used == "local_openai.local.qwen3-14b"

    mock_completion.assert_awaited_once()
    call_kwargs = mock_completion.call_args.kwargs
    assert call_kwargs["api_base"] == "http://localhost:1234/v1"
    assert call_kwargs["api_key"] == "local-no-key"
    assert call_kwargs["model"] == "openai/qwen3-14b"
    assert call_kwargs["num_retries"] == 0


async def test_fallback_chain_recovers_on_second_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOCAL_OPENAI_API_KEYS", raising=False)
    monkeypatch.setenv("GEMINI_FREE_API_KEYS", "gemini-fallback-key")
    cfg = _build_engine_config(
        primary=RouteRef(provider="local_openai", tier="local", model="qwen3-14b"),
        fallbacks=[RouteRef(provider="gemini", tier="free", model="gemma-3-27b")],
        local_max_retries=2,
        max_global_retries=0,
    )
    engine = TranslationEngine(cfg)

    mock_completion = AsyncMock(
        side_effect=[
            RuntimeError("local connection refused 1"),
            RuntimeError("local connection refused 2"),
            _make_response("Bản dịch từ Gemini"),
        ]
    )
    monkeypatch.setattr("src.translator.litellm.acompletion", mock_completion)

    result = await engine.translate_text("测试文本", task_name="translate")

    assert result.succeeded is True
    assert result.text == "Bản dịch từ Gemini"
    assert result.route_used == "gemini.free.gemma-3-27b"
    assert result.error is None
    assert mock_completion.await_count == 3
    assert [c.kwargs["model"] for c in mock_completion.call_args_list] == [
        "openai/qwen3-14b",
        "openai/qwen3-14b",
        "gemini/gemma-3-27b-it",
    ]


async def test_unconfigured_cloud_route_skipped_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_FREE_API_KEYS", raising=False)
    monkeypatch.setenv("OPENROUTER_FREE_API_KEYS", "or-live-key")
    cfg = _build_engine_config(
        primary=RouteRef(provider="gemini", tier="free", model="gemma-3-27b"),
        fallbacks=[RouteRef(provider="openrouter", tier="free", model="deepseek-v3")],
        max_global_retries=0,
    )
    engine = TranslationEngine(cfg)

    mock_completion = AsyncMock(return_value=_make_response("Dịch qua OpenRouter"))
    monkeypatch.setattr("src.translator.litellm.acompletion", mock_completion)

    result = await engine.translate_text("江湖", task_name="translate")

    assert result.succeeded is True
    assert result.text == "Dịch qua OpenRouter"
    assert result.route_used == "openrouter.free.deepseek-v3"
    mock_completion.assert_awaited_once()
    assert (
        mock_completion.call_args.kwargs["model"]
        == "openrouter/deepseek/deepseek-chat-v3-0324:free"
    )
    assert mock_completion.call_args.kwargs["api_key"] == "or-live-key"

    # When NO routes have credentials, litellm.acompletion is never called at all
    monkeypatch.delenv("OPENROUTER_FREE_API_KEYS", raising=False)
    mock_none = AsyncMock()
    monkeypatch.setattr("src.translator.litellm.acompletion", mock_none)
    sleep_mock = AsyncMock()
    monkeypatch.setattr("src.translator.asyncio.sleep", sleep_mock)

    failed_result = await engine.translate_text("江湖", task_name="translate")
    assert failed_result.succeeded is False
    assert failed_result.text == "江湖"
    assert failed_result.error is not None
    mock_none.assert_not_awaited()
    sleep_mock.assert_not_awaited()


async def test_global_retry_cycle_recovers_after_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_FREE_API_KEYS", "gem-key-1")
    cfg = _build_engine_config(
        primary=RouteRef(provider="gemini", tier="free", model="gemma-3-27b"),
        gemini_max_retries=1,
        gemini_cooldown=17.5,
        max_global_retries=2,
    )
    engine = TranslationEngine(cfg)

    mock_completion = AsyncMock(
        side_effect=[
            RuntimeError("429 quota exceeded"),
            _make_response("Thành công ở chu kỳ 2"),
        ]
    )
    sleep_mock = AsyncMock()
    monkeypatch.setattr("src.translator.litellm.acompletion", mock_completion)
    monkeypatch.setattr("src.translator.asyncio.sleep", sleep_mock)

    result = await engine.translate_text("重试测试", task_name="translate")

    assert result.succeeded is True
    assert result.text == "Thành công ở chu kỳ 2"
    assert result.route_used == "gemini.free.gemma-3-27b"
    assert mock_completion.await_count == 2
    sleep_mock.assert_awaited_once_with(17.5)


async def test_exhausting_all_global_retries_returns_failed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_FREE_API_KEYS", "secret-gemini-key-1234567890")
    cfg = _build_engine_config(
        primary=RouteRef(provider="gemini", tier="free", model="gemma-3-27b"),
        gemini_max_retries=1,
        gemini_cooldown=9.0,
        max_global_retries=2,
    )
    engine = TranslationEngine(cfg)

    mock_completion = AsyncMock(
        side_effect=RuntimeError("API error with key secret-gemini-key-1234567890")
    )
    sleep_mock = AsyncMock()
    monkeypatch.setattr("src.translator.litellm.acompletion", mock_completion)
    monkeypatch.setattr("src.translator.asyncio.sleep", sleep_mock)

    original = "无法翻译的原文"
    result = await engine.translate_text(original, task_name="translate")

    assert result.succeeded is False
    assert result.text == original
    assert result.route_used is None
    assert result.error is not None
    # Verify raw key material was sanitized out of error string
    assert "secret-gemini-key-1234567890" not in result.error
    # 1 initial cycle + 2 global retries = 3 calls, 2 cooldown sleeps
    assert mock_completion.await_count == 3
    assert sleep_mock.await_count == 2
    assert all(call.args == (9.0,) for call in sleep_mock.call_args_list)


async def test_prompt_data_dict_string_default_and_num_retries_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOCAL_OPENAI_API_KEYS", raising=False)
    cfg = _build_engine_config(
        primary=RouteRef(provider="local_openai", tier="local", model="qwen3-14b")
    )
    engine = TranslationEngine(cfg)

    mock_completion = AsyncMock(return_value=_make_response("Kết quả"))
    monkeypatch.setattr("src.translator.litellm.acompletion", mock_completion)

    # 1. Dict prompt_data
    res_dict = await engine.translate_text(
        "原文1",
        task_name="translate",
        prompt_data={"prompt": "DICT_CUSTOM_PROMPT"},
    )
    assert res_dict.succeeded is True
    assert mock_completion.call_args.kwargs["messages"] == [
        {"role": "user", "content": "DICT_CUSTOM_PROMPT"}
    ]
    assert mock_completion.call_args.kwargs["num_retries"] == 0

    # 2. String prompt_data
    res_str = await engine.translate_text(
        "原文2",
        task_name="translate",
        prompt_data="STRING_CUSTOM_PROMPT",
    )
    assert res_str.succeeded is True
    assert mock_completion.call_args.kwargs["messages"] == [
        {"role": "user", "content": "STRING_CUSTOM_PROMPT"}
    ]
    assert mock_completion.call_args.kwargs["num_retries"] == 0

    # 3. No prompt_data falls back to build_translation_prompt
    res_default = await engine.translate_text("原文3", task_name="translate")
    assert res_default.succeeded is True
    assert mock_completion.call_args.kwargs["messages"] == [
        {"role": "user", "content": build_translation_prompt("原文3")}
    ]
    assert mock_completion.call_args.kwargs["num_retries"] == 0
