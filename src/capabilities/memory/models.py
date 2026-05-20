"""
Memory System SQLAlchemy Models
MySQL存储层 - 长期记忆数据模型
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BIGINT,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    SMALLINT,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import AsyncAttrs

from src.infrastructure.database import Base


class MemoryRecord(AsyncAttrs, Base):
    """记忆记录模型 - 存储长期记忆数据"""

    __tablename__ = "memory_records"

    # 主键 (雪花ID)
    id = Column(BIGINT, primary_key=True, autoincrement=False, comment="主键ID (雪花算法生成)")

    # 标识字段
    user_id = Column(String(64), nullable=False, index=True, comment="用户ID")
    session_id = Column(String(64), nullable=False, index=True, comment="会话ID")

    # 记忆分类
    memory_type = Column(
        String(32),
        nullable=False,
        default="long_term",
        comment="记忆类型: short_term/long_term/episodic/semantic",
    )
    role = Column(String(16), nullable=False, comment="角色: user/assistant/system")

    # 记忆内容
    content = Column(Text, nullable=False, comment="记忆内容")
    embedding_id = Column(String(64), nullable=True, comment="ES向量ID")

    # 元数据
    extra_metadata = Column("metadata", JSON, nullable=True, comment="扩展元数据 (tokens, timestamp, tags等)")

    # 重要性评分与访问统计
    importance_score = Column(
        Float, nullable=False, default=0.5, index=True, comment="重要性评分 (0-1, 用于遗忘策略)"
    )
    access_count = Column(Integer, nullable=False, default=0, comment="访问次数")
    last_accessed_at = Column(DateTime, nullable=True, comment="最后访问时间")

    # 时间戳
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )

    # 软删除
    is_deleted = Column(SMALLINT, nullable=False, default=0, comment="软删除标记: 0-正常, 1-已删除")

    # 联合索引
    __table_args__ = (
        Index("idx_user_session_created", "user_id", "session_id", "created_at"),
        Index("idx_user_memory_type", "user_id", "memory_type"),
        Index("idx_session_created", "session_id", "created_at"),
    )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "memory_type": self.memory_type,
            "role": self.role,
            "content": self.content,
            "embedding_id": self.embedding_id,
            "metadata": self.extra_metadata,
            "importance_score": self.importance_score,
            "access_count": self.access_count,
            "last_accessed_at": self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_deleted": self.is_deleted,
        }

    def __repr__(self) -> str:
        return (
            f"<MemoryRecord(id={self.id}, user_id={self.user_id}, "
            f"session_id={self.session_id}, type={self.memory_type})>"
        )
