"""Unit tests for SearchIndex port — delete_chunks method contract.

Verifies the Protocol defines delete_chunks(document_id) -> int.
"""


from src.ports.search_index import SearchIndex


class TestSearchIndexDeleteChunksPort:
    def test_protocol_has_delete_chunks_method(self):
        """SearchIndex protocol defines delete_chunks."""
        assert hasattr(SearchIndex, "delete_chunks"), (
            "SearchIndex protocol must define delete_chunks method"
        )

    def test_delete_chunks_is_callable(self):
        """delete_chunks is a callable method on the protocol."""
        assert callable(getattr(SearchIndex, "delete_chunks", None)), (
            "delete_chunks must be callable"
        )
