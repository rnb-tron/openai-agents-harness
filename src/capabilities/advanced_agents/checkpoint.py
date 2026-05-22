"""
Checkpoint 检查点管理器

提供:
- 保存 Agent 状态
- 恢复到历史状态
- 检查点历史管理
- 自动保存机制
"""

import time
import uuid
from typing import Optional, Any
from dataclasses import dataclass, field

from .config import CheckpointConfig, AgentState
from src.core.logging import setup_logger

logger = setup_logger("advanced_agents.checkpoint")


@dataclass
class Checkpoint:
    """检查点"""
    id: str
    session_id: str
    timestamp: float
    state: AgentState
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def context(self) -> dict[str, Any]:
        """Backward-compatible shortcut for tests and older callers."""
        return self.state.context


class CheckpointManager:
    """Checkpoint 检查点管理器"""
    
    def __init__(self, config: CheckpointConfig):
        self.config = config
        self._checkpoints: dict[str, Checkpoint] = {}
        self._session_checkpoints: dict[str, list[str]] = {}  # session_id -> [checkpoint_ids]
    
    def is_enabled(self) -> bool:
        """是否启用 Checkpoint"""
        return self.config.enabled
    
    async def save(
        self,
        session_id: str,
        state: AgentState,
        description: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """保存检查点"""
        if not self.config.enabled:
            return ""
        
        checkpoint_id = str(uuid.uuid4())
        checkpoint = Checkpoint(
            id=checkpoint_id,
            session_id=session_id,
            timestamp=time.time(),
            state=state,
            description=description,
            metadata=metadata or {},
        )
        
        # 保存检查点
        self._checkpoints[checkpoint_id] = checkpoint
        
        # 更新会话检查点列表
        if session_id not in self._session_checkpoints:
            self._session_checkpoints[session_id] = []
        self._session_checkpoints[session_id].append(checkpoint_id)
        
        # 限制检查点数量
        if len(self._session_checkpoints[session_id]) > self.config.max_checkpoints:
            old_id = self._session_checkpoints[session_id].pop(0)
            if old_id in self._checkpoints:
                del self._checkpoints[old_id]
        
        logger.info(
            "checkpoint_saved",
            extra={
                "checkpoint_id": checkpoint_id,
                "session_id": session_id,
                "description": description,
            },
        )
        return checkpoint_id
    
    async def load(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """加载检查点"""
        return self._checkpoints.get(checkpoint_id)
    
    async def restore(self, checkpoint_id: str) -> Optional[AgentState]:
        """恢复到检查点状态"""
        checkpoint = await self.load(checkpoint_id)
        if not checkpoint:
            logger.warning(
                "checkpoint_not_found",
                extra={"checkpoint_id": checkpoint_id},
            )
            return None

        logger.info(
            "checkpoint_restored",
            extra={
                "checkpoint_id": checkpoint_id,
                "description": checkpoint.description,
                "timestamp": checkpoint.timestamp,
            },
        )

        return checkpoint.state
    
    def list_checkpoints(self, session_id: str) -> list[Checkpoint]:
        """列出会话的所有检查点"""
        if session_id not in self._session_checkpoints:
            return []
        
        checkpoint_ids = self._session_checkpoints[session_id]
        return [
            self._checkpoints[cid]
            for cid in checkpoint_ids
            if cid in self._checkpoints
        ]
    
    async def get_latest(self, session_id: str) -> Optional[Checkpoint]:
        """获取最新检查点"""
        checkpoints = self.list_checkpoints(session_id)
        if not checkpoints:
            return None
        return checkpoints[-1]
    
    def cleanup(self):
        """清理所有检查点"""
        self._checkpoints.clear()
        self._session_checkpoints.clear()
        logger.info("checkpoint_manager_cleaned")
