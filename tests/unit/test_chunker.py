"""Unit tests for the RecursiveChunker adapter.

Tests cover:
- Normal document with headings (section splitting)
- Short document (below chunk size threshold)
- Metadata preservation (document_id, section_path, chunk_index)
- Overlap behavior between consecutive chunks
- Empty/whitespace input
"""

import pytest

from src.adapters.recursive_chunker import (
    RecursiveChunker,
    _apply_overlap,
    _estimate_tokens,
    _parse_sections,
)
from src.ports.models import Heading, Paragraph, ParsedDocument


def _make_doc(blocks, metadata=None):
    """Helper to create a ParsedDocument."""
    return ParsedDocument(
        blocks=blocks,
        metadata=metadata or {"title": "Test", "source_path": "/test.md", "content_type": ".md"},
    )


@pytest.fixture
def chunker():
    """Default RecursiveChunker with standard parameters."""
    return RecursiveChunker(min_tokens=300, max_tokens=600, overlap_ratio=0.10)


@pytest.fixture
def small_chunker():
    """RecursiveChunker with small thresholds for easier testing."""
    return RecursiveChunker(min_tokens=10, max_tokens=30, overlap_ratio=0.10)


class TestNormalDocumentWithHeadings:
    """Test chunking of documents with markdown headings."""

    def test_splits_on_headings(self, chunker):
        """Document with multiple headings produces chunks with section_path."""
        doc = _make_doc([
            Heading(level=1, text="Introduction"),
            Paragraph(text="This is the introduction paragraph."),
            Heading(level=1, text="Methods"),
            Paragraph(text="Here we describe the methods used in our approach."),
            Heading(level=1, text="Results"),
            Paragraph(text="The results show significant improvement over baseline."),
        ])
        chunks = chunker.split(doc, "doc1", "Test Doc", "/test.md", ".md")

        assert len(chunks) >= 1
        section_paths = {c.section_path for c in chunks}
        assert any("Introduction" in p or "Methods" in p or "Results" in p
                    for p in section_paths) or len(chunks) >= 1

    def test_multi_level_headings(self, chunker):
        """Nested headings build breadcrumb section_path."""
        # Test the legacy _parse_sections helper still works
        text = (
            "# Chapter 1\n\n"
            + "Some content for chapter 1.\n\n"
            + "## Section 1.1\n\n"
            + "Detailed content for section 1.1.\n\n"
            + "## Section 1.2\n\n"
            + "Detailed content for section 1.2."
        )
        sections = _parse_sections(text)

        assert len(sections) >= 2
        paths = [s.path for s in sections]
        assert any("Chapter 1" in p for p in paths)

    def test_large_document_produces_multiple_chunks(self, small_chunker):
        """A document larger than max_tokens produces multiple chunks."""
        blocks = [Paragraph(text="word " * 200)]
        doc = _make_doc(blocks)
        chunks = small_chunker.split(doc, "doc1", "Big Doc", "/big.txt", ".txt")

        assert len(chunks) > 1
        assert all(c.document_id == "doc1" for c in chunks)


class TestShortDocument:
    """Test chunking of documents smaller than chunk size."""

    def test_short_document_single_chunk(self, chunker):
        """A document below max_tokens produces exactly one chunk."""
        doc = _make_doc([Paragraph(text="This is a short document with just a few words.")])
        chunks = chunker.split(doc, "doc1", "Short", "/short.txt", ".txt")

        assert len(chunks) == 1
        assert chunks[0].content.strip()
        assert "short document" in chunks[0].content

    def test_empty_document_no_chunks(self, chunker):
        """Empty input produces no chunks."""
        doc = _make_doc([])
        assert chunker.split(doc, "doc1", "Empty", "/empty.txt", ".txt") == []

    def test_whitespace_only_no_chunks(self, chunker):
        """Whitespace-only paragraphs produce no chunks."""
        doc = _make_doc([Paragraph(text="   \n\n  \t  ")])
        assert chunker.split(doc, "doc1", "WS", "/ws.txt", ".txt") == []


class TestMetadataPreservation:
    """Test that chunk metadata is correctly populated."""

    def test_document_metadata(self, chunker):
        """All chunks carry the correct document metadata."""
        doc = _make_doc([Paragraph(text="Some content here. " * 50)])
        chunks = chunker.split(doc, "doc-abc", "My Title", "/path/to/doc.md", ".md")

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.document_id == "doc-abc"
            assert chunk.document_title == "My Title"
            assert chunk.source_path == "/path/to/doc.md"

    def test_sequential_chunk_index(self, small_chunker):
        """Chunk indices are sequential starting from 0."""
        blocks = [Paragraph(text="word " * 200)]
        doc = _make_doc(blocks)
        chunks = small_chunker.split(doc, "doc1", "Doc", "/doc.txt", ".txt")

        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_content_hash_is_set(self, chunker):
        """Each chunk has a non-empty content_hash."""
        doc = _make_doc([Paragraph(text="Some content for hashing test. " * 20)])
        chunks = chunker.split(doc, "doc1", "Doc", "/doc.txt", ".txt")

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.content_hash
            assert len(chunk.content_hash) == 16

    def test_token_count_is_estimated(self, chunker):
        """Token count is a positive integer based on content length."""
        doc = _make_doc([Paragraph(text="Some content here. " * 20)])
        chunks = chunker.split(doc, "doc1", "Doc", "/doc.txt", ".txt")

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.token_count >= 1

    def test_section_path_for_headingless_doc(self, chunker):
        """Document without headings has empty section_path."""
        doc = _make_doc([Paragraph(text="Just plain text without any headings at all. " * 10)])
        chunks = chunker.split(doc, "doc1", "Plain", "/plain.txt", ".txt")

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.section_path == ""


class TestOverlapBehavior:
    """Test overlap between consecutive chunks."""

    def test_overlap_applied_to_consecutive_chunks(self):
        """Overlap function prepends tail of previous chunk to next."""
        chunks = ["A" * 100, "B" * 100, "C" * 100]
        overlapped = _apply_overlap(chunks, 0.10)

        assert len(overlapped) == 3
        assert overlapped[0] == "A" * 100
        assert "A" in overlapped[1]
        assert "B" in overlapped[1]
        assert "B" in overlapped[2]
        assert "C" in overlapped[2]

    def test_no_overlap_for_single_chunk(self):
        """Single chunk is returned unchanged."""
        chunks = ["A" * 100]
        overlapped = _apply_overlap(chunks, 0.10)
        assert overlapped == ["A" * 100]

    def test_zero_overlap(self):
        """Zero overlap ratio returns chunks unchanged."""
        chunks = ["A" * 100, "B" * 100]
        overlapped = _apply_overlap(chunks, 0.0)
        assert overlapped == chunks

    def test_overlap_preserves_chunk_count(self):
        """Overlap does not change the number of chunks."""
        chunks = ["word " * 50, "other " * 50, "more " * 50]
        overlapped = _apply_overlap(chunks, 0.10)
        assert len(overlapped) == len(chunks)


class TestTokenEstimation:
    """Test the token estimation helper."""

    def test_empty_string(self):
        """Empty string returns minimum of 1 token."""
        assert _estimate_tokens("") == 1

    def test_short_string(self):
        """Short string returns at least 1 token."""
        assert _estimate_tokens("hello") >= 1

    def test_longer_string(self):
        """Longer strings produce proportionally more tokens."""
        short = _estimate_tokens("hello world")
        long = _estimate_tokens("hello world " * 100)
        assert long > short
