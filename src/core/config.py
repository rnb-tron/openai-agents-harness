import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def _load_env_file() -> str:
    env_type = os.getenv("ENVTYPE", "test")
    project_root = Path(__file__).resolve().parents[2]
    env_file = project_root / "config" / f"{env_type}.env"
    if env_file.exists():
        load_dotenv(env_file)
    return env_type


def _split_csv(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def _load_json_object(raw: str, name: str) -> dict[str, dict]:
    if not raw.strip():
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


@dataclass
class Settings:
    env_type: str
    app_name: str
    app_profile: str
    debug: bool
    host: str
    port: int
    log_level: str
    http_client_enabled: bool
    http_timeout_seconds: float
    http_connect_timeout_seconds: float
    http_read_timeout_seconds: float
    http_write_timeout_seconds: float
    http_max_connections: int
    http_max_keepalive_connections: int
    http_keepalive_expiry_seconds: float
    http_follow_redirects: bool
    http_verify_tls: bool
    redis_enabled: bool
    kafka_enabled: bool
    database_enabled: bool
    redis_url: str
    redis_slave_url: str | None
    kafka_bootstrap_servers: str
    kafka_topic: str
    database_url: str
    database_pool_size: int
    database_max_overflow: int
    database_pool_timeout_seconds: float
    database_pool_recycle_seconds: int
    database_pool_pre_ping: bool
    openai_api_key: str
    openai_base_url: str | None
    agent_model_default: str
    agent_model_reasoning: str
    
    # Memory System Configuration
    memory_enabled: bool
    memory_short_term_ttl: int
    memory_long_term_enabled: bool
    memory_es_hosts: str
    memory_es_index: str
    memory_vector_backend: str
    memory_pgvector_table: str
    memory_embedding_provider: str
    memory_embedding_model: str
    memory_vector_dimension: int
    memory_max_context_turns: int
    memory_retrieval_top_k: int
    memory_importance_threshold: float
    memory_forgetting_enabled: bool
    
    # Observability System Configuration
    observability_enabled: bool

    # Human-in-the-Loop (SDK native tool approval)
    hitl_enabled: bool = False
    hitl_approval_timeout: float = 300.0
    hitl_require_approval_tools: list[str] = field(default_factory=list)
    hitl_auto_approve_tools: list[str] = field(default_factory=list)

    # In-process execution checkpoint snapshots
    checkpoint_enabled: bool = False
    checkpoint_max_checkpoints: int = 10
    checkpoint_auto_save: bool = True

    # OpenAI Agents SDK native handoffs
    handoff_enabled: bool = False
    handoff_agents: dict[str, dict] = field(default_factory=dict)

    # Protocol-layer security (default disabled, zero overhead when off)
    auth_enabled: bool = False
    auth_strict: bool = False
    auth_jwt_algorithm: str = "HS256"
    auth_jwt_secret: str = ""
    auth_jwt_public_key: str = ""
    auth_jwt_issuer: Optional[str] = None
    auth_jwt_audience: Optional[str] = None
    auth_jwt_leeway_sec: int = 30
    auth_skip_paths: list = None  # type: ignore[assignment]

    rate_limit_enabled: bool = False
    rate_limit_backend: str = "redis"  # redis / memory
    rate_limit_default_limit: int = 60
    rate_limit_default_window_sec: int = 60
    rate_limit_default_burst: int = 10
    rate_limit_key_strategy: str = "principal_or_ip"
    rate_limit_fail_open: bool = False
    rate_limit_routes: str = ""  # JSON string: {"/chat": {"limit": 5, "window_sec": 60, "burst": 1}}
    rate_limit_skip_paths: list = None  # type: ignore[assignment]

    # Context Compression Capability (default disabled, zero overhead when off)
    compression_enabled: bool = False
    compression_strategy: str = "token_budget"  # token_budget | rolling_summary | hybrid
    compression_safety_ratio: float = 0.9
    compression_keep_recent_turns: int = 4
    compression_summary_model: str = ""  # empty -> reuse agent_model_default
    compression_summary_max_tokens: int = 512
    compression_cache_ttl_sec: int = 3600
    compression_fail_open: bool = True

    # Prompt Management Capability (default disabled, zero overhead when off)
    prompt_enabled: bool = False
    prompt_backend: str = "composite"  # composite | langfuse | yaml
    prompt_local_dir: str = "prompts"
    prompt_default_label: str = "prod"
    prompt_cache_ttl_sec: int = 300
    prompt_warmup_names: str = ""  # CSV of prompt names to warm at startup
    prompt_fail_open: bool = True

    @property
    def is_smoke(self) -> bool:
        return self.app_profile == "smoke" or self.env_type == "smoke"


def get_settings() -> Settings:
    env_type = _load_env_file()
    app_profile = os.getenv("APP_PROFILE", env_type)
    return Settings(
        env_type=env_type,
        app_name=os.getenv("APP_NAME", "openai-agent-sdk"),
        app_profile=app_profile,
        debug=os.getenv("DEBUG", "false").lower() == "true",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        http_client_enabled=os.getenv("HTTP_CLIENT_ENABLED", "true").lower() == "true",
        http_timeout_seconds=float(os.getenv("HTTP_TIMEOUT_SECONDS", "30")),
        http_connect_timeout_seconds=float(os.getenv("HTTP_CONNECT_TIMEOUT_SECONDS", "10")),
        http_read_timeout_seconds=float(os.getenv("HTTP_READ_TIMEOUT_SECONDS", "20")),
        http_write_timeout_seconds=float(os.getenv("HTTP_WRITE_TIMEOUT_SECONDS", "10")),
        http_max_connections=int(os.getenv("HTTP_MAX_CONNECTIONS", "100")),
        http_max_keepalive_connections=int(os.getenv("HTTP_MAX_KEEPALIVE_CONNECTIONS", "20")),
        http_keepalive_expiry_seconds=float(os.getenv("HTTP_KEEPALIVE_EXPIRY_SECONDS", "30")),
        http_follow_redirects=os.getenv("HTTP_FOLLOW_REDIRECTS", "true").lower() == "true",
        http_verify_tls=os.getenv("HTTP_VERIFY_TLS", "true").lower() == "true",
        redis_enabled=os.getenv("REDIS_ENABLED", "false").lower() == "true",
        kafka_enabled=os.getenv("KAFKA_ENABLED", "false").lower() == "true",
        database_enabled=os.getenv("DATABASE_ENABLED", "false").lower() == "true",
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        redis_slave_url=os.getenv("REDIS_SLAVE_URL", "") or None,
        kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        kafka_topic=os.getenv("KAFKA_TOPIC", "agent_events"),
        database_url=os.getenv("DATABASE_URL", ""),
        database_pool_size=int(os.getenv("DATABASE_POOL_SIZE", "10")),
        database_max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "20")),
        database_pool_timeout_seconds=float(os.getenv("DATABASE_POOL_TIMEOUT_SECONDS", "30")),
        database_pool_recycle_seconds=int(os.getenv("DATABASE_POOL_RECYCLE_SECONDS", "1800")),
        database_pool_pre_ping=os.getenv("DATABASE_POOL_PRE_PING", "true").lower() == "true",
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "") or None,
        agent_model_default=os.getenv("AGENT_MODEL_DEFAULT", "gpt-4o-mini"),
        agent_model_reasoning=os.getenv("AGENT_MODEL_REASONING", "gpt-4.1-mini"),
        # Memory Configuration
        memory_enabled=os.getenv("MEMORY_ENABLED", "false").lower() == "true",
        memory_short_term_ttl=int(os.getenv("MEMORY_SHORT_TERM_TTL", "3600")),
        memory_long_term_enabled=os.getenv("MEMORY_LONG_TERM_ENABLED", "false").lower() == "true",
        memory_es_hosts=os.getenv("MEMORY_ES_HOSTS", "http://localhost:9200"),
        memory_es_index=os.getenv("MEMORY_ES_INDEX", "agent_memories"),
        memory_vector_backend=os.getenv("MEMORY_VECTOR_BACKEND", "none"),
        memory_pgvector_table=os.getenv("MEMORY_PGVECTOR_TABLE", "memory_vectors"),
        memory_embedding_provider=os.getenv("MEMORY_EMBEDDING_PROVIDER", "none"),
        memory_embedding_model=os.getenv(
            "MEMORY_EMBEDDING_MODEL", "text-embedding-3-small"
        ),
        memory_vector_dimension=int(os.getenv("MEMORY_VECTOR_DIMENSION", "1536")),
        memory_max_context_turns=int(os.getenv("MEMORY_MAX_CONTEXT_TURNS", "6")),
        memory_retrieval_top_k=int(os.getenv("MEMORY_RETRIEVAL_TOP_K", "3")),
        memory_importance_threshold=float(os.getenv("MEMORY_IMPORTANCE_THRESHOLD", "0.3")),
        memory_forgetting_enabled=os.getenv("MEMORY_FORGETTING_ENABLED", "true").lower() == "true",
        # Observability Configuration
        observability_enabled=os.getenv("LANGFUSE_ENABLED", "false").lower() == "true",
        # Human-in-the-Loop
        hitl_enabled=os.getenv("HITL_ENABLED", "false").lower() == "true",
        hitl_approval_timeout=float(os.getenv("HITL_APPROVAL_TIMEOUT", "300")),
        hitl_require_approval_tools=_split_csv(os.getenv("HITL_REQUIRE_APPROVAL_TOOLS", "")),
        hitl_auto_approve_tools=_split_csv(os.getenv("HITL_AUTO_APPROVE_TOOLS", "")),
        # Execution Checkpoints
        checkpoint_enabled=os.getenv("CHECKPOINT_ENABLED", "false").lower() == "true",
        checkpoint_max_checkpoints=int(os.getenv("CHECKPOINT_MAX_CHECKPOINTS", "10")),
        checkpoint_auto_save=os.getenv("CHECKPOINT_AUTO_SAVE", "true").lower() == "true",
        # Native Handoffs
        handoff_enabled=os.getenv("HANDOFF_ENABLED", "false").lower() == "true",
        handoff_agents=_load_json_object(os.getenv("HANDOFF_AGENTS_JSON", ""), "HANDOFF_AGENTS_JSON"),
        # Protocol-layer Auth
        auth_enabled=os.getenv("AUTH_ENABLED", "false").lower() == "true",
        auth_strict=os.getenv("AUTH_STRICT", "false").lower() == "true",
        auth_jwt_algorithm=os.getenv("AUTH_JWT_ALGORITHM", "HS256"),
        auth_jwt_secret=os.getenv("AUTH_JWT_SECRET", ""),
        auth_jwt_public_key=os.getenv("AUTH_JWT_PUBLIC_KEY", ""),
        auth_jwt_issuer=os.getenv("AUTH_JWT_ISSUER", "") or None,
        auth_jwt_audience=os.getenv("AUTH_JWT_AUDIENCE", "") or None,
        auth_jwt_leeway_sec=int(os.getenv("AUTH_JWT_LEEWAY_SEC", "30")),
        auth_skip_paths=_split_csv(os.getenv("AUTH_SKIP_PATHS", "/health,/docs,/redoc,/openapi.json,/ui")),
        # Protocol-layer Rate Limit
        rate_limit_enabled=os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true",
        rate_limit_backend=os.getenv("RATE_LIMIT_BACKEND", "redis"),
        rate_limit_default_limit=int(os.getenv("RATE_LIMIT_DEFAULT_LIMIT", "60")),
        rate_limit_default_window_sec=int(os.getenv("RATE_LIMIT_DEFAULT_WINDOW_SEC", "60")),
        rate_limit_default_burst=int(os.getenv("RATE_LIMIT_DEFAULT_BURST", "10")),
        rate_limit_key_strategy=os.getenv("RATE_LIMIT_KEY_STRATEGY", "principal_or_ip"),
        rate_limit_fail_open=os.getenv("RATE_LIMIT_FAIL_OPEN", "false").lower() == "true",
        rate_limit_routes=os.getenv("RATE_LIMIT_ROUTES", ""),
        rate_limit_skip_paths=_split_csv(os.getenv("RATE_LIMIT_SKIP_PATHS", "/health,/docs,/redoc,/openapi.json,/ui")),
        # Context Compression
        compression_enabled=os.getenv("COMPRESSION_ENABLED", "false").lower() == "true",
        compression_strategy=os.getenv("COMPRESSION_STRATEGY", "token_budget"),
        compression_safety_ratio=float(os.getenv("COMPRESSION_SAFETY_RATIO", "0.9")),
        compression_keep_recent_turns=int(os.getenv("COMPRESSION_KEEP_RECENT_TURNS", "4")),
        compression_summary_model=os.getenv("COMPRESSION_SUMMARY_MODEL", ""),
        compression_summary_max_tokens=int(os.getenv("COMPRESSION_SUMMARY_MAX_TOKENS", "512")),
        compression_cache_ttl_sec=int(os.getenv("COMPRESSION_CACHE_TTL_SEC", "3600")),
        compression_fail_open=os.getenv("COMPRESSION_FAIL_OPEN", "true").lower() == "true",
        # Prompt Management
        prompt_enabled=os.getenv("PROMPT_ENABLED", "false").lower() == "true",
        prompt_backend=os.getenv("PROMPT_BACKEND", "composite"),
        prompt_local_dir=os.getenv("PROMPT_LOCAL_DIR", "prompts"),
        prompt_default_label=os.getenv("PROMPT_DEFAULT_LABEL", "prod"),
        prompt_cache_ttl_sec=int(os.getenv("PROMPT_CACHE_TTL_SEC", "300")),
        prompt_warmup_names=os.getenv("PROMPT_WARMUP_NAMES", ""),
        prompt_fail_open=os.getenv("PROMPT_FAIL_OPEN", "true").lower() == "true",
    )


current_settings = get_settings()
