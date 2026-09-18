"""Chunker port — splits parsed documents into retrievable chunks."""

from typing import Protocol

from src.ports.models import Chunk, ParsedDocument


class Chunker(Protocol):
    """Splits a ParsedDocument into semantically coherent chunks.

    Implementations: block-aware recursive splitter, fixed-size, etc.
    """

    def split(
        self,
        doc: ParsedDocument,
        doc_id: str,
        doc_title: str,
        source: str,
        source_type: str,
    ) -> list[Chunk]:
        """Split a ParsedDocument into a list of Chunk dataclasses.

        Each chunk carries document metadata, a sequential chunk_index,
        and optional page_number/anchor from structural markers.
        """
        ...
