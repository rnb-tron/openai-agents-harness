import os
from dataclasses import dataclass
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
    redis_enabled: bool
    kafka_enabled: bool
    database_enabled: bool
    redis_url: str
    redis_slave_url: str | None
    kafka_bootstrap_servers: str
    kafka_topic: str
    database_url: str
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
    memory_vector_dimension: int
    memory_max_context_turns: int
    memory_retrieval_top_k: int
    memory_importance_threshold: float
    memory_forgetting_enabled: bool

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
        redis_enabled=os.getenv("REDIS_ENABLED", "false").lower() == "true",
        kafka_enabled=os.getenv("KAFKA_ENABLED", "false").lower() == "true",
        database_enabled=os.getenv("DATABASE_ENABLED", "false").lower() == "true",
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        redis_slave_url=os.getenv("REDIS_SLAVE_URL", "") or None,
        kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        kafka_topic=os.getenv("KAFKA_TOPIC", "agent_events"),
        database_url=os.getenv("DATABASE_URL", ""),
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
        memory_vector_dimension=int(os.getenv("MEMORY_VECTOR_DIMENSION", "1536")),
        memory_max_context_turns=int(os.getenv("MEMORY_MAX_CONTEXT_TURNS", "6")),
        memory_retrieval_top_k=int(os.getenv("MEMORY_RETRIEVAL_TOP_K", "3")),
        memory_importance_threshold=float(os.getenv("MEMORY_IMPORTANCE_THRESHOLD", "0.3")),
        memory_forgetting_enabled=os.getenv("MEMORY_FORGETTING_ENABLED", "true").lower() == "true",
    )


current_settings = get_settings()
