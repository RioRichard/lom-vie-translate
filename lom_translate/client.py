"""OpenAI-compatible client with autonomous rate limiting and true round-robin rotation."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from openai import AsyncOpenAI

from lom_translate.logger import logger
from lom_translate.models import ModelConfig


class LLMClient:
    """Isolated client instance bound to a single ModelConfig with live state tracking."""

    def __init__(self, model_config: ModelConfig) -> None:
        self.config = model_config
        self._client = AsyncOpenAI(
            api_key=model_config.api_key or "not-needed",
            base_url=model_config.url,
        )
        self._call_timestamps: list[float] = []
        self._last_call_time: float = 0.0
        self._cooldown_until: float = 0.0
        self._active_requests: int = 0
        self._lock = asyncio.Lock()

    @property
    def model_id(self) -> str:
        return self.config.id

    def is_free_and_in_limit(self) -> tuple[bool, float]:
        """Check if this model is free to take a call right now.

        Returns (is_ready, seconds_until_ready).
        """
        now = time.time()

        # 1. Check quota cooldown
        if now < self._cooldown_until:
            return False, self._cooldown_until - now

        # 2. Check rate_limit_delay spacing between consecutive calls
        time_since_last = now - self._last_call_time
        if self.config.rate_limit_delay > 0 and time_since_last < self.config.rate_limit_delay:
            return False, self.config.rate_limit_delay - time_since_last

        # 3. Check limit_per_minute sliding window
        if self.config.limit_per_minute > 0:
            cutoff = now - 60.0
            recent_calls = [t for t in self._call_timestamps if t > cutoff]
            if len(recent_calls) >= self.config.limit_per_minute:
                return False, recent_calls[0] - cutoff

        return True, 0.0

    def mark_quota_exceeded(self) -> None:
        """Mark this model in quota cooldown."""
        self._cooldown_until = time.time() + self.config.rate_limit_if_quota_exceeded
        logger.warning(
            f"[{self.model_id}] Quota exceeded / 429. Cooling down for {self.config.rate_limit_if_quota_exceeded}s"
        )

    def mark_error_delay(self) -> None:
        """Apply rate_limit_delay on error before next retry."""
        self._cooldown_until = time.time() + self.config.rate_limit_delay

    async def generate(self, prompt: str, system_prompt: str = "") -> str | None:
        async with self._lock:
            self._active_requests += 1
            now = time.time()
            self._last_call_time = now
            self._call_timestamps.append(now)

        try:
            messages: list[dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            kwargs: dict[str, Any] = {
                "model": self.config.model_name,
                "messages": messages,
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
            }
            if self.config.top_k is not None:
                kwargs["extra_body"] = {"top_k": self.config.top_k}

            response = await self._client.chat.completions.create(**kwargs)
            if response.choices and response.choices[0].message.content:
                return str(response.choices[0].message.content).strip()
            return None
        finally:
            async with self._lock:
                self._active_requests -= 1


class LLMClientPool:
    """True Round-Robin Model Rotator.

    Rotates to the next model after EACH call, picking only models that are
    free and within their configured limits.
    """

    def __init__(self, clients: list[LLMClient]) -> None:
        if not clients:
            raise ValueError("LLMClientPool must contain at least one client.")
        self.clients = clients
        self._cursor = 0
        self._lock = asyncio.Lock()

    @classmethod
    def from_task(cls, app_config: Any, task: str) -> LLMClientPool:
        models = app_config.get_models_for_task(task)
        clients = [LLMClient(m) for m in models]
        logger.info(f"Initialized client pool for '{task}': {[c.model_id for c in clients]}")
        return cls(clients)

    async def acquire_next_available_client(self, exclude_ids: set[str] | None = None) -> LLMClient:
        """Rotate to the next model in the pool that is free and within limits.

        If all candidates are temporarily busy/waiting, sleeps briefly for the
        earliest model to become ready.
        """
        exclude = exclude_ids or set()

        while True:
            candidates: list[tuple[LLMClient, float]] = []

            async with self._lock:
                n = len(self.clients)
                for offset in range(n):
                    idx = (self._cursor + offset) % n
                    client = self.clients[idx]

                    if client.model_id in exclude:
                        continue

                    ready, wait_needed = client.is_free_and_in_limit()
                    if ready:
                        self._cursor = (idx + 1) % n
                        return client
                    candidates.append((client, wait_needed))

            if not candidates:
                raise RuntimeError("No available models in pool (all models excluded).")

            shortest_wait = min(wait for _, wait in candidates)
            await asyncio.sleep(max(0.1, shortest_wait))
