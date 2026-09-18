"""Unit tests for DocumentRegistry diff logic.

Tests the pure-function compute_diff() method for detecting:
- new files (on disk but not in registry)
- changed files (hash differs from registry)
- unchanged files (hash matches registry)
- renamed files (hash match + path differs, one-to-one)
- deleted files (in registry but not on disk)
- ambiguous renames (2:2 → delete+insert)
"""


from src.adapters.document_registry import DocumentRecord, DocumentRegistry


def _make_record(
    doc_id: str,
    source_path: str,
    content_hash: str,
    title: str = "Test",
    content_type: str = ".md",
    chunk_count: int = 3,
) -> DocumentRecord:
    """Create a DocumentRecord for testing."""
    from datetime import datetime, timezone

    return DocumentRecord(
        id=doc_id,
        source_path=source_path,
        title=title,
        content_hash=content_hash,
        content_type=content_type,
        chunk_count=chunk_count,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        modified_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        indexed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_scan(path: str, content_hash: str, title: str = "Test", extension: str = ".md"):
    """Create a scan result dict for testing."""
    return {
        "path": path,
        "title": title,
        "extension": extension,
        "content_hash": content_hash,
        "size": 100,
    }


class TestComputeDiffAllUnchanged:
    """Scenario: all files in registry match scan — everything skipped."""

    def test_all_unchanged_skipped(self):
        """5 files with matching hashes → all skipped, nothing new/changed/deleted."""
        registry = {
            "/docs/a.md": _make_record("id_a", "/docs/a.md", "hash_a"),
            "/docs/b.md": _make_record("id_b", "/docs/b.md", "hash_b"),
            "/docs/c.md": _make_record("id_c", "/docs/c.md", "hash_c"),
            "/docs/d.md": _make_record("id_d", "/docs/d.md", "hash_d"),
            "/docs/e.md": _make_record("id_e", "/docs/e.md", "hash_e"),
        }
        scan = [
            _make_scan("/docs/a.md", "hash_a"),
            _make_scan("/docs/b.md", "hash_b"),
            _make_scan("/docs/c.md", "hash_c"),
            _make_scan("/docs/d.md", "hash_d"),
            _make_scan("/docs/e.md", "hash_e"),
        ]

        diff = DocumentRegistry.compute_diff(scan, registry)

        assert len(diff.new) == 0
        assert len(diff.changed) == 0
        assert len(diff.unchanged) == 5
        assert len(diff.renamed) == 0
        assert len(diff.deleted) == 0


class TestComputeDiffOneChanged:
    """Scenario: one file has different hash → re-process."""

    def test_one_changed_detected(self):
        """File with different hash → appears in changed list."""
        registry = {
            "/docs/a.md": _make_record("id_a", "/docs/a.md", "hash_a_old"),
        }
        scan = [_make_scan("/docs/a.md", "hash_a_new")]

        diff = DocumentRegistry.compute_diff(scan, registry)

        assert len(diff.changed) == 1
        assert diff.changed[0]["path"] == "/docs/a.md"
        assert len(diff.unchanged) == 0
        assert len(diff.new) == 0
        assert len(diff.deleted) == 0


class TestComputeDiffOneNew:
    """Scenario: new file on disk not in registry → full process."""

    def test_one_new_detected(self):
        """File not in registry → appears in new list."""
        registry = {
            "/docs/existing.md": _make_record("id_ex", "/docs/existing.md", "hash_ex"),
        }
        scan = [
            _make_scan("/docs/existing.md", "hash_ex"),
            _make_scan("/docs/new.md", "hash_new"),
        ]

        diff = DocumentRegistry.compute_diff(scan, registry)

        assert len(diff.new) == 1
        assert diff.new[0]["path"] == "/docs/new.md"
        assert len(diff.unchanged) == 1
        assert len(diff.changed) == 0
        assert len(diff.deleted) == 0


class TestComputeDiffOneDeleted:
    """Scenario: file in registry but not on disk → cleanup."""

    def test_one_deleted_detected(self):
        """Registry file missing from disk → appears in deleted list."""
        registry = {
            "/docs/keep.md": _make_record("id_k", "/docs/keep.md", "hash_k"),
            "/docs/gone.md": _make_record("id_g", "/docs/gone.md", "hash_g"),
        }
        scan = [_make_scan("/docs/keep.md", "hash_k")]

        diff = DocumentRegistry.compute_diff(scan, registry)

        assert len(diff.deleted) == 1
        assert diff.deleted[0].source_path == "/docs/gone.md"
        assert len(diff.unchanged) == 1
        assert len(diff.new) == 0
        assert len(diff.changed) == 0


class TestComputeDiffRename:
    """Scenario: file renamed — hash match + path differs, one-to-one."""

    def test_rename_detected(self):
        """File moved from old path to new path with same hash → rename."""
        registry = {
            "/docs/old.md": _make_record("id_r", "/docs/old.md", "hash_xyz"),
        }
        scan = [_make_scan("/docs/new.md", "hash_xyz")]

        diff = DocumentRegistry.compute_diff(scan, registry)

        assert len(diff.renamed) == 1
        assert diff.renamed[0].old_path == "/docs/old.md"
        assert diff.renamed[0].new_path == "/docs/new.md"
        assert diff.renamed[0].record.id == "id_r"
        assert len(diff.new) == 0
        assert len(diff.deleted) == 0

    def test_rename_preserves_chunks(self):
        """Rename detection means no re-processing — chunks preserved."""
        registry = {
            "/docs/original.md": _make_record(
                "id_x", "/docs/original.md", "hash_same", chunk_count=5,
            ),
        }
        scan = [_make_scan("/docs/renamed.md", "hash_same")]

        diff = DocumentRegistry.compute_diff(scan, registry)

        assert len(diff.renamed) == 1
        # Renamed files should NOT appear in new or changed
        assert len(diff.new) == 0
        assert len(diff.changed) == 0
        # And NOT in deleted
        assert len(diff.deleted) == 0


class TestComputeDiffAmbiguousRename:
    """Scenario: 2 files removed, 2 new with same hash → truly ambiguous."""

    def test_ambiguous_rename_falls_back_to_delete_insert(self):
        """2 files with same hash removed + 2 new with same hash → delete+insert."""
        registry = {
            "/docs/a.md": _make_record("id_a", "/docs/a.md", "hash_same"),
            "/docs/b.md": _make_record("id_b", "/docs/b.md", "hash_same"),
        }
        scan = [
            _make_scan("/docs/c.md", "hash_same"),
            _make_scan("/docs/d.md", "hash_same"),
        ]

        diff = DocumentRegistry.compute_diff(scan, registry)

        # Ambiguous: can't determine which old maps to which new
        # Falls back to delete+insert (not rename)
        assert len(diff.deleted) == 2
        assert len(diff.new) == 2
        assert len(diff.renamed) == 0

    def test_one_to_one_hash_match_is_rename(self):
        """Each hash unique to one old + one new path → detected as renames."""
        registry = {
            "/docs/a.md": _make_record("id_a", "/docs/a.md", "hash_1"),
            "/docs/b.md": _make_record("id_b", "/docs/b.md", "hash_2"),
        }
        scan = [
            _make_scan("/docs/c.md", "hash_1"),
            _make_scan("/docs/d.md", "hash_2"),
        ]

        diff = DocumentRegistry.compute_diff(scan, registry)

        # Unambiguous: each hash maps one-to-one
        assert len(diff.renamed) == 2
        assert len(diff.deleted) == 0
        assert len(diff.new) == 0


class TestComputeDiffMixedScenario:
    """Scenario: combination of new, changed, unchanged, renamed, deleted."""

    def test_mixed_diff(self):
        """Complex scenario with all categories."""
        registry = {
            "/docs/unchanged.md": _make_record("id_u", "/docs/unchanged.md", "hash_u"),
            "/docs/changed.md": _make_record("id_c", "/docs/changed.md", "hash_c_old"),
            "/docs/renamed.md": _make_record("id_r", "/docs/renamed.md", "hash_r"),
            "/docs/deleted.md": _make_record("id_d", "/docs/deleted.md", "hash_d"),
        }
        scan = [
            _make_scan("/docs/unchanged.md", "hash_u"),
            _make_scan("/docs/changed.md", "hash_c_new"),
            _make_scan("/docs/renamed_new.md", "hash_r"),  # renamed
            _make_scan("/docs/new.md", "hash_new"),
        ]

        diff = DocumentRegistry.compute_diff(scan, registry)

        assert len(diff.unchanged) == 1
        assert diff.unchanged[0]["path"] == "/docs/unchanged.md"

        assert len(diff.changed) == 1
        assert diff.changed[0]["path"] == "/docs/changed.md"

        assert len(diff.renamed) == 1
        assert diff.renamed[0].old_path == "/docs/renamed.md"
        assert diff.renamed[0].new_path == "/docs/renamed_new.md"

        assert len(diff.deleted) == 1
        assert diff.deleted[0].source_path == "/docs/deleted.md"

        assert len(diff.new) == 1
        assert diff.new[0]["path"] == "/docs/new.md"


class TestComputeDiffEmptyRegistry:
    """Scenario: first scan — registry is empty, all files are new."""

    def test_empty_registry_all_new(self):
        """Empty registry → all scan results are new."""
        scan = [
            _make_scan("/docs/a.md", "hash_a"),
            _make_scan("/docs/b.md", "hash_b"),
        ]

        diff = DocumentRegistry.compute_diff(scan, {})

        assert len(diff.new) == 2
        assert len(diff.unchanged) == 0
        assert len(diff.changed) == 0
        assert len(diff.deleted) == 0
        assert len(diff.renamed) == 0


class TestComputeDiffEmptyScan:
    """Scenario: empty scan — all registry files are deleted."""

    def test_empty_scan_all_deleted(self):
        """No files on disk → all registry entries are deleted."""
        registry = {
            "/docs/a.md": _make_record("id_a", "/docs/a.md", "hash_a"),
            "/docs/b.md": _make_record("id_b", "/docs/b.md", "hash_b"),
        }

        diff = DocumentRegistry.compute_diff([], registry)

        assert len(diff.deleted) == 2
        assert len(diff.new) == 0
        assert len(diff.unchanged) == 0


class TestComputeDiffDuplicateContentNewFiles:
    """Scenario: two new files with identical content → both ingested."""

    def test_duplicate_content_both_new(self):
        """Two new files with same hash → both ingested as separate docs."""
        registry = {}
        scan = [
            _make_scan("/docs/a.md", "hash_same"),
            _make_scan("/docs/b.md", "hash_same"),
        ]

        diff = DocumentRegistry.compute_diff(scan, registry)

        assert len(diff.new) == 2
        paths = {r["path"] for r in diff.new}
        assert paths == {"/docs/a.md", "/docs/b.md"}
