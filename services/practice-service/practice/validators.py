from .models import QUESTION_TYPE_MCQ, QUESTION_TYPE_FIB


def get_publish_blockers(question) -> list[str]:
    """
    Reasons this question cannot be published — empty list means it's ready.

    Checked against real DB state (via `question.options.all()`, not a
    request payload), so this is safe to call after ANY mutation that could
    affect publishability — editing the question itself, or creating/
    editing/deleting one of its options — not just the moment `is_published`
    is first flipped to True. A published question must stay valid; if an
    edit would leave it invalid, the caller should reject that edit rather
    than let a broken question stay visible to students.

    Rules (admin-defined, mirrors the question-authoring UI):
      1. Question body must have real content (text and/or image).
      2. MCQ: at least two options (a single option isn't a real choice),
         none left blank, and at least one marked correct. FIB: a
         non-empty answer.
      3. An explanation (text and/or image) must be present.
    """
    blockers: list[str] = []
    MIN_MCQ_OPTIONS = 2

    has_question_content = bool(question.question_text.strip()) or bool(question.question_image_key)
    if not has_question_content:
        blockers.append("Question must have text or an image.")

    if question.question_type == QUESTION_TYPE_MCQ:
        options = list(question.options.all())
        if len(options) < MIN_MCQ_OPTIONS:
            blockers.append(f"At least {MIN_MCQ_OPTIONS} options are required.")
        elif any(not o.text.strip() for o in options):
            blockers.append("All options must have text filled in.")
        if not any(o.is_correct for o in options):
            blockers.append("At least one option must be marked as the correct answer.")
    elif question.question_type == QUESTION_TYPE_FIB:
        if not question.fib_answer.strip():
            blockers.append("A fill-in-the-blank answer is required.")

    has_explanation = bool(question.explanation_text.strip()) or bool(question.explanation_image_key)
    if not has_explanation:
        blockers.append("An explanation (text or image) is required.")

    return blockers
