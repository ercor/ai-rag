"""CitationValidator port — validates citation markers in generated text."""

from typing import Protocol


class CitationValidator(Protocol):
    """Validates and cleans citation markers ([N]) in generated answer text.

    Strips references to chunk IDs that are not in the valid set.
    """

    def validate(self, answer: str, valid_ids: set[int]) -> str:
        """Return answer text with invalid [N] citation markers removed.

        `valid_ids` is the set of 1-based citation indices that correspond
        to actual retrieved chunks.
        """
        ...
