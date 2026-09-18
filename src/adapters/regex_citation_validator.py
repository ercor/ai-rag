"""Regex-based CitationValidator adapter.

Extracts [N] citation markers from generated text, validates them
against the set of valid chunk indices, and strips invalid references.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Pattern to match citation markers like [1], [2], [12], etc.
CITATION_PATTERN = re.compile(r"\[(\d+)\]")


class RegexCitationValidator:
    """Validates citation markers using regex extraction.

    Implements the CitationValidator port protocol.
    Finds all [N] markers, checks if N is in the valid set,
    and removes invalid references from the text.
    """

    def validate(self, answer: str, valid_ids: set[int]) -> str:
        """Return answer text with invalid [N] citation markers removed.

        Scans the answer for all [N] patterns. If N is not in valid_ids,
        the marker is stripped from the text. Valid markers are preserved.

        Args:
            answer: The generated answer text potentially containing [N] markers.
            valid_ids: Set of 1-based citation indices that correspond to
                       actual retrieved chunks.

        Returns:
            The answer text with invalid citation markers removed.
        """
        if not answer:
            return answer

        if not valid_ids:
            # No valid citations — strip all markers
            cleaned = CITATION_PATTERN.sub("", answer)
            if cleaned != answer:
                logger.warning(
                    "Stripped all citation markers (no valid IDs): removed %d markers",
                    len(CITATION_PATTERN.findall(answer)),
                )
            return cleaned

        def _replace_match(match: re.Match) -> str:
            """Keep valid citations, remove invalid ones."""
            citation_num = int(match.group(1))
            if citation_num in valid_ids:
                return match.group(0)  # Keep [N]
            else:
                logger.warning(
                    "Invalid citation [%d] removed (valid: %s)",
                    citation_num,
                    sorted(valid_ids),
                )
                return ""  # Strip invalid [N]

        cleaned = CITATION_PATTERN.sub(_replace_match, answer)

        # Log summary if anything was stripped
        original_count = len(CITATION_PATTERN.findall(answer))
        cleaned_count = len(CITATION_PATTERN.findall(cleaned))
        if original_count != cleaned_count:
            logger.info(
                "Citation validation: %d markers found, %d valid, %d stripped",
                original_count,
                cleaned_count,
                original_count - cleaned_count,
            )

        return cleaned

    def extract_citations(self, answer: str) -> list[int]:
        """Extract all citation numbers from the answer text.

        Returns a sorted list of unique citation indices found in [N] markers.
        """
        matches = CITATION_PATTERN.findall(answer)
        return sorted(set(int(m) for m in matches))
