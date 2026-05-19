"""
Elasticsearch Vector Store
向量存储层 - 用于记忆相似度检索
"""

import hashlib
from typing import Any

from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import NotFoundError

from src.core.logging import service_logger


class ElasticsearchVectorStore:
    """Elasticsearch向量存储 - 支持记忆向量检索"""

    def __init__(self, hosts: str, index_name: str, dimension: int = 1536):
        """
        初始化ES向量存储

        Args:
            hosts: ES连接地址,如 "http://localhost:9200"
            index_name: 索引名称
            dimension: 向量维度 (默认1536,对应text-embedding-3-small)
        """
        self.hosts = [hosts] if not hosts.startswith("http") else [hosts]
        self.index_name = index_name
        self.dimension = dimension
        self.client: AsyncElasticsearch | None = None

    async def init_client(self) -> None:
        """初始化ES异步客户端"""
        self.client = AsyncElasticsearch(
            self.hosts,
            request_timeout=30,
            maxsize=10,  # 连接池大小
        )
        service_logger.info(f"Elasticsearch client initialized: {self.hosts}")

    async def close(self) -> None:
        """关闭ES客户端"""
        if self.client:
            await self.client.close()
            service_logger.info("Elasticsearch client closed")

    async def create_index(self) -> None:
        """
        创建向量索引
        索引结构: memory_id (keyword) + embedding (dense_vector) + 元数据字段
        """
        if not self.client:
            await self.init_client()

        index_config = {
            "settings": {
                "number_of_shards": 3,
                "number_of_replicas": 1,
                "refresh_interval": "5s",
            },
            "mappings": {
                "properties": {
                    "memory_id": {"type": "keyword"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": self.dimension,
                        "index": True,
                        "similarity": "cosine",  # 余弦相似度
                    },
                    "user_id": {"type": "keyword"},
                    "session_id": {"type": "keyword"},
                    "memory_type": {"type": "keyword"},
                    "role": {"type": "keyword"},
                    "content_hash": {"type": "keyword"},
                    "content_preview": {"type": "text", "analyzer": "standard"},
                    "importance_score": {"type": "float"},
                    "created_at": {"type": "date"},
                    "metadata": {"type": "object"},
                }
            },
        }

        try:
            # 检查索引是否存在
            exists = await self.client.indices.exists(index=self.index_name)
            if exists:
                service_logger.info(f"Index {self.index_name} already exists")
                return

            # 创建索引
            await self.client.indices.create(index=self.index_name, body=index_config)
            service_logger.info(f"Index {self.index_name} created with dimension={self.dimension}")

        except Exception as e:
            service_logger.error(f"Failed to create index {self.index_name}: {e}", exc_info=True)
            raise

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
        """
        插入或更新向量

        Args:
            memory_id: 记忆ID (与MySQL主键对应)
            embedding: 向量数组
            user_id: 用户ID
            session_id: 会话ID
            memory_type: 记忆类型
            role: 角色
            content: 记忆内容
            importance_score: 重要性评分
            metadata: 扩展元数据

        Returns:
            bool: 是否成功
        """
        if not self.client:
            await self.init_client()

        try:
            # 生成内容hash (用于去重)
            content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

            # 内容预览 (前200字符)
            content_preview = content[:200] if len(content) > 200 else content

            doc = {
                "memory_id": str(memory_id),
                "embedding": embedding,
                "user_id": user_id,
                "session_id": session_id,
                "memory_type": memory_type,
                "role": role,
                "content_hash": content_hash,
                "content_preview": content_preview,
                "importance_score": importance_score,
                "created_at": None,  # 由MySQL管理,ES不存储
                "metadata": metadata or {},
            }

            await self.client.index(
                index=self.index_name,
                id=str(memory_id),
                document=doc,
                refresh=True,
            )

            service_logger.debug(f"Vector upserted for memory_id={memory_id}")
            return True

        except Exception as e:
            service_logger.error(f"Failed to upsert vector for memory_id={memory_id}: {e}", exc_info=True)
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
        """
        向量相似度检索

        Args:
            query_embedding: 查询向量
            top_k: 返回Top-K结果
            user_id: 用户ID过滤 (可选)
            session_id: 会话ID过滤 (可选)
            memory_type: 记忆类型过滤 (可选)
            min_importance: 最低重要性评分过滤

        Returns:
            list[dict]: 检索结果列表,包含 memory_id, score, metadata
        """
        if not self.client:
            await self.init_client()

        try:
            # 构建过滤条件
            filter_conditions = []
            if user_id:
                filter_conditions.append({"term": {"user_id": user_id}})
            if session_id:
                filter_conditions.append({"term": {"session_id": session_id}})
            if memory_type:
                filter_conditions.append({"term": {"memory_type": memory_type}})
            if min_importance > 0:
                filter_conditions.append({"range": {"importance_score": {"gte": min_importance}}})

            # 构建查询
            query = {
                "knn": {
                    "field": "embedding",
                    "query_vector": query_embedding,
                    "k": top_k,
                    "num_candidates": top_k * 2,  # 候选集大小
                    "filter": filter_conditions if filter_conditions else None,
                }
            }

            # 执行查询
            response = await self.client.search(
                index=self.index_name,
                knn=query["knn"],
                size=top_k,
                _source=["memory_id", "user_id", "session_id", "memory_type", "role", "metadata"],
            )

            # 解析结果
            results = []
            for hit in response["hits"]["hits"]:
                results.append(
                    {
                        "memory_id": hit["_source"]["memory_id"],
                        "score": hit["_score"],
                        "user_id": hit["_source"].get("user_id"),
                        "session_id": hit["_source"].get("session_id"),
                        "memory_type": hit["_source"].get("memory_type"),
                        "role": hit["_source"].get("role"),
                        "metadata": hit["_source"].get("metadata", {}),
                    }
                )

            service_logger.debug(f"Vector search returned {len(results)} results")
            return results

        except Exception as e:
            service_logger.error(f"Failed to search vectors: {e}", exc_info=True)
            return []

    async def delete(self, memory_ids: list[str]) -> bool:
        """
        批量删除向量

        Args:
            memory_ids: 记忆ID列表

        Returns:
            bool: 是否成功
        """
        if not self.client:
            await self.init_client()

        try:
            for memory_id in memory_ids:
                try:
                    await self.client.delete(index=self.index_name, id=str(memory_id), refresh=True)
                except NotFoundError:
                    pass  # 不存在则忽略

            service_logger.info(f"Deleted {len(memory_ids)} vectors from ES")
            return True

        except Exception as e:
            service_logger.error(f"Failed to delete vectors: {e}", exc_info=True)
            return False

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            bool: ES是否可用
        """
        try:
            if not self.client:
                await self.init_client()

            info = await self.client.info()
            cluster_health = await self.client.cluster.health()

            status = cluster_health.get("status", "red")
            service_logger.info(f"ES health check: status={status}, version={info.get('version', {}).get('number')}")

            return status in ("green", "yellow")

        except Exception as e:
            service_logger.error(f"ES health check failed: {e}", exc_info=True)
            return False
