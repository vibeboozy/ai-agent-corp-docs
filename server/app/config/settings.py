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
    """Minimal settings skeleton — extend toward full .env.example in later phases."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    use_stubs: bool = Field(default=True, alias="USE_STUBS")
    llm_use_stub: bool = Field(default=True, alias="LLM_USE_STUB")
    embeddings_use_stub: bool = Field(default=True, alias="EMBEDDINGS_USE_STUB")
    qdrant_use_stub: bool = Field(default=True, alias="QDRANT_USE_STUB")
    docling_use_stub: bool = Field(default=True, alias="DOCLING_USE_STUB")
    libreoffice_use_stub: bool = Field(default=True, alias="LIBREOFFICE_USE_STUB")
    escalation_use_stub: bool = Field(default=True, alias="ESCALATION_USE_STUB")
    persistence_use_stub: bool = Field(default=True, alias="PERSISTENCE_USE_STUB")

    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    dialogue_max_clarify_turns: int = Field(default=3, alias="DIALOGUE_MAX_CLARIFY_TURNS")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
