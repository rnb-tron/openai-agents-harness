"""基于关系数据库的会话持久化仓储。"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.capabilities.session_store.models import (
    ChatMessageRecord,
    ChatSessionRecord,
    ChatSessionSummaryRecord,
)
from src.core.logging import setup_logger

logger = setup_logger("capabilities.session_store")


class SessionStore:
    """持久化用户会话和完整消息流水。

    这层记录产品态会话数据和完整消息流水；当 Redis 短期缓存未启用或 miss
    时，记忆管理器会从这里读取最近消息作为短期原文记忆来源。
    """

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_session(
        self,
        *,
        session_id: str,
        user_id: str | None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_user_id = user_id or "anonymous"
        async with self._session_factory() as db:
            existing = await db.get(ChatSessionRecord, session_id)
            if existing is None:
                existing = ChatSessionRecord(
                    id=session_id,
                    user_id=normalized_user_id,
                    title=title or "新会话",
                    metadata_json=metadata or {},
                )
                db.add(existing)
            else:
                if title:
                    existing.title = title
                if metadata:
                    existing.metadata_json = {**(existing.metadata_json or {}), **metadata}
                existing.updated_at = datetime.now()
            await db.commit()
            await db.refresh(existing)
            return self._session_to_dict(existing)

    async def ensure_session(
        self,
        *,
        session_id: str,
        user_id: str | None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        normalized_user_id = user_id or "anonymous"
        async with self._session_factory() as db:
            existing = await db.get(ChatSessionRecord, session_id)
            if existing is None:
                db.add(
                    ChatSessionRecord(
                        id=session_id,
                        user_id=normalized_user_id,
                        title=title,
                        metadata_json=metadata or {},
                    )
                )
            else:
                if title and not existing.title:
                    existing.title = title
                if metadata:
                    existing.metadata_json = {**(existing.metadata_json or {}), **metadata}
                existing.updated_at = datetime.now()
            await db.commit()

    async def append_message(
        self,
        *,
        session_id: str,
        user_id: str | None,
        role: str,
        content: str,
        model: str | None = None,
        status: str = "completed",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        normalized_user_id = user_id or "anonymous"
        async with self._session_factory() as db:
            existing = await db.get(ChatSessionRecord, session_id)
            if existing is None:
                db.add(
                    ChatSessionRecord(
                        id=session_id,
                        user_id=normalized_user_id,
                        title=self._default_title(content) if role == "user" else None,
                    )
                )
            else:
                existing.updated_at = datetime.now()
            message_id = str(uuid.uuid4())
            db.add(
                ChatMessageRecord(
                    id=message_id,
                    session_id=session_id,
                    user_id=normalized_user_id,
                    role=role,
                    content=content,
                    model=model,
                    status=status,
                    metadata_json=metadata or {},
                )
            )
            await db.commit()
            return message_id

    async def append_turn(
        self,
        *,
        session_id: str,
        user_id: str | None,
        user_input: str,
        assistant_output: str | None,
        model: str | None = None,
        status: str = "completed",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        normalized_user_id = user_id or "anonymous"
        async with self._session_factory() as db:
            existing = await db.get(ChatSessionRecord, session_id)
            if existing is None:
                db.add(
                    ChatSessionRecord(
                        id=session_id,
                        user_id=normalized_user_id,
                        title=self._default_title(user_input),
                    )
                )
            else:
                existing.updated_at = datetime.now()
            db.add(
                ChatMessageRecord(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    user_id=normalized_user_id,
                    role="user",
                    content=user_input,
                    status="completed",
                    metadata_json=metadata or {},
                )
            )
            if assistant_output is not None:
                db.add(
                    ChatMessageRecord(
                        id=str(uuid.uuid4()),
                        session_id=session_id,
                        user_id=normalized_user_id,
                        role="assistant",
                        content=assistant_output,
                        model=model,
                        status=status,
                        metadata_json=metadata or {},
                    )
                )
            await db.commit()

    async def list_sessions(
        self,
        *,
        user_id: str | None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        normalized_user_id = user_id or "anonymous"
        async with self._session_factory() as db:
            rows = await db.execute(
                select(ChatSessionRecord)
                .where(ChatSessionRecord.user_id == normalized_user_id)
                .order_by(ChatSessionRecord.updated_at.desc())
                .limit(limit)
            )
            return [self._session_to_dict(row) for row in rows.scalars()]

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        async with self._session_factory() as db:
            row = await db.get(ChatSessionRecord, session_id)
            return self._session_to_dict(row) if row is not None else None

    async def delete_session(self, session_id: str) -> bool:
        async with self._session_factory() as db:
            row = await db.get(ChatSessionRecord, session_id)
            if row is None:
                return False
            await db.execute(delete(ChatMessageRecord).where(ChatMessageRecord.session_id == session_id))
            await db.execute(delete(ChatSessionSummaryRecord).where(ChatSessionSummaryRecord.session_id == session_id))
            await db.execute(delete(ChatSessionRecord).where(ChatSessionRecord.id == session_id))
            await db.commit()
            return True

    async def list_messages(
        self,
        *,
        session_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        async with self._session_factory() as db:
            rows = await db.execute(
                select(ChatMessageRecord)
                .where(ChatMessageRecord.session_id == session_id)
                .order_by(
                    ChatMessageRecord.created_at.asc(),
                    case(
                        (ChatMessageRecord.role == "user", 0),
                        (ChatMessageRecord.role == "assistant", 1),
                        else_=2,
                    ),
                )
                .limit(limit)
            )
            return [self._message_to_dict(row) for row in rows.scalars()]

    async def list_recent_messages(
        self,
        *,
        session_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """读取最近 N 条消息，并按自然对话顺序返回。"""
        async with self._session_factory() as db:
            rows = await db.execute(
                select(ChatMessageRecord)
                .where(ChatMessageRecord.session_id == session_id)
                .order_by(
                    ChatMessageRecord.created_at.desc(),
                    case(
                        (ChatMessageRecord.role == "assistant", 0),
                        (ChatMessageRecord.role == "user", 1),
                        else_=2,
                    ),
                )
                .limit(limit)
            )
            messages = [self._message_to_dict(row) for row in rows.scalars()]
            return list(reversed(messages))

    async def count_messages(self, session_id: str) -> int:
        """统计会话消息数量，用于摘要更新的高水位判断。"""
        async with self._session_factory() as db:
            count = await db.scalar(
                select(func.count()).select_from(ChatMessageRecord).where(ChatMessageRecord.session_id == session_id)
            )
            return int(count or 0)

    async def get_summary(self, session_id: str) -> dict[str, Any] | None:
        async with self._session_factory() as db:
            row = await db.get(ChatSessionSummaryRecord, session_id)
            return self._summary_to_dict(row) if row is not None else None

    async def upsert_summary(
        self,
        *,
        session_id: str,
        user_id: str | None,
        summary: str,
        covered_message_count: int,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_user_id = user_id or "anonymous"
        async with self._session_factory() as db:
            existing_session = await db.get(ChatSessionRecord, session_id)
            if existing_session is None:
                db.add(
                    ChatSessionRecord(
                        id=session_id,
                        user_id=normalized_user_id,
                        title="新会话",
                    )
                )
            else:
                existing_session.updated_at = datetime.now()

            row = await db.get(ChatSessionSummaryRecord, session_id)
            if row is None:
                row = ChatSessionSummaryRecord(
                    session_id=session_id,
                    user_id=normalized_user_id,
                    summary=summary,
                    covered_message_count=covered_message_count,
                    model=model,
                    metadata_json=metadata or {},
                )
                db.add(row)
            else:
                row.user_id = normalized_user_id
                row.summary = summary
                row.covered_message_count = covered_message_count
                row.model = model
                row.version += 1
                row.metadata_json = {**(row.metadata_json or {}), **(metadata or {})}
                row.updated_at = datetime.now()
            await db.commit()
            await db.refresh(row)
            return self._summary_to_dict(row)

    @staticmethod
    def _default_title(text: str) -> str:
        normalized = " ".join(text.strip().split())
        return normalized[:40] if normalized else "新会话"

    @staticmethod
    def _session_to_dict(row: ChatSessionRecord) -> dict[str, Any]:
        return {
            "id": row.id,
            "user_id": row.user_id,
            "title": row.title,
            "status": row.status,
            "metadata": row.metadata_json or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _message_to_dict(row: ChatMessageRecord) -> dict[str, Any]:
        return {
            "id": row.id,
            "session_id": row.session_id,
            "user_id": row.user_id,
            "role": row.role,
            "content": row.content,
            "model": row.model,
            "status": row.status,
            "metadata": row.metadata_json or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _summary_to_dict(row: ChatSessionSummaryRecord) -> dict[str, Any]:
        return {
            "session_id": row.session_id,
            "user_id": row.user_id,
            "summary": row.summary,
            "covered_message_count": row.covered_message_count,
            "model": row.model,
            "version": row.version,
            "metadata": row.metadata_json or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
