"""基于 Mem0 的记忆管理器。

Mem0 负责用户偏好、长期记忆的抽取和检索；当前 manager 保留会话内短期
记忆，并把 Mem0 适配成 ``MemoryCapability`` 使用的统一方法。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI

from src.capabilities.memory.store import ShortTermMemory
from src.core.config import Settings
from src.core.logging import service_logger
from src.infrastructure.redis_client import get_redis_client

_SESSION_SUMMARY_SYSTEM_PROMPT = """你是一个面向 Agent 执行恢复的会话摘要器。
请把会话压缩为结构化中文摘要，保留：
1. 当前任务和目标
2. 已确认事实与用户约束
3. 用户临时要求
4. 工具或外部结果
5. 未完成事项
6. 最近结论
跳过寒暄，不要编造。"""


class Mem0MemoryManager:
    """使用 Mem0 持久化用户记忆的管理器。

    运行时契约：
    - ``get_context`` 在 BEFORE_RUN 阶段调用，负责拼接用户偏好、相关长期
      记忆和当前会话最近几轮消息。最近消息 Redis 优先，Redis 不可用或
      miss 时从 MySQL 会话记录回源；
    - ``add_memory`` 在 AFTER_RUN 阶段调用，写入 Redis 短期缓存并异步更新
      会话摘要；长期记忆只做异步噪声过滤，是否抽取、合并或忽略交给 Mem0
      决定。
    """

    provider_name = "mem0"
    vector_store = None
    embedding_provider = None
    supports_vector_search = True

    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
        redis_client: Any | None = None,
        session_store: Any | None = None,
        summary_client: Any | None = None,
    ) -> None:
        self.settings = settings
        self.short_term = ShortTermMemory(
            redis_client=redis_client,
            ttl=settings.memory_short_term_ttl,
        )
        self._client = client
        self._session_store = session_store
        self._summary_client = summary_client
        self._pending_user_inputs: dict[str, str] = {}
        self._preference_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._summary_tasks: set[asyncio.Task] = set()

    async def init(self) -> None:
        if self.short_term.redis is None and getattr(self.settings, "redis_enabled", False):
            self.short_term.redis = get_redis_client()
        if self._client is None:
            self._client = self._build_client()
        service_logger.info("Mem0 memory manager initialized")

    def _build_client(self) -> Any:
        mode = getattr(self.settings, "memory_mem0_mode", "local").strip().lower()
        if mode == "platform":
            try:
                from mem0 import MemoryClient
            except ImportError as exc:  # pragma: no cover - 依赖可选安装包
                raise RuntimeError(
                    "MEMORY_ENABLED=true with MEMORY_MEM0_MODE=platform requires mem0ai"
                ) from exc
            api_key = getattr(self.settings, "memory_mem0_api_key", "")
            if not api_key:
                raise ValueError("MEMORY_MEM0_MODE=platform requires MEMORY_MEM0_API_KEY")
            return MemoryClient(api_key=api_key)

        try:
            from mem0 import Memory
        except ImportError as exc:  # pragma: no cover - 依赖可选安装包
            raise RuntimeError("MEMORY_ENABLED=true requires package mem0ai") from exc

        raw_config = getattr(self.settings, "memory_mem0_config_json", "") or ""
        if raw_config.strip():
            return Memory.from_config(json.loads(raw_config))

        return Memory.from_config(self._build_local_config())

    def _build_local_config(self) -> dict[str, Any]:
        openai_base_url = getattr(self.settings, "openai_base_url", None)
        llm_config: dict[str, Any] = {
            "api_key": getattr(self.settings, "openai_api_key", ""),
            "model": getattr(self.settings, "agent_model_default", "gpt-4o-mini"),
        }
        embedder_config: dict[str, Any] = {
            "api_key": getattr(self.settings, "openai_api_key", ""),
            "model": getattr(
                self.settings,
                "memory_embedding_model",
                "text-embedding-3-small",
            ),
        }
        if openai_base_url:
            llm_config["openai_base_url"] = openai_base_url
            embedder_config["openai_base_url"] = openai_base_url

        config: dict[str, Any] = {
            "llm": {
                "provider": "openai",
                "config": llm_config,
            },
            "embedder": {
                "provider": "openai",
                "config": embedder_config,
            },
        }
        vector_store = self._build_vector_store_config()
        if vector_store is not None:
            config["vector_store"] = vector_store
        return config

    def _build_vector_store_config(self) -> dict[str, Any] | None:
        backend = getattr(self.settings, "memory_vector_store", "none").strip().lower()
        if backend in ("", "none"):
            return None
        if backend == "pgvector":
            database_url = (
                getattr(self.settings, "memory_pgvector_database_url", "")
                or getattr(self.settings, "database_url", "")
            )
            if not database_url:
                raise ValueError(
                    "MEMORY_VECTOR_STORE=pgvector requires MEMORY_PGVECTOR_DATABASE_URL"
                )
            return {
                "provider": "pgvector",
                "config": {
                    "connection_string": database_url,
                    "collection_name": getattr(
                        self.settings,
                        "memory_pgvector_table",
                        "agent_memories",
                    ),
                    "embedding_model_dims": getattr(
                        self.settings,
                        "memory_vector_dimension",
                        1536,
                    ),
                },
            }
        if backend in ("elasticsearch", "es"):
            return {
                "provider": "elasticsearch",
                "config": {
                    "host": getattr(
                        self.settings,
                        "memory_es_hosts",
                        "http://localhost:9200",
                    ),
                    "index_name": getattr(
                        self.settings,
                        "memory_es_index",
                        "agent_memories",
                    ),
                },
            }
        raise ValueError(f"Unsupported MEMORY_VECTOR_STORE: {backend}")

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    async def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self.client, method_name)
        if inspect.iscoroutinefunction(method):
            return await method(*args, **kwargs)
        return await asyncio.to_thread(method, *args, **kwargs)

    async def add_memory(
        self,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        memory_type: str = "long_term",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        await self.short_term.append(session_id, role, content, metadata)
        if role == "user":
            self._pending_user_inputs[session_id] = content
            return True
        if role != "assistant":
            return True

        user_content = self._pending_user_inputs.pop(session_id, "")
        messages = [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": content},
        ]
        self._schedule_session_summary_update(
            session_id=session_id,
            user_id=user_id,
            latest_messages=messages,
        )

        if not await self._should_submit_to_mem0(user_content, content):
            return True

        mem0_metadata = {
            "source": "chat",
            "source_session_id": session_id,
            "memory_type": memory_type,
            **(metadata or {}),
        }
        try:
            await self._add_to_mem0(
                messages,
                user_id=user_id,
                session_id=session_id,
                metadata=mem0_metadata,
            )
            self._preference_cache.pop(user_id, None)
            return True
        except Exception as exc:
            service_logger.warning(
                f"Mem0 add failed open: session={session_id}, user={user_id}, error={exc}"
            )
            return False

    async def _add_to_mem0(
        self,
        messages: list[dict[str, str]],
        *,
        user_id: str,
        session_id: str,
        metadata: dict[str, Any],
    ) -> Any:
        try:
            return await self._call(
                "add",
                messages,
                user_id=user_id,
                run_id=session_id,
                metadata=metadata,
            )
        except TypeError:
            return await self._call("add", messages, user_id=user_id, metadata=metadata)

    async def get_context(
        self,
        session_id: str,
        user_id: str,
        user_input: str,
        max_turns: int | None = None,
        enable_retrieval: bool = True,
    ) -> str:
        short_memories = await self._get_recent_short_memories(
            session_id,
            max_turns or self.settings.memory_max_context_turns,
        )
        session_summary = await self._get_session_summary(session_id)
        preferences = await self._get_preferences(user_id)
        long_memories: list[dict[str, Any]] = []
        if enable_retrieval and self._should_retrieve(user_input):
            long_memories = await self.search_memories(
                user_id=user_id,
                query=user_input,
                top_k=self.settings.memory_retrieval_top_k,
            )
        return self._format_context(
            preferences=preferences,
            long_memories=long_memories,
            session_summary=session_summary,
            short_memories=short_memories,
            current_input=user_input,
        )

    async def _get_recent_short_memories(
        self,
        session_id: str,
        max_turns: int,
    ) -> list[dict[str, Any]]:
        memories = await self.short_term.get_recent(session_id, max_turns)
        if memories:
            return memories
        if self._session_store is None:
            return []
        messages = await self._list_recent_session_messages(
            session_id=session_id,
            limit=max_turns * 2,
        )
        return [
            {
                "role": item.get("role", "unknown"),
                "content": item.get("content", ""),
                "timestamp": item.get("created_at"),
                "metadata": {
                    **(item.get("metadata") or {}),
                    "source": "mysql_session_store",
                    "message_id": item.get("id"),
                },
            }
            for item in messages
            if item.get("content")
        ]

    async def _list_recent_session_messages(
        self,
        *,
        session_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if self._session_store is None:
            return []
        if hasattr(self._session_store, "list_recent_messages"):
            return await self._session_store.list_recent_messages(
                session_id=session_id,
                limit=limit,
            )
        messages = await self._session_store.list_messages(
            session_id=session_id,
            limit=limit,
        )
        return messages[-limit:] if limit > 0 else []

    async def _count_session_messages(self, session_id: str, fallback_count: int) -> int:
        if self._session_store is None:
            return fallback_count
        if hasattr(self._session_store, "count_messages"):
            return await self._session_store.count_messages(session_id)
        return fallback_count

    async def _get_preferences(self, user_id: str) -> list[dict[str, Any]]:
        ttl = getattr(self.settings, "memory_preference_cache_ttl_sec", 900)
        now = time.time()
        cached = self._preference_cache.get(user_id)
        if cached and cached[0] > now:
            return cached[1]

        preferences = await self.search_memories(
            user_id=user_id,
            query="user preferences, stable instructions, communication style",
            top_k=max(self.settings.memory_retrieval_top_k, 10),
        )
        preferences = self._select_effective_preferences(preferences)
        self._preference_cache[user_id] = (now + ttl, preferences)
        return preferences

    async def search_memories(
        self,
        user_id: str,
        query: str,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        limit = top_k or self.settings.memory_retrieval_top_k
        if self._is_preference_query(query):
            limit = max(limit, 10)
        try:
            raw = await self._search_mem0(query=query, user_id=user_id, limit=limit)
            results = self._normalize_search_results(raw)
            if self._is_preference_query(query):
                results = self._select_effective_preferences(results)
            return results[: top_k or len(results)]
        except Exception as exc:
            service_logger.warning(
                f"Mem0 search failed open: user={user_id}, error={exc}"
            )
            return []

    async def _search_mem0(self, *, query: str, user_id: str, limit: int) -> Any:
        try:
            return await self._call(
                "search",
                query=query,
                filters={"user_id": user_id},
                limit=limit,
            )
        except TypeError:
            try:
                return await self._call(
                    "search",
                    query,
                    user_id=user_id,
                    top_k=limit,
                )
            except TypeError:
                return await self._call("search", query, user_id=user_id, limit=limit)

    @staticmethod
    def _normalize_search_results(raw: Any) -> list[dict[str, Any]]:
        if raw is None:
            return []
        if isinstance(raw, dict):
            raw_items = raw.get("results") or raw.get("memories") or []
        else:
            raw_items = raw
        results: list[dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, str):
                results.append({"content": item, "memory": item})
                continue
            if not isinstance(item, dict):
                continue
            content = (
                item.get("memory")
                or item.get("content")
                or item.get("text")
                or item.get("metadata", {}).get("content")
                or ""
            )
            if content:
                normalized = dict(item)
                normalized["content"] = content
                results.append(normalized)
        return results

    @staticmethod
    def _infer_preference_keys(content: str) -> list[str]:
        text = content.lower()
        keys: list[str] = []
        rules = (
            (
                "response_language",
                (
                    "英文",
                    "英语",
                    "english",
                    "中文",
                    "汉语",
                    "chinese",
                    "使用中文",
                    "use chinese",
                    "use english",
                ),
            ),
            (
                "answer_order",
                (
                    "先给结论",
                    "结论先行",
                    "先说结论",
                    "conclusion first",
                    "answer first",
                    "tl;dr first",
                ),
            ),
            (
                "answer_detail",
                (
                    "简洁",
                    "详细",
                    "展开说明",
                    "concise",
                    "brief",
                    "detailed",
                    "more detail",
                ),
            ),
            (
                "answer_format",
                (
                    "markdown",
                    "表格",
                    "列表",
                    "代码块",
                    "bullet",
                    "table",
                    "format",
                ),
            ),
            (
                "tone",
                (
                    "语气",
                    "正式",
                    "轻松",
                    "口语",
                    "tone",
                    "formal",
                    "casual",
                ),
            ),
        )
        for key, signals in rules:
            if any(signal in text for signal in signals):
                keys.append(key)
        if not keys and any(signal in text for signal in ("偏好", "prefer", "preference")):
            keys.append("general_preference")
        return keys

    @staticmethod
    def _is_preference_query(query: str) -> bool:
        text = query.lower()
        return any(
            signal in text
            for signal in (
                "偏好",
                "用户偏好",
                "preference",
                "preferences",
                "communication style",
                "stable instructions",
            )
        )

    @classmethod
    def _select_effective_preferences(
        cls,
        memories: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        selected_by_key: dict[str, dict[str, Any]] = {}
        passthrough: list[dict[str, Any]] = []
        for memory in memories:
            keys = cls._preference_keys(memory)
            if not keys:
                passthrough.append(memory)
                continue
            for key in keys:
                existing = selected_by_key.get(key)
                if existing is None or cls._memory_timestamp(memory) >= cls._memory_timestamp(existing):
                    selected_by_key[key] = memory

        ordered: list[dict[str, Any]] = []
        seen: set[str] = set()
        for memory in sorted(
            selected_by_key.values(),
            key=cls._memory_timestamp,
            reverse=True,
        ):
            identity = cls._memory_identity(memory)
            if identity in seen:
                continue
            seen.add(identity)
            ordered.append(memory)
        ordered.extend(passthrough)
        return ordered

    @classmethod
    def _preference_keys(cls, memory: dict[str, Any]) -> list[str]:
        metadata = cls._memory_metadata(memory)
        raw_keys = metadata.get("preference_keys") or metadata.get("preference_key")
        if isinstance(raw_keys, str):
            keys = [raw_keys]
        elif isinstance(raw_keys, list):
            keys = [str(key) for key in raw_keys if key]
        else:
            keys = []
        if metadata.get("memory_kind") == "preference" and not keys:
            keys = ["general_preference"]
        if not keys:
            keys = cls._infer_preference_keys(memory.get("content", ""))
        return keys

    @staticmethod
    def _memory_metadata(memory: dict[str, Any]) -> dict[str, Any]:
        metadata = memory.get("metadata") or {}
        return metadata if isinstance(metadata, dict) else {}

    @classmethod
    def _memory_timestamp(cls, memory: dict[str, Any]) -> float:
        metadata = cls._memory_metadata(memory)
        for value in (
            metadata.get("updated_at"),
            metadata.get("created_at"),
            memory.get("updated_at"),
            memory.get("created_at"),
        ):
            timestamp = cls._parse_timestamp(value)
            if timestamp is not None:
                return timestamp
        return 0.0

    @staticmethod
    def _parse_timestamp(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if not isinstance(value, str) or not value:
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).timestamp()
        except ValueError:
            return None

    @staticmethod
    def _memory_identity(memory: dict[str, Any]) -> str:
        return str(
            memory.get("id")
            or memory.get("memory_id")
            or memory.get("content")
            or json.dumps(memory, sort_keys=True, ensure_ascii=False)
        )

    @staticmethod
    def _should_retrieve(user_input: str) -> bool:
        text = user_input.strip()
        if len(text) < 8:
            return False
        low_value = {"好的", "好", "ok", "OK", "谢谢", "继续", "收到", "嗯", "是的"}
        return text not in low_value

    @staticmethod
    async def _should_submit_to_mem0(user_content: str, assistant_content: str) -> bool:
        """只过滤明显噪声，语义层面的记忆抽取交给 Mem0。"""
        user_text = user_content.strip()
        assistant_text = assistant_content.strip()
        if not user_text or not assistant_text:
            return False
        low_value_pairs = {
            ("好的", "收到"),
            ("好", "收到"),
            ("ok", "ok"),
            ("OK", "OK"),
            ("谢谢", "不客气"),
            ("嗯", "好的"),
        }
        if (user_text, assistant_text) in low_value_pairs:
            return False
        text = f"{user_text}\n{assistant_text}"
        blocked = (
            "操作已被拒绝",
            "rejected_by_user",
            "工具调用失败",
            "tool call failed",
            "Traceback",
        )
        return not any(marker in text for marker in blocked)

    async def _get_session_summary(self, session_id: str) -> str | None:
        if not getattr(self.settings, "memory_session_summary_enabled", False):
            return None
        cached = await self.short_term.get_summary(session_id)
        if cached and cached.get("summary"):
            return str(cached["summary"])
        if self._session_store is None:
            return None
        stored = await self._session_store.get_summary(session_id)
        if not stored:
            return None
        await self.short_term.save_summary(
            session_id,
            stored,
            ttl=getattr(self.settings, "memory_session_summary_cache_ttl", 2592000),
        )
        return str(stored["summary"])

    def _schedule_session_summary_update(
        self,
        *,
        session_id: str,
        user_id: str,
        latest_messages: list[dict[str, Any]] | None = None,
    ) -> None:
        if not getattr(self.settings, "memory_session_summary_enabled", False):
            return
        task = asyncio.create_task(
            self.update_session_summary(
                session_id=session_id,
                user_id=user_id,
                latest_messages=latest_messages,
            )
        )
        self._summary_tasks.add(task)
        task.add_done_callback(self._summary_tasks.discard)
        task.add_done_callback(self._log_summary_task_error)

    @staticmethod
    def _log_summary_task_error(task: asyncio.Task) -> None:
        try:
            task.result()
        except Exception as exc:
            service_logger.warning(
                "session_summary_update_failed",
                extra={"error_type": type(exc).__name__, "error": str(exc)},
            )

    async def update_session_summary(
        self,
        *,
        session_id: str,
        user_id: str,
        latest_messages: list[dict[str, Any]] | None = None,
    ) -> bool:
        if not getattr(self.settings, "memory_session_summary_enabled", False):
            return False
        if self._session_store is None:
            return False

        stored_summary = await self._session_store.get_summary(session_id)
        covered_count = int((stored_summary or {}).get("covered_message_count") or 0)
        messages = await self.short_term.get_all(session_id)
        message_count = len(messages)
        if not messages:
            message_count = await self._count_session_messages(session_id, 0)
            if message_count > 0:
                source_limit = min(
                    message_count,
                    getattr(self.settings, "memory_session_summary_max_source_messages", 20),
                )
                messages = await self._list_recent_session_messages(
                    session_id=session_id,
                    limit=source_limit,
                )
            if latest_messages:
                messages = [*messages, *latest_messages]
                message_count += len(latest_messages)
        if not messages:
            if stored_summary:
                await self.short_term.save_summary(
                    session_id,
                    stored_summary,
                    ttl=getattr(self.settings, "memory_session_summary_cache_ttl", 2592000),
                )
            return False

        initial_threshold = getattr(self.settings, "memory_session_summary_initial_messages", 4)
        update_threshold = getattr(self.settings, "memory_session_summary_update_messages", 6)
        should_create = stored_summary is None and message_count >= initial_threshold
        should_update = stored_summary is not None and (message_count - covered_count) >= update_threshold
        if not should_create and not should_update:
            if stored_summary:
                await self.short_term.save_summary(
                    session_id,
                    stored_summary,
                    ttl=getattr(self.settings, "memory_session_summary_cache_ttl", 2592000),
                )
            return False

        if stored_summary is None:
            new_messages = messages
        else:
            recent_offset = max(0, covered_count - (message_count - len(messages)))
            new_messages = messages[recent_offset:]
            if not new_messages:
                new_messages = messages
        summary_text = await self._generate_session_summary(
            previous_summary=(stored_summary or {}).get("summary"),
            messages=new_messages,
        )
        saved = await self._session_store.upsert_summary(
            session_id=session_id,
            user_id=user_id,
            summary=summary_text,
            covered_message_count=message_count,
            model=self._summary_model(),
            metadata={"source": "memory_session_summary"},
        )
        await self.short_term.save_summary(
            session_id,
            saved,
            ttl=getattr(self.settings, "memory_session_summary_cache_ttl", 2592000),
        )
        return True

    def _summary_model(self) -> str:
        return (
            getattr(self.settings, "memory_session_summary_model", "")
            or getattr(self.settings, "agent_model_default", "gpt-4o-mini")
        )

    async def _generate_session_summary(
        self,
        *,
        previous_summary: str | None,
        messages: list[dict[str, Any]],
    ) -> str:
        block = self._format_messages_for_summary(messages)
        user_prompt = (
            f"已有会话摘要：\n{previous_summary}\n\n"
            f"新增消息：\n{block}\n\n"
            "请在旧摘要基础上更新会话摘要。"
            if previous_summary
            else f"会话消息：\n{block}\n\n请生成第一版会话摘要。"
        )
        client = self._summary_client or self._build_summary_client()
        resp = await client.chat.completions.create(
            model=self._summary_model(),
            messages=[
                {"role": "system", "content": _SESSION_SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=getattr(self.settings, "memory_session_summary_max_tokens", 512),
            temperature=0.2,
        )
        content = resp.choices[0].message.content or ""
        return content.strip()

    def _build_summary_client(self) -> AsyncOpenAI:
        client_kwargs: dict[str, Any] = {"api_key": getattr(self.settings, "openai_api_key", "")}
        base_url = getattr(self.settings, "openai_base_url", None)
        if base_url:
            client_kwargs["base_url"] = base_url
        return AsyncOpenAI(**client_kwargs)

    @staticmethod
    def _format_messages_for_summary(messages: list[dict[str, Any]]) -> str:
        lines = []
        for item in messages:
            role = item.get("role", "unknown")
            content = item.get("content", "")
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _format_context(
        *,
        preferences: list[dict[str, Any]],
        long_memories: list[dict[str, Any]],
        session_summary: str | None,
        short_memories: list[dict[str, Any]],
        current_input: str,
    ) -> str:
        context_parts: list[str] = []
        if preferences:
            context_parts.append("=== User Preferences ===")
            for idx, memory in enumerate(preferences, 1):
                context_parts.append(f"[{idx}] {memory['content']}")
            context_parts.append("")
        if long_memories:
            context_parts.append("=== Relevant Long-Term Memories ===")
            for idx, memory in enumerate(long_memories, 1):
                context_parts.append(f"[{idx}] {memory['content']}")
            context_parts.append("")
        if session_summary:
            context_parts.append("=== Session Summary ===")
            context_parts.append(session_summary)
            context_parts.append("")
        if short_memories:
            context_parts.append("=== Recent Conversation ===")
            for memory in short_memories:
                role = memory.get("role", "user")
                content = memory.get("content", "")
                context_parts.append(f"{role}: {content}")
            context_parts.append("")
        context_parts.append(f"user: {current_input}")
        return "\n".join(context_parts)

    async def clear_session(self, session_id: str) -> bool:
        self._pending_user_inputs.pop(session_id, None)
        return await self.short_term.clear(session_id)

    async def clear_user_memories(self, user_id: str) -> bool:
        self._preference_cache.pop(user_id, None)
        return await self._delete_mem0_memories(user_id=user_id)

    async def _delete_mem0_memories(self, **filters: str | None) -> bool:
        filters = {key: value for key, value in filters.items() if value}
        if not filters:
            return True
        try:
            await self._call("delete_all", **filters)
            return True
        except Exception as exc:
            service_logger.warning(
                "mem0_delete_all_failed",
                extra={
                    "filters": filters,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            return False

    async def get_stats(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        recent = await self.short_term.get_all(session_id) if session_id else []
        summary = await self._get_session_summary_record(session_id) if session_id else None
        return {
            "backend": "mem0",
            "user_id": user_id,
            "short_term_backend": "redis" if self.short_term.redis is not None else "disabled",
            "short_term_session_id": session_id,
            "short_term_count": len(recent),
            "short_term_recent": recent[-10:],
            "session_summary": summary,
            "vector_store": getattr(self.settings, "memory_vector_store", "none"),
            "preference_cache_users": len(self._preference_cache),
            "pending_sessions": len(self._pending_user_inputs),
        }

    async def _get_session_summary_record(
        self,
        session_id: str | None,
    ) -> dict[str, Any] | None:
        if not session_id or not getattr(self.settings, "memory_session_summary_enabled", False):
            return None
        cached = await self.short_term.get_summary(session_id)
        if cached:
            return cached
        if self._session_store is None:
            return None
        stored = await self._session_store.get_summary(session_id)
        if stored:
            await self.short_term.save_summary(
                session_id,
                stored,
                ttl=getattr(self.settings, "memory_session_summary_cache_ttl", 2592000),
            )
        return stored

    async def cleanup_old_memories(self) -> dict[str, Any]:
        return {"skipped": True, "reason": "mem0_manages_memory_lifecycle"}

    async def close(self) -> None:
        if self._summary_tasks:
            await asyncio.gather(*self._summary_tasks, return_exceptions=True)
            self._summary_tasks.clear()
        if self._client is None:
            return
        close = getattr(self._client, "close", None)
        if close is None:
            return
        if inspect.iscoroutinefunction(close):
            await close()
        else:
            await asyncio.to_thread(close)
