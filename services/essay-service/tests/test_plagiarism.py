"""
test_plagiarism.py — Task 5.4's own testing checklist: positive
(near-identical essays flagged), negative (genuinely different essays not
flagged), edge (very short essays excluded below the minimum-length
floor), idempotency (re-running doesn't duplicate-flag the same pair),
and scope (only compared within the same assignment + set).
"""
import time
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayAttempt, EssayFailedJob, EssayMalpracticeEvent,
    MALPRACTICE_EVENT_TEXT_SIMILARITY, ATTEMPT_STATUS_IN_PROGRESS, ATTEMPT_STATUS_SUBMITTED,
)
from essays.tasks import check_text_similarity, _MAX_RETRIES

from .conftest import INSTITUTION_A, ADMIN_USER_ID

LONG_ESSAY = (
    "Climate change is one of the most pressing challenges facing humanity today. "
    "Rising global temperatures are driven primarily by greenhouse gas emissions "
    "from human activities such as burning fossil fuels and deforestation."
)
DIFFERENT_ESSAY = (
    "The history of jazz music traces back to the early twentieth century, "
    "emerging from a rich blend of African American musical traditions "
    "including blues, ragtime, and spirituals in New Orleans."
)


@pytest.fixture
def paper_and_set(db):
    paper = EssayPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID)
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    EssayQuestion.objects.create(set=eset, question_text="Q", llm_rubric_prompt="R", word_limit=500, time_limit_minutes=30)
    return paper, eset


@pytest.fixture
def assignment(paper_and_set):
    paper, _ = paper_and_set
    return EssayAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
    )


def _make_attempt(assignment, eset, draft_response, status=ATTEMPT_STATUS_SUBMITTED):
    # Defaults to a terminal status — check_text_similarity only ever
    # compares against "already-completed peers" (ADR 002 Decision 4);
    # an IN_PROGRESS attempt is a moving target, deliberately excluded
    # (see TestScope's own dedicated test for that exclusion below).
    return EssayAttempt.objects.create(
        assignment=assignment, student_id=uuid.uuid4(), set=eset,
        ends_at=timezone.now() + timedelta(hours=1), draft_response=draft_response, status=status,
    )


class TestPositiveMatch:
    def test_near_identical_essays_flagged(self, assignment, paper_and_set):
        _, eset = paper_and_set
        peer = _make_attempt(assignment, eset, LONG_ESSAY)
        mine = _make_attempt(assignment, eset, LONG_ESSAY)

        result = check_text_similarity.apply(args=[str(mine.id)]).result

        assert result["flagged"] == 1
        event = EssayMalpracticeEvent.objects.get(attempt=mine, event_type=MALPRACTICE_EVENT_TEXT_SIMILARITY)
        assert event.metadata["other_attempt_id"] == str(peer.id)
        assert event.metadata["similarity_ratio"] >= 0.85

        mine.refresh_from_db()
        assert mine.malpractice_flag is True
        assert "text_similarity" in mine.malpractice_reasons


class TestPartialCopyMatch:
    """Real, serious bug found via live testing (not assumed): the
    existing suite only ever tested two extremes — fully identical
    (TestPositiveMatch) and completely unrelated (TestNegativeMatch) —
    which is exactly why this bug shipped undetected. The actual common
    cheating pattern (copy most of the essay, personalize the intro/
    conclusion, or lightly paraphrase) was never covered at all.
    The original difflib.SequenceMatcher comparison (autojunk=True default)
    scored a genuinely-mostly-copied essay in the single digits — confirmed
    live: the essays below scored 1.1% with that bug. The checker now uses
    word 5-gram containment (essays/tasks.py::_shingle_containment), which
    these tests guard against regressing."""

    ORIGINAL = (
        "The industrial revolution transformed economies across Europe by shifting production from manual "
        "labor to machine-based manufacturing. Factories emerged as the dominant workplace, replacing small "
        "workshops and cottage industries. Urbanization accelerated rapidly as workers migrated from rural "
        "farms to growing industrial cities in search of employment. This period also introduced significant "
        "social challenges including poor working conditions, child labor, and stark income inequality "
        "between factory owners and laborers. Governments eventually responded with labor laws and "
        "regulations to address these issues."
    )
    # 3 of 5 sentences copied verbatim; own intro/conclusion written to
    # disguise it — the realistic, common cheating pattern.
    PARTIAL_COPY = (
        "In my opinion the industrial era changed everything for regular people. Factories emerged as the "
        "dominant workplace, replacing small workshops and cottage industries. Urbanization accelerated "
        "rapidly as workers migrated from rural farms to growing industrial cities in search of employment. "
        "This period also introduced significant social challenges including poor working conditions, child "
        "labor, and stark income inequality between factory owners and laborers. Overall it was a mixed "
        "blessing for society."
    )

    def test_partially_copied_essay_scores_a_genuinely_high_ratio(self, assignment, paper_and_set):
        # Deliberately independent of the production threshold (a separate
        # tuning decision): this test's only job is that the containment
        # score for a 3-of-5-sentences copy is high, by forcing a low
        # threshold so any correctly-computed high score crosses it.
        _, eset = paper_and_set
        peer = _make_attempt(assignment, eset, self.ORIGINAL)
        mine = _make_attempt(assignment, eset, self.PARTIAL_COPY)

        with override_settings(ESSAY_TEXT_SIMILARITY_THRESHOLD=0.5):
            result = check_text_similarity.apply(args=[str(mine.id)]).result

        assert result["flagged"] == 1
        event = EssayMalpracticeEvent.objects.get(attempt=mine, event_type=MALPRACTICE_EVENT_TEXT_SIMILARITY)
        # Measured: ~62% containment for this fixture. Lower bound 50%, not
        # the exact figure, so minor fixture wording tweaks don't break it.
        assert event.metadata["similarity_ratio"] >= 0.50


class TestDefaultThresholdBehavior:
    """Tests at the REAL production default threshold (no override), so a
    future threshold change that breaks the behavior that matters gets caught
    here, not only in the threshold's own settings comment."""

    ORIGINAL_SENTENCES = [
        "The industrial revolution transformed economies across Europe by shifting production from manual labor to machine-based manufacturing.",
        "Factories emerged as the dominant workplace, replacing small workshops and cottage industries.",
        "Urbanization accelerated rapidly as workers migrated from rural farms to growing industrial cities in search of employment.",
        "This period also introduced significant social challenges including poor working conditions, child labor, and stark income inequality between factory owners and laborers.",
        "Governments eventually responded with labor laws and regulations to address these issues.",
    ]

    def test_weak_partial_copy_two_of_five_sentences_is_flagged(self, assignment, paper_and_set):
        _, eset = paper_and_set
        _make_attempt(assignment, eset, " ".join(self.ORIGINAL_SENTENCES))
        weak_copy = (
            "My own view of this era is that it mattered a lot. "
            + " ".join(self.ORIGINAL_SENTENCES[1:3])
            + " In the end the consequences were mixed for everyone."
        )
        mine = _make_attempt(assignment, eset, weak_copy)

        result = check_text_similarity.apply(args=[str(mine.id)]).result
        assert result["flagged"] == 1

    def test_reordered_full_copy_is_flagged(self, assignment, paper_and_set):
        # The order-sensitivity blind spot of the old whole-text comparison:
        # every sentence copied, paragraphs shuffled. Must be caught now.
        _, eset = paper_and_set
        _make_attempt(assignment, eset, " ".join(self.ORIGINAL_SENTENCES))
        reordered = " ".join(reversed(self.ORIGINAL_SENTENCES))
        mine = _make_attempt(assignment, eset, reordered)

        result = check_text_similarity.apply(args=[str(mine.id)]).result
        assert result["flagged"] == 1

    def test_honest_same_topic_independent_writing_is_not_flagged(self, assignment, paper_and_set):
        _, eset = paper_and_set
        _make_attempt(assignment, eset, " ".join(self.ORIGINAL_SENTENCES))
        independent = (
            "Historians widely agree that the shift toward factory based mass production during the eighteenth "
            "and nineteenth centuries fundamentally altered how goods were manufactured and who controlled the "
            "process. Where artisans once worked alone or in small family groups, production moved into large "
            "facilities staffed by hundreds of wage workers. Cities grew quickly as rural families sought factory "
            "jobs, though housing and sanitation often failed to keep pace with the population."
        )
        mine = _make_attempt(assignment, eset, independent)

        result = check_text_similarity.apply(args=[str(mine.id)]).result
        assert result["flagged"] == 0


class TestNegativeMatch:
    def test_genuinely_different_essays_not_flagged(self, assignment, paper_and_set):
        _, eset = paper_and_set
        _make_attempt(assignment, eset, LONG_ESSAY)
        mine = _make_attempt(assignment, eset, DIFFERENT_ESSAY)

        result = check_text_similarity.apply(args=[str(mine.id)]).result

        assert result["flagged"] == 0
        mine.refresh_from_db()
        assert mine.malpractice_flag is False


class TestMinLengthFloor:
    def test_very_short_essay_excluded_from_comparison_entirely(self, assignment, paper_and_set):
        _, eset = paper_and_set
        _make_attempt(assignment, eset, LONG_ESSAY)
        mine = _make_attempt(assignment, eset, "Too short.")

        result = check_text_similarity.apply(args=[str(mine.id)]).result
        assert result["reason"] == "below_min_length"
        assert EssayMalpracticeEvent.objects.filter(attempt=mine).count() == 0

    def test_short_peer_excluded_even_if_my_essay_is_long(self, assignment, paper_and_set):
        _, eset = paper_and_set
        _make_attempt(assignment, eset, "Short peer.")
        mine = _make_attempt(assignment, eset, LONG_ESSAY)

        result = check_text_similarity.apply(args=[str(mine.id)]).result
        assert result["flagged"] == 0
        assert result["peers_compared"] == 0


class TestOnlyCompletedPeers:
    """Real gap found by this phase's own final audit: the peer query had
    no status filter at all, comparing against ANY peer with non-empty
    draft text — including a student still actively mid-exam, whose
    autosaved draft is a moving target, not the "already-completed peers"
    ADR 002 Decision 4 and CLAP's own reference implementation
    (`status='completed'`) both specify."""

    def test_in_progress_peer_excluded_from_comparison(self, assignment, paper_and_set):
        _, eset = paper_and_set
        _make_attempt(assignment, eset, LONG_ESSAY, status=ATTEMPT_STATUS_IN_PROGRESS)
        mine = _make_attempt(assignment, eset, LONG_ESSAY)  # terminal by default

        result = check_text_similarity.apply(args=[str(mine.id)]).result
        assert result["peers_compared"] == 0
        assert result["flagged"] == 0

    def test_auto_submitted_peer_is_still_compared(self, assignment, paper_and_set):
        from essays.models import ATTEMPT_STATUS_AUTO_SUBMITTED
        _, eset = paper_and_set
        _make_attempt(assignment, eset, LONG_ESSAY, status=ATTEMPT_STATUS_AUTO_SUBMITTED)
        mine = _make_attempt(assignment, eset, LONG_ESSAY)

        result = check_text_similarity.apply(args=[str(mine.id)]).result
        assert result["peers_compared"] == 1
        assert result["flagged"] == 1


class TestScope:
    def test_not_compared_against_a_different_assignment(self, paper_and_set):
        paper, eset = paper_and_set
        assignment_a = EssayAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
        )
        assignment_b = EssayAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
        )
        _make_attempt(assignment_a, eset, LONG_ESSAY)
        mine = _make_attempt(assignment_b, eset, LONG_ESSAY)

        result = check_text_similarity.apply(args=[str(mine.id)]).result
        assert result["peers_compared"] == 0

    def test_not_compared_against_a_different_set_same_assignment(self, assignment, paper_and_set):
        paper, eset_a = paper_and_set
        eset_b = EssaySet.objects.create(paper=paper, label="Set B", order=2)
        EssayQuestion.objects.create(set=eset_b, question_text="Q2", llm_rubric_prompt="R2", word_limit=500, time_limit_minutes=30)
        _make_attempt(assignment, eset_a, LONG_ESSAY)
        mine = _make_attempt(assignment, eset_b, LONG_ESSAY)

        result = check_text_similarity.apply(args=[str(mine.id)]).result
        assert result["peers_compared"] == 0


class TestIdempotency:
    def test_rerunning_does_not_duplicate_flag_the_same_pair(self, assignment, paper_and_set):
        _, eset = paper_and_set
        _make_attempt(assignment, eset, LONG_ESSAY)
        mine = _make_attempt(assignment, eset, LONG_ESSAY)

        check_text_similarity.apply(args=[str(mine.id)])
        result = check_text_similarity.apply(args=[str(mine.id)]).result

        assert result["flagged"] == 0  # already flagged, not re-flagged
        assert EssayMalpracticeEvent.objects.filter(attempt=mine, event_type=MALPRACTICE_EVENT_TEXT_SIMILARITY).count() == 1


class TestTimingAtAssumedBatchSize:
    def test_real_timing_measurement_at_a_realistic_batch_size(self, assignment, paper_and_set):
        # ADR 002 Decision 4 / Task 5.4's own testing checklist: a real
        # timing measurement at the assumed batch size, not just a
        # theoretical complexity claim. 150 peers is within the "tens to
        # low hundreds of students per batch" scope Decision 4 itself
        # names as the realistic upper bound for one assignment's cohort.
        _, eset = paper_and_set
        for _ in range(150):
            _make_attempt(assignment, eset, DIFFERENT_ESSAY + f" Variant {uuid.uuid4()}.")
        mine = _make_attempt(assignment, eset, LONG_ESSAY)

        start = time.monotonic()
        result = check_text_similarity.apply(args=[str(mine.id)]).result
        elapsed = time.monotonic() - start

        assert result["peers_compared"] == 150
        assert elapsed < 1.0  # sub-second per newly-completed student, as Decision 4 point 2 requires


class TestTransientFailureRetriesThenDlqs:
    """Real gap found by this phase's own 5th final-audit round: this
    task's decorator has always declared max_retries=3,
    default_retry_delay=10 — values that only mean anything if the body
    actually calls self.retry() — but the body never did, so a transient
    failure during the comparison loop simply propagated with no retry
    and no DLQ record, unlike every sibling task in this file. Confirms
    the fix: a failure retries up to the declared ceiling, then is
    recorded in the same EssayFailedJob DLQ via base=DeadLetteringTask.

    A second, genuinely new thing this test class had to discover along
    the way, not specific to check_text_similarity: `.apply(throw=True)`
    — and this test suite's own `CELERY_TASK_EAGER_PROPAGATES = True`
    default, which every other `.apply()` call in this suite implicitly
    inherits — makes Celery's own `on_error()` hit an `if propagate:
    raise` short-circuit that re-raises immediately and skips
    `handle_failure()` entirely, which is the ONLY thing that ever calls
    `task.on_failure()` (confirmed by reading celery.app.trace directly,
    version 5.4.0). `evaluate_essay`'s own DLQ tests never noticed this
    because that task writes to `EssayFailedJob` manually and deliberately
    does NOT use `base=DeadLetteringTask` — but any test that wants to
    observe an `on_failure()`-driven DLQ write (as this task, and in
    principle `sweep_expired_assignments`/`sweep_expired_attempts`, all
    rely on) must call `.apply(throw=False)` explicitly to get a normal
    `EagerResult` instead of a raised exception."""

    def test_transient_failure_retries_within_ceiling(self, assignment, paper_and_set):
        _, eset = paper_and_set
        attempt = _make_attempt(assignment, eset, LONG_ESSAY)
        _make_attempt(assignment, eset, LONG_ESSAY)  # a peer, so the comparison loop actually runs

        # difflib is imported locally inside the task body (not a
        # module-level essays.tasks.difflib attribute), so the real
        # difflib.SequenceMatcher itself is patched. Deliberately left at
        # this suite's own throw=True default (not throw=False like the
        # sibling ceiling test below): with retries=0 the ceiling isn't
        # reached, so Celery's own eager `.apply()` would try to
        # auto-recurse into a second attempt — and that recursive
        # `sig.apply()` call (celery/app/task.py's own `retval.sig.apply
        # (retries=retries + 1)`) does NOT forward the original `throw`
        # kwarg, silently reverting to this suite's `throw=True` default
        # regardless, which then raises past the outer call uncaught — a
        # real Celery eager-testing quirk (confirmed by reading
        # celery.app.trace/task directly, not a product bug), not
        # something to work around by chasing the recursion; asserting the
        # single, first, expected Retry directly is the correct scope for
        # this test.
        with patch("essays.tasks._text_shingles", side_effect=RuntimeError("boom")):
            with pytest.raises(Exception):
                check_text_similarity.apply(args=[str(attempt.id)], retries=0, throw=True)

        assert EssayFailedJob.objects.count() == 0

    def test_transient_failure_dlqs_once_retry_ceiling_is_reached(self, assignment, paper_and_set):
        _, eset = paper_and_set
        attempt = _make_attempt(assignment, eset, LONG_ESSAY)
        _make_attempt(assignment, eset, LONG_ESSAY)  # a peer, so the comparison loop actually runs

        # `retries=_MAX_RETRIES` simulates the delivery of the final,
        # already-retried-3-times attempt Celery would make in a real
        # worker — self.retry() sees the ceiling already reached and gives
        # up instead of scheduling another attempt, so Celery treats this
        # as a genuine failure and calls DeadLetteringTask.on_failure(),
        # recording it in the same EssayFailedJob DLQ every other task in
        # this service uses (the real gap this test closes: previously
        # nothing ever wrote a DLQ entry for this task at all).
        with patch("essays.tasks._text_shingles", side_effect=RuntimeError("boom")):
            result = check_text_similarity.apply(args=[str(attempt.id)], retries=_MAX_RETRIES, throw=False)

        assert result.state == "FAILURE"
        job = EssayFailedJob.objects.get(task_name=check_text_similarity.name)
        assert "boom" in job.error


class TestThresholdBoundaryAndReorderedPhrases:
    ORIGINAL_SENTENCES = TestDefaultThresholdBehavior.ORIGINAL_SENTENCES

    def test_score_exactly_at_threshold_is_flagged(self, assignment, paper_and_set):
        # "At or above" is the rule: a score of exactly the threshold must flag.
        _, eset = paper_and_set
        _make_attempt(assignment, eset, " ".join(self.ORIGINAL_SENTENCES))
        mine = _make_attempt(assignment, eset, "Some student wording that is long enough to be compared at all here.")
        with patch("essays.tasks._shingle_containment", return_value=0.30):
            result = check_text_similarity.apply(args=[str(mine.id)]).result
        assert result["flagged"] == 1

    def test_phrases_reordered_within_sentences_are_flagged(self, assignment, paper_and_set):
        # Smarter cheating: keep each sentence's content but reverse the order
        # of its comma-separated phrases. Measured at 66% containment.
        _, eset = paper_and_set
        _make_attempt(assignment, eset, " ".join(self.ORIGINAL_SENTENCES))
        reordered = []
        for sentence in self.ORIGINAL_SENTENCES:
            chunks = [c.strip() for c in sentence.split(",")]
            reordered.append(", ".join(reversed(chunks)))
        mine = _make_attempt(assignment, eset, " ".join(reordered))
        result = check_text_similarity.apply(args=[str(mine.id)]).result
        assert result["flagged"] == 1
