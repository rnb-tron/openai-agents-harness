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
