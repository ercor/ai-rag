"""Ollama-based Embedder adapter.

Uses the Ollama API to generate text embeddings via nomic-embed-text
(768 dimensions). Supports single and batch embedding.
"""

import logging

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)


class OllamaEmbedder:
    """Generates embeddings via the Ollama /api/embed endpoint.

    Implements the Embedder port protocol.
    Uses native batch API: sends input as string[] array.
    Automatically detects GPU availability and adjusts batch size accordingly.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        embed_batch_size: int | None = None,
        gpu_enabled: bool | None = None,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_embed_model
        self.gpu_enabled = gpu_enabled if gpu_enabled is not None else settings.gpu_enabled
        self._gpu_detected = None  # Lazy detection
        # Use provided batch size, or default based on GPU setting
        if embed_batch_size is not None:
            self.embed_batch_size = embed_batch_size
        else:
            self.embed_batch_size = settings.get_effective_embed_batch_size(self.gpu_enabled)

    async def embed(self, text: str) -> list[float]:
        """Return the embedding vector for a single text string."""
        return (await self.embed_batch([text]))[0]

    async def _ensure_gpu_detection(self):
        """Lazily detect GPU availability and adjust batch size if needed."""
        if self._gpu_detected is None:
            settings = get_settings()
            self._gpu_detected = await settings.detect_gpu_available()
            if self._gpu_detected and not self.gpu_enabled:
                # GPU detected but not explicitly enabled - log and adjust
                logger.info(
                    "GPU detected, increasing embed_batch_size from %d to %d",
                    self.embed_batch_size,
                    settings.embed_batch_size_gpu,
                )
                self.embed_batch_size = settings.embed_batch_size_gpu
                self.gpu_enabled = True

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for a batch of texts.

        Splits texts into groups of embed_batch_size, sends each group
        as {"model": ..., "input": string[]} — one HTTP call per batch.
        Returns vectors in the same order as input.
        Automatically adjusts batch size based on GPU availability.
        """
        if not texts:
            return []

        # Detect GPU on first call
        await self._ensure_gpu_detection()

        embeddings: list[list[float]] = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Process in batches of embed_batch_size
            for batch_start in range(0, len(texts), self.embed_batch_size):
                batch_end = min(batch_start + self.embed_batch_size, len(texts))
                batch_texts = texts[batch_start:batch_end]

                try:
                    response = await client.post(
                        f"{self.base_url}/api/embed",
                        json={
                            "model": self.model,
                            "input": batch_texts,  # Native array input
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                    # Ollama returns {"embeddings": [[...], [...], ...]}
                    emb_list = data.get("embeddings", [])
                    if len(emb_list) != len(batch_texts):
                        raise ValueError(
                            f"Ollama returned {len(emb_list)} embeddings "
                            f"for {len(batch_texts)} texts"
                        )

                    embeddings.extend(emb_list)
                except Exception as exc:
                    logger.error(
                        "Embedding failed for batch %d-%d: %s",
                        batch_start,
                        batch_end,
                        exc,
                    )
                    raise

        logger.debug(
            "Embedded %d texts via Ollama (%s) in %d batches, dim=%d, gpu=%s",
            len(texts),
            self.model,
            (len(texts) + self.embed_batch_size - 1) // self.embed_batch_size,
            len(embeddings[0]) if embeddings else 0,
            "enabled" if self.gpu_enabled else "disabled",
        )
        return embeddings
