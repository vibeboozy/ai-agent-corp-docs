"""
ANCHOR: app.config.settings
PURPOSE: Load env into Settings; stub flags and connection placeholders.
Dependencies: pydantic_settings; .env.example keys
DO:
- Default stubs on
- Document keys in .env.example
DONT:
- Require live secrets to import Settings
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings — mirrors server/.env.example (stubs on by default)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # --- stubs ---
    use_stubs: bool = Field(default=True, alias="USE_STUBS")
    llm_use_stub: bool = Field(default=True, alias="LLM_USE_STUB")
    embeddings_use_stub: bool = Field(default=True, alias="EMBEDDINGS_USE_STUB")
    qdrant_use_stub: bool = Field(default=True, alias="QDRANT_USE_STUB")
    docling_use_stub: bool = Field(default=True, alias="DOCLING_USE_STUB")
    libreoffice_use_stub: bool = Field(default=True, alias="LIBREOFFICE_USE_STUB")
    escalation_use_stub: bool = Field(default=True, alias="ESCALATION_USE_STUB")
    persistence_use_stub: bool = Field(default=True, alias="PERSISTENCE_USE_STUB")

    # --- app ---
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    api_prefix: str = Field(default="/api/v1", alias="API_PREFIX")
    auth_mode: str = Field(default="none", alias="AUTH_MODE")
    auth_officer_token: str | None = Field(default=None, alias="AUTH_OFFICER_TOKEN")

    # --- docs corpus (local-only; not committed) ---
    # Prefer DOCS_CORPUS_PATH; DOCS_DIR accepted as alias via model validator below.
    docs_corpus_path: str = Field(default="docs", alias="DOCS_CORPUS_PATH")
    docs_dir: str | None = Field(default=None, alias="DOCS_DIR")

    # --- persistence ---
    database_url: str | None = Field(
        default="postgresql+asyncpg://rag:rag@127.0.0.1:5432/rag_agent",
        alias="DATABASE_URL",
    )
    database_pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW")
    database_pool_timeout_s: float = Field(default=30.0, alias="DATABASE_POOL_TIMEOUT_S")
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")

    # --- LLM ---
    llm_base_url: str = Field(default="https://example.invalid/v1", alias="LLM_BASE_URL")
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_model: str = Field(default="gpt-4.1-mini", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=1500, alias="LLM_MAX_TOKENS")
    llm_timeout_s: float = Field(default=180.0, alias="LLM_TIMEOUT_S")

    # --- embeddings ---
    embeddings_base_url: str = Field(
        default="https://example.invalid/v1", alias="EMBEDDINGS_BASE_URL"
    )
    embeddings_api_key: str | None = Field(default=None, alias="EMBEDDINGS_API_KEY")
    embeddings_dense_model: str = Field(default="bge-m3-dense", alias="EMBEDDINGS_DENSE_MODEL")
    embeddings_sparse_model: str = Field(default="bge-m3-sparse", alias="EMBEDDINGS_SPARSE_MODEL")
    embeddings_dense_dim: int = Field(default=1024, alias="EMBEDDINGS_DENSE_DIM")
    embeddings_batch_size: int = Field(default=32, alias="EMBEDDINGS_BATCH_SIZE")
    embeddings_timeout_s: float = Field(default=120.0, alias="EMBEDDINGS_TIMEOUT_S")

    # --- qdrant ---
    qdrant_url: str = Field(default="http://127.0.0.1:6333", alias="QDRANT_URL")
    qdrant_api_key: str | None = Field(default=None, alias="QDRANT_API_KEY")
    qdrant_collection: str = Field(default="corp_regs", alias="QDRANT_COLLECTION")
    qdrant_timeout_s: float = Field(default=60.0, alias="QDRANT_TIMEOUT_S")
    qdrant_upsert_batch: int = Field(default=64, alias="QDRANT_UPSERT_BATCH")

    # --- docling ---
    docling_base_url: str = Field(
        default="https://example.invalid/docling", alias="DOCLING_BASE_URL"
    )
    docling_api_key: str | None = Field(default=None, alias="DOCLING_API_KEY")
    docling_timeout_s: float = Field(default=300.0, alias="DOCLING_TIMEOUT_S")

    # --- libreoffice ---
    libreoffice_soffice_path: str = Field(default="soffice", alias="LIBREOFFICE_SOFFICE_PATH")
    libreoffice_timeout_s: float = Field(default=120.0, alias="LIBREOFFICE_TIMEOUT_S")

    # --- retrieval / dialogue / grounding ---
    retrieval_prefetch: int = Field(default=50, alias="RETRIEVAL_PREFETCH")
    retrieval_prefer_latest: bool = Field(default=True, alias="RETRIEVAL_PREFER_LATEST")
    dialogue_max_clarify_turns: int = Field(default=3, alias="DIALOGUE_MAX_CLARIFY_TURNS")
    grounding_min_citations: int = Field(default=1, alias="GROUNDING_MIN_CITATIONS")
    grounding_min_score: float = Field(default=0.0, alias="GROUNDING_MIN_SCORE")

    # --- quality ---
    quality_service_email: str = Field(
        default="quality@example.invalid", alias="QUALITY_SERVICE_EMAIL"
    )
    escalation_enabled: bool = Field(default=True, alias="ESCALATION_ENABLED")
    escalation_email_subject_prefix: str = Field(
        default="[RAG-Escalation]", alias="ESCALATION_EMAIL_SUBJECT_PREFIX"
    )

    # --- logging ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")
    log_request_body: bool = Field(default=False, alias="LOG_REQUEST_BODY")
    log_redact_secrets: bool = Field(default=True, alias="LOG_REDACT_SECRETS")
    log_correlation_header: str = Field(default="X-Request-Id", alias="LOG_CORRELATION_HEADER")

    # --- egress ---
    egress_allow_hosts: str | None = Field(default=None, alias="EGRESS_ALLOW_HOSTS")

    def stub_for(self, service: str) -> bool:
        """Resolve whether a named adapter should use its stub."""
        if self.use_stubs:
            return True
        mapping = {
            "llm": self.llm_use_stub,
            "embeddings": self.embeddings_use_stub,
            "qdrant": self.qdrant_use_stub,
            "vectorstore": self.qdrant_use_stub,
            "docling": self.docling_use_stub,
            "libreoffice": self.libreoffice_use_stub,
            "escalation": self.escalation_use_stub,
            "persistence": self.persistence_use_stub,
        }
        return mapping.get(service, True)

    def resolved_docs_corpus_path(self) -> str:
        """Local corpus directory (gitignored); DOCS_DIR overrides when set."""
        if self.docs_dir:
            return self.docs_dir
        return self.docs_corpus_path

    def egress_hosts(self) -> set[str]:
        if not self.egress_allow_hosts:
            return set()
        return {h.strip().lower() for h in self.egress_allow_hosts.split(",") if h.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    """Drop Settings cache and DI container so API/CLI see fresh env flags."""
    get_settings.cache_clear()
    # Avoid circular import at module load; clear container when available.
    try:
        from app.config.factories import reset_container

        reset_container()
    except Exception:
        pass
