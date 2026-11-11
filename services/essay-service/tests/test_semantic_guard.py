"""
test_semantic_guard.py — ADR 003 Decision 3 point 3 / Decision 5: the
second, independent layer of the prompt-injection defense (see
test_prompts.py's own module docstring for the first layer and how the
two connect) — even if an injection attempt partially succeeds at
nudging a score, an internally-contradictory result is caught here, not
accepted at face value. Part of Task 15.3's own formalized regression
suite alongside test_prompts.py, for the same reason: it already runs on
every change as part of the normal suite, no separate mechanism needed.
"""
from essays.semantic_guard import is_semantically_consistent


class TestSemanticGuard:
    def test_high_score_with_negative_feedback_is_contradictory(self):
        assert is_semantically_consistent(9, "This is a very weak and poor response overall.") is False

    def test_low_score_with_positive_feedback_is_contradictory(self):
        assert is_semantically_consistent(2, "An excellent and outstanding piece of writing.") is False

    def test_high_score_with_positive_feedback_is_consistent(self):
        assert is_semantically_consistent(9, "An outstanding, well-argued response.") is True

    def test_low_score_with_negative_feedback_is_consistent(self):
        assert is_semantically_consistent(2, "A very weak response lacking structure.") is True

    def test_middling_score_with_mixed_feedback_is_not_flagged(self):
        # Only the extremes are checked — a genuinely nuanced middling
        # score paired with mixed language is normal, not a sign of
        # injection or model noise.
        assert is_semantically_consistent(5, "Some good points but poor structure overall.") is True

    def test_case_insensitive_keyword_matching(self):
        assert is_semantically_consistent(10, "VERY WEAK response, POOR execution.") is False

    def test_score_at_high_threshold_boundary(self):
        assert is_semantically_consistent(8, "A poor and incomprehensible attempt.") is False

    def test_score_at_low_threshold_boundary(self):
        assert is_semantically_consistent(3, "A perfect and outstanding essay.") is False

    def test_score_just_below_high_threshold_not_checked(self):
        assert is_semantically_consistent(7, "A poor and weak response.") is True

    def test_score_just_above_low_threshold_not_checked(self):
        assert is_semantically_consistent(4, "An excellent response.") is True

    def test_neutral_feedback_never_flagged_at_any_score(self):
        assert is_semantically_consistent(10, "The essay addresses the prompt directly.") is True
        assert is_semantically_consistent(0, "The essay addresses the prompt directly.") is True
