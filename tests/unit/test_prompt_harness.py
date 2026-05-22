from types import SimpleNamespace

from src.harness.builder import HarnessBuilder


def _settings(**overrides):
    defaults = dict(
        agent_model_default="gpt-4o-mini",
        agent_model_reasoning="gpt-4.1-mini",
        auth_enabled=False,
        rate_limit_enabled=False,
        database_enabled=False,
        database_url="",
        memory_enabled=False,
        memory_long_term_enabled=False,
        memory_short_term_ttl=3600,
        memory_es_hosts="http://localhost:9200",
        memory_es_index="agent_memories",
        memory_vector_dimension=1536,
        memory_max_context_turns=6,
        memory_retrieval_top_k=3,
        memory_importance_threshold=0.3,
        memory_forgetting_enabled=True,
        compression_enabled=False,
        prompt_enabled=False,
        prompt_backend="yaml",
        prompt_local_dir="prompts",
        prompt_default_label="prod",
        prompt_cache_ttl_sec=300,
        prompt_warmup_names="",
        prompt_fail_open=True,
        observability_enabled=False,
        openai_api_key="",
        openai_base_url=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_harness_omits_prompt_manager_when_disabled():
    harness = HarnessBuilder(_settings(prompt_enabled=False)).build()

    assert harness.prompt_manager is None
    assert harness.context.get_resource("prompt_manager") is None
    names = {manifest.name for manifest in harness.context.capability_manifests()}
    assert "prompt" not in names


def test_harness_builds_prompt_manager_and_registers_capability_when_enabled(tmp_path):
    harness = HarnessBuilder(
        _settings(
            prompt_enabled=True,
            prompt_backend="yaml",
            prompt_local_dir=str(tmp_path),
        )
    ).build()

    assert harness.prompt_manager is not None
    assert harness.context.get_resource("prompt_manager") is harness.prompt_manager
    names = {manifest.name for manifest in harness.context.capability_manifests()}
    provided = harness.context.provided_names()
    assert "prompt" in names
    assert "prompt_manager" in provided
