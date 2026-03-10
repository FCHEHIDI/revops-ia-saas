from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"
    server_host: str = "0.0.0.0"
    server_port: int = 8002

    # Inter-service authentication
    internal_api_key: str = "change_me_in_production"

    # Qdrant vector store
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None

    # Embeddings (sentence-transformers)
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimensions: int = 384
    embedding_batch_size: int = 32

    # Chunking strategy
    chunk_size: int = 512
    chunk_overlap: int = 50

    # Retrieval
    default_top_k: int = 5
    min_score: float = 0.0

    # Redis ingestion queue
    redis_url: str = "redis://localhost:6379"
    indexing_queue_name: str = "rag:indexing"

    # Storage (shared volume mount from mcp-filesystem)
    storage_base_path: str = "/data/storage"

    # Observability
    otel_exporter_otlp_endpoint: Optional[str] = None


settings = Settings()
