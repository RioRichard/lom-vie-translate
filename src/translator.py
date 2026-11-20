from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING, Any

import litellm

from src.logger import logger
from src.utils import build_translation_prompt, postprocess_text

if TYPE_CHECKING:
    from src.config import AppConfig, ResolvedRoute

litellm.suppress_debug_info = True


@dataclass
class TranslationResult:
    text: str
    succeeded: bool
    route_used: str | None = None
    error: str | None = None


class KeyPool:
    """Universal round-robin API key rotator."""

    def __init__(self, keys: Sequence[str | None]) -> None:
        self._keys: list[str | None] = list(keys) if keys else [None]
        self._index = 0
        self._lock = Lock()

    def __len__(self) -> int:
        return len(self._keys)

    def next_key(self) -> tuple[int, str | None]:
        with self._lock:
            idx = self._index
            key = self._keys[idx]
            self._index = (self._index + 1) % len(self._keys)
            return idx, key


class _TierLimiter:
    """Per-(provider, tier) concurrency semaphore and minimum-delay rate limiter."""

    def __init__(self, max_concurrent: int, rate_limit_delay: float) -> None:
        self.semaphore = asyncio.Semaphore(max(1, max_concurrent))
        self.rate_limit_delay = max(0.0, rate_limit_delay)
        self._lock = asyncio.Lock()
        self._next_allowed: float = 0.0

    async def acquire_slot(self) -> None:
        if self.rate_limit_delay <= 0.0:
            return
        async with self._lock:
            now = time.monotonic()
            wait_time = self._next_allowed - now
            if wait_time > 0.0:
                await asyncio.sleep(wait_time)
                now = time.monotonic()
            self._next_allowed = now + self.rate_limit_delay


def _extract_response_content(response: Any) -> str | None:
    """Safely extract message content from a LiteLLM completion response."""
    if response is None:
        return None
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    if not choices:
        return None
    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    if message is None and isinstance(first_choice, dict):
        message = first_choice.get("message")
    if message is None:
        return None
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    if not isinstance(content, str):
        return None
    return content


def _sanitize_error(error: Exception, api_key: str | None) -> str:
    """Ensure raw API key material never appears in logged or returned error strings."""
    message = str(error)
    if api_key and api_key in message:
        message = message.replace(api_key, logger.mask_api_key(api_key))
    return message


class TranslationEngine:
    """Multi-provider, multi-tier async translation engine built on LiteLLM."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._key_pools: dict[tuple[str, str], KeyPool] = {}
        self._limiters: dict[tuple[str, str], _TierLimiter] = {}

    def _get_key_pool(self, route: ResolvedRoute) -> KeyPool:
        tier_key = (route.provider_name, route.tier_name)
        pool = self._key_pools.get(tier_key)
        if pool is None:
            pool = KeyPool(route.api_keys)
            self._key_pools[tier_key] = pool
        return pool

    def _get_limiter(self, route: ResolvedRoute) -> _TierLimiter:
        tier_key = (route.provider_name, route.tier_name)
        limiter = self._limiters.get(tier_key)
        if limiter is None:
            limiter = _TierLimiter(
                max_concurrent=route.max_concurrent,
                rate_limit_delay=route.rate_limit_delay,
            )
            self._limiters[tier_key] = limiter
        return limiter

    async def translate_text(
        self,
        text: str,
        task_name: str = "translate",
        name: str | None = None,
        prompt_data: dict[str, Any] | str | None = None,
        override_provider: str | None = None,
        override_tier: str | None = None,
        override_model: str | None = None,
    ) -> TranslationResult:
        """Translate text using resolved task routes with per-tier key rotation and fallbacks."""
        if isinstance(prompt_data, dict) and prompt_data.get("prompt"):
            prompt = str(prompt_data["prompt"])
        elif isinstance(prompt_data, str) and prompt_data.strip():
            prompt = prompt_data
        else:
            prompt = build_translation_prompt(text)

        logger.debug(f"Using prompt:\n{prompt}")

        routes, max_global_retries = self.config.resolve_task_routes(
            task_name,
            provider=override_provider,
            tier=override_tier,
            model=override_model,
        )
        if not routes:
            error_msg = f"No routes resolved for task '{task_name}'"
            logger.critical(error_msg)
            return TranslationResult(text=text, succeeded=False, error=error_msg)

        last_error: str | None = None

        for global_attempt in range(max_global_retries + 1):
            attempted_any_route = False

            for route in routes:
                if route.requires_api_key and not route.api_keys:
                    logger.warning(
                        f"Skipping unconfigured route '{route.route_label}': "
                        f"no API keys found in env var '{route.api_key_env}'."
                    )
                    if last_error is None:
                        last_error = (
                            f"Route '{route.route_label}' requires API keys in '{route.api_key_env}'."
                        )
                    continue

                attempted_any_route = True
                pool = self._get_key_pool(route)
                limiter = self._get_limiter(route)
                attempts = (
                    route.max_retries
                    if route.max_retries is not None
                    else max(len(route.api_keys), 1)
                )

                for attempt in range(attempts):
                    key_idx, api_key = pool.next_key()
                    kwargs: dict[str, Any] = {
                        "model": route.litellm_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": route.temperature,
                        "max_tokens": route.max_tokens,
                        "timeout": route.timeout,
                        "num_retries": 0,
                    }
                    if api_key is not None:
                        kwargs["api_key"] = api_key
                    if route.api_base is not None:
                        kwargs["api_base"] = route.api_base
                    if route.extra_headers:
                        kwargs["extra_headers"] = dict(route.extra_headers)
                    if route.extra_params:
                        kwargs.update(route.extra_params)

                    try:
                        async with limiter.semaphore:
                            await limiter.acquire_slot()
                            logger.api_call(key_idx, api_key, route.route_label)
                            logger.translation_start(name, text, route.route_label)
                            call_start = time.monotonic()
                            response = await litellm.acompletion(**kwargs)
                            duration = time.monotonic() - call_start

                        content = _extract_response_content(response)
                        if content and content.strip():
                            translated = postprocess_text(content)
                            logger.translation_output(translated, duration, route.route_label)
                            return TranslationResult(
                                text=translated,
                                succeeded=True,
                                route_used=route.route_label,
                            )

                        last_error = f"Empty response received from route {route.route_label}"
                        logger.error(
                            f"Empty response on route {route.route_label} "
                            f"(API key {key_idx}, attempt {attempt + 1}/{attempts})"
                        )
                        logger.translation_output("", duration, route.route_label)
                    except Exception as exc:
                        sanitized = _sanitize_error(exc, api_key)
                        last_error = f"{route.route_label}: {sanitized}"
                        logger.error(
                            f"Translation error on route {route.route_label} "
                            f"(API key {key_idx}, attempt {attempt + 1}/{attempts}): {sanitized}"
                        )

                    if attempt + 1 < attempts and route.rate_limit_delay > 0:
                        await asyncio.sleep(route.rate_limit_delay)

            if not attempted_any_route:
                break

            if global_attempt < max_global_retries:
                cooldown = routes[0].quota_cooldown
                logger.info(
                    f"All routes exhausted for task '{task_name}'. "
                    f"Initiating global retry {global_attempt + 1}/{max_global_retries} "
                    f"after {cooldown:.1f}s cooldown."
                )
                await asyncio.sleep(cooldown)

        logger.critical(
            f"All routes failed for task '{task_name}' after retries. "
            f"Last error: {last_error}. Returning original text."
        )
        return TranslationResult(text=text, succeeded=False, error=last_error)
