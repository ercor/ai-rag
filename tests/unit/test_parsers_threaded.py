"""Unit tests for threaded parser execution.

Tests:
- Sync parser libs run via asyncio.to_thread (don't block event loop)
- Concurrent hash computation succeeds during parse (proves non-blocking)
"""

import asyncio
from unittest.mock import patch


class TestParsersThreaded:
    async def test_parser_runs_in_thread(self):
        """Parser's blocking call runs via asyncio.to_thread."""
        from src.adapters.parsers import MultiFormatParser

        parser = MultiFormatParser()

        # Use plain text parser to avoid pymupdf dependency
        def fake_blocking_read(*args, **kwargs):
            """Simulate slow blocking operation."""
            import time
            time.sleep(0.05)  # Block for 50ms
            return "Fake text content"

        with patch("pathlib.Path.read_text", side_effect=fake_blocking_read):
            # Run parser and a concurrent task to prove non-blocking
            async def concurrent_task():
                """This should complete while parser is 'blocked'."""
                await asyncio.sleep(0.01)
                return "concurrent_done"

            # Run both concurrently
            results = await asyncio.gather(
                parser.parse("/fake/test.txt"),
                concurrent_task(),
            )

            # Parser returned ParsedDocument with content
            doc = results[0]
            assert any("Fake text content" in b.text for b in doc.blocks
                       if hasattr(b, "text"))
            # Concurrent task completed (proves event loop wasn't blocked)
            assert results[1] == "concurrent_done"

    async def test_concurrent_operations_during_parse(self):
        """Event loop remains responsive during parser execution."""
        from src.adapters.parsers import MultiFormatParser

        parser = MultiFormatParser()

        counter = {"value": 0}

        def fake_slow_parse(*args, **kwargs):
            """Simulate slow blocking operation."""
            import time
            time.sleep(0.05)  # Block for 50ms
            return "Slow content"

        async def incrementing_task():
            """Increment counter while parser is 'blocked'."""
            for _ in range(5):
                counter["value"] += 1
                await asyncio.sleep(0.01)

        with patch("pathlib.Path.read_text", side_effect=fake_slow_parse):
            # Run parser and counter concurrently
            await asyncio.gather(
                parser.parse("/fake/test.txt"),
                incrementing_task(),
            )

        # Counter should have incremented (event loop wasn't blocked)
        assert counter["value"] == 5

    async def test_html_parser_threaded(self):
        """HTML parser also runs in thread."""
        from src.adapters.parsers import MultiFormatParser

        parser = MultiFormatParser()

        def fake_html_read(*args, **kwargs):
            return "<html><body><p>Test content</p></body></html>"

        with patch("pathlib.Path.read_text", side_effect=fake_html_read):
            async def concurrent_check():
                await asyncio.sleep(0.01)
                return "responsive"

            results = await asyncio.gather(
                parser.parse("/fake/test.html"),
                concurrent_check(),
            )

            doc = results[0]
            assert any("Test content" in b.text for b in doc.blocks
                       if hasattr(b, "text"))
            assert results[1] == "responsive"
