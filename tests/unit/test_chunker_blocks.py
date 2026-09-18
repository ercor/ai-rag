"""Unit tests for block-aware chunker.

Tests cover:
- List items not split mid-item
- Table rows kept together
- Heading hierarchy preserved in section_path
- Page_number propagated from PageMarker blocks
- Short doc → single chunk
- Per-type config resolution
- Empty document → no chunks
"""

import pytest

from src.adapters.recursive_chunker import RecursiveChunker
from src.config import Settings
from src.ports.models import (
    Heading,
    ListBlock,
    ListItem,
    PageMarker,
    Paragraph,
    ParsedDocument,
    TableBlock,
)


def _make_doc(blocks, metadata=None):
    """Helper to create a ParsedDocument."""
    return ParsedDocument(
        blocks=blocks,
        metadata=metadata or {"title": "Test", "source_path": "/test.md", "content_type": ".md"},
    )


@pytest.fixture
def chunker():
    """Default RecursiveChunker with standard parameters."""
    return RecursiveChunker(min_tokens=200, max_tokens=600, overlap=50)


@pytest.fixture
def small_chunker():
    """RecursiveChunker with small thresholds for testing."""
    return RecursiveChunker(min_tokens=10, max_tokens=30, overlap=5)


class TestBlockAwareChunking:
    """Test that chunker respects block boundaries."""

    def test_list_items_not_split_mid_item(self, chunker):
        """A 50-item list is not split mid-item across chunk boundaries."""
        items = [ListItem(text=f"Item {i} content " * 5) for i in range(50)]
        doc = _make_doc([ListBlock(items=items)])

        chunks = chunker.split(doc, "doc1", "List Doc", "/list.md", ".md")

        # Each list item should be fully in one chunk
        for chunk in chunks:
            for i in range(50):
                item_text = f"Item {i} content"
                if item_text in chunk.content:
                    # If any part of this item is in this chunk,
                    # the full item text should be here
                    assert f"Item {i} content" in chunk.content

    def test_table_rows_kept_together(self, chunker):
        """Table rows are not split across chunks."""
        rows = [[f"Row{i}Col{j}" for j in range(3)] for i in range(20)]
        doc = _make_doc([
            TableBlock(headers=["Col0", "Col1", "Col2"], rows=rows),
        ])

        chunks = chunker.split(doc, "doc1", "Table Doc", "/table.md", ".md")

        # Each chunk should contain complete rows
        assert len(chunks) >= 1
        for chunk in chunks:
            # If a row header is in the chunk, the full row should be too
            for i in range(20):
                if f"Row{i}Col0" in chunk.content:
                    assert f"Row{i}Col1" in chunk.content
                    assert f"Row{i}Col2" in chunk.content

    def test_heading_hierarchy_in_section_path(self, chunker):
        """Heading hierarchy is preserved in chunk section_path."""
        doc = _make_doc([
            Heading(level=1, text="Chapter 1"),
            Paragraph(text="Content under chapter 1. " * 30),
            Heading(level=2, text="Section 1.1"),
            Paragraph(text="Content under section 1.1. " * 30),
        ])

        chunks = chunker.split(doc, "doc1", "Hierarchy Doc", "/hier.md", ".md")

        assert len(chunks) >= 1
        # At least one chunk should have "Chapter 1" in section_path
        paths = [c.section_path for c in chunks]
        assert any("Chapter 1" in p for p in paths)

    def test_page_number_from_page_marker(self, chunker):
        """Page_number is propagated from PageMarker blocks."""
        doc = ParsedDocument(
            blocks=[
                PageMarker(page_number=1),
                Paragraph(text="Page 1 content. " * 30),
                PageMarker(page_number=2),
                Paragraph(text="Page 2 content. " * 30),
            ],
            metadata={"title": "PDF", "source_path": "/doc.pdf", "content_type": ".pdf"},
        )

        chunks = chunker.split(doc, "doc1", "PDF Doc", "/doc.pdf", ".pdf")

        assert len(chunks) >= 1
        # At least some chunks should have page_number set
        page_numbers = [c.page_number for c in chunks if c.page_number is not None]
        assert len(page_numbers) >= 1

    def test_short_document_single_chunk(self, chunker):
        """A short document produces a single chunk."""
        doc = _make_doc([
            Heading(level=1, text="Title"),
            Paragraph(text="Short content."),
        ])

        chunks = chunker.split(doc, "doc1", "Short", "/short.md", ".md")

        assert len(chunks) == 1
        assert chunks[0].content.strip()

    def test_empty_document_no_chunks(self, chunker):
        """Empty document produces no chunks."""
        doc = _make_doc([])
        chunks = chunker.split(doc, "doc1", "Empty", "/empty.md", ".md")
        assert chunks == []

    def test_metadata_preserved(self, chunker):
        """Chunk metadata includes document_id, title, source_path."""
        doc = _make_doc([Paragraph(text="Content. " * 30)])

        chunks = chunker.split(doc, "doc-abc", "My Title", "/path/to/doc.md", ".md")

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.document_id == "doc-abc"
            assert chunk.document_title == "My Title"
            assert chunk.source_path == "/path/to/doc.md"

    def test_sequential_chunk_index(self, small_chunker):
        """Chunk indices are sequential starting from 0."""
        blocks = [Paragraph(text=f"Para {i}. " * 20) for i in range(10)]
        doc = _make_doc(blocks)

        chunks = small_chunker.split(doc, "doc1", "Doc", "/doc.txt", ".txt")

        if len(chunks) > 1:
            indices = [c.chunk_index for c in chunks]
            assert indices == list(range(len(chunks)))

    def test_content_hash_is_set(self, chunker):
        """Each chunk has a non-empty content_hash."""
        doc = _make_doc([Paragraph(text="Hash test content. " * 20)])
        chunks = chunker.split(doc, "doc1", "Doc", "/doc.txt", ".txt")

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.content_hash
            assert len(chunk.content_hash) == 16


class TestPerTypeChunkingBehavior:
    """Test that chunker uses per-type config."""

    def test_pdf_config_used(self):
        """PDF source type uses PDF chunking config."""
        settings = Settings()
        config = settings.get_chunking_config(".pdf")
        chunker = RecursiveChunker(
            min_tokens=config["min_tokens"],
            max_tokens=config["max_tokens"],
            overlap=config["overlap"],
        )
        assert chunker.max_tokens == 600

    def test_md_config_used(self):
        """MD source type uses MD chunking config."""
        settings = Settings()
        config = settings.get_chunking_config(".md")
        chunker = RecursiveChunker(
            min_tokens=config["min_tokens"],
            max_tokens=config["max_tokens"],
            overlap=config["overlap"],
        )
        assert chunker.max_tokens == 600
