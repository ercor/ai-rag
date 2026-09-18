"""Multi-format Parser adapter.

Dispatches to format-specific parsers based on file extension:
  - PDF: pymupdf (fitz)
  - DOCX: python-docx
  - HTML/HTM: beautifulsoup4
  - TXT/MD: plain text read

All sync parser libs run via asyncio.to_thread to avoid blocking the event loop.
Each parser returns a ParsedDocument with structured blocks.

Raises on parse failure — callers should catch per-file errors.
"""

import asyncio
import logging
import re
from pathlib import Path

from src.ports.models import (
    Heading,
    ListBlock,
    ListItem,
    PageMarker,
    Paragraph,
    ParsedDocument,
    TableBlock,
)

logger = logging.getLogger(__name__)


class MultiFormatParser:
    """Parses documents by dispatching to format-specific extractors.

    Implements the Parser port protocol.
    Sync parser libs run in thread pool via asyncio.to_thread.
    """

    async def parse(self, path: str) -> ParsedDocument:
        """Extract structured blocks from the document at `path`.

        Dispatches based on file extension. Raises ValueError for
        unsupported formats, and re-raises parsing exceptions after logging.
        """
        file_path = Path(path)
        ext = file_path.suffix.lower()

        if ext == ".pdf":
            return await asyncio.to_thread(self._parse_pdf, file_path)
        elif ext == ".docx":
            return await asyncio.to_thread(self._parse_docx, file_path)
        elif ext in (".html", ".htm"):
            return await asyncio.to_thread(self._parse_html, file_path)
        elif ext in (".txt", ".md"):
            return await asyncio.to_thread(self._parse_plain, file_path, ext)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    def _parse_pdf(self, path: Path) -> ParsedDocument:
        """Extract text from PDF using pymupdf, with PageMarker blocks."""
        import pymupdf

        doc = pymupdf.open(str(path))
        try:
            blocks: list = []
            for page_num, page in enumerate(doc, start=1):
                blocks.append(PageMarker(page_number=page_num))
                text = page.get_text()
                if text.strip():
                    for para_text in text.split("\n\n"):
                        para_text = para_text.strip()
                        if para_text:
                            blocks.append(Paragraph(text=para_text))

            logger.debug(
                "Parsed PDF %s: %d pages, %d blocks",
                path.name,
                len(doc),
                len(blocks),
            )
            return ParsedDocument(
                blocks=blocks,
                metadata={
                    "title": path.stem,
                    "source_path": str(path),
                    "content_type": ".pdf",
                },
            )
        finally:
            doc.close()

    def _parse_docx(self, path: Path) -> ParsedDocument:
        """Extract text from DOCX using python-docx."""
        from docx import Document

        doc = Document(str(path))
        blocks: list = []

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # Detect heading style
            if para.style and para.style.name and para.style.name.startswith("Heading"):
                try:
                    level = int(para.style.name.split()[-1])
                except (ValueError, IndexError):
                    level = 1
                blocks.append(Heading(level=level, text=text))
            else:
                blocks.append(Paragraph(text=text))

        # Extract tables
        for table in doc.tables:
            headers: list[str] = []
            rows: list[list[str]] = []
            for row_idx, row in enumerate(table.rows):
                cells = [cell.text.strip() for cell in row.cells]
                if row_idx == 0:
                    headers = cells
                else:
                    rows.append(cells)
            if headers or rows:
                blocks.append(TableBlock(headers=headers, rows=rows))

        logger.debug(
            "Parsed DOCX %s: %d blocks",
            path.name,
            len(blocks),
        )
        return ParsedDocument(
            blocks=blocks,
            metadata={
                "title": path.stem,
                "source_path": str(path),
                "content_type": ".docx",
            },
        )

    def _parse_html(self, path: Path) -> ParsedDocument:
        """Extract text from HTML using beautifulsoup4."""
        from bs4 import BeautifulSoup

        content = path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(content, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style"]):
            element.decompose()

        blocks: list = []
        body = soup.body if soup.body else soup

        for element in body.children:
            if not hasattr(element, "name") or element.name is None:
                text = str(element).strip()
                if text:
                    blocks.append(Paragraph(text=text))
                continue

            tag = element.name.lower()

            # Headings
            if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                level = int(tag[1])
                text = element.get_text(strip=True)
                if text:
                    blocks.append(Heading(level=level, text=text))

            # Paragraphs
            elif tag == "p":
                text = element.get_text(strip=True)
                if text:
                    blocks.append(Paragraph(text=text))

            # Lists
            elif tag in ("ul", "ol"):
                ordered = tag == "ol"
                items = []
                for li in element.find_all("li", recursive=False):
                    text = li.get_text(strip=True)
                    if text:
                        items.append(ListItem(text=text, ordered=ordered))
                if items:
                    blocks.append(ListBlock(items=items))

            # Tables
            elif tag == "table":
                headers: list[str] = []
                rows: list[list[str]] = []

                # Extract headers from thead or first row th
                thead = element.find("thead")
                if thead:
                    for th in thead.find_all("th"):
                        headers.append(th.get_text(strip=True))

                # Extract rows from tbody or all tr
                tbody = element.find("tbody")
                target = tbody if tbody else element
                for tr in target.find_all("tr", recursive=False):
                    cells = []
                    for td in tr.find_all(["td", "th"]):
                        cells.append(td.get_text(strip=True))
                    if cells:
                        if not headers:
                            # Use first row as headers if no thead
                            headers = cells
                        else:
                            rows.append(cells)

                if headers or rows:
                    blocks.append(TableBlock(headers=headers, rows=rows))

            # Div and other block elements — extract text as paragraph
            elif tag in ("div", "section", "article", "blockquote"):
                text = element.get_text(strip=True)
                if text:
                    blocks.append(Paragraph(text=text))

        logger.debug("Parsed HTML %s: %d blocks", path.name, len(blocks))
        return ParsedDocument(
            blocks=blocks,
            metadata={
                "title": path.stem,
                "source_path": str(path),
                "content_type": path.suffix.lower(),
            },
        )

    def _parse_plain(self, path: Path, ext: str = ".txt") -> ParsedDocument:
        """Read plain text files (TXT, MD) with heading detection for MD."""
        content = path.read_text(encoding="utf-8", errors="replace")
        blocks: list = []

        if ext == ".md":
            # Markdown: detect headings by # prefix
            blocks = self._parse_markdown_blocks(content)
        else:
            # Plain text: split into paragraphs
            paragraphs = re.split(r"\n\s*\n", content)
            for para in paragraphs:
                text = para.strip()
                if text:
                    blocks.append(Paragraph(text=text))

        logger.debug("Parsed plain text %s: %d blocks", path.name, len(blocks))
        return ParsedDocument(
            blocks=blocks,
            metadata={
                "title": path.stem,
                "source_path": str(path),
                "content_type": ext,
            },
        )

    @staticmethod
    def _parse_markdown_blocks(content: str) -> list:
        """Parse markdown content into blocks, detecting headings and lists."""
        blocks: list = []
        lines = content.split("\n")
        current_paragraph_lines: list[str] = []
        current_list_items: list[ListItem] = []

        def flush_paragraph():
            if current_paragraph_lines:
                text = " ".join(current_paragraph_lines).strip()
                if text:
                    blocks.append(Paragraph(text=text))
                current_paragraph_lines.clear()

        def flush_list():
            if current_list_items:
                blocks.append(ListBlock(items=current_list_items.copy()))
                current_list_items.clear()

        for line in lines:
            stripped = line.strip()

            # Check for heading
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if heading_match:
                flush_paragraph()
                flush_list()
                level = len(heading_match.group(1))
                text = heading_match.group(2).strip()
                blocks.append(Heading(level=level, text=text))
                continue

            # Check for list item (unordered: - * +, ordered: 1. 2. etc.)
            list_match = re.match(r"^[-*+]\s+(.+)$", stripped) or re.match(
                r"^\d+\.\s+(.+)$", stripped
            )
            if list_match:
                flush_paragraph()
                text = list_match.group(1).strip()
                # Detect if ordered (starts with digit)
                ordered = bool(re.match(r"^\d+\.", stripped))
                current_list_items.append(ListItem(text=text, ordered=ordered))
                continue

            # Blank line → paragraph/list boundary
            if not stripped:
                flush_paragraph()
                flush_list()
                continue

            # Accumulate paragraph lines
            flush_list()  # Flush any pending list before starting paragraph
            current_paragraph_lines.append(stripped)

        flush_paragraph()
        flush_list()
        return blocks
