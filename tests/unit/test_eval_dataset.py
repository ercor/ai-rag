"""Unit tests for gold dataset loader."""

import json
import pytest
import tempfile
from pathlib import Path

from src.evaluation.dataset import load_gold_dataset, EvalSample


class TestLoadGoldDataset:
    """Tests for load_gold_dataset function."""

    def _write_dataset(self, data: list[dict]) -> str:
        """Write dataset to a temp file and return the path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            return f.name

    def test_valid_dataset_loads(self):
        """Valid dataset with all required fields loads successfully."""
        data = [
            {
                "question": "What is X?",
                "ground_truth": "X is Y.",
                "contexts": ["Context about X being Y."],
            }
            for _ in range(25)
        ]
        path = self._write_dataset(data)
        samples = load_gold_dataset(path)
        assert len(samples) == 25
        assert all(isinstance(s, EvalSample) for s in samples)
        Path(path).unlink()

    def test_invalid_sample_missing_ground_truth(self):
        """Sample missing ground_truth raises validation error."""
        data = [
            {
                "question": "What is X?",
                "contexts": ["Context."],
                # Missing ground_truth
            }
        ]
        path = self._write_dataset(data)
        with pytest.raises(ValueError, match="missing required field"):
            load_gold_dataset(path)
        Path(path).unlink()

    def test_invalid_sample_missing_question(self):
        """Sample missing question raises validation error."""
        data = [
            {
                "ground_truth": "X is Y.",
                "contexts": ["Context."],
            }
        ]
        path = self._write_dataset(data)
        with pytest.raises(ValueError, match="missing required field.*question"):
            load_gold_dataset(path)
        Path(path).unlink()

    def test_invalid_sample_missing_contexts(self):
        """Sample missing contexts raises validation error."""
        data = [
            {
                "question": "What is X?",
                "ground_truth": "X is Y.",
            }
        ]
        path = self._write_dataset(data)
        with pytest.raises(ValueError, match="missing required field.*contexts"):
            load_gold_dataset(path)
        Path(path).unlink()

    def test_error_indicates_sample_index(self):
        """Error message indicates which sample is invalid."""
        data = [
            {
                "question": "Q1",
                "ground_truth": "A1",
                "contexts": ["C1"],
            },
            {
                "question": "Q2",
                # Missing ground_truth
                "contexts": ["C2"],
            },
        ]
        path = self._write_dataset(data)
        with pytest.raises(ValueError, match="Sample 1"):
            load_gold_dataset(path)
        Path(path).unlink()

    def test_non_array_raises_error(self):
        """Non-array JSON raises error."""
        path = self._write_dataset({"not": "an array"})  # type: ignore
        with pytest.raises(ValueError, match="must be a JSON array"):
            load_gold_dataset(path)
        Path(path).unlink()

    def test_non_object_sample_raises_error(self):
        """Non-object sample raises error."""
        path = self._write_dataset(["not an object"])  # type: ignore
        with pytest.raises(ValueError, match="must be a JSON object"):
            load_gold_dataset(path)
        Path(path).unlink()

    def test_file_not_found(self):
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Dataset file not found"):
            load_gold_dataset("/nonexistent/path.json")

    def test_metadata_is_optional(self):
        """Samples without metadata load successfully."""
        data = [
            {
                "question": "Q?",
                "ground_truth": "A.",
                "contexts": ["C."],
            }
        ]
        path = self._write_dataset(data)
        samples = load_gold_dataset(path)
        assert len(samples) == 1
        assert samples[0].metadata == {}
        Path(path).unlink()

    def test_metadata_is_preserved(self):
        """Metadata dict is preserved when present."""
        data = [
            {
                "question": "Q?",
                "ground_truth": "A.",
                "contexts": ["C."],
                "metadata": {"source": "doc1", "difficulty": "easy"},
            }
        ]
        path = self._write_dataset(data)
        samples = load_gold_dataset(path)
        assert samples[0].metadata == {"source": "doc1", "difficulty": "easy"}
        Path(path).unlink()

    def test_gold_set_file_loads(self):
        """The actual gold_set.json file loads successfully."""
        samples = load_gold_dataset("data/eval/gold_set.json")
        assert len(samples) >= 20
        # Check stratification
        sources = {s.metadata.get("source") for s in samples}
        difficulties = {s.metadata.get("difficulty") for s in samples}
        categories = {s.metadata.get("category") for s in samples}
        assert len(sources) >= 3
        assert "easy" in difficulties
        assert "medium" in difficulties
        assert "hard" in difficulties
        assert "factual" in categories
        assert "comparative" in categories
        assert "procedural" in categories
