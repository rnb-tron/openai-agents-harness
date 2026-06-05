"""基于 PostgreSQL pgvector 的记忆向量存储。"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import service_logger


class PostgresVectorStore:
    """使用同一个 PostgreSQL 数据库保存记忆向量并执行相似度检索。"""

    backend_name = "pgvector"
    _VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def __init__(
        self,
        session: AsyncSession,
        table_name: str = "memory_vectors",
        dimension: int = 1536,
    ) -> None:
        if not self._VALID_IDENTIFIER.fullmatch(table_name):
            raise ValueError("pgvector memory table name must be a valid SQL identifier")
        if dimension <= 0:
            raise ValueError("MEMORY_VECTOR_DIMENSION must be greater than zero")
        self.session = session
        self.table_name = table_name
        self.dimension = dimension

    def _vector_literal(self, values: list[float]) -> str:
        if len(values) != self.dimension:
            raise ValueError(f"Expected vector dimension {self.dimension}, got {len(values)}")
        return "[" + ",".join(str(float(value)) for value in values) + "]"

    async def create_index(self) -> None:
        """创建 pgvector 扩展、向量表和检索索引。"""
        table = self.table_name
        await self.session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await self.session.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    memory_id VARCHAR(64) PRIMARY KEY,
                    embedding vector({self.dimension}) NOT NULL,
                    user_id VARCHAR(64) NOT NULL,
                    session_id VARCHAR(64) NOT NULL,
                    memory_type VARCHAR(32) NOT NULL,
                    role VARCHAR(16) NOT NULL,
                    importance_score DOUBLE PRECISION NOT NULL DEFAULT 0.5,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        await self.session.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table}_user ON {table} (user_id)"))
        await self.session.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_embedding_hnsw "
                f"ON {table} USING hnsw (embedding vector_cosine_ops)"
            )
        )
        await self.session.commit()
        service_logger.info(f"pgvector table initialized: {table}")

    async def upsert(
        self,
        memory_id: str,
        embedding: list[float],
        user_id: str,
        session_id: str,
        memory_type: str,
        role: str,
        content: str,
        importance_score: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        try:
            payload = {**(metadata or {}), "content": content}
            await self.session.execute(
                text(
                    f"""
                    INSERT INTO {self.table_name} (
                        memory_id, embedding, user_id, session_id, memory_type,
                        role, importance_score, metadata
                    ) VALUES (
                        :memory_id, CAST(:embedding AS vector), :user_id,
                        :session_id, :memory_type, :role, :importance_score,
                        CAST(:metadata AS jsonb)
                    )
                    ON CONFLICT (memory_id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        user_id = EXCLUDED.user_id,
                        session_id = EXCLUDED.session_id,
                        memory_type = EXCLUDED.memory_type,
                        role = EXCLUDED.role,
                        importance_score = EXCLUDED.importance_score,
                        metadata = EXCLUDED.metadata
                    """
                ),
                {
                    "memory_id": str(memory_id),
                    "embedding": self._vector_literal(embedding),
                    "user_id": user_id,
                    "session_id": session_id,
                    "memory_type": memory_type,
                    "role": role,
                    "importance_score": importance_score,
                    "metadata": json.dumps(payload, ensure_ascii=False),
                },
            )
            return True
        except Exception as exc:
            service_logger.error(f"Failed to upsert pgvector memory: {exc}", exc_info=True)
            return False

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 3,
        user_id: str | None = None,
        session_id: str | None = None,
        memory_type: str | None = None,
        min_importance: float = 0.0,
    ) -> list[dict[str, Any]]:
        conditions = ["importance_score >= :min_importance"]
        params: dict[str, Any] = {
            "embedding": self._vector_literal(query_embedding),
            "top_k": top_k,
            "min_importance": min_importance,
        }
        if user_id:
            conditions.append("user_id = :user_id")
            params["user_id"] = user_id
        if session_id:
            conditions.append("session_id = :session_id")
            params["session_id"] = session_id
        if memory_type:
            conditions.append("memory_type = :memory_type")
            params["memory_type"] = memory_type
        try:
            result = await self.session.execute(
                text(
                    f"""
                    SELECT memory_id, user_id, session_id, memory_type, role,
                           metadata, 1 - (embedding <=> CAST(:embedding AS vector)) AS score
                    FROM {self.table_name}
                    WHERE {" AND ".join(conditions)}
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT :top_k
                    """
                ),
                params,
            )
            return [
                {
                    "memory_id": row.memory_id,
                    "score": float(row.score),
                    "user_id": row.user_id,
                    "session_id": row.session_id,
                    "memory_type": row.memory_type,
                    "role": row.role,
                    "metadata": row.metadata or {},
                }
                for row in result
            ]
        except Exception as exc:
            service_logger.error(f"Failed to search pgvector memories: {exc}", exc_info=True)
            return []

    async def delete(self, memory_ids: list[str]) -> bool:
        if not memory_ids:
            return True
        try:
            await self.session.execute(
                text(f"DELETE FROM {self.table_name} WHERE memory_id IN :memory_ids").bindparams(
                    bindparam("memory_ids", expanding=True)
                ),
                {"memory_ids": [str(item) for item in memory_ids]},
            )
            return True
        except Exception as exc:
            service_logger.error(f"Failed to delete pgvector memories: {exc}", exc_info=True)
            return False

    async def health_check(self) -> bool:
        try:
            await self.session.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            service_logger.error(f"pgvector health check failed: {exc}", exc_info=True)
            return False

    async def close(self) -> None:
        """数据库会话生命周期由 Harness 管理，无额外连接需要关闭。"""
