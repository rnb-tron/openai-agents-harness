"""
Human-in-the-Loop (HITL) 人工审批管理器

提供:
- 创建审批请求
- 批准/拒绝操作
- 等待审批结果 (阻塞)
- 超时控制
"""

import asyncio
import time
import uuid
from enum import Enum
from typing import Optional, Any

from src.core.logging import setup_logger
from .config import HITLConfig

logger = setup_logger("advanced_agents.hitl")


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class ApprovalRequest:
    """审批请求"""
    
    def __init__(
        self,
        id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        session_id: str,
        user_id: str,
        reason: str = "",
    ):
        self.id = id
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.session_id = session_id
        self.user_id = user_id
        self.reason = reason
        self.status = ApprovalStatus.PENDING
        self.created_at = time.time()
        self.reviewed_by: Optional[str] = None
        self.reviewed_at: Optional[float] = None
        self.review_comment: Optional[str] = None
        self.sdk_interruption_index: int | None = None
        self.sdk_call_id: str | None = None
        self.sdk_run_state: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation for APIs and snapshots."""
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "reason": self.reason,
            "status": self.status.value,
            "created_at": self.created_at,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "review_comment": self.review_comment,
            "sdk_interruption_index": self.sdk_interruption_index,
            "sdk_call_id": self.sdk_call_id,
        }


class ApprovalManager:
    """HITL 审批管理器"""
    
    def __init__(self, config: HITLConfig):
        self.config = config
        self._requests: dict[str, ApprovalRequest] = {}
        self._approval_events: dict[str, asyncio.Event] = {}
    
    def is_enabled(self) -> bool:
        """是否启用 HITL"""
        return self.config.enabled
    
    def requires_approval(self, tool_name: str) -> bool:
        """检查工具是否需要审批"""
        if not self.config.enabled:
            return False
        
        # 如果在自动审批列表中,不需要审批
        if tool_name in self.config.auto_approve_tools:
            return False
        
        # 如果在需要审批列表中,需要审批
        if tool_name in self.config.require_approval_tools:
            return True
        
        # 默认不需要审批
        return False

    def list_requests(self, session_id: str | None = None) -> list[ApprovalRequest]:
        """List approval requests, optionally scoped to one chat session."""
        requests = list(self._requests.values())
        if session_id is not None:
            requests = [request for request in requests if request.session_id == session_id]
        return sorted(requests, key=lambda request: request.created_at)
    
    async def request_approval(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        session_id: str,
        user_id: str,
        reason: str = "",
    ) -> ApprovalRequest:
        """创建审批请求"""
        request_id = str(uuid.uuid4())
        request = ApprovalRequest(
            id=request_id,
            tool_name=tool_name,
            tool_args=tool_args,
            session_id=session_id,
            user_id=user_id,
            reason=reason,
        )
        
        self._requests[request_id] = request
        self._approval_events[request_id] = asyncio.Event()
        
        logger.info(
            "approval_requested",
            extra={
                "request_id": request_id,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "session_id": session_id,
                "user_id": user_id,
                "reason": reason,
            },
        )
        
        return request

    async def request_sdk_approval(
        self,
        *,
        interruption: Any,
        interruption_index: int,
        run_state: dict[str, Any],
        session_id: str,
        user_id: str,
        reason: str = "",
    ) -> ApprovalRequest:
        """Create an approval request from an OpenAI Agents SDK interruption."""
        tool_name = getattr(interruption, "qualified_name", None) or getattr(
            interruption, "name", None
        ) or "unknown"
        raw_args = getattr(interruption, "arguments", None)
        tool_args: dict[str, Any]
        if isinstance(raw_args, dict):
            tool_args = raw_args
        elif raw_args:
            tool_args = {"arguments": raw_args}
        else:
            tool_args = {}
        request = await self.request_approval(
            tool_name=tool_name,
            tool_args=tool_args,
            session_id=session_id,
            user_id=user_id,
            reason=reason or f"工具 {tool_name} 需要人工审批",
        )
        request.sdk_interruption_index = interruption_index
        request.sdk_call_id = getattr(interruption, "call_id", None)
        request.sdk_run_state = run_state
        return request

    async def request_approvals_from_result(
        self,
        run_result: Any,
        *,
        session_id: str,
        user_id: str,
    ) -> tuple[dict[str, Any] | None, list[ApprovalRequest]]:
        """Create approval requests from a native SDK RunResult interruption payload."""
        interruptions = list(getattr(run_result, "interruptions", []) or [])
        if not interruptions:
            return None, []

        run_state = run_result.to_state().to_json()
        requests = [
            await self.request_sdk_approval(
                interruption=interruption,
                interruption_index=index,
                run_state=run_state,
                session_id=session_id,
                user_id=user_id,
            )
            for index, interruption in enumerate(interruptions)
        ]
        return run_state, requests

    def apply_approval_to_state(
        self,
        run_state: Any,
        *,
        interruption_index: int,
        approved: bool,
        always: bool = False,
        rejection_message: str | None = None,
    ) -> None:
        """Apply a human decision to an SDK RunState before resuming via Runner.run_streamed()."""
        interruptions = run_state.get_interruptions()
        if interruption_index < 0 or interruption_index >= len(interruptions):
            raise ValueError(f"审批中断不存在: {interruption_index}")
        interruption = interruptions[interruption_index]
        if approved:
            run_state.approve(interruption, always_approve=always)
        else:
            run_state.reject(
                interruption,
                always_reject=always,
                rejection_message=rejection_message,
            )

    async def review_sdk_approval(
        self,
        *,
        request_id: str,
        session_id: str,
        interruption_index: int,
        run_state: dict[str, Any],
        approved: bool,
        reviewer: str,
        comment: str = "",
    ) -> ApprovalRequest:
        """Validate and record a decision for a native SDK interruption."""
        request = self._requests.get(request_id)
        if not request:
            raise ValueError(f"审批请求不存在: {request_id}")
        if request.session_id != session_id:
            raise ValueError("审批请求与会话不匹配")
        if request.sdk_interruption_index != interruption_index:
            raise ValueError("审批请求与中断序号不匹配")
        if request.sdk_run_state != run_state:
            raise ValueError("审批请求与运行状态不匹配")

        if approved:
            await self.approve(request_id, reviewer=reviewer, comment=comment)
        else:
            await self.reject(request_id, reviewer=reviewer, reason=comment)
        return request
    
    async def approve(
        self,
        request_id: str,
        reviewer: str,
        comment: str = "",
    ) -> bool:
        """批准请求"""
        request = self._requests.get(request_id)
        if not request:
            raise ValueError(f"审批请求不存在: {request_id}")
        
        if request.status != ApprovalStatus.PENDING:
            raise ValueError(f"审批请求已完成: {request.status}")
        
        request.status = ApprovalStatus.APPROVED
        request.reviewed_by = reviewer
        request.reviewed_at = time.time()
        request.review_comment = comment
        
        # 通知等待者
        event = self._approval_events.get(request_id)
        if event:
            event.set()
        
        logger.info(
            "approval_approved",
            extra={
                "request_id": request_id,
                "reviewer": reviewer,
                "comment": comment,
            },
        )
        return True
    
    async def reject(
        self,
        request_id: str,
        reviewer: str,
        reason: str = "",
    ) -> bool:
        """拒绝请求"""
        request = self._requests.get(request_id)
        if not request:
            raise ValueError(f"审批请求不存在: {request_id}")
        
        if request.status != ApprovalStatus.PENDING:
            raise ValueError(f"审批请求已完成: {request.status}")
        
        request.status = ApprovalStatus.REJECTED
        request.reviewed_by = reviewer
        request.reviewed_at = time.time()
        request.review_comment = reason
        
        # 通知等待者
        event = self._approval_events.get(request_id)
        if event:
            event.set()
        
        logger.info(
            "approval_rejected",
            extra={
                "request_id": request_id,
                "reviewer": reviewer,
                "reason": reason,
            },
        )
        return True
    
    async def wait_for_approval(
        self,
        request_id: str,
        timeout: Optional[float] = None,
    ) -> bool:
        """等待审批结果 (阻塞)"""
        event = self._approval_events.get(request_id)
        if not event:
            raise ValueError(f"审批请求不存在: {request_id}")
        
        timeout = timeout or self.config.approval_timeout
        
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            request = self._requests[request_id]
            return request.status == ApprovalStatus.APPROVED
        except asyncio.TimeoutError:
            request = self._requests[request_id]
            request.status = ApprovalStatus.TIMEOUT
            logger.warning(
                "approval_timeout",
                extra={
                    "request_id": request_id,
                    "timeout": timeout,
                },
            )
            return False
    
    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """获取审批请求"""
        return self._requests.get(request_id)
    
    def cleanup(self):
        """清理所有请求和事件"""
        self._requests.clear()
        self._approval_events.clear()
        logger.info("hitl_manager_cleaned")
