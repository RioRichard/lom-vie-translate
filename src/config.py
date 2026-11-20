import os
import tomllib
from pathlib import Path
from typing import Any, Literal, Self

from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

VALID_MODES: tuple[str, ...] = ("translate", "improve")
DEFAULT_CONFIG_FILENAME = "config.toml"


class TierConfig(BaseModel):
    api_key_env: str | None = None
    max_concurrent: int = Field(5, ge=1)
    rate_limit_delay: float = Field(0.0, ge=0.0)
    quota_cooldown: float = Field(30.0, ge=0.0)
    max_retries: int | None = Field(None, ge=1)
    model_suffix: str = ""
    extra_headers: dict[str, str] = Field(default_factory=dict)


class ModelConfig(BaseModel):
    model_id: str
    temperature: float = Field(0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(1500, ge=1)
    timeout: float | None = Field(None, gt=0)
    allowed_tiers: list[str] | None = None
    tier_model_ids: dict[str, str] = Field(default_factory=dict)
    extra_params: dict[str, Any] = Field(default_factory=dict)


class ProviderConfig(BaseModel):
    api_base: str | None = None
    timeout: float = Field(120.0, gt=0)
    default_api_key: str | None = None
    tiers: dict[str, TierConfig] = Field(default_factory=dict)
    models: dict[str, ModelConfig] = Field(default_factory=dict)


class RouteRef(BaseModel):
    provider: str
    tier: str
    model: str


class TaskConfig(BaseModel):
    primary: RouteRef
    fallbacks: list[RouteRef] = Field(default_factory=list)
    max_global_retries: int = Field(3, ge=0)
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=1)


class RunConfig(BaseModel):
    mode: Literal["translate", "improve"] = "translate"
    input_dir: str = "Resource/LeanLocalJson"
    output_dir: str = "translated_output"
    raw_dir: str | None = None
    json_output_dir: str | None = None
    details_output_dir: str | None = None
    pairs_output_dir: str | None = None
    glossary_dir: str = "Resource/glossary"
    glossary_file: str | None = None
    old_dir: str | None = None
    old_file: str | None = None
    flowchart_file: str | None = None
    relationship_file: str | None = None
    dialogue_window: int = Field(4, ge=0)
    max_concurrent_file_opens: int = Field(100, ge=1)


class ResolvedRoute(BaseModel):
    provider_name: str
    tier_name: str
    model_name: str
    litellm_model: str
    api_base: str | None
    api_keys: list[str]
    api_key_env: str | None
    uses_default_key: bool
    requires_api_key: bool
    max_concurrent: int
    rate_limit_delay: float
    quota_cooldown: float
    max_retries: int | None
    temperature: float
    max_tokens: int
    timeout: float
    extra_headers: dict[str, str]
    extra_params: dict[str, Any]

    @property
    def route_label(self) -> str:
        return f"{self.provider_name}.{self.tier_name}.{self.model_name}"


def parse_api_keys(env_var: str | None) -> list[str]:
    if not env_var:
        return []
    raw_keys = os.getenv(env_var, "")
    if not raw_keys:
        return []
    return [key.strip() for key in raw_keys.split(",") if key.strip()]


class AppConfig(BaseModel):
    run: RunConfig = Field(default_factory=RunConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    tasks: dict[str, TaskConfig] = Field(default_factory=dict)

    def _validate_route_ref(
        self,
        route: RouteRef,
        context: str = "route",
    ) -> tuple[ProviderConfig, TierConfig, ModelConfig]:
        if route.provider not in self.providers:
            available = sorted(self.providers)
            raise ValueError(
                f"{context}: unknown provider '{route.provider}' (available: {available})"
            )

        provider_cfg = self.providers[route.provider]

        if route.tier not in provider_cfg.tiers:
            available = sorted(provider_cfg.tiers)
            raise ValueError(
                f"{context}: unknown tier '{route.tier}' for provider '{route.provider}' "
                f"(available: {available})"
            )

        if route.model not in provider_cfg.models:
            available = sorted(provider_cfg.models)
            raise ValueError(
                f"{context}: unknown model '{route.model}' for provider '{route.provider}' "
                f"(available: {available})"
            )

        tier_cfg = provider_cfg.tiers[route.tier]
        model_cfg = provider_cfg.models[route.model]

        if model_cfg.allowed_tiers is not None and route.tier not in model_cfg.allowed_tiers:
            raise ValueError(
                f"{context}: tier '{route.tier}' is not allowed for model "
                f"'{route.provider}.{route.model}' (allowed: {model_cfg.allowed_tiers})"
            )

        return provider_cfg, tier_cfg, model_cfg

    @model_validator(mode="after")
    def _validate_all_task_routes(self) -> Self:
        for task_name, task_cfg in self.tasks.items():
            self._validate_route_ref(task_cfg.primary, context=f"task '{task_name}' primary")
            for idx, fallback in enumerate(task_cfg.fallbacks):
                self._validate_route_ref(
                    fallback,
                    context=f"task '{task_name}' fallback[{idx}]",
                )
        return self

    def resolve_route(
        self,
        route: RouteRef,
        task_cfg: TaskConfig | None = None,
    ) -> ResolvedRoute:
        provider_cfg, tier_cfg, model_cfg = self._validate_route_ref(route)
        litellm_model = (
            model_cfg.tier_model_ids.get(route.tier)
            or f"{model_cfg.model_id}{tier_cfg.model_suffix}"
        )

        env_keys = parse_api_keys(tier_cfg.api_key_env)
        if env_keys:
            api_keys = env_keys
        elif provider_cfg.default_api_key:
            api_keys = [provider_cfg.default_api_key]
        else:
            api_keys = []

        uses_default_key = (not env_keys) and bool(provider_cfg.default_api_key)
        requires_api_key = bool(tier_cfg.api_key_env) and not provider_cfg.default_api_key

        temperature = (
            task_cfg.temperature
            if task_cfg is not None and task_cfg.temperature is not None
            else model_cfg.temperature
        )
        max_tokens = (
            task_cfg.max_tokens
            if task_cfg is not None and task_cfg.max_tokens is not None
            else model_cfg.max_tokens
        )
        timeout = model_cfg.timeout if model_cfg.timeout is not None else provider_cfg.timeout

        return ResolvedRoute(
            provider_name=route.provider,
            tier_name=route.tier,
            model_name=route.model,
            litellm_model=litellm_model,
            api_base=provider_cfg.api_base,
            api_keys=api_keys,
            api_key_env=tier_cfg.api_key_env,
            uses_default_key=uses_default_key,
            requires_api_key=requires_api_key,
            max_concurrent=tier_cfg.max_concurrent,
            rate_limit_delay=tier_cfg.rate_limit_delay,
            quota_cooldown=tier_cfg.quota_cooldown,
            max_retries=tier_cfg.max_retries,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            extra_headers=dict(tier_cfg.extra_headers),
            extra_params=dict(model_cfg.extra_params),
        )

    def resolve_task_routes(
        self,
        task_name: str,
        provider: str | None = None,
        tier: str | None = None,
        model: str | None = None,
    ) -> tuple[list[ResolvedRoute], int]:
        if task_name not in self.tasks:
            available = sorted(self.tasks)
            raise ValueError(f"Unknown task '{task_name}' (available: {available})")

        task_cfg = self.tasks[task_name]

        if provider is not None or tier is not None or model is not None:
            primary_ref = RouteRef(
                provider=provider if provider is not None else task_cfg.primary.provider,
                tier=tier if tier is not None else task_cfg.primary.tier,
                model=model if model is not None else task_cfg.primary.model,
            )
            self._validate_route_ref(primary_ref, context=f"task '{task_name}' override")
        else:
            primary_ref = task_cfg.primary

        route_refs: list[RouteRef] = [primary_ref]
        seen = {(primary_ref.provider, primary_ref.tier, primary_ref.model)}
        for fallback in task_cfg.fallbacks:
            key = (fallback.provider, fallback.tier, fallback.model)
            if key not in seen:
                seen.add(key)
                route_refs.append(fallback)

        resolved_routes = [self.resolve_route(ref, task_cfg=task_cfg) for ref in route_refs]
        return resolved_routes, task_cfg.max_global_retries


def load_config(
    config_path: str | Path | None = None,
    load_env: bool = True,
) -> AppConfig:
    if load_env:
        load_dotenv()

    if config_path is not None:
        resolved_path = Path(config_path)
    else:
        env_path = os.getenv("LOM_CONFIG_FILE")
        resolved_path = Path(env_path) if env_path else Path(DEFAULT_CONFIG_FILENAME)

    if not resolved_path.is_file():
        raise FileNotFoundError(
            f"Configuration file not found: '{resolved_path}'. "
            f"Copy 'config.toml.template' to '{DEFAULT_CONFIG_FILENAME}' "
            "and customize your settings, or pass --config-file / set LOM_CONFIG_FILE."
        )

    with resolved_path.open("rb") as f:
        raw_data = tomllib.load(f)

    return AppConfig.model_validate(raw_data)
