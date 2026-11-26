"""
ANCHOR: app.config.factories
PURPOSE: DI factory: build real port implementations from Settings.
Dependencies: Settings; adapters.* (Http*/Qdrant/SqlAlchemy/Soffice/Email)
DO:
- Construction of real adapters only here (CS-DI-01)
DONT:
- Let application services import Http* / Qdrant* directly
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.application.appeals.service import AppealsService
from app.application.connectivity.service import ConnectivityService
from app.application.dialogue.nodes import DialogueDeps
from app.application.dialogue.service import DialogueService
from app.application.grounding.service import GroundingService
from app.application.ingest.service import IngestService
from app.application.learning.service import LearningService
from app.application.quality_escalation.service import QualityEscalationService
from app.application.retrieval.service import RetrievalService
from app.config.settings import Settings, get_settings


@dataclass
class Container:
    """Port + application service holder."""

    settings: Settings
    llm: Any
    embeddings: Any
    vectorstore: Any
    docling: Any
    libreoffice: Any
    escalation: Any
    persistence: Any
    appeals: AppealsService
    dialogue: DialogueService
    learning: LearningService
    ingest: IngestService
    quality_escalation: QualityEscalationService
    connectivity: ConnectivityService


def _build_llm(settings: Settings) -> Any:
    from app.adapters.llm.http import HttpLLMClient

    return HttpLLMClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout_s=settings.llm_timeout_s,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        reasoning_tokens=settings.llm_reasoning_tokens,
        allow_hosts=settings.egress_hosts(),
    )


def _build_embeddings(settings: Settings) -> Any:
    from app.adapters.embeddings.http import HttpEmbeddingsClient

    return HttpEmbeddingsClient(
        base_url=settings.embeddings_base_url,
        api_key=settings.embeddings_api_key,
        dense_model=settings.embeddings_dense_model,
        sparse_model=settings.embeddings_sparse_model,
        timeout_s=settings.embeddings_timeout_s,
        batch_size=settings.embeddings_batch_size,
        allow_hosts=settings.egress_hosts(),
    )


def _build_vectorstore(settings: Settings) -> Any:
    from app.adapters.vectorstore.qdrant import QdrantVectorStore

    return QdrantVectorStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection=settings.qdrant_collection,
        timeout_s=settings.qdrant_timeout_s,
        upsert_batch=settings.qdrant_upsert_batch,
        vector_size=settings.embeddings_dense_dim,
    )


def _build_docling(settings: Settings) -> Any:
    from app.adapters.docling.http import HttpDoclingClient

    return HttpDoclingClient(
        base_url=settings.docling_base_url,
        api_key=settings.docling_api_key,
        timeout_s=settings.docling_timeout_s,
        connect_timeout_s=settings.docling_connect_timeout_s,
        concurrency=settings.docling_concurrency,
        split_pages=settings.docling_split_pages,
        ocr_langs=settings.docling_ocr_langs,
        chunker=settings.docling_chunker,
        chunk_tokenizer=settings.docling_chunk_tokenizer,
        chunk_max_tokens=settings.docling_chunk_max_tokens,
        chunk_overlap_tokens=settings.docling_chunk_overlap_tokens,
        chunk_min_tokens=settings.docling_chunk_min_tokens,
        allow_hosts=settings.egress_hosts(),
    )


def _build_libreoffice(settings: Settings) -> Any:
    from app.adapters.libreoffice.soffice import SofficeLibreOffice

    return SofficeLibreOffice(
        soffice_path=settings.libreoffice_soffice_path,
        timeout_s=settings.libreoffice_timeout_s,
    )


def _build_escalation(settings: Settings) -> Any:
    from app.adapters.escalation.email import EmailEscalationNotifier

    return EmailEscalationNotifier(
        to_email=settings.quality_service_email,
        subject_prefix=settings.escalation_email_subject_prefix,
    )


def _build_persistence(settings: Settings) -> Any:
    from app.adapters.persistence.sqlalchemy.adapter import SqlAlchemyPersistence

    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required")
    return SqlAlchemyPersistence(
        database_url=settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout_s=settings.database_pool_timeout_s,
        echo=settings.database_echo,
    )


def build_container(settings: Settings | None = None) -> Container:
    """Wire real adapters and application services from settings."""
    settings = settings or get_settings()
    llm = _build_llm(settings)
    embeddings = _build_embeddings(settings)
    vectorstore = _build_vectorstore(settings)
    docling = _build_docling(settings)
    libreoffice = _build_libreoffice(settings)
    escalation = _build_escalation(settings)
    persistence = _build_persistence(settings)

    retrieval = RetrievalService(
        embeddings=embeddings,
        vectorstore=vectorstore,
        prefetch=settings.retrieval_prefetch,
        prefer_latest=settings.retrieval_prefer_latest,
        rerank_mode=settings.rerank_mode,
        rerank_candidates=settings.rerank_candidates,
        rerank_top_k=settings.rerank_top_k,
        rerank_max_per_doc=settings.rerank_max_per_doc,
        rerank_min_score=settings.rerank_min_score,
        llm=llm,
        rerank_llm_model=settings.rerank_llm_model,
    )
    grounding = GroundingService(
        min_citations=settings.grounding_min_citations,
        min_score=settings.grounding_min_score,
    )
    quality = QualityEscalationService(
        persistence=persistence,
        notifier=escalation,
        quality_email=settings.quality_service_email,
        enabled=settings.escalation_enabled,
    )
    dialogue_deps = DialogueDeps(
        llm=llm,
        retrieval=retrieval,
        grounding=grounding,
        quality_email=settings.quality_service_email,
    )
    dialogue = DialogueService(
        persistence=persistence,
        deps=dialogue_deps,
        escalation=quality,
        max_clarify_turns=settings.dialogue_max_clarify_turns,
    )
    ingest = IngestService(
        docling=docling,
        embeddings=embeddings,
        vectorstore=vectorstore,
        persistence=persistence,
    )
    learning = LearningService(persistence=persistence, ingest=ingest)
    appeals = AppealsService(persistence=persistence, dialogue=dialogue)
    connectivity = ConnectivityService(
        llm=llm,
        embeddings=embeddings,
        vectorstore=vectorstore,
        docling=docling,
        persistence=persistence,
    )

    # Keep libreoffice constructed for DI completeness (used by ingest CLI).
    _ = libreoffice

    return Container(
        settings=settings,
        llm=llm,
        embeddings=embeddings,
        vectorstore=vectorstore,
        docling=docling,
        libreoffice=libreoffice,
        escalation=escalation,
        persistence=persistence,
        appeals=appeals,
        dialogue=dialogue,
        learning=learning,
        ingest=ingest,
        quality_escalation=quality,
        connectivity=connectivity,
    )


@lru_cache
def get_container() -> Container:
    return build_container(get_settings())


def reset_container() -> None:
    get_container.cache_clear()
