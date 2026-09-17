"""Translation engine rotating across free/in-limit models with soft validation."""

from __future__ import annotations

import asyncio
import time

from lom_translate import config as cfg
from lom_translate.client import LLMClientPool
from lom_translate.logger import logger
from lom_translate.text import postprocess_text
from lom_translate.validation import ValidationResult, soft_validate_translation


async def translate_text(
    text: str, name: str, prompt: str, client_pool: LLMClientPool
) -> tuple[str, float, ValidationResult]:
    """Translate text with per-call model rotation, soft validation, and pool fallback."""
    app_config = cfg.get()
    start = time.time()

    model_attempts: dict[str, int] = {c.model_id: 0 for c in client_pool.clients}
    exhausted_models: set[str] = set()

    for global_cycle in range(app_config.settings.max_global_retries + 1):
        while len(exhausted_models) < len(client_pool.clients):
            # 1. Rotate to next free and in-limit model
            client = await client_pool.acquire_next_available_client(exclude_ids=exhausted_models)
            model_attempts[client.model_id] += 1

            try:
                logger.debug(
                    f"Dispatching '{name}' to [{client.model_id}] "
                    f"(attempt {model_attempts[client.model_id]}/{client.config.max_retries})"
                )
                raw_result = await client.generate(prompt)

                if raw_result:
                    # 2. Apply Soft Validation & Auto-Healing
                    val_result = soft_validate_translation(text, raw_result)
                    translated = postprocess_text(val_result.healed_text)

                    if val_result.warning_messages:
                        for w in val_result.warning_messages:
                            logger.warning(f"[{name}] Soft validation warning via [{client.model_id}]: {w}")

                    # If clean or only minor warnings (no critical missing tokens), accept!
                    if val_result.is_clean or len(val_result.missing_tokens) == 0:
                        return translated, time.time() - start, val_result

                    logger.warning(
                        f"[{client.model_id}] Dropped critical tokens on '{name}': {val_result.missing_tokens}. Rotating..."
                    )
                    client.mark_error_delay()
                else:
                    logger.warning(f"Empty response for '{name}' via [{client.model_id}]")
                    client.mark_error_delay()

            except Exception as e:
                err_msg = str(e).lower()
                logger.error(f"Error on '{name}' via [{client.model_id}]: {e}")
                if "429" in err_msg or "quota" in err_msg:
                    client.mark_quota_exceeded()
                else:
                    client.mark_error_delay()

            if model_attempts[client.model_id] >= client.config.max_retries:
                exhausted_models.add(client.model_id)
                logger.warning(f"[{client.model_id}] exhausted retries for '{name}'.")

        # Global backoff if all models exhausted
        if global_cycle < app_config.settings.max_global_retries:
            max_backoff = max(c.config.rate_limit_if_quota_exceeded for c in client_pool.clients)
            logger.warning(
                f"All models exhausted for '{name}'. Global retry {global_cycle + 1}, waiting {max_backoff}s"
            )
            await asyncio.sleep(max_backoff)
            exhausted_models.clear()
            model_attempts = {c.model_id: 0 for c in client_pool.clients}

    logger.critical(f"Translation permanently failed for '{name}'. Returning original text.")
    fallback_val = soft_validate_translation(text, text)
    return text, time.time() - start, fallback_val
