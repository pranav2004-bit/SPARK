"""
Task 5.1's own testing checklist explicitly calls for "genuine OS-thread
concurrency, not sequential simulation — this exact class of test is what
found a real bug in assessment-service" (Task 12.1's audit — see that
service's own tests/test_concurrency.py, mirrored here). Every existing
race-safety test for finalize_attempts() elsewhere in this suite
(test_scoring.py's test_manual_submit_wins_race_against_sweep) simulates a
race by calling finalize_attempts() twice in a row on one thread/
connection — proves idempotency, not safety under genuine concurrent
execution.

This file uses real OS threads, each closing and reopening its own DB
connection, to fire truly concurrent finalize_attempts() calls at the
same candidate attempt — the ET4 guarantee (a client-beacon + server-sweep
double-trigger must never create two EssaySubmission rows for one
attempt).

Uses `transactional_db`, not `db`, for the same reason assessment-service's
own file does: `db` wraps the test in one transaction invisible to other
threads' own connections.
"""
import time
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection
from django.db.utils import OperationalError
from django.utils import timezone

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayAttempt, EssaySubmission,
    ATTEMPT_STATUS_IN_PROGRESS, ATTEMPT_STATUS_SUBMITTED,
)
from essays.scoring import finalize_attempts

from .conftest import INSTITUTION_A, ADMIN_USER_ID, STUDENT_USER_ID


def _request_with_sqlite_lock_retry(fn, retries=400, delay=0.05):
    """Same SQLite-vs-Postgres locking-granularity accommodation as
    assessment-service's own test_concurrency.py — see that file's
    identical helper for the full reasoning. Real Postgres (this
    service's actual production/dev DB) doesn't serialize writes to
    different rows this way; this only works around the test DB's
    coarser locking getting in the way of observing the real invariant."""
    last_exc = None
    for _ in range(retries):
        try:
            return fn()
        except OperationalError as exc:
            if "locked" not in str(exc):
                raise
            last_exc = exc
            connection.close()
            time.sleep(delay)
    raise last_exc


@pytest.fixture
def concurrency_setup(transactional_db):
    paper = EssayPaper.objects.create(institution_id=INSTITUTION_A, title="Concurrency Test Paper", created_by=ADMIN_USER_ID)
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    EssayQuestion.objects.create(set=eset, question_text="Q", llm_rubric_prompt="R", word_limit=500, time_limit_minutes=30)
    assignment = EssayAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
    )
    attempt = EssayAttempt.objects.create(
        assignment=assignment, student_id=STUDENT_USER_ID, set=eset,
        ends_at=timezone.now() + timedelta(hours=1), status=ATTEMPT_STATUS_IN_PROGRESS,
    )
    return {"attempt": attempt}


class TestConcurrentFinalize:
    """ET4 — a client-beacon-triggered manual submit racing the beat sweep
    (or an admin close/ cascade) calling finalize_attempts() on the same
    attempt at the same instant must never double-finalize it or create
    two EssaySubmission rows."""

    def test_ten_concurrent_finalize_calls_produce_exactly_one_submission(self, concurrency_setup):
        attempt = concurrency_setup["attempt"]

        def worker(_):
            try:
                return _request_with_sqlite_lock_retry(lambda: finalize_attempts(
                    EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_SUBMITTED,
                ))
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(worker, range(10)))

        # Asserting final state, not summed per-call return values — see
        # the sibling test below's own comment for why: finalize_attempts()
        # now does more than one write (status UPDATE, then submission
        # creation/repair), so a "database is locked" landing between them
        # under SQLite's whole-DB write lock can make the retry helper
        # legitimately re-run a call that already succeeded, correctly
        # returning 0 the second time. The real invariant — exactly one
        # EssaySubmission ever exists for this attempt, never zero, never
        # two — is enforced by the OneToOneField constraint regardless of
        # how many threads' repair passes raced to create it.
        assert EssaySubmission.objects.filter(attempt=attempt).count() == 1
        attempt.refresh_from_db()
        assert attempt.status == ATTEMPT_STATUS_SUBMITTED

    def test_concurrent_finalize_on_different_attempts_both_survive(self, concurrency_setup):
        # Sanity check the row-scoped guard isn't accidentally too broad:
        # concurrent finalizes of DIFFERENT attempts must both succeed,
        # not collapse into one via an over-eager lock.
        attempt1 = concurrency_setup["attempt"]
        paper = attempt1.assignment.paper
        eset2 = EssaySet.objects.create(paper=paper, label="Set B", order=2)
        EssayQuestion.objects.create(set=eset2, question_text="Q2", llm_rubric_prompt="R2", word_limit=500, time_limit_minutes=30)
        attempt2 = EssayAttempt.objects.create(
            assignment=attempt1.assignment, student_id=uuid.uuid4(), set=eset2,
            ends_at=timezone.now() + timedelta(hours=1), status=ATTEMPT_STATUS_IN_PROGRESS,
        )

        def worker(attempt):
            try:
                return _request_with_sqlite_lock_retry(lambda: finalize_attempts(
                    EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_SUBMITTED,
                ))
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(worker, [attempt1, attempt2]))

        # Asserting final state, not the raw per-call return values: on
        # SQLite's coarser whole-DB write lock (unlike Postgres's row-level
        # locking), a call can commit its UPDATE and then hit a transient
        # "database is locked" on a later statement in the same
        # finalize_attempts() invocation (the EssaySubmission bulk_create
        # or the eager-dispatched Celery tasks' own writes) — the retry
        # wrapper correctly re-runs the whole call, which then correctly
        # finds 0 remaining candidates and returns 0, an accurate
        # idempotent result, not a lost finalize. The real invariant this
        # test cares about — both attempts end up finalized exactly once,
        # neither lost nor duplicated — is the end state below, which a
        # retried-but-idempotent 0 doesn't violate.
        for attempt in (attempt1, attempt2):
            attempt.refresh_from_db()
            assert attempt.status == ATTEMPT_STATUS_SUBMITTED
        assert EssaySubmission.objects.filter(attempt__in=[attempt1, attempt2]).count() == 2
