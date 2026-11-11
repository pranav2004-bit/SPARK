def get_assignment_readiness_blockers(paper) -> list[str]:
    """Reasons this paper isn't ready to be assigned to a batch — empty
    list means it's ready. Adapted from assessment-service's
    get_assignment_readiness_blockers (same "assign is the only gate"
    philosophy — this service never had a separate publish/ step to begin
    with), simplified for essay-service's one-question-per-set shape: there
    are no per-question option/content-type checks to run, since a set
    either has its one question authored or it doesn't.

    Sets are meant to be equivalent alternates for anti-cheating
    distribution (ET7), not different-length/different-weight variants —
    the same cross-set uniformity requirement assessment-service enforces
    for question counts/marks, applied here to word limit / time limit /
    max score."""
    blockers: list[str] = []

    sets = list(paper.sets.select_related("question").all())
    if not sets:
        return ["This paper has no essay sets — add at least one set before assigning it."]

    word_limits = {}
    time_limits = {}
    max_scores = {}
    for eset in sets:
        question = getattr(eset, "question", None)
        if question is None:
            blockers.append(f"Set '{eset.label}' has no prompt authored yet.")
            continue
        word_limits[eset.label] = question.word_limit
        time_limits[eset.label] = question.time_limit_minutes
        max_scores[eset.label] = question.max_score

    if blockers:
        # A set with no question at all has nothing to compare — the
        # uniformity checks below would just be noise on top of the real
        # problem (author it first).
        return blockers

    if len(set(word_limits.values())) > 1:
        blockers.append(f"Sets have unequal word limits: {word_limits}. They must match.")
    if len(set(time_limits.values())) > 1:
        blockers.append(f"Sets have unequal time limits: {time_limits}. They must match.")
    if len(set(max_scores.values())) > 1:
        blockers.append(f"Sets have unequal max scores: {max_scores}. They must match.")

    return blockers
