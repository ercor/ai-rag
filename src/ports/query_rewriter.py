"""QueryRewriter port — generates query variants for multi-query retrieval."""

from typing import Protocol


class QueryRewriter(Protocol):
    """Generates query variants for multi-query retrieval.

    Implementations: LLM-based (multi-query expansion), rule-based, etc.
    """

    async def rewrite(self, query: str) -> list[str]:
        """Return a list of query variants including the original.

        Minimum return length: 1 (the original query).
        Each variant is a standalone query string.
        """
        ...
