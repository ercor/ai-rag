"""Unit tests for custom evaluation metrics."""

import pytest
from src.evaluation.custom_metrics import CitationPrecision, CitationCompleteness, RetrievalHitRate


class TestCitationPrecision:
    """Tests for CitationPrecision metric."""

    def setup_method(self):
        self.metric = CitationPrecision()

    def test_name(self):
        assert self.metric.name == "citation_precision"

    def test_all_valid_citations_returns_1(self):
        """All citations reference valid chunks."""
        answer = "The policy states [1] and also [2] and [3]."
        contexts = ["Context A", "Context B", "Context C"]
        score = self.metric.compute("Q?", answer, contexts)
        assert score == 1.0

    def test_some_invalid_citations_returns_fraction(self):
        """Some citations reference invalid chunks."""
        answer = "See [1] and [5]."
        contexts = ["Context A", "Context B", "Context C"]
        score = self.metric.compute("Q?", answer, contexts)
        assert score == 0.5

    def test_all_invalid_returns_0(self):
        """All citations reference invalid chunks."""
        answer = "See [4] and [5]."
        contexts = ["Context A", "Context B", "Context C"]
        score = self.metric.compute("Q?", answer, contexts)
        assert score == 0.0

    def test_no_citations_returns_none(self):
        """No citations in the answer."""
        answer = "The answer without any citations."
        contexts = ["Context A"]
        score = self.metric.compute("Q?", answer, contexts)
        assert score is None

    def test_empty_contexts_returns_none(self):
        """No retrieved contexts."""
        answer = "See [1]."
        score = self.metric.compute("Q?", answer, [])
        assert score is None

    def test_citation_zero_is_invalid(self):
        """Citation [0] is out of valid range."""
        answer = "See [0]."
        contexts = ["Context A"]
        score = self.metric.compute("Q?", answer, contexts)
        assert score == 0.0

    def test_duplicate_citations_counted_separately(self):
        """Duplicate citations are each counted."""
        answer = "See [1] and [1] and [2]."
        contexts = ["Context A", "Context B"]
        score = self.metric.compute("Q?", answer, contexts)
        assert score == 1.0  # All 3 are valid


class TestCitationCompleteness:
    """Tests for CitationCompleteness metric."""

    def setup_method(self):
        self.metric = CitationCompleteness()

    def test_name(self):
        assert self.metric.name == "citation_completeness"

    def test_all_sentences_cited_returns_1(self):
        """All sentences have citations."""
        answer = "First claim [1]. Second claim [2]."
        contexts = ["A", "B"]
        score = self.metric.compute("Q?", answer, contexts)
        assert score == 1.0

    def test_half_sentences_cited_returns_half(self):
        """Half the sentences have citations."""
        answer = "First claim [1]. Second claim without citation."
        contexts = ["A"]
        score = self.metric.compute("Q?", answer, contexts)
        assert score == 0.5

    def test_no_sentences_cited_returns_0(self):
        """No sentences have citations."""
        answer = "First claim. Second claim."
        contexts = ["A"]
        score = self.metric.compute("Q?", answer, contexts)
        assert score == 0.0

    def test_empty_answer_returns_none(self):
        """Empty answer has no sentences."""
        score = self.metric.compute("Q?", "", ["A"])
        assert score is None


class TestRetrievalHitRate:
    """Tests for RetrievalHitRate metric."""

    def setup_method(self):
        self.metric = RetrievalHitRate()

    def test_name(self):
        assert self.metric.name == "retrieval_hit_rate"

    def test_hit_returns_1(self):
        """Gold context appears in retrieved contexts."""
        contexts = ["The per diem rate is $75 per day for meals."]
        ground_truth = "The per diem rate is $75 per day for meals."
        score = self.metric.compute("Q?", "A", contexts, ground_truth=ground_truth)
        assert score == 1.0

    def test_miss_returns_0(self):
        """No gold context in retrieved contexts."""
        contexts = ["Something completely unrelated about cats."]
        ground_truth = "The per diem rate is $75 per day for meals."
        score = self.metric.compute("Q?", "A", contexts, ground_truth=ground_truth)
        assert score == 0.0

    def test_no_ground_truth_returns_none(self):
        """Missing ground truth."""
        score = self.metric.compute("Q?", "A", ["context"])
        assert score is None

    def test_empty_contexts_returns_none(self):
        """No retrieved contexts."""
        score = self.metric.compute("Q?", "A", [], ground_truth="truth")
        assert score is None

    def test_partial_overlap_above_threshold(self):
        """More than 50% word overlap counts as hit."""
        contexts = ["The per diem rate is $75 per day for meals and some extra words"]
        ground_truth = "The per diem rate is $75 per day for meals."
        score = self.metric.compute("Q?", "A", contexts, ground_truth=ground_truth)
        assert score == 1.0
