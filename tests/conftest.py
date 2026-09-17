"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import pytest

from lom_translate.models import AppConfig, ModelConfig, Settings


@pytest.fixture
def sample_schema_a_dict() -> dict:
    """Schema A: wrapped in entries.Array."""
    return {
        "Language": "ChineseSimplified",
        "entries": {
            "Array": [
                {
                    "Id": 101,
                    "Name": "Story/Intro_1",
                    "Text": "南宫伯伯，请安。\r\n祝您福如东海。",
                    "Speaker": "HuynhNhi",
                    "Voice": "voice_101.wav",
                },
                {
                    "Id": 102,
                    "Name": "Story/Intro_2",
                    "Text": "整装待发，捅人伤害+{0:N0}",
                    "Speaker": "ChieuHoat",
                },
            ]
        },
    }


@pytest.fixture
def sample_schema_b_dict() -> dict:
    """Schema B: flat entries list."""
    return {
        "Language": "ChineseSimplified",
        "entries": [
            {
                "Id": 201,
                "Name": "LegendInfo/Skill_1",
                "Text": "暗器投掷：{title}",
                "Context": "CombatSkill",
            },
            {
                "Id": 202,
                "Name": "LegendInfo/Skill_2",
                "Text": "？？？",
            },
        ],
    }


@pytest.fixture
def sample_app_config() -> AppConfig:
    """Test application configuration with 2 models for round-robin."""
    return AppConfig(
        models=[
            ModelConfig(
                id="model-primary",
                url="http://localhost:8000/v1",
                api_key="test-key-1",
                model_name="test-llm-1",
                max_retries=2,
                limit_per_minute=30,
                rate_limit_delay=0.01,
                rate_limit_if_quota_exceeded=0.05,
            ),
            ModelConfig(
                id="model-secondary",
                url="http://localhost:8001/v1",
                api_key="test-key-2",
                model_name="test-llm-2",
                max_retries=2,
                limit_per_minute=30,
                rate_limit_delay=0.01,
                rate_limit_if_quota_exceeded=0.05,
            ),
        ],
        task_assignments={
            "translate": ["model-primary", "model-secondary"],
            "improve": ["model-primary"],
        },
        settings=Settings(
            max_concurrent=2,
            max_concurrent_files=2,
            max_global_retries=1,
            input_dir="Resource/LeanLocalJson",
            output_dir="translated_output",
            glossary_dir="Resource/glossary",
        ),
    )
