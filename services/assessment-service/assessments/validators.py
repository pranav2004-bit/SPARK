from .models import MCQ_TYPE_SINGLE, QUESTION_CONTENT_BOTH

MIN_MCQ_OPTIONS = 2


def get_question_publish_blockers(question) -> list[str]:
    """
    Reasons this single question would block its paper from publishing —
    empty list means it's ready. Mirrors practice-service's
    get_publish_blockers shape, adapted for this service's paper-level (not
    per-question) publish model — a QuestionPaper has no is_published field
    on Question/QuestionSet, so these checks run across every question at
    paper-publish time (Task 2.2's publish endpoint), not incrementally per
    question the way practice-service gates each question individually.

    Checked against real DB state (question.options.all()), not a request
    payload — safe to call after any mutation.
    """
    blockers: list[str] = []
    q_label = f"Q{question.question_number} ({question.set.label})"

    has_content = bool(question.question_text.strip()) or bool(question.question_image_key)
    if not has_content:
        blockers.append(f"{q_label}: must have text or an image.")

    options = list(question.options.all())
    if len(options) < MIN_MCQ_OPTIONS:
        blockers.append(f"{q_label}: at least {MIN_MCQ_OPTIONS} options are required.")
    else:
        empty = [o for o in options if not o.text.strip() and not o.image_key]
        if empty:
            blockers.append(f"{q_label}: all options must have text or an image.")
    correct_count = sum(1 for o in options if o.is_correct)
    if correct_count == 0:
        blockers.append(f"{q_label}: at least one option must be marked correct.")
    elif question.mcq_type == MCQ_TYPE_SINGLE and correct_count > 1:
        # Shouldn't normally be reachable — the option views reject a second
        # correct answer on a single-choice question immediately (see
        # views.py) — but checked here too as defense in depth, since this
        # function is the paper-publish gate and must not pass a truly
        # invalid state even if that immediate check is ever bypassed.
        blockers.append(f"{q_label}: single-choice question has more than one correct option.")

    return blockers


def get_content_type_blocker(content_type: str, text: str, image_key: str) -> str | None:
    """Returns an error message, or None. `content_type='both'` requires
    both text and an image — not just one or the other."""
    if content_type == QUESTION_CONTENT_BOTH:
        if not (text or "").strip() or not (image_key or "").strip():
            return "content_type='both' requires both text and an image."
    return None
