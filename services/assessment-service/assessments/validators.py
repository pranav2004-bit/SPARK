from .models import MCQ_TYPE_SINGLE, MCQ_TYPE_MULTIPLE, QUESTION_CONTENT_BOTH

MIN_MCQ_OPTIONS = 2


def get_question_publish_blockers(question) -> list[str]:
    """
    Reasons this single question would block its paper from being ready to
    assign — empty list means it's ready. Mirrors practice-service's
    get_publish_blockers shape, adapted for this service's paper-level (not
    per-question) readiness model — these checks run across every question
    at assignment-creation time (get_assignment_readiness_blockers below),
    not incrementally per question the way practice-service gates each
    question individually.

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
        # function is the assignment-readiness gate and must not pass a
        # truly invalid state even if that immediate check is ever bypassed.
        blockers.append(f"{q_label}: single-choice question has more than one correct option.")
    elif question.mcq_type == MCQ_TYPE_MULTIPLE and correct_count < 2:
        blockers.append(f"{q_label}: a multiple-correct question needs more than one correct option.")

    return blockers


def get_assignment_readiness_blockers(paper) -> list[str]:
    """Reasons this paper isn't ready to be assigned to a batch — empty
    list means it's ready. Runs at assignment-creation time now instead of
    at a separate publish/ step (publish/unpublish removed from the admin
    workflow per user decision, 2026-08-14): "assign" is now the only gate,
    so everything that used to block publishing has to block here instead,
    plus the anti-cheating cross-set uniformity checks below that publish
    never enforced (previously only a non-blocking warning)."""
    blockers: list[str] = []

    sets = list(paper.sets.prefetch_related("questions__options", "sections__questions").all())
    if not sets:
        return ["This paper has no question sets — add at least one set before assigning it."]

    question_counts = {}
    mark_totals = {}
    section_counts = {}
    for qset in sets:
        questions = list(qset.questions.all())
        question_counts[qset.label] = len(questions)
        mark_totals[qset.label] = sum(q.marks for q in questions)
        section_counts[qset.label] = len(qset.sections.all())
        if not questions:
            blockers.append(f"Set '{qset.label}' has no questions.")
        for question in questions:
            blockers.extend(get_question_publish_blockers(question))
        for section in qset.sections.all():
            if len(section.questions.all()) == 0:
                blockers.append(f"Section '{section.title}' in Set '{qset.label}' has no questions.")

    # Sets are meant to be equivalent alternates for anti-cheating
    # distribution (AT7), not different-length/different-weight variants —
    # a hard requirement now that assignment is the only gate, not just the
    # publish-time warning it used to be.
    if len(set(question_counts.values())) > 1:
        blockers.append(f"Sets have unequal question counts: {question_counts}. They must match.")
    if len(set(mark_totals.values())) > 1:
        blockers.append(f"Sets have unequal total marks: {mark_totals}. They must match.")
    # Same anti-cheating rationale extended to sections (added alongside the
    # Sections feature) — only meaningful once a paper has more than one
    # set; a single-set paper has nothing to compare sections against.
    if len(sets) > 1 and len(set(section_counts.values())) > 1:
        blockers.append(f"Sets have unequal section counts: {section_counts}. They must match.")

    return blockers


def get_content_type_blocker(content_type: str, text: str, image_key: str) -> str | None:
    """Returns an error message, or None. `content_type='both'` requires
    both text and an image — not just one or the other."""
    if content_type == QUESTION_CONTENT_BOTH:
        if not (text or "").strip() or not (image_key or "").strip():
            return "content_type='both' requires both text and an image."
    return None
