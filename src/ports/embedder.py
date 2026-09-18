"""Embedder port — produces vector embeddings from text."""

from typing import Protocol


class Embedder(Protocol):
    """Converts text into dense vector embeddings for similarity search.

    Implementations: Ollama (nomic-embed-text), OpenAI, etc.
    """

    async def embed(self, text: str) -> list[float]:
        """Return the embedding vector for a single text string."""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for a batch of texts.

        The returned list must be the same length as `texts` and in the
        same order.
        """
        ...
