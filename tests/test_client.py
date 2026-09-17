"""Tests for LLM client, rate limiter, and round-robin pool (DEF-02, DEF-19)."""

from __future__ import annotations

import pytest

from lom_translate.client import LLMClient, LLMClientPool
from lom_translate.models import ModelConfig


def test_per_client_isolation(sample_app_config):
    """DEF-02: Each client is isolated to its own config without global state mutation."""
    models = sample_app_config.models
    client1 = LLMClient(models[0])
    client2 = LLMClient(models[1])

    assert client1.model_id == "model-primary"
    assert client2.model_id == "model-secondary"
    assert client1._client != client2._client


def test_client_is_free_and_in_limit():
    """Client correctly reports readiness and cooldowns."""
    m = ModelConfig(
        id="test-m",
        url="http://localhost:8000/v1",
        model_name="test",
        limit_per_minute=2,
        rate_limit_delay=0.1,
    )
    client = LLMClient(m)

    # Initially ready
    ready, wait = client.is_free_and_in_limit()
    assert ready is True
    assert wait == 0.0

    # Put into quota cooldown
    client.mark_quota_exceeded()
    ready, wait = client.is_free_and_in_limit()
    assert ready is False
    assert wait > 0.0


@pytest.mark.asyncio
async def test_pool_rotates_after_each_call(sample_app_config):
    """Pool advances cursor after each call, alternating across models."""
    pool = LLMClientPool.from_task(sample_app_config, "translate")

    c1 = await pool.acquire_next_available_client()
    c2 = await pool.acquire_next_available_client()
    c3 = await pool.acquire_next_available_client()

    assert c1.model_id == "model-primary"
    assert c2.model_id == "model-secondary"
    assert c3.model_id == "model-primary"


@pytest.mark.asyncio
async def test_pool_skips_model_in_cooldown(sample_app_config):
    """If a model is in cooldown, pool skips it and picks the next available model."""
    pool = LLMClientPool.from_task(sample_app_config, "translate")

    # Put primary model into cooldown
    pool.clients[0].mark_quota_exceeded()

    # Acquiring client should immediately return model-secondary
    c = await pool.acquire_next_available_client()
    assert c.model_id == "model-secondary"


@pytest.mark.asyncio
async def test_pool_respects_exclude_ids(sample_app_config):
    """Pool excludes models passed in exclude_ids."""
    pool = LLMClientPool.from_task(sample_app_config, "translate")

    c = await pool.acquire_next_available_client(exclude_ids={"model-primary"})
    assert c.model_id == "model-secondary"
