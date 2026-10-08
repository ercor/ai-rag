"""Gold dataset loader for RAG evaluation.

Loads and validates evaluation samples from a JSON file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EvalSample:
    """A single evaluation sample from the gold dataset."""

    question: str
    ground_truth: str
    contexts: list[str]
    metadata: dict = field(default_factory=dict)


def load_gold_dataset(path: str) -> list[EvalSample]:
    """Load and validate a gold dataset from a JSON file.

    The file must contain a JSON array of objects, each with:
    - question (str, required)
    - ground_truth (str, required)
    - contexts (list[str], required)
    - metadata (dict, optional)

    Args:
        path: Path to the JSON file.

    Returns:
        List of validated EvalSample objects.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If a sample is missing required fields.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Dataset must be a JSON array, got {type(data).__name__}")

    samples = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Sample {i} must be a JSON object, got {type(item).__name__}")

        # Validate required fields
        missing = []
        for field_name in ("question", "ground_truth", "contexts"):
            if field_name not in item:
                missing.append(field_name)

        if missing:
            raise ValueError(
                f"Sample {i} is missing required field(s): {', '.join(missing)}"
            )

        # Validate types
        if not isinstance(item["question"], str):
            raise ValueError(f"Sample {i}: 'question' must be a string")
        if not isinstance(item["ground_truth"], str):
            raise ValueError(f"Sample {i}: 'ground_truth' must be a string")
        if not isinstance(item["contexts"], list):
            raise ValueError(f"Sample {i}: 'contexts' must be a list")
        if not all(isinstance(c, str) for c in item["contexts"]):
            raise ValueError(f"Sample {i}: all items in 'contexts' must be strings")

        samples.append(
            EvalSample(
                question=item["question"],
                ground_truth=item["ground_truth"],
                contexts=item["contexts"],
                metadata=item.get("metadata", {}),
            )
        )

    return samples
