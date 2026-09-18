"""Filesystem-based DocumentSource adapter.

Scans a local directory (WATCH_DIR) for supported document files
and returns metadata dicts for each discoverable file.
"""

import hashlib
import logging
from pathlib import Path

from src.config import get_settings

logger = logging.getLogger(__name__)

# Supported file extensions for ingestion
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm", ".txt", ".md"}


class FilesystemSource:
    """Scans a local directory for documents.

    Implements the DocumentSource port protocol.
    """

    def __init__(self, watch_dir: str | None = None):
        settings = get_settings()
        self.watch_dir = Path(watch_dir or settings.watch_dir)

    async def scan(self) -> list[dict]:
        """Return metadata dicts for all supported files in WATCH_DIR.

        Each dict contains:
          - path: absolute path to the file
          - title: filename without extension
          - extension: file extension (lowercase)
          - size: file size in bytes

        Unsupported extensions and unreadable files are skipped with a warning.
        """
        results: list[dict] = []

        if not self.watch_dir.exists():
            logger.warning("Watch directory does not exist: %s", self.watch_dir)
            return results

        if not self.watch_dir.is_dir():
            logger.warning("Watch path is not a directory: %s", self.watch_dir)
            return results

        for entry in sorted(self.watch_dir.rglob("*")):
            if not entry.is_file():
                continue

            ext = entry.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                logger.debug("Skipping unsupported file: %s", entry)
                continue

            try:
                stat = entry.stat()
                if stat.st_size == 0:
                    logger.warning("Skipping zero-byte file: %s", entry)
                    continue

                content_hash = hashlib.sha256(entry.read_bytes()).hexdigest()

                results.append(
                    {
                        "path": str(entry.resolve()),
                        "title": entry.stem,
                        "extension": ext,
                        "size": stat.st_size,
                        "content_hash": content_hash,
                    }
                )
            except OSError as exc:
                logger.warning("Cannot stat file %s: %s", entry, exc)
                continue

        logger.info(
            "FilesystemSource scanned %s: found %d supported files",
            self.watch_dir,
            len(results),
        )
        return results
