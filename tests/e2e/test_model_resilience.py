"""Model routing and resilience behavior, plus an opt-in provider smoke test."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / "config" / "test.env", override=True)

from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, RunConfig, Runner

from src.capabilities.model_routing import (
    FallbackConfig,
    ModelRouter,
    ResilienceConfig,
    RetryConfig,
    TimeoutConfig,
)
from src.capabilities.model_routing.timeout import TimeoutError as ModelTimeoutError


class APIConnectionError(Exception):
    """Named like the SDK recoverable exception to exercise configured policy."""


def _completed(value):
    async def complete():
        return value

    return complete()


@pytest.mark.asyncio
async def test_basic_routing_selects_configured_default_model():
    called_models = []
    router = ModelRouter(default_model="configured-default")

    async def run_with_model(model: str):
        called_models.append(model)
        return _completed("ok")

    result = await router.run_with_resilience(run_with_model)

    assert result == "ok"
    assert called_models == ["configured-default"]
    assert router.last_metrics is None


@pytest.mark.asyncio
async def test_fallback_attempts_secondary_model_after_recoverable_failure():
    called_models = []
    router = ModelRouter(
        default_model="primary",
        resilience_config=ResilienceConfig(
            enabled=True,
            fallback=FallbackConfig(enabled=True, models=["primary", "secondary"]),
        ),
    )

    async def run_with_model(model: str):
        called_models.append(model)

        async def complete():
            if model == "primary":
                raise APIConnectionError("primary unavailable")
            return "secondary response"

        return complete()

    result = await router.run_with_resilience(run_with_model)

    assert result == "secondary response"
    assert called_models == ["primary", "secondary"]
    assert router.last_metrics.models_tried == ["primary", "secondary"]
    assert router.last_metrics.success_model == "secondary"
    assert router.last_metrics.fallback_count == 1
    assert router.last_metrics.retry_count == 0


@pytest.mark.asyncio
async def test_retry_repeats_same_model_without_counting_a_fallback():
    attempts = 0
    router = ModelRouter(
        default_model="primary",
        resilience_config=ResilienceConfig(
            enabled=True,
            retry=RetryConfig(enabled=True, max_retries=1, initial_delay=0, max_delay=0),
        ),
    )

    async def run_with_model(model: str):
        nonlocal attempts

        async def complete():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise APIConnectionError("transient failure")
            return model

        return complete()

    result = await router.run_with_resilience(run_with_model)

    assert result == "primary"
    assert attempts == 2
    assert router.last_metrics.models_tried == ["primary"]
    assert router.last_metrics.success_model == "primary"
    assert router.last_metrics.retry_count == 1
    assert router.last_metrics.fallback_count == 0


@pytest.mark.asyncio
async def test_retry_exhaustion_can_trigger_fallback_to_secondary_model():
    called_models = []
    router = ModelRouter(
        default_model="primary",
        resilience_config=ResilienceConfig(
            enabled=True,
            fallback=FallbackConfig(enabled=True, models=["primary", "secondary"]),
            retry=RetryConfig(enabled=True, max_retries=1, initial_delay=0, max_delay=0),
        ),
    )

    async def run_with_model(model: str):
        called_models.append(model)

        async def complete():
            if model == "primary":
                raise APIConnectionError("primary unavailable")
            return "secondary response"

        return complete()

    result = await router.run_with_resilience(run_with_model)

    assert result == "secondary response"
    assert called_models == ["primary", "primary", "secondary"]
    assert router.last_metrics.models_tried == ["primary", "secondary"]
    assert router.last_metrics.retry_count == 1
    assert router.last_metrics.fallback_count == 1
    assert router.last_metrics.success_model == "secondary"


@pytest.mark.asyncio
async def test_timeout_raises_when_total_budget_is_exceeded():
    router = ModelRouter(
        default_model="slow-model",
        resilience_config=ResilienceConfig(
            enabled=True,
            timeout=TimeoutConfig(enabled=True, total_timeout=0.01),
        ),
    )

    async def run_with_model(model: str):
        async def complete():
            await asyncio.sleep(0.1)
            return model

        return complete()

    with pytest.raises(ModelTimeoutError, match="Total timeout"):
        await router.run_with_resilience(run_with_model)

    assert router.last_metrics.models_tried == ["slow-model"]
    assert "TimeoutError" in router.last_metrics.error


@pytest.mark.skipif(
    os.getenv("RUN_EXTERNAL_TESTS", "false").lower() != "true",
    reason="requires external OpenAI-compatible model service; set RUN_EXTERNAL_TESTS=true",
)
@pytest.mark.asyncio
async def test_configured_model_service_smoke():
    """Perform one real request using the model and endpoint from local config."""
    model = os.environ["AGENT_MODEL_DEFAULT"]
    client = AsyncOpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.getenv("OPENAI_BASE_URL") or None,
    )
    router = ModelRouter(default_model=model)

    async def run_with_model(model: str):
        return Runner.run(
            Agent(
                name="resilience-smoke",
                instructions="Reply with only OK.",
                model=OpenAIChatCompletionsModel(
                    model=model,
                    openai_client=client,
                ),
            ),
            "Reply with only OK.",
            run_config=RunConfig(tracing_disabled=True),
        )

    result = await router.run_with_resilience(run_with_model)

    assert result.final_output.strip()
