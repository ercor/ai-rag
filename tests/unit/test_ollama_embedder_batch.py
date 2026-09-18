"""Unit tests for OllamaEmbedder batch embedding.

Tests:
- 20 texts → single call with input: string[]
- 100 texts → two calls (64 + 36)
- ordering preserved
- empty list → empty result
"""

from unittest.mock import AsyncMock, MagicMock, patch


class TestOllamaEmbedderBatch:
    async def test_single_batch_under_limit(self):
        """20 texts → single HTTP call with input as array."""
        from src.adapters.ollama_embedder import OllamaEmbedder

        embedder = OllamaEmbedder(base_url="http://test:11434", model="test-model")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "embeddings": [[0.1] * 768 for _ in range(20)]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            texts = [f"text {i}" for i in range(20)]
            result = await embedder.embed_batch(texts)

            assert len(result) == 20
            # Single call with array input
            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args
            assert call_kwargs[1]["json"]["model"] == "test-model"
            assert isinstance(call_kwargs[1]["json"]["input"], list)
            assert len(call_kwargs[1]["json"]["input"]) == 20

    async def test_split_batch_over_limit(self):
        """100 texts → two calls (64 + 36)."""
        from src.adapters.ollama_embedder import OllamaEmbedder

        embedder = OllamaEmbedder(
            base_url="http://test:11434", model="test-model", embed_batch_size=64
        )

        # First batch response (64 texts)
        mock_response_1 = MagicMock()
        mock_response_1.json.return_value = {
            "embeddings": [[0.1] * 768 for _ in range(64)]
        }
        mock_response_1.raise_for_status = MagicMock()

        # Second batch response (36 texts)
        mock_response_2 = MagicMock()
        mock_response_2.json.return_value = {
            "embeddings": [[0.2] * 768 for _ in range(36)]
        }
        mock_response_2.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[mock_response_1, mock_response_2])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            texts = [f"text {i}" for i in range(100)]
            result = await embedder.embed_batch(texts)

            assert len(result) == 100
            # Two calls
            assert mock_client.post.call_count == 2

            # First call: 64 texts
            first_call = mock_client.post.call_args_list[0]
            assert len(first_call[1]["json"]["input"]) == 64

            # Second call: 36 texts
            second_call = mock_client.post.call_args_list[1]
            assert len(second_call[1]["json"]["input"]) == 36

    async def test_ordering_preserved(self):
        """Results maintain same order as input texts."""
        from src.adapters.ollama_embedder import OllamaEmbedder

        embedder = OllamaEmbedder(
            base_url="http://test:11434", model="test-model", embed_batch_size=2
        )

        # First batch: texts 0,1 → embeddings [1,1,1], [2,2,2]
        mock_response_1 = MagicMock()
        mock_response_1.json.return_value = {
            "embeddings": [[1.0] * 768, [2.0] * 768]
        }
        mock_response_1.raise_for_status = MagicMock()

        # Second batch: texts 2,3 → embeddings [3,3,3], [4,4,4]
        mock_response_2 = MagicMock()
        mock_response_2.json.return_value = {
            "embeddings": [[3.0] * 768, [4.0] * 768]
        }
        mock_response_2.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[mock_response_1, mock_response_2])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            texts = ["a", "b", "c", "d"]
            result = await embedder.embed_batch(texts)

            # Order preserved: first embedding from first batch, etc.
            assert result[0][0] == 1.0
            assert result[1][0] == 2.0
            assert result[2][0] == 3.0
            assert result[3][0] == 4.0

    async def test_empty_list_returns_empty(self):
        """Empty input → empty output, no HTTP calls."""
        from src.adapters.ollama_embedder import OllamaEmbedder

        embedder = OllamaEmbedder(base_url="http://test:11434", model="test-model")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await embedder.embed_batch([])

            assert result == []
            mock_client.post.assert_not_called()
