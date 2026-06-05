from __future__ import annotations

from typing import Any

from src.capabilities.plugin import CapabilityRegistry

try:
    from src.capabilities.advanced_agents import (
        ApprovalManager,
        CheckpointCapability,
        CheckpointConfig,
        CheckpointManager,
        HandoffCapability,
        HandoffConfig,
        HandoffManager,
        HITLCapability,
        HITLConfig,
    )

    ADVANCED_AGENTS_AVAILABLE = True
except ImportError:
    ADVANCED_AGENTS_AVAILABLE = False
    ApprovalManager = None
    CheckpointCapability = None
    CheckpointConfig = None
    CheckpointManager = None
    HandoffCapability = None
    HandoffConfig = None
    HandoffManager = None
    HITLCapability = None
    HITLConfig = None


class AdvancedAgentRuntime:
    """Optional HITL, checkpoint, and handoff wiring."""

    def __init__(
        self,
        *,
        registry: CapabilityRegistry,
        hitl_config: "HITLConfig | None" = None,
        checkpoint_config: "CheckpointConfig | None" = None,
        handoff_config: "HandoffConfig | None" = None,
    ) -> None:
        self.hitl_mgr = None
        self.checkpoint_mgr = None
        self.handoff_mgr = None
        if not ADVANCED_AGENTS_AVAILABLE:
            return

        if hitl_config is not None and ApprovalManager is not None and HITLCapability is not None:
            self.hitl_mgr = ApprovalManager(hitl_config)
            registry.register(HITLCapability(self.hitl_mgr))
        if (
            checkpoint_config is not None
            and CheckpointManager is not None
            and CheckpointCapability is not None
        ):
            self.checkpoint_mgr = CheckpointManager(checkpoint_config)
            registry.register(CheckpointCapability(self.checkpoint_mgr))
        if (
            handoff_config is not None
            and HandoffManager is not None
            and HandoffCapability is not None
        ):
            self.handoff_mgr = HandoffManager(handoff_config)
            registry.register(HandoffCapability(self.handoff_mgr))

    def build_handoffs(self, sdk_model: Any) -> list[Any]:
        if self.handoff_mgr is None:
            return []
        return self.handoff_mgr.build_configured_handoffs(sdk_model)

    async def request_approvals_from_result(
        self,
        run_result: Any,
        *,
        session_id: str,
        user_id: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        run_state = run_result.to_state().to_json()
        if self.hitl_mgr is None:
            requests = [
                {
                    "tool_name": getattr(item, "qualified_name", None)
                    or getattr(item, "name", None)
                    or "unknown",
                    "arguments": getattr(item, "arguments", None),
                    "call_id": getattr(item, "call_id", None),
                    "sdk_interruption_index": index,
                }
                for index, item in enumerate(
                    list(getattr(run_result, "interruptions", []) or [])
                )
            ]
            return run_state, requests

        run_state, requests = await self.hitl_mgr.request_approvals_from_result(
            run_result,
            session_id=session_id,
            user_id=user_id,
        )
        return run_state, [request.to_dict() for request in requests]
