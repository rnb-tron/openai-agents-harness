from dataclasses import dataclass
from types import SimpleNamespace

from agents import function_tool

from src.capabilities.advanced_agents import ApprovalManager, HITLCapability, HITLConfig
from src.capabilities.plugin import RunContext
from src.capabilities.tools import ToolRegistry


def test_tool_registry_maps_requires_approval_to_sdk_function_tool():
    @function_tool
    async def delete_user(user_id: str) -> str:
        return f"deleted {user_id}"

    registry = ToolRegistry()
    registry.register(
        "delete_user",
        delete_user,
        requires_approval=True,
        timeout_sec=3.0,
    )

    [agent_tool] = registry.list_agent_tools()

    assert agent_tool is not delete_user
    assert agent_tool.needs_approval is True
    assert agent_tool.timeout_seconds == 3.0
    assert delete_user.needs_approval is False


def test_apply_approval_to_native_run_state():
    manager = ApprovalManager(HITLConfig(enabled=True))
    interruption = object()

    @dataclass
    class FakeRunState:
        approved: bool = False
        rejected: bool = False

        def get_interruptions(self):
            return [interruption]

        def approve(self, item, always_approve=False):
            assert item is interruption
            assert always_approve is True
            self.approved = True

        def reject(self, item, always_reject=False, rejection_message=None):
            assert item is interruption
            self.rejected = True

    state = FakeRunState()

    manager.apply_approval_to_state(
        state,
        interruption_index=0,
        approved=True,
        always=True,
    )

    assert state.approved is True
    assert state.rejected is False


def test_tool_registry_applies_hitl_policy_to_tools_registered_later():
    @function_tool
    async def remove_record(record_id: str) -> str:
        return record_id

    registry = ToolRegistry()
    registry.configure_approval_policy(require_approval=["remove_record"])
    registry.register("remove_record", remove_record)

    [agent_tool] = registry.list_agent_tools()
    assert registry.list_approval_required() == ["remove_record"]
    assert agent_tool.needs_approval is True


async def test_request_sdk_approval_captures_run_state():
    manager = ApprovalManager(HITLConfig(enabled=True))
    interruption = SimpleNamespace(
        qualified_name="delete_user",
        arguments='{"user_id":"u1"}',
        call_id="call-1",
    )

    request = await manager.request_sdk_approval(
        interruption=interruption,
        interruption_index=2,
        run_state={"state": "snapshot"},
        session_id="s1",
        user_id="u1",
    )

    assert request.tool_name == "delete_user"
    assert request.tool_args == {"arguments": '{"user_id":"u1"}'}
    assert request.sdk_interruption_index == 2
    assert request.sdk_call_id == "call-1"
    assert request.sdk_run_state == {"state": "snapshot"}


async def test_review_sdk_approval_binds_decision_to_original_state():
    manager = ApprovalManager(HITLConfig(enabled=True))
    request = await manager.request_sdk_approval(
        interruption=SimpleNamespace(name="delete_user", arguments={}, call_id="call-1"),
        interruption_index=0,
        run_state={"state": "snapshot"},
        session_id="s1",
        user_id="u1",
    )

    result = await manager.review_sdk_approval(
        request_id=request.id,
        session_id="s1",
        interruption_index=0,
        run_state={"state": "snapshot"},
        approved=True,
        reviewer="reviewer-1",
    )

    assert result.status.value == "approved"
    assert result.reviewed_by == "reviewer-1"


async def test_list_requests_can_be_scoped_to_session():
    manager = ApprovalManager(HITLConfig(enabled=True))
    await manager.request_approval("delete_user", {}, "s1", "u1")
    await manager.request_approval("delete_user", {}, "s2", "u2")

    requests = manager.list_requests("s1")

    assert len(requests) == 1
    assert requests[0].session_id == "s1"


async def test_hitl_capability_does_not_request_approval_after_execution():
    manager = ApprovalManager(HITLConfig(enabled=True, require_approval_tools=["delete_user"]))
    capability = HITLCapability(manager)

    await capability.after_run(RunContext(session_id="s1", tool_calls=[{"tool": "delete_user", "args": {}}]))

    assert manager._requests == {}
