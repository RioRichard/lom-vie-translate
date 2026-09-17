"""Typed data models for game localization entries and application configuration."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ── Game Data Models ──────────────────────────────────────────────


class LocalizationEntry(BaseModel):
    """Single game entry. extra='allow' preserves Id, Speaker, Voice, Context, etc."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    Name: str = Field(default="", alias="key")
    Text: str = Field(default="", alias="value")

    def clone_with_translation(self, translated_text: str) -> LocalizationEntry:
        """DEF-06 FIX: Clone entry preserving ALL auxiliary engine metadata."""
        data = self.model_dump(by_alias=False)
        data["Text"] = translated_text
        return LocalizationEntry.model_validate(data)


class LocalizationFile(BaseModel):
    """Game localization JSON container — supports Schema A and Schema B."""

    Language: str = ""
    entries: Any = []

    def get_entries(self) -> list[LocalizationEntry]:
        """DEF-07 FIX: Unified parsing across both schema formats."""
        if isinstance(self.entries, dict) and "Array" in self.entries:
            items = self.entries["Array"]
        elif isinstance(self.entries, list):
            items = self.entries
        else:
            return []
        return [LocalizationEntry.model_validate(e) for e in items]

    @property
    def is_schema_a(self) -> bool:
        return isinstance(self.entries, dict) and "Array" in self.entries

    def to_output_dict(self, translated: list[LocalizationEntry]) -> dict[str, Any]:
        """Reconstruct output dict matching original schema format byte-for-byte."""
        dumped = [e.model_dump(by_alias=False, exclude_none=True) for e in translated]
        result: dict[str, Any] = self.model_dump()
        if self.is_schema_a:
            result["entries"]["Array"] = dumped
        else:
            result["entries"] = dumped
        return result


# ── Configuration Models ──────────────────────────────────────────


class ModelConfig(BaseModel):
    """Configuration, credentials, and rate limits for an individual LLM endpoint."""

    id: str
    url: str
    api_key: str = ""
    model_name: str
    temperature: float = 0.1
    top_p: float = 0.9
    top_k: int | None = None
    max_retries: int = 3
    limit_per_minute: int = 15
    rate_limit_delay: float = 1.0
    rate_limit_if_quota_exceeded: float = 30.0


class Settings(BaseModel):
    """Global operational settings."""

    max_concurrent: int = 5
    max_concurrent_files: int = 3
    max_global_retries: int = 3
    soft_validation_max_retries: int = 2
    input_dir: str = "Resource/LeanLocalJson"
    output_dir: str = "translated_output"
    glossary_dir: str = "Resource/glossary"


class AppConfig(BaseModel):
    """Root configuration model loaded from config.json."""

    models: list[ModelConfig] = []
    task_assignments: dict[str, list[str]] = {}
    settings: Settings = Settings()

    def get_model(self, model_id: str) -> ModelConfig | None:
        for m in self.models:
            if m.id == model_id:
                return m
        return None

    def get_models_for_task(self, task: str) -> list[ModelConfig]:
        model_ids = self.task_assignments.get(task, [])
        if not model_ids:
            raise ValueError(f"No models assigned for task '{task}' in config.json")
        models = []
        for mid in model_ids:
            m = self.get_model(mid)
            if not m:
                raise ValueError(f"Model '{mid}' (task '{task}') not found in models list")
            models.append(m)
        return models
