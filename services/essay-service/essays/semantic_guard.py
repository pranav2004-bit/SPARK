"""
semantic_guard.py — Task 5.2 / ADR 003 Decision 5.

New essay-service code (see that decision's own correction note — CLAP has
no `_semantic_guard` or equivalent anywhere). A second, independent layer
of ET1 defense: even if a prompt-injection attempt partially succeeds in
nudging a score, an internally-contradictory score+feedback pairing is
rejected and retried rather than accepted at face value (ADR 003 Decision
3, point 3).
"""

_HIGH_SCORE_THRESHOLD = 8   # score >= this paired with negative language is contradictory
_LOW_SCORE_THRESHOLD = 3    # score <= this paired with positive language is contradictory

_NEGATIVE_KEYWORDS = ("poor", "very weak", "weak", "incomprehensible", "off-topic", "off topic")
_POSITIVE_KEYWORDS = ("excellent", "outstanding", "exceptional", "perfect")


def is_semantically_consistent(score: int, feedback_overall: str) -> bool:
    """Returns False if the numeric score and the overall feedback text
    are self-contradictory. Only checks the extremes (very high / very
    low score against clearly opposite language) — a genuinely nuanced
    middling score (e.g. 5-7) paired with mixed feedback is not flagged,
    since that's normal, not a sign of injection or model noise."""
    text = feedback_overall.lower()

    if score >= _HIGH_SCORE_THRESHOLD and any(kw in text for kw in _NEGATIVE_KEYWORDS):
        return False
    if score <= _LOW_SCORE_THRESHOLD and any(kw in text for kw in _POSITIVE_KEYWORDS):
        return False
    return True
