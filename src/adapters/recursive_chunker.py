"""Block-aware recursive chunker adapter.

Splits ParsedDocument blocks into semantically coherent chunks,
respecting block boundaries (never splits inside lists or tables),
preserving heading hierarchy in section_path, and attaching page_number
from PageMarker blocks.

Uses per-type config for chunk size and overlap.
"""

import hashlib
import logging
import re
from dataclasses import dataclass

from src.ports.models import (
    Chunk,
    Heading,
    ListBlock,
    PageMarker,
    Paragraph,
    ParsedDocument,
    TableBlock,
)

logger = logging.getLogger(__name__)

# Rough token estimation: ~4 chars per token (English approximation)
CHARS_PER_TOKEN = 4

# Heading patterns for legacy text-based parsing
HEADING_PATTERN = re.compile(
    r"^(#{1,6}\s+.+|[\w][^\n]{0,72}\n=+\n|[\w][^\n]{0,72}\n-+\n)$",
    re.MULTILINE,
)


@dataclass
class _Section:
    """Internal representation of a document section."""

    heading: str
    level: int
    content: str
    path: str  # breadcrumb path like "Introduction > Background"


def _estimate_tokens(text: str) -> int:
    """Estimate token count from character length."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def _content_hash(text: str) -> str:
    """Compute SHA-256 hash of chunk content for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _detect_heading_level(heading_line: str) -> int:
    """Detect heading level from a heading line."""
    heading_line = heading_line.strip()
    if heading_line.startswith("#"):
        return len(heading_line) - len(heading_line.lstrip("#"))
    return 1


def _parse_sections(text: str) -> list[_Section]:
    """Split text into sections based on heading boundaries (legacy).

    Kept for backward compatibility with existing tests.
    """
    sections: list[_Section] = []
    heading_stack: list[tuple[int, str]] = []

    parts = HEADING_PATTERN.split(text)

    if len(parts) <= 1:
        return [_Section(heading="", level=0, content=text.strip(), path="")]

    current_content_parts: list[str] = []
    current_heading = ""
    current_level = 0

    first_text = parts[0] if parts else ""
    if first_text.strip():
        sections.append(
            _Section(heading="", level=0, content=first_text.strip(), path="")
        )

    for i in range(1, len(parts)):
        part = parts[i]
        if not part or not part.strip():
            continue

        if HEADING_PATTERN.match(part.strip()):
            if current_content_parts:
                content = "\n".join(current_content_parts).strip()
                if content:
                    path = _build_path(heading_stack)
                    sections.append(
                        _Section(
                            heading=current_heading,
                            level=current_level,
                            content=content,
                            path=path,
                        )
                    )
                current_content_parts = []

            level = _detect_heading_level(part.strip())
            title = re.sub(r"^#+\s*", "", part.strip()).strip()

            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))

            current_heading = title
            current_level = level
        else:
            current_content_parts.append(part)

    if current_content_parts:
        content = "\n".join(current_content_parts).strip()
        if content:
            path = _build_path(heading_stack)
            sections.append(
                _Section(
                    heading=current_heading,
                    level=current_level,
                    content=content,
                    path=path,
                )
            )

    return sections


def _build_path(heading_stack: list[tuple[int, str]]) -> str:
    """Build a breadcrumb path from the heading stack."""
    if not heading_stack:
        return ""
    return " > ".join(title for _, title in heading_stack)


def _recursive_split(text: str, min_tokens: int, max_tokens: int) -> list[str]:
    """Recursively split text to fit within token bounds."""
    tokens = _estimate_tokens(text)

    if tokens <= max_tokens:
        return [text] if text.strip() else []

    chunks = _split_on_separator(text, "\n\n", min_tokens, max_tokens)
    if chunks:
        return chunks

    chunks = _split_on_separator(text, "\n", min_tokens, max_tokens)
    if chunks:
        return chunks

    chunks = _split_on_separator(text, ". ", min_tokens, max_tokens)
    if chunks:
        return chunks

    return _hard_split(text, max_tokens)


def _split_on_separator(
    text: str, sep: str, min_tokens: int, max_tokens: int
) -> list[str]:
    """Split text on a separator, merging small pieces and splitting large ones."""
    parts = text.split(sep)
    if len(parts) <= 1:
        return []

    chunks: list[str] = []
    current = ""

    for part in parts:
        candidate = f"{current}{sep}{part}".strip() if current else part.strip()

        if _estimate_tokens(candidate) <= max_tokens:
            current = candidate
        else:
            if current:
                if _estimate_tokens(current) >= min_tokens:
                    chunks.append(current)
                    current = part.strip()
                else:
                    current = candidate
            else:
                sub_chunks = _recursive_split(part, min_tokens, max_tokens)
                chunks.extend(sub_chunks)
                current = ""

    if current and current.strip():
        if chunks and _estimate_tokens(current) < min_tokens:
            chunks[-1] = f"{chunks[-1]}{sep}{current}"
        else:
            chunks.append(current)

    return chunks if len(chunks) > 1 else []


def _hard_split(text: str, max_tokens: int) -> list[str]:
    """Split text into fixed-size chunks by word boundaries."""
    words = text.split()
    max_words = max_tokens * CHARS_PER_TOKEN // 5
    if max_words < 1:
        max_words = 50

    chunks: list[str] = []
    for i in range(0, len(words), max_words):
        chunk = " ".join(words[i : i + max_words])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def _apply_overlap(chunks: list[str], overlap_ratio: float) -> list[str]:
    """Apply overlap between consecutive chunks by repeating trailing content."""
    if len(chunks) <= 1:
        return chunks

    result = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        curr = chunks[i]

        overlap_chars = int(len(prev) * overlap_ratio)
        if overlap_chars > 0 and overlap_chars < len(prev):
            overlap_text = prev[-overlap_chars:]
            result.append(overlap_text + " " + curr)
        else:
            result.append(curr)

    return result


def _block_to_text(block) -> str:
    """Convert a block to its text representation."""
    if isinstance(block, Heading):
        prefix = "#" * block.level
        return f"{prefix} {block.text}"
    elif isinstance(block, Paragraph):
        return block.text
    elif isinstance(block, ListBlock):
        lines = []
        for item in block.items:
            if item.ordered:
                lines.append(f"1. {item.text}")
            else:
                lines.append(f"- {item.text}")
        return "\n".join(lines)
    elif isinstance(block, TableBlock):
        lines = []
        if block.headers:
            lines.append("| " + " | ".join(block.headers) + " |")
            lines.append("| " + " | ".join("---" for _ in block.headers) + " |")
        for row in block.rows:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)
    elif isinstance(block, PageMarker):
        return ""  # PageMarkers are metadata, not content
    return ""


def _is_atomic_block(block) -> bool:
    """Check if a block should never be split (ListBlock, TableBlock)."""
    return isinstance(block, (ListBlock, TableBlock))


class RecursiveChunker:
    """Block-aware recursive text chunker.

    Implements the Chunker port protocol.
    Respects block boundaries — never splits inside lists or tables.
    """

    def __init__(
        self,
        min_tokens: int = 200,
        max_tokens: int = 600,
        overlap: int = 50,
        overlap_ratio: float | None = None,
    ):
        self.min_tokens = min_tokens
        self.max_tokens = max_tokens
        # Support both old (overlap_ratio) and new (overlap) API
        if overlap_ratio is not None:
            self.overlap_ratio = overlap_ratio
            self.overlap = int(max_tokens * overlap_ratio)
        else:
            self.overlap = overlap
            self.overlap_ratio = overlap / max_tokens if max_tokens > 0 else 0.1

    def split(
        self,
        doc: ParsedDocument,
        doc_id: str,
        doc_title: str,
        source: str,
        source_type: str = ".txt",
    ) -> list[Chunk]:
        """Split ParsedDocument into Chunk dataclasses with metadata.

        Process:
        1. Iterate blocks, tracking heading hierarchy for section_path
        2. Accumulate text within token bounds
        3. Never split atomic blocks (ListBlock, TableBlock)
        4. Attach page_number from PageMarker blocks
        5. Apply overlap between consecutive chunks
        """
        if not doc.blocks:
            return []

        # Build sections from blocks with heading hierarchy tracking
        sections = self._build_sections(doc)

        if not sections:
            return []

        # Split sections into raw chunks
        raw_chunks: list[tuple[str, str, int | None]] = []  # (content, path, page)

        for section in sections:
            if section.atomic:
                # Atomic blocks (lists, tables) are never split
                raw_chunks.append((section.content, section.path, section.page_number))
            else:
                # Regular content can be split
                pieces = _recursive_split(
                    section.content, self.min_tokens, self.max_tokens
                )
                for piece in pieces:
                    raw_chunks.append((piece, section.path, section.page_number))

        if not raw_chunks:
            return []

        # Apply overlap
        contents = [c for c, _, _ in raw_chunks]
        paths = [p for _, p, _ in raw_chunks]
        pages = [pg for _, _, pg in raw_chunks]
        overlapped = _apply_overlap(contents, self.overlap_ratio)
        raw_chunks = list(zip(overlapped, paths, pages))

        # Build Chunk objects
        chunks: list[Chunk] = []
        for idx, (content, section_path, page_number) in enumerate(raw_chunks):
            content = content.strip()
            if not content:
                continue

            chunks.append(
                Chunk(
                    document_id=doc_id,
                    document_title=doc_title,
                    source_path=source,
                    section_path=section_path,
                    chunk_index=idx,
                    content=content,
                    token_count=_estimate_tokens(content),
                    content_hash=_content_hash(content),
                    page_number=page_number,
                )
            )

        # Re-index sequentially
        for i, chunk in enumerate(chunks):
            chunks[i] = Chunk(
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                source_path=chunk.source_path,
                section_path=chunk.section_path,
                chunk_index=i,
                content=chunk.content,
                token_count=chunk.token_count,
                content_hash=chunk.content_hash,
                page_number=chunk.page_number,
                anchor=chunk.anchor,
            )

        logger.debug(
            "Chunked document %s (%s): %d chunks from %d sections",
            doc_id,
            doc_title,
            len(chunks),
            len(sections),
        )
        return chunks

    def _build_sections(self, doc: ParsedDocument) -> list["_BlockSection"]:
        """Build sections from blocks, tracking heading hierarchy and page markers."""
        sections: list[_BlockSection] = []
        heading_stack: list[tuple[int, str]] = []
        current_page: int | None = None
        current_content_parts: list[str] = []
        current_atomic = False

        def flush_content():
            nonlocal current_content_parts, current_atomic
            if current_content_parts:
                content = "\n\n".join(current_content_parts).strip()
                if content:
                    path = _build_path(heading_stack)
                    sections.append(
                        _BlockSection(
                            content=content,
                            path=path,
                            page_number=current_page,
                            atomic=current_atomic,
                        )
                    )
                current_content_parts = []
                current_atomic = False

        for block in doc.blocks:
            if isinstance(block, PageMarker):
                flush_content()
                current_page = block.page_number
                continue

            if isinstance(block, Heading):
                flush_content()
                level = block.level
                title = block.text

                # Pop stack to find parent level
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, title))
                continue

            if _is_atomic_block(block):
                flush_content()
                text = _block_to_text(block)
                if text.strip():
                    path = _build_path(heading_stack)
                    sections.append(
                        _BlockSection(
                            content=text,
                            path=path,
                            page_number=current_page,
                            atomic=True,
                        )
                    )
                continue

            # Regular paragraph
            text = _block_to_text(block)
            if text.strip():
                current_content_parts.append(text)

        flush_content()
        return sections


@dataclass
class _BlockSection:
    """Internal section representation for block-aware chunking."""

    content: str
    path: str
    page_number: int | None = None
    atomic: bool = False
