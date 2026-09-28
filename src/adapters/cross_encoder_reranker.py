"""Cross-Encoder Reranker adapter.

Uses sentence-transformers CrossEncoder to re-score (query, chunk) pairs.
Model is lazy-loaded on first rerank() call and cached for subsequent calls.
"""

import logging
import time

from src.core.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker:
    """Re-ranks retrieval candidates using a cross-encoder model.

    Implements the Reranker port protocol.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL):
        self._model_name = model_name
        self._model = None  # Lazy-loaded on first rerank()

    def _ensure_model(self):
        """Load the cross-encoder model on first use."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import CrossEncoder

            logger.info("Loading cross-encoder model: %s", self._model_name)
            self._model = CrossEncoder(self._model_name)
            logger.info("Cross-encoder model loaded successfully")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load cross-encoder model '{self._model_name}'. "
                f"Ensure the model is available locally or that network access "
                f"is enabled for download. Original error: {exc}"
            ) from exc

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        """Re-score candidates with cross-encoder and return top_k."""
        if not candidates:
            return []

        self._ensure_model()

        start = time.monotonic()

        # Build (query, chunk_content) pairs
        pairs = [(query, rc.chunk.content) for rc in candidates]

        # CrossEncoder.predict returns numpy array of scores
        scores = self._model.predict(pairs)

        # Attach cross-encoder scores and sort descending
        scored = list(zip(candidates, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        # Truncate to top_k and replace RRF score with cross-encoder score
        result: list[RetrievedChunk] = []
        for rc, ce_score in scored[:top_k]:
            result.append(
                RetrievedChunk(
                    chunk=rc.chunk,
                    score=float(ce_score),
                    bm25_rank=rc.bm25_rank,
                    vector_rank=rc.vector_rank,
                )
            )

        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "Reranking complete: %d candidates -> %d results in %.1fms",
            len(candidates),
            len(result),
            elapsed_ms,
        )

        return result
