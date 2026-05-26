-- PostgreSQL + pgvector Memory Backend Migration
-- 默认维度与 MEMORY_VECTOR_DIMENSION=1536 对应；修改维度时请同步调整本表。

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memory_records (
    id BIGINT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    memory_type VARCHAR(32) NOT NULL DEFAULT 'long_term',
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    embedding_id VARCHAR(64),
    metadata JSONB,
    importance_score DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted SMALLINT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_user_session_created
    ON memory_records (user_id, session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_user_memory_type
    ON memory_records (user_id, memory_type);
CREATE INDEX IF NOT EXISTS idx_session_created
    ON memory_records (session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_importance_score
    ON memory_records (importance_score);

CREATE TABLE IF NOT EXISTS memory_vectors (
    memory_id VARCHAR(64) PRIMARY KEY,
    embedding vector(1536) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    memory_type VARCHAR(32) NOT NULL,
    role VARCHAR(16) NOT NULL,
    importance_score DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memory_vectors_user ON memory_vectors (user_id);
CREATE INDEX IF NOT EXISTS idx_memory_vectors_embedding_hnsw
    ON memory_vectors USING hnsw (embedding vector_cosine_ops);
