"""
Per-student, per-session deterministic shuffling of question and option
DISPLAY order for assessment-taking. Never touches storage order.

Why this is safe for evaluation (the property this module must never
break): correctness is keyed entirely by QuestionOption.id (a UUID) and
QuestionOption.is_correct — scoring.py compares the student's submitted
selected_option_ids against the set of option ids where is_correct=True,
by ID, never by position/label/order (verified directly against that
file before writing this). This module only ever reorders what gets
SERIALIZED to the student, and relabels/renumbers for a clean, non-
confusing display; it never writes to the database and never changes
which option a given id refers to.

Shuffle is DETERMINISTIC, keyed by (session_id, question_id/section_id)
rather than stored as a per-session array:
  - Zero migration, zero extra storage, zero write path.
  - Naturally stable across repeated requests for the same session —
    resuming an exam, refreshing the page, or re-fetching the question
    list all show the identical order every time, with nothing to
    persist or invalidate.
  - Two different sessions get, for all practical purposes, independent
    permutations — the seed is derived from each session's own random
    UUID, so the chance two different students' sessions land on the
    identical permutation across a whole exam's worth of questions and
    options is astronomically small. That is what "no two students see
    the same order" means in practice for any shuffle-based scheme —
    storing and explicitly deduplicating past permutations would be
    real over-engineering for a guarantee no system can make absolute
    anyway, since two independently-random permutations can always
    coincide with some tiny probability regardless of mechanism.
"""
import hashlib
import random
import string


def _seeded_rng(*parts):
    key = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big")
    return random.Random(seed)


def shuffle_questions_within_sections(questions, session_id):
    """`questions` must already be in canonical admin order (section__order,
    question_number — see StudentSessionQuestionsView's own query). Groups
    by section, preserving section order exactly as the admin defined it
    (sections are a deliberate, intentional grouping/sequence — e.g.
    "Section 1: Quant" before "Section 2: Verbal" — not something to
    randomize away), and shuffles only the questions WITHIN each section.

    Returns a new list; never mutates the input list or the DB."""
    if not questions:
        return []

    sections = {}
    section_order = []
    for q in questions:
        sid = q.section_id
        if sid not in sections:
            sections[sid] = []
            section_order.append(sid)
        sections[sid].append(q)

    result = []
    for sid in section_order:
        bucket = sections[sid]
        if len(bucket) > 1:
            rng = _seeded_rng("question-shuffle", session_id, sid)
            bucket = list(bucket)
            rng.shuffle(bucket)
        result.extend(bucket)
    return result


def shuffle_options(options, session_id, question_id):
    """Returns a NEW list of the same QuestionOption instances, shuffled,
    each annotated with transient (never-saved) `display_label` /
    `display_order` attributes reflecting its NEW position — so the
    student always sees a clean, sequential A/B/C/D... regardless of each
    option's original admin-authored label/order, with the original
    position not recoverable from the response.

    Labels only go up to Z (26 options) before falling back to plain
    numbers — no real exam question has anywhere near that many choices,
    but it degrades instead of raising if one somehow did."""
    if len(options) < 2:
        shuffled = list(options)
    else:
        rng = _seeded_rng("option-shuffle", session_id, question_id)
        shuffled = list(options)
        rng.shuffle(shuffled)

    for i, opt in enumerate(shuffled):
        opt.display_label = string.ascii_uppercase[i] if i < 26 else str(i + 1)
        opt.display_order = i

    return shuffled
