"""Parser port — extracts structured blocks from a document file."""

from typing import Protocol

from src.ports.models import ParsedDocument


class Parser(Protocol):
    """Parses a document file at the given path and returns a ParsedDocument.

    Implementations: pymupdf (PDF), python-docx (DOCX), bs4 (HTML), plain text.
    """

    async def parse(self, path: str) -> ParsedDocument:
        """Extract structured blocks from the document at `path`.

        Returns a ParsedDocument with blocks (Heading, Paragraph, ListBlock,
        TableBlock, PageMarker) and metadata (title, source_path, content_type).

        Raises on parse failure — callers should catch and log per-file errors.
        """
        ...
