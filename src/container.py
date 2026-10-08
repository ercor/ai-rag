"""Dependency injection container.

Factory functions configurable via environment variables.
Used with FastAPI's Depends() for port-based injection.
"""

import logging
from functools import lru_cache

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_settings() -> Settings:
    return get_settings()


def get_db_url() -> str:
    """Return the database connection URL."""
    return _get_settings().database_url


def get_ollama_base_url() -> str:
    """Return the Ollama API base URL."""
    return _get_settings().ollama_base_url


def get_settings_dep() -> Settings:
    """FastAPI dependency: return the application Settings."""
    return _get_settings()


# ---------------------------------------------------------------------------
# Port factories — concrete adapter instantiation.
# ---------------------------------------------------------------------------


def get_embedder():
    """Return the Embedder adapter instance.

    Configured via EMBEDDER_ADAPTER env var.
    """
    settings = _get_settings()
    adapter = settings.embedder_adapter
    if adapter == "ollama":
        from src.adapters.ollama_embedder import OllamaEmbedder

        return OllamaEmbedder()
    raise ValueError(f"Unknown embedder adapter: {adapter}")


def get_generator():
    """Return the Generator adapter instance.

    Configured via GENERATOR_ADAPTER env var.
    """
    settings = _get_settings()
    adapter = settings.generator_adapter
    if adapter == "ollama":
        from src.adapters.ollama_generator import OllamaGenerator

        return OllamaGenerator()
    raise ValueError(f"Unknown generator adapter: {adapter}")


def get_search_index():
    """Return the SearchIndex adapter instance (pgvector)."""
    from src.adapters.pgvector_index import PgvectorIndex

    return PgvectorIndex()


def get_answer_repository():
    """Return the AnswerRepository adapter instance (asyncpg)."""
    from src.adapters.pg_answer_repository import PgAnswerRepository

    return PgAnswerRepository()


def get_document_source():
    """Return the DocumentSource adapter instance (filesystem)."""
    from src.adapters.filesystem_source import FilesystemSource

    return FilesystemSource()


def get_parser():
    """Return the Parser adapter instance (multi-format)."""
    from src.adapters.parsers import MultiFormatParser

    return MultiFormatParser()


def get_chunker():
    """Return the Chunker adapter instance (block-aware recursive)."""
    from src.adapters.recursive_chunker import RecursiveChunker

    settings = _get_settings()
    # Use txt defaults as the base; per-type config is resolved at split time
    return RecursiveChunker(
        min_tokens=settings.chunk_min_txt,
        max_tokens=settings.chunk_max_txt,
        overlap=settings.chunk_overlap_txt,
    )


def get_citation_validator():
    """Return the CitationValidator adapter instance (regex)."""
    from src.adapters.regex_citation_validator import RegexCitationValidator

    return RegexCitationValidator()


def get_document_registry():
    """Return the DocumentRegistry adapter instance."""
    from src.adapters.document_registry import DocumentRegistry

    return DocumentRegistry()


def get_job_registry():
    """Return the JobRegistry instance (singleton for in-memory job tracking)."""
    from src.core.job_registry import JobRegistry

    # Use module-level singleton to ensure same registry across requests
    if not hasattr(get_job_registry, "_instance"):
        get_job_registry._instance = JobRegistry()
    return get_job_registry._instance


def get_reranker():
    """Return the Reranker adapter instance, or None when disabled.

    Configured via RERANKER_ENABLED env var.
    """
    settings = _get_settings()
    if not settings.reranker_enabled:
        return None
    from src.adapters.cross_encoder_reranker import CrossEncoderReranker

    return CrossEncoderReranker(model_name=settings.reranker_model)


def get_query_rewriter():
    """Return the QueryRewriter adapter instance, or None when disabled.

    Configured via QUERY_REWRITER_ENABLED env var.
    """
    settings = _get_settings()
    if not settings.query_rewriter_enabled:
        return None
    from src.adapters.llm_query_rewriter import LLMQueryRewriter

    return LLMQueryRewriter(
        generator=get_generator(),
        num_variants=settings.query_rewriter_num_variants,
    )


def get_cache():
    """Return the Cache adapter instance.

    When cache_enabled=true: returns RedisCache connected to redis_url.
    When cache_enabled=false: returns NoopCache (always misses).
    """
    settings = _get_settings()
    if not settings.cache_enabled:
        from src.adapters.noop_cache import NoopCache

        return NoopCache()
    from src.adapters.redis_cache import RedisCache

    return RedisCache(redis_url=settings.redis_url)


def get_conversation_repository():
    """Return the ConversationRepository adapter instance (asyncpg)."""
    from src.adapters.pg_conversation_repository import PgConversationRepository

    return PgConversationRepository()


def get_ingestion_service():
    """Return a fully-wired IngestionService instance."""
    from src.core.ingestion_service import IngestionService

    settings = _get_settings()
    return IngestionService(
        source=get_document_source(),
        parser=get_parser(),
        chunker=get_chunker(),
        embedder=get_embedder(),
        search_index=get_search_index(),
        registry=get_document_registry(),
        ingest_concurrency=settings.ingest_concurrency,
    )
