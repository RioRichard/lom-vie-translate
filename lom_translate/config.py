"""Lazy configuration loader. Never raises on import."""

from __future__ import annotations

import json
from pathlib import Path

from lom_translate.models import AppConfig

_config: AppConfig | None = None


def load(config_path: str | Path = "config.json") -> AppConfig:
    """Load and validate config.json. Call explicitly during CLI execution."""
    global _config
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\nPlease copy config.template.json to {path} and configure your settings."
        )
    with open(path, encoding="utf-8") as f:
        _config = AppConfig.model_validate(json.load(f))
    return _config


def get() -> AppConfig:
    """Retrieve currently active configuration. Raises if not loaded."""
    if _config is None:
        raise RuntimeError("Configuration has not been loaded. Call config.load() first.")
    return _config


def set_config(config_obj: AppConfig) -> None:
    """Set active configuration programmatically (used in tests)."""
    global _config
    _config = config_obj
