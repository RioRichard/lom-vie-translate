import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.config import (
    AppConfig,
    ModelConfig,
    ProviderConfig,
    RouteRef,
    TaskConfig,
    TierConfig,
    load_config,
    parse_api_keys,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_CONFIG = REPO_ROOT / "config.toml.template"


def _minimal_app_config_data() -> dict:
    return {
        "providers": {
            "local_openai": {
                "api_base": "http://localhost:1234/v1",
                "timeout": 180.0,
                "default_api_key": "local-no-key",
                "tiers": {
                    "local": {
                        "api_key_env": "LOCAL_OPENAI_API_KEYS",
                        "max_concurrent": 2,
                        "rate_limit_delay": 0.0,
                        "quota_cooldown": 5.0,
                        "max_retries": 2,
                    },
                },
                "models": {
                    "qwen3-14b": {
                        "model_id": "openai/qwen3-14b",
                    },
                },
            },
            "cloud": {
                "timeout": 60.0,
                "tiers": {
                    "free": {
                        "api_key_env": "CLOUD_FREE_KEYS",
                        "model_suffix": ":free",
                    },
                    "paid": {
                        "api_key_env": "CLOUD_PAID_KEYS",
                    },
                },
                "models": {
                    "std-model": {
                        "model_id": "cloud/std",
                    },
                    "paid-only-model": {
                        "model_id": "cloud/pro",
                        "allowed_tiers": ["paid"],
                    },
                },
            },
        },
        "tasks": {
            "translate": {
                "primary": {"provider": "local_openai", "tier": "local", "model": "qwen3-14b"},
                "fallbacks": [
                    {"provider": "cloud", "tier": "free", "model": "std-model"},
                    {"provider": "cloud", "tier": "paid", "model": "paid-only-model"},
                ],
                "max_global_retries": 2,
            },
        },
    }


def test_template_config_loads_and_validates() -> None:
    cfg = load_config(TEMPLATE_CONFIG, load_env=False)

    assert cfg.run.mode == "translate"
    assert {"local_openai", "gemini", "openrouter"}.issubset(cfg.providers.keys())
    assert {"translate", "improve", "improve_glossary"}.issubset(cfg.tasks.keys())

    routes, max_global_retries = cfg.resolve_task_routes("translate")
    assert max_global_retries == 3
    assert [r.route_label for r in routes] == [
        "local_openai.local.qwen3-14b",
        "gemini.free.gemma-3-27b",
        "gemini.free.gemini-2.5-flash",
        "openrouter.free.deepseek-v3",
    ]


def test_invalid_provider_raises_value_error() -> None:
    data = _minimal_app_config_data()
    data["tasks"]["translate"]["primary"] = {
        "provider": "nonexistent_provider",
        "tier": "local",
        "model": "qwen3-14b",
    }

    with pytest.raises(ValueError, match="unknown provider"):
        AppConfig.model_validate(data)


def test_invalid_tier_raises_value_error() -> None:
    data = _minimal_app_config_data()
    data["tasks"]["translate"]["primary"] = {
        "provider": "local_openai",
        "tier": "nonexistent_tier",
        "model": "qwen3-14b",
    }

    with pytest.raises(ValueError, match="unknown tier"):
        AppConfig.model_validate(data)


def test_invalid_model_raises_value_error() -> None:
    data = _minimal_app_config_data()
    data["tasks"]["translate"]["fallbacks"][0] = {
        "provider": "cloud",
        "tier": "free",
        "model": "nonexistent_model",
    }

    with pytest.raises(ValueError, match="unknown model"):
        AppConfig.model_validate(data)


def test_disallowed_tier_raises_value_error() -> None:
    data = _minimal_app_config_data()
    data["tasks"]["translate"]["fallbacks"][1] = {
        "provider": "cloud",
        "tier": "free",
        "model": "paid-only-model",
    }

    with pytest.raises(ValueError, match="not allowed for model"):
        AppConfig.model_validate(data)


def test_parse_api_keys_and_key_fallback_semantics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_KEYS_ENV", raising=False)
    assert parse_api_keys(None) == []
    assert parse_api_keys("") == []
    assert parse_api_keys("TEST_KEYS_ENV") == []

    monkeypatch.setenv("TEST_KEYS_ENV", "  ,  , ")
    assert parse_api_keys("TEST_KEYS_ENV") == []

    monkeypatch.setenv("TEST_KEYS_ENV", " key-1 , , key-2,  key-3 ")
    assert parse_api_keys("TEST_KEYS_ENV") == ["key-1", "key-2", "key-3"]

    cfg = load_config(TEMPLATE_CONFIG, load_env=False)

    # Keyless local_openai falls back to default_api_key and does not require env keys
    monkeypatch.delenv("LOCAL_OPENAI_API_KEYS", raising=False)
    monkeypatch.delenv("GEMINI_FREE_API_KEYS", raising=False)
    local_route = cfg.resolve_route(
        RouteRef(provider="local_openai", tier="local", model="qwen3-14b")
    )
    assert local_route.api_keys == ["local-no-key"]
    assert local_route.uses_default_key is True
    assert local_route.requires_api_key is False

    # Local provider with env keys uses those instead of default_api_key
    monkeypatch.setenv("LOCAL_OPENAI_API_KEYS", " local-a , local-b ")
    local_auth_route = cfg.resolve_route(
        RouteRef(provider="local_openai", tier="local", model="qwen3-14b")
    )
    assert local_auth_route.api_keys == ["local-a", "local-b"]
    assert local_auth_route.uses_default_key is False
    assert local_auth_route.requires_api_key is False

    # Cloud tier without env keys has requires_api_key=True and empty api_keys
    gemini_empty = cfg.resolve_route(
        RouteRef(provider="gemini", tier="free", model="gemma-3-27b")
    )
    assert gemini_empty.api_keys == []
    assert gemini_empty.uses_default_key is False
    assert gemini_empty.requires_api_key is True

    # Cloud tier with env keys populates api_keys
    monkeypatch.setenv("GEMINI_FREE_API_KEYS", "gem-1, gem-2")
    gemini_ready = cfg.resolve_route(
        RouteRef(provider="gemini", tier="free", model="gemma-3-27b")
    )
    assert gemini_ready.api_keys == ["gem-1", "gem-2"]
    assert gemini_ready.uses_default_key is False
    assert gemini_ready.requires_api_key is True


def test_model_suffix_and_tier_model_ids_precedence() -> None:
    cfg = load_config(TEMPLATE_CONFIG, load_env=False)

    free_route = cfg.resolve_route(
        RouteRef(provider="openrouter", tier="free", model="deepseek-v3")
    )
    paid_route = cfg.resolve_route(
        RouteRef(provider="openrouter", tier="paid", model="deepseek-v3")
    )
    assert free_route.litellm_model == "openrouter/deepseek/deepseek-chat-v3-0324:free"
    assert paid_route.litellm_model == "openrouter/deepseek/deepseek-chat-v3-0324"

    # tier_model_ids must take precedence over model_id + tier.model_suffix
    custom_cfg = AppConfig(
        providers={
            "openrouter": ProviderConfig(
                tiers={
                    "free": TierConfig(api_key_env="OR_FREE", model_suffix=":free"),
                    "paid": TierConfig(api_key_env="OR_PAID"),
                },
                models={
                    "custom": ModelConfig(
                        model_id="openrouter/vendor/base-model",
                        tier_model_ids={"free": "openrouter/vendor/explicit-free-id"},
                    ),
                },
            ),
        },
        tasks={
            "translate": TaskConfig(
                primary=RouteRef(provider="openrouter", tier="free", model="custom"),
            ),
        },
    )

    resolved_free = custom_cfg.resolve_route(
        RouteRef(provider="openrouter", tier="free", model="custom")
    )
    resolved_paid = custom_cfg.resolve_route(
        RouteRef(provider="openrouter", tier="paid", model="custom")
    )
    assert resolved_free.litellm_model == "openrouter/vendor/explicit-free-id"
    assert resolved_paid.litellm_model == "openrouter/vendor/base-model"


def test_resolve_task_routes_with_overrides_and_deduplication() -> None:
    cfg = load_config(TEMPLATE_CONFIG, load_env=False)

    # Overriding primary to match an existing fallback deduplicates that fallback
    routes, max_retries = cfg.resolve_task_routes(
        "translate",
        provider="gemini",
        tier="free",
        model="gemma-3-27b",
    )
    assert max_retries == 3
    labels = [r.route_label for r in routes]
    assert labels == [
        "gemini.free.gemma-3-27b",
        "gemini.free.gemini-2.5-flash",
        "openrouter.free.deepseek-v3",
    ]
    assert len(labels) == len(set(labels))

    # Overriding with a route not in fallbacks keeps all non-duplicate fallbacks
    paid_routes, _ = cfg.resolve_task_routes(
        "translate",
        provider="openrouter",
        tier="paid",
        model="deepseek-v3",
    )
    assert [r.route_label for r in paid_routes] == [
        "openrouter.paid.deepseek-v3",
        "gemini.free.gemma-3-27b",
        "gemini.free.gemini-2.5-flash",
        "openrouter.free.deepseek-v3",
    ]

    # Invalid override raises ValueError
    with pytest.raises(ValueError, match="unknown tier"):
        cfg.resolve_task_routes("translate", tier="nonexistent")

    # Unknown task raises ValueError
    with pytest.raises(ValueError, match="Unknown task"):
        cfg.resolve_task_routes("nonexistent_task")


def test_import_src_config_has_zero_side_effects(tmp_path: Path) -> None:
    """Importing src.config in an empty directory without config.toml or .env must succeed cleanly."""
    env = os.environ.copy()
    env.pop("LOM_CONFIG_FILE", None)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{REPO_ROOT}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(REPO_ROOT)
    )

    result = subprocess.run(
        [sys.executable, "-c", "import src.config; print(src.config.DEFAULT_CONFIG_FILENAME)"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip() == "config.toml"
    assert list(tmp_path.iterdir()) == []
