"""Unit tests for FilesystemSource content_hash computation.

Verifies that scan() includes a SHA-256 content_hash for each file.
"""

import hashlib

from src.adapters.filesystem_source import FilesystemSource


class TestFilesystemSourceContentHash:
    async def test_scan_includes_content_hash(self, tmp_path):
        """Each scan result includes a content_hash field with SHA-256 hex."""
        test_file = tmp_path / "doc.md"
        content = b"# Hello World\nThis is test content."
        test_file.write_bytes(content)
        expected_hash = hashlib.sha256(content).hexdigest()

        source = FilesystemSource(watch_dir=str(tmp_path))
        results = await source.scan()

        assert len(results) == 1
        assert "content_hash" in results[0]
        assert results[0]["content_hash"] == expected_hash

    async def test_content_hash_changes_with_content(self, tmp_path):
        """Different file content produces different hashes."""
        file_a = tmp_path / "a.md"
        file_b = tmp_path / "b.md"
        file_a.write_bytes(b"content A")
        file_b.write_bytes(b"content B")

        source = FilesystemSource(watch_dir=str(tmp_path))
        results = await source.scan()

        assert len(results) == 2
        hashes = {r["content_hash"] for r in results}
        assert len(hashes) == 2, "Different files must have different hashes"

    async def test_content_hash_matches_sha256(self, tmp_path):
        """content_hash is the SHA-256 hex digest of the file bytes."""
        test_file = tmp_path / "report.pdf"
        content = b"%PDF-1.4 fake pdf content for testing"
        test_file.write_bytes(content)

        source = FilesystemSource(watch_dir=str(tmp_path))
        results = await source.scan()

        assert len(results) == 1
        expected = hashlib.sha256(content).hexdigest()
        assert results[0]["content_hash"] == expected
        assert len(results[0]["content_hash"]) == 64  # SHA-256 hex length

    async def test_empty_dir_returns_no_results(self, tmp_path):
        """Empty directory returns empty list (no hash computation needed)."""
        source = FilesystemSource(watch_dir=str(tmp_path))
        results = await source.scan()
        assert results == []
