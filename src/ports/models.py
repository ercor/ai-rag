"""Shared domain models used across port interfaces."""

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Block types for ParsedDocument (structure-aware parsing)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Heading:
    """A heading block with level (1-6) and text."""

    level: int
    text: str


@dataclass(frozen=True)
class Paragraph:
    """A paragraph text block."""

    text: str


@dataclass(frozen=True)
class ListItem:
    """A single list item (ordered or unordered)."""

    text: str
    ordered: bool = False


@dataclass(frozen=True)
class ListBlock:
    """A list block containing multiple list items."""

    items: list[ListItem]


@dataclass(frozen=True)
class TableBlock:
    """A table block with headers and rows."""

    headers: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class PageMarker:
    """A page boundary marker (used in PDF parsing)."""

    page_number: int


# Block = Heading | Paragraph | ListBlock | TableBlock | PageMarker


@dataclass
class ParsedDocument:
    """A parsed document containing structured blocks and metadata.

    Produced by Parser port implementations. Consumed by Chunker port.
    """

    blocks: list  # list[Heading | Paragraph | ListBlock | TableBlock | PageMarker]
    metadata: dict  # {title, source_path, content_type, ...}


# ---------------------------------------------------------------------------
# Chunk model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Chunk:
    """A single text chunk produced by the Chunker port.

    Immutable after creation — chunk identity is determined by
    (document_id, chunk_index, content_hash).
    """

    document_id: str
    document_title: str
    source_path: str
    section_path: str
    chunk_index: int
    content: str
    token_count: int
    content_hash: str
    page_number: int | None = None
    anchor: str | None = None
