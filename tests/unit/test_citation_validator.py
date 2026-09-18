"""Unit tests for RegexCitationValidator adapter.

Tests cover:
- Valid citations preserved
- Invalid citations stripped
- All-invalid scenario (all citations removed)
- Edge cases: empty text, no citations, mixed valid/invalid
"""

import pytest

from src.adapters.regex_citation_validator import RegexCitationValidator


@pytest.fixture
def validator():
    """Default RegexCitationValidator instance."""
    return RegexCitationValidator()


class TestValidCitations:
    """Test that valid citations are preserved."""

    def test_single_valid_citation(self, validator):
        """A valid [N] marker is kept in the text."""
        text = "The answer is 42 [1]."
        result = validator.validate(text, valid_ids={1})
        assert result == "The answer is 42 [1]."

    def test_multiple_valid_citations(self, validator):
        """Multiple valid [N] markers are all preserved."""
        text = "Source A says X [1] and source B says Y [2]."
        result = validator.validate(text, valid_ids={1, 2})
        assert result == "Source A says X [1] and source B says Y [2]."

    def test_all_three_valid(self, validator):
        """Three valid citations in sequence are preserved."""
        text = "Multiple sources agree [1] [2] [3]."
        result = validator.validate(text, valid_ids={1, 2, 3})
        assert "[1]" in result
        assert "[2]" in result
        assert "[3]" in result


class TestInvalidCitations:
    """Test that invalid citations are stripped."""

    def test_single_invalid_citation(self, validator):
        """An invalid [N] marker is removed from the text."""
        text = "The answer is 42 [5]."
        result = validator.validate(text, valid_ids={1, 2, 3})
        assert "[5]" not in result
        assert "The answer is 42" in result

    def test_mixed_valid_and_invalid(self, validator):
        """Valid citations kept, invalid ones stripped."""
        text = "From source A [1] and source X [9]."
        result = validator.validate(text, valid_ids={1, 2})
        assert "[1]" in result
        assert "[9]" not in result

    def test_high_number_invalid(self, validator):
        """A citation number higher than any valid ID is stripped."""
        text = "See reference [100] for details."
        result = validator.validate(text, valid_ids={1, 2, 3})
        assert "[100]" not in result
        assert "See reference" in result
        assert "for details." in result


class TestAllInvalid:
    """Test scenario where all citations are invalid."""

    def test_all_citations_invalid(self, validator):
        """All [N] markers removed when none are valid."""
        text = "Claim A [1] and claim B [2] and claim C [3]."
        result = validator.validate(text, valid_ids=set())
        assert "[1]" not in result
        assert "[2]" not in result
        assert "[3]" not in result
        assert "Claim A" in result
        assert "claim B" in result
        assert "claim C" in result

    def test_empty_valid_ids(self, validator):
        """Empty valid_ids set strips all citations."""
        text = "Some text [1] with [2] citations."
        result = validator.validate(text, valid_ids=set())
        assert "[1]" not in result
        assert "[2]" not in result


class TestEdgeCases:
    """Test edge cases in citation validation."""

    def test_empty_text(self, validator):
        """Empty text returns empty text."""
        result = validator.validate("", valid_ids={1, 2})
        assert result == ""

    def test_no_citations_in_text(self, validator):
        """Text without [N] markers is returned unchanged."""
        text = "This is plain text without any citations."
        result = validator.validate(text, valid_ids={1, 2})
        assert result == text

    def test_brackets_without_numbers(self, validator):
        """Non-numeric brackets like [abc] are not treated as citations."""
        text = "See [note] and [appendix] for details."
        result = validator.validate(text, valid_ids={1, 2})
        assert result == text  # Unchanged — not citation patterns

    def test_duplicate_citations(self, validator):
        """Duplicate [N] markers are handled correctly."""
        text = "Source [1] says X. Also source [1] says Y."
        result = validator.validate(text, valid_ids={1})
        assert result.count("[1]") == 2

    def test_citation_at_boundaries(self, validator):
        """Citations at start and end of text are handled."""
        text = "[1] Some text [2]"
        result = validator.validate(text, valid_ids={1, 2})
        assert result == "[1] Some text [2]"


class TestExtractCitations:
    """Test the extract_citations helper method."""

    def test_extract_multiple(self, validator):
        """Extract all citation numbers from text."""
        text = "From [1] and [3] and [2]."
        citations = validator.extract_citations(text)
        assert citations == [1, 2, 3]  # Sorted

    def test_extract_deduplicates(self, validator):
        """Duplicate citations are returned only once."""
        text = "Source [1] and again [1]."
        citations = validator.extract_citations(text)
        assert citations == [1]

    def test_extract_empty(self, validator):
        """No citations returns empty list."""
        citations = validator.extract_citations("No citations here.")
        assert citations == []

    def test_extract_ignores_non_numeric(self, validator):
        """Non-numeric brackets are ignored."""
        text = "See [note] and [1] for details."
        citations = validator.extract_citations(text)
        assert citations == [1]
