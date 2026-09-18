"""Unit tests for ParsedDocument block model and extended Chunk fields.

Tests cover:
- Construction of Heading, Paragraph, ListItem, ListBlock, TableBlock, PageMarker
- ParsedDocument with blocks and metadata
- Chunk accepts optional page_number and anchor (backward-compatible)
"""


from src.ports.models import (
    Chunk,
    Heading,
    ListBlock,
    ListItem,
    PageMarker,
    Paragraph,
    ParsedDocument,
    TableBlock,
)


class TestBlockTypes:
    """Test individual block type construction."""

    def test_heading_with_level_and_text(self):
        """Heading stores level and text."""
        h = Heading(level=2, text="Introduction")
        assert h.level == 2
        assert h.text == "Introduction"

    def test_heading_levels_1_through_6(self):
        """Heading supports levels 1-6."""
        for level in range(1, 7):
            h = Heading(level=level, text=f"H{level}")
            assert h.level == level

    def test_paragraph_with_text(self):
        """Paragraph stores text content."""
        p = Paragraph(text="Some paragraph content.")
        assert p.text == "Some paragraph content."

    def test_list_item_default_unordered(self):
        """ListItem defaults to unordered (ordered=False)."""
        item = ListItem(text="Item text")
        assert item.text == "Item text"
        assert item.ordered is False

    def test_list_item_ordered(self):
        """ListItem can be marked as ordered."""
        item = ListItem(text="Step 1", ordered=True)
        assert item.ordered is True

    def test_list_block_with_items(self):
        """ListBlock contains a list of ListItem objects."""
        items = [
            ListItem(text="First"),
            ListItem(text="Second"),
            ListItem(text="Third", ordered=True),
        ]
        block = ListBlock(items=items)
        assert len(block.items) == 3
        assert block.items[0].text == "First"
        assert block.items[2].ordered is True

    def test_table_block_with_headers_and_rows(self):
        """TableBlock stores headers and rows."""
        block = TableBlock(
            headers=["Name", "Age"],
            rows=[["Alice", "30"], ["Bob", "25"]],
        )
        assert block.headers == ["Name", "Age"]
        assert len(block.rows) == 2
        assert block.rows[0] == ["Alice", "30"]

    def test_page_marker_with_page_number(self):
        """PageMarker stores page number."""
        pm = PageMarker(page_number=5)
        assert pm.page_number == 5


class TestParsedDocument:
    """Test ParsedDocument construction."""

    def test_parsed_document_with_blocks_and_metadata(self):
        """ParsedDocument holds blocks list and metadata dict."""
        blocks = [
            Heading(level=1, text="Title"),
            Paragraph(text="First paragraph."),
            Paragraph(text="Second paragraph."),
        ]
        metadata = {
            "title": "My Doc",
            "source_path": "/docs/test.md",
            "content_type": ".md",
        }
        doc = ParsedDocument(blocks=blocks, metadata=metadata)
        assert len(doc.blocks) == 3
        assert doc.metadata["title"] == "My Doc"
        assert doc.metadata["source_path"] == "/docs/test.md"

    def test_parsed_document_empty_blocks(self):
        """ParsedDocument can have empty blocks list."""
        doc = ParsedDocument(blocks=[], metadata={"title": "Empty"})
        assert len(doc.blocks) == 0

    def test_parsed_document_mixed_block_types(self):
        """ParsedDocument can contain mixed block types."""
        blocks = [
            Heading(level=1, text="Chapter"),
            Paragraph(text="Intro text."),
            ListBlock(items=[ListItem(text="Item 1"), ListItem(text="Item 2")]),
            TableBlock(headers=["Col"], rows=[["Val"]]),
            PageMarker(page_number=3),
        ]
        doc = ParsedDocument(blocks=blocks, metadata={})
        assert len(doc.blocks) == 5
        assert isinstance(doc.blocks[0], Heading)
        assert isinstance(doc.blocks[1], Paragraph)
        assert isinstance(doc.blocks[2], ListBlock)
        assert isinstance(doc.blocks[3], TableBlock)
        assert isinstance(doc.blocks[4], PageMarker)


class TestChunkExtendedFields:
    """Test that Chunk accepts optional page_number and anchor fields."""

    def test_chunk_without_page_number_and_anchor(self):
        """Chunk works without page_number and anchor (backward-compatible)."""
        chunk = Chunk(
            document_id="doc1",
            document_title="Test",
            source_path="/test.md",
            section_path="",
            chunk_index=0,
            content="content",
            token_count=1,
            content_hash="abc123",
        )
        assert chunk.page_number is None
        assert chunk.anchor is None

    def test_chunk_with_page_number(self):
        """Chunk accepts page_number."""
        chunk = Chunk(
            document_id="doc1",
            document_title="Test",
            source_path="/test.pdf",
            section_path="",
            chunk_index=0,
            content="content",
            token_count=1,
            content_hash="abc123",
            page_number=5,
        )
        assert chunk.page_number == 5
        assert chunk.anchor is None

    def test_chunk_with_anchor(self):
        """Chunk accepts anchor."""
        chunk = Chunk(
            document_id="doc1",
            document_title="Test",
            source_path="/test.md",
            section_path="Chapter 1",
            chunk_index=0,
            content="content",
            token_count=1,
            content_hash="abc123",
            anchor="chapter-1",
        )
        assert chunk.anchor == "chapter-1"
        assert chunk.page_number is None

    def test_chunk_with_both_page_number_and_anchor(self):
        """Chunk accepts both page_number and anchor."""
        chunk = Chunk(
            document_id="doc1",
            document_title="Test",
            source_path="/test.pdf",
            section_path="Section 2",
            chunk_index=3,
            content="content",
            token_count=10,
            content_hash="abc123",
            page_number=12,
            anchor="section-2",
        )
        assert chunk.page_number == 12
        assert chunk.anchor == "section-2"
