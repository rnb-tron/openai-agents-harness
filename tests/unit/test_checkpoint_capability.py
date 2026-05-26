import pytest

from src.capabilities.advanced_agents import CheckpointCapability, CheckpointConfig, CheckpointManager
from src.capabilities.plugin import RunContext


@pytest.mark.asyncio
async def test_checkpoint_capability_skips_hooks_when_auto_save_is_disabled():
    manager = CheckpointManager(CheckpointConfig(enabled=True, auto_save=False))
    capability = CheckpointCapability(manager)
    ctx = RunContext(session_id="s1", user_input="hello", final_output="done")

    await capability.before_run(ctx)
    await capability.after_run(ctx)

    assert manager.list_checkpoints("s1") == []


@pytest.mark.asyncio
async def test_checkpoint_capability_saves_run_boundaries_when_auto_save_is_enabled():
    manager = CheckpointManager(CheckpointConfig(enabled=True, auto_save=True))
    capability = CheckpointCapability(manager)
    ctx = RunContext(
        session_id="s1",
        user_id="u1",
        user_input="hello",
        selected_model="gpt-4o-mini",
        final_output="done",
    )

    await capability.before_run(ctx)
    await capability.after_run(ctx)

    checkpoints = manager.list_checkpoints("s1")
    assert [item.description for item in checkpoints] == ["Agent 调用前", "Agent 调用完成"]
    assert checkpoints[-1].state.conversation_history[-1]["content"] == "done"
