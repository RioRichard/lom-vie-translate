"""Translation engine rotating across free/in-limit models with dual-tier bounded retries."""

from __future__ import annotations

import time

from lom_translate import config as cfg
from lom_translate.client import LLMClientPool
from lom_translate.logger import logger
from lom_translate.prompt import build_corrective_prompt
from lom_translate.text import postprocess_text
from lom_translate.validation import ValidationResult, validate_translation


async def translate_text(
    text: str,
    name: str,
    prompt: str,
    client_pool: LLMClientPool,
    glossary_matches: list[tuple[str, str]] | list[dict[str, str]] | None = None,
    soft_max_retries: int | None = None,
) -> tuple[str, float, ValidationResult]:
    """Translate text with dual-budget state machine, model rotation, and safe fallback.

    Budgets:
    - soft_retries_remaining: starts at soft_max_retries (default from settings: 2).
      Decrements on each soft failure. When 0, accepts candidate with logged warnings.
    - model_attempts: tracks per-model calls. When attempt >= max_retries, model is exhausted.
      When all models exhausted, safely falls back to original text.
    """
    app_config = cfg.get()
    start = time.time()

    if soft_max_retries is None:
        soft_retries_remaining: int = getattr(app_config.settings, "soft_validation_max_retries", 2)
    else:
        soft_retries_remaining = soft_max_retries

    model_attempts: dict[str, int] = {c.model_id: 0 for c in client_pool.clients}
    exhausted_models: set[str] = set()
    current_prompt = prompt
    max_total_calls = sum(c.config.max_retries for c in client_pool.clients)
    total_calls = 0

    while len(exhausted_models) < len(client_pool.clients) and total_calls < max_total_calls:
        # 1. Rotate to next free and in-limit model
        try:
            client = await client_pool.acquire_next_available_client(exclude_ids=exhausted_models)
        except RuntimeError:
            break

        model_attempts[client.model_id] += 1
        total_calls += 1

        try:
            logger.debug(
                f"Dispatching '{name}' to [{client.model_id}] "
                f"(attempt {model_attempts[client.model_id]}/{client.config.max_retries}, "
                f"soft_retries_left={soft_retries_remaining})"
            )
            raw_result = await client.generate(current_prompt)

            if raw_result:
                # 2. Stage 1 Auto-Healing + Stage 2/3 Dual-Tier Validation
                val_result = validate_translation(
                    text,
                    raw_result,
                    glossary_matches=glossary_matches,
                )
                translated = postprocess_text(val_result.healed_text)

                is_hard_valid = getattr(val_result, "is_hard_valid", len(val_result.missing_tokens) == 0)
                is_soft_valid = getattr(
                    val_result, "is_soft_valid", not getattr(val_result, "has_untranslated_cjk", False)
                )

                # Path A: Hard Valid
                if is_hard_valid:
                    # Clean pass (or soft valid with no significant issues)
                    if val_result.is_clean or is_soft_valid:
                        return translated, time.time() - start, val_result

                    # Soft failure (lingering CJK, verbatim identity, missing glossary, extreme length)
                    if soft_retries_remaining > 0:
                        soft_retries_remaining -= 1
                        logger.warning(
                            f"[{name}] Soft validation warning via [{client.model_id}]: "
                            f"{val_result.warning_messages}. "
                            f"Re-prompting ({soft_retries_remaining} soft retries left)..."
                        )
                        current_prompt = build_corrective_prompt(
                            original_text=text,
                            failed_translation=val_result.healed_text,
                            val_result=val_result,
                            base_prompt=prompt,
                            glossary_matches=glossary_matches,
                        )
                        if model_attempts[client.model_id] >= client.config.max_retries:
                            exhausted_models.add(client.model_id)
                        continue
                    else:
                        # Soft retries exhausted (soft_retries_remaining == 0) -> accept with logged warnings!
                        for w in val_result.warning_messages:
                            logger.warning(
                                f"[{name}] Soft validation accepted after retries via [{client.model_id}]: {w}"
                            )
                        return translated, time.time() - start, val_result

                # Path B: Hard failure (dropped linebreaks, corrupted engine tokens, broken tags)
                logger.warning(
                    f"[{client.model_id}] Hard validation failed on '{name}': "
                    f"missing_tokens={val_result.missing_tokens}, "
                    f"extra_tokens={val_result.extra_tokens}. Rotating..."
                )
                client.mark_error_delay()
                current_prompt = build_corrective_prompt(
                    original_text=text,
                    failed_translation=val_result.healed_text,
                    val_result=val_result,
                    base_prompt=prompt,
                    glossary_matches=glossary_matches,
                )
            else:
                # Path C: Empty response (Hard failure)
                logger.warning(f"Empty response for '{name}' via [{client.model_id}]")
                client.mark_error_delay()
                empty_val = validate_translation(text, "", glossary_matches=glossary_matches)
                current_prompt = build_corrective_prompt(
                    original_text=text,
                    failed_translation="",
                    val_result=empty_val,
                    base_prompt=prompt,
                    glossary_matches=glossary_matches,
                )

        except Exception as e:
            err_msg = str(e).lower()
            logger.error(f"Error on '{name}' via [{client.model_id}]: {e}")
            if "429" in err_msg or "quota" in err_msg:
                client.mark_quota_exceeded()
            else:
                client.mark_error_delay()

        # Update exhausted models
        if model_attempts[client.model_id] >= client.config.max_retries:
            exhausted_models.add(client.model_id)
            logger.warning(f"[{client.model_id}] exhausted retries for '{name}'.")

    # Path D: Safe Fallback when all models in pool are exhausted
    logger.critical(f"Translation permanently failed for '{name}'. Returning original text safe fallback.")
    fallback_val = validate_translation(text, text, glossary_matches=glossary_matches)
    return postprocess_text(text), time.time() - start, fallback_val
