"""Tests for configuration loading and validation (DEF-01)."""

from __future__ import annotations

import json

import pytest

from lom_translate import config as cfg
from lom_translate.models import AppConfig, ModelConfig


def test_import_has_zero_side_effects():
    """DEF-01: Importing config must never raise an exception or crash."""
    from lom_translate import config

    assert config is not None


def test_get_raises_before_load():
    """Calling config.get() before load() raises RuntimeError."""
    cfg._config = None
    with pytest.raises(RuntimeError, match="not been loaded"):
        cfg.get()


def test_load_nonexistent_file_raises(tmp_path):
    """Loading missing config file raises clear FileNotFoundError."""
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        cfg.load(missing)


def test_load_valid_config(tmp_path):
    """Loading a valid config file populates configuration correctly."""
    config_file = tmp_path / "config.json"
    data = {
        "models": [
            {
                "id": "m1",
                "url": "http://localhost:11434/v1",
                "model_name": "llama3",
                "max_retries": 3,
            }
        ],
        "task_assignments": {"translate": ["m1"]},
        "settings": {"max_concurrent": 10},
    }
    config_file.write_text(json.dumps(data), encoding="utf-8")

    loaded = cfg.load(config_file)
    assert len(loaded.models) == 1
    assert loaded.models[0].id == "m1"
    assert loaded.models[0].max_retries == 3
    assert loaded.settings.max_concurrent == 10
    assert cfg.get() == loaded


def test_get_models_for_task_raises_on_unassigned():
    """Requesting models for unassigned task raises ValueError."""
    app_cfg = AppConfig(models=[], task_assignments={})
    with pytest.raises(ValueError, match="No models assigned"):
        app_cfg.get_models_for_task("unknown_task")


def test_get_models_for_task_raises_on_missing_model_definition():
    """Requesting a model ID that isn't in 'models' list raises ValueError."""
    app_cfg = AppConfig(
        models=[ModelConfig(id="m1", url="http://x", model_name="test")],
        task_assignments={"translate": ["m2"]},
    )
    with pytest.raises(ValueError, match="not found in models list"):
        app_cfg.get_models_for_task("translate")
