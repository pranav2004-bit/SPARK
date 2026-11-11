"""
load_test.py — Task 18.1's load test tool.

Stdlib-only (urllib + concurrent.futures), directly mirroring
assessment-service's own load_test.py (Task 14.1) — same tool shape, same
"talk to the service container directly, not through nginx" reasoning
(see that file's own module docstring for the full nginx-per-IP-throttle
finding this reuses verbatim), same roster-seeding workaround for the
cross-service roster-fetch dependency. Adapted for essay-service's own
traffic shape: exactly one question per attempt, so there is no
per-question answer loop — instead, a debounced autosave cadence against
one growing draft field, then a single final submit per student. Adds two
scenarios assessment-service has no equivalent of at all: LLM-evaluation
queue drain time after the submit rush (Non-Negotiable Constraint §5 — a
student's own experience never blocks on this, but ADR 004 Section 3
still needs a real number), and cross-service latency during the spike
(ET13).

Scale note (same environment as assessment-service's own Task 14.1 run,
now with 24 containers instead of ~19): this dev environment's Docker
Desktop VM has 2 CPU cores total, shared across the whole platform. See
docs/essay-service-load-test-results.md for the actual numbers and the
honest comparison against assessment-service's own prior run.
"""
import json
import statistics
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import ProtectedError
from django.utils import timezone

# Dedicated load-test institution/admin IDs — distinct from
# assessment-service's own Task 14.1 constants (infra/scripts/
# seed_load_test_roster.py) so the two services' load tests never collide,
# and distinct from essay-service's own dev seed data / devadmin-devstudent
# accounts, matching every other test-data-isolation decision this build
# has made (Phase 16/17's own hygiene discipline).
ESSAY_LOAD_TEST_INSTITUTION_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
ESSAY_LOAD_TEST_ADMIN_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")

# Fixed batch_id + deterministic per-index student user_ids — same reasoning
# as assessment-service's own tool: AdminEssayAssignmentDashboardView and
# friends need a real, resolvable roster (core/user_service_client.py), not
# a synthetic batch_id that 502s the roster fetch. See
# infra/scripts/seed_essay_load_test_roster.py for the matching one-time
# setup step this tool's student_user_id(i) must agree with.
ESSAY_LOAD_TEST_BATCH_ID = uuid.UUID("dddddddd-eeee-dddd-eeee-dddddddddddd")
_ESSAY_STUDENT_UUID_NAMESPACE = uuid.UUID("eeeeeeee-ffff-eeee-ffff-eeeeeeeeeeee")


def student_user_id(i):
    return uuid.uuid5(_ESSAY_STUDENT_UUID_NAMESPACE, f"spark-essay-load-test-student-{i}")


GATEWAY_BASE = "http://essay-service:8000"
# Deliberately NOT going through nginx — identical finding and identical
# reasoning to assessment-service's own load_test.py (see that file's
# docstring): nginx's rate zones are keyed on $binary_remote_addr, and
# every request this tool issues shares this one container's IP, so at
# any real concurrency it would self-trigger 429s a real multi-student
# exam (N students, N real client IPs) would never produce. Skipping
# nginx doesn't change what's measured — Django, JWT auth, DB, Redis, and
# the cross-service roster call are all still exercised for real.

# Other 7 services' health endpoints — ET13's own "does the spike degrade
# unrelated services" question, checked directly rather than inferred.
OTHER_SERVICE_HEALTH_URLS = {
    "auth-service": "http://auth-service:8000/api/auth/health/",
    "user-service": "http://user-service:8000/api/users/health/",
    "assessment-service": "http://assessment-service:8000/api/assessments/health/",
    "resource-service": "http://resource-service:8000/api/resources/health/",
    "practice-service": "http://practice-service:8000/api/practice/health/",
    "notification-service": "http://notification-service:8000/api/notifications/health/",
    "analytics-service": "http://analytics-service:8000/api/analytics/health/",
}


def _token_for(user_id, role, student_id=None):
    from rest_framework_simplejwt.tokens import RefreshToken

    class FakeUser:
        pk = user_id
        id = user_id

    refresh = RefreshToken.for_user(FakeUser())
    refresh["role"] = role
    refresh["email"] = f"essayloadtest-{role}@test.com"
    refresh["institution_id"] = str(ESSAY_LOAD_TEST_INSTITUTION_ID)
    refresh["student_id"] = str(student_id) if student_id else None
    refresh["is_profile_completed"] = True
    return str(refresh.access_token)


def _request(method, path, token=None, body=None, timeout=15, base=GATEWAY_BASE):
    url = f"{base}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        exc.read()
        status = exc.code
    except Exception:
        status = -1  # network-level failure: timeout, connection refused, DNS, etc.
    elapsed = time.monotonic() - start
    return status, elapsed


def _stats(latencies, statuses):
    ok = [l for l, s in zip(latencies, statuses) if 200 <= s < 300]
    errors = [s for s in statuses if not (200 <= s < 300)]
    # -1 means _request's own except-clause caught a timeout/connection-
    # refused/DNS failure, not a real HTTP response — surfaced as its own
    # bucket (not lumped into "error 500" etc.) so root-cause analysis can
    # actually tell "the server rejected this" from "this never got a
    # response at all," the exact distinction Task 18.1's own root-cause
    # requirement needs.
    status_breakdown = {}
    for s in statuses:
        key = "timeout_or_connection_failure" if s == -1 else str(s)
        status_breakdown[key] = status_breakdown.get(key, 0) + 1
    result = {
        "count": len(statuses),
        "success": len(ok),
        "errors": len(errors),
        "error_rate_pct": round(len(errors) / len(statuses) * 100, 2) if statuses else 0.0,
        "status_breakdown": status_breakdown,
    }
    if ok:
        s = sorted(ok)

        def pct(p):
            idx = min(int(len(s) * p), len(s) - 1)
            return round(s[idx] * 1000, 1)  # ms

        result.update({
            "p50_ms": pct(0.50), "p95_ms": pct(0.95), "p99_ms": pct(0.99),
            "max_ms": round(s[-1] * 1000, 1),
            "mean_ms": round(statistics.mean(s) * 1000, 1),
        })
    return result


class Command(BaseCommand):
    help = (
        "Task 18.1's load test: mass attempt-start, steady-state draft autosave, "
        "end-of-exam submit rush, concurrent admin traffic, LLM-evaluation queue "
        "drain time, and cross-service latency (ET13) — all through the real "
        "essay-service container. Prints p50/p95/p99 latency and error rate per scenario."
    )

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, default=200, help="Concurrent virtual students for this run")
        parser.add_argument("--admin-requests", type=int, default=20, help="Concurrent admin dashboard/overview requests fired during the autosave phase")
        parser.add_argument("--autosave-rounds", type=int, default=3, help="How many times each student autosaves during the steady-state phase")
        parser.add_argument("--workers", type=int, default=100, help="Thread pool size for issuing concurrent requests")
        parser.add_argument("--keep-data", action="store_true", help="Don't delete the load-test paper/assignment/attempts afterward (for manual DB inspection)")

    def handle(self, *args, **options):
        n = options["students"]
        admin_n = options["admin_requests"]
        rounds = options["autosave_rounds"]
        workers = options["workers"]

        self.stdout.write(self.style.NOTICE(f"=== Task 18.1 load test: {n} students, {workers} worker threads ==="))

        assignment, question, students = self._setup(n)
        self.stdout.write(f"Setup complete: assignment={assignment.id}, question word_limit={question.word_limit}, {n} students allocated.")

        other_services_baseline = self._check_other_services()
        self._print("Other-service latency BEFORE the spike (ET13 baseline)", other_services_baseline)

        try:
            results = {}
            results["attempt_start"] = self._scenario_attempt_start(assignment, students, workers)
            self._print("Mass attempt-start", results["attempt_start"])

            self._reconnect()
            attempts_by_student = self._collect_attempts(assignment, students)

            results["autosave"], results["admin_concurrent"], results["other_services_during_spike"] = \
                self._scenario_autosave_with_admin_and_cross_service_traffic(
                    attempts_by_student, rounds, admin_n, assignment, workers,
                )
            self._print(f"Steady-state autosave ({rounds} rounds/student)", results["autosave"])
            self._print("Concurrent admin traffic (during autosave)", results["admin_concurrent"])
            self._print("Other-service latency DURING the spike (ET13)", results["other_services_during_spike"])

            results["submit"] = self._scenario_submit_rush(attempts_by_student, workers)
            self._print("End-of-exam submit rush", results["submit"])

            self._reconnect()
            results["llm_queue_drain"] = self._measure_llm_queue_drain(assignment, n)
            self._print("LLM-evaluation queue drain", results["llm_queue_drain"])

            self._reconnect()
            self._verify_data_integrity(assignment, n)

            self.stdout.write(self.style.SUCCESS("\n=== load test complete ==="))
            self.stdout.write(json.dumps(results, indent=2, default=str))
        finally:
            self._reconnect()
            if not options["keep_data"]:
                self._teardown(assignment)
                self.stdout.write("Test data cleaned up.")
            else:
                self.stdout.write(self.style.WARNING(f"--keep-data set: assignment {assignment.id} left in place."))

    def _reconnect(self):
        """Same real finding as assessment-service's own load_test.py
        (Task 14.1): this command's main-thread ORM connection sits idle
        for the full duration of each concurrent scenario, long enough at
        higher student counts to exceed the DB's own idle-connection
        timeout. Forcing a fresh connection before any post-scenario
        query avoids OperationalError('server closed the connection
        unexpectedly') — not a service bug, a load-test-tool artifact."""
        from django.db import connection
        connection.close()

    # ── Setup ────────────────────────────────────────────────────────────

    def _setup(self, n):
        from essays.models import (
            EssayPaper, EssaySet, EssayQuestion, EssayAssignment,
            EssayStudentSetAllocation, ASSIGNMENT_STATUS_LIVE,
        )

        paper = EssayPaper.objects.create(
            institution_id=ESSAY_LOAD_TEST_INSTITUTION_ID, title=f"Load Test Paper {uuid.uuid4().hex[:8]}",
            created_by=ESSAY_LOAD_TEST_ADMIN_ID,
        )
        eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
        question = EssayQuestion.objects.create(
            set=eset, question_text="Load test prompt: describe a real system you have worked on.",
            llm_rubric_prompt="Score coherence and structure out of 10.",
            word_limit=500, time_limit_minutes=60, max_score=10,
        )

        assignment = EssayAssignment.objects.create(
            paper=paper, batch_id=ESSAY_LOAD_TEST_BATCH_ID, institution_id=ESSAY_LOAD_TEST_INSTITUTION_ID,
            global_expire_time=timezone.now() + timedelta(hours=3),
            created_by=ESSAY_LOAD_TEST_ADMIN_ID, status=ASSIGNMENT_STATUS_LIVE,
        )

        # EssayStudentSetAllocation rows created directly via the ORM,
        # exactly matching what a real roster-based allocation would have
        # produced — but student_user_id(i) is deterministic and must
        # match real Student rows already seeded in user-service (see
        # infra/scripts/seed_essay_load_test_roster.py), or the roster-
        # fetch-dependent admin endpoints (dashboard/results) will 502,
        # the same real gap assessment-service's own Task 14.1 found first.
        student_ids = [student_user_id(i) for i in range(n)]
        EssayStudentSetAllocation.objects.bulk_create([
            EssayStudentSetAllocation(assignment=assignment, student_id=sid, set=eset)
            for sid in student_ids
        ], batch_size=500)

        students = [
            {"id": sid, "token": _token_for(sid, "student", student_id=f"ESSAYLOADTEST-{i:04d}")}
            for i, sid in enumerate(student_ids)
        ]
        return assignment, question, students

    def _teardown(self, assignment):
        from essays.models import (
            EssayPaper, EssayAttempt, EssaySubmission, EssayScore, EssayLLMTrace,
            EssaySubmissionEvent, EssayStudentSetAllocation, EssayFailedJob,
            EssayMalpracticeEvent,
        )
        paper = assignment.paper
        # Bottom-up: every PROTECT FK in this chain (EssaySubmission.attempt,
        # EssayScore.submission, EssayLLMTrace.submission,
        # EssayMalpracticeEvent.attempt) must be cleared before the row it
        # protects, matching Task 13.3-style cleanup ordering already
        # established for assessment-service. EssayMalpracticeEvent was a
        # real gap found live in this task's own validation run: check_text_
        # similarity (dispatched alongside evaluate_essay on every submit)
        # writes text_similarity rows here, and this teardown's first draft
        # never accounted for them — ProtectedError on EssayAttempt.delete().
        submission_ids = list(EssaySubmission.objects.filter(attempt__assignment=assignment).values_list("id", flat=True))
        EssayFailedJob.objects.filter(task_name="evaluate_essay", args__0__in=[str(s) for s in submission_ids]).delete()
        EssayLLMTrace.objects.filter(submission_id__in=submission_ids).delete()
        EssayScore.objects.filter(submission_id__in=submission_ids).delete()
        EssayMalpracticeEvent.objects.filter(attempt__assignment=assignment).delete()

        # Real race found live at 200-student scale (not reproducible below
        # ~50): _measure_llm_queue_drain's "drained" check (queue_depth==0,
        # no PENDING/LLM_PROCESSING submissions left) can be satisfied by a
        # submission that already flipped to its terminal status while its
        # OWN EssaySubmissionEvent row (written by _transition_submission_
        # status as a separate statement, not the same transaction) is
        # still landing. A single delete pass here can lose that race.
        # Retried, not just delayed, since the exact settle time isn't
        # knowable in advance and a fixed sleep would either be wasted at
        # small scale or still insufficient at larger scale.
        for attempt_n in range(3):
            EssaySubmissionEvent.objects.filter(submission_id__in=submission_ids).delete()
            try:
                EssaySubmission.objects.filter(id__in=submission_ids).delete()
                break
            except ProtectedError:
                if attempt_n == 2:
                    raise
                time.sleep(1)

        EssayAttempt.objects.filter(assignment=assignment).delete()
        EssayStudentSetAllocation.objects.filter(assignment=assignment).delete()
        assignment.delete()
        paper.delete()  # cascades to sets/questions

    # ── Scenarios ────────────────────────────────────────────────────────

    def _scenario_attempt_start(self, assignment, students, workers):
        def worker(student):
            return _request(
                "POST", f"/api/essay/student/assignments/{assignment.id}/start-attempt/",
                token=student["token"],
            )
        return self._run_concurrent(worker, students, workers)

    def _collect_attempts(self, assignment, students):
        from essays.models import EssayAttempt
        attempts = {
            a.student_id: a.id for a in
            EssayAttempt.objects.filter(assignment=assignment).only("id", "student_id")
        }
        return [(student, attempts[student["id"]]) for student in students if student["id"] in attempts]

    def _scenario_autosave_with_admin_and_cross_service_traffic(self, attempts_by_student, rounds, admin_n, assignment, workers):
        admin_token = _token_for(ESSAY_LOAD_TEST_ADMIN_ID, "admin")
        admin_paths = [
            f"/api/essay/admin/assignments/{assignment.id}/dashboard/",
            "/api/essay/admin/submissions/overview/",
        ]

        autosave_jobs = []
        for student, attempt_id in attempts_by_student:
            for r in range(rounds):
                # Growing draft, matching a real student writing
                # progressively — not a fixed/replaced value each round.
                draft = f"Round {r+1} of {rounds}. " * (20 * (r + 1))
                autosave_jobs.append((student["token"], attempt_id, draft))

        admin_jobs = [admin_paths[i % len(admin_paths)] for i in range(admin_n)]
        other_service_jobs = list(OTHER_SERVICE_HEALTH_URLS.items()) * max(1, admin_n // len(OTHER_SERVICE_HEALTH_URLS))

        autosave_results, admin_results, other_results = [], [], []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            autosave_futures = {
                pool.submit(
                    _request, "PUT", f"/api/essay/student/attempts/{attempt_id}/autosave/",
                    token, {"draft_response": draft},
                ): None
                for token, attempt_id, draft in autosave_jobs
            }
            admin_futures = {
                pool.submit(_request, "GET", path, admin_token): None
                for path in admin_jobs
            }
            other_futures = {
                pool.submit(_request, "GET", "", None, None, 10, base): name
                for name, base in other_service_jobs
            }
            all_futures = list(autosave_futures) + list(admin_futures) + list(other_futures)
            for fut in as_completed(all_futures):
                status, elapsed = fut.result()
                if fut in autosave_futures:
                    autosave_results.append((status, elapsed))
                elif fut in admin_futures:
                    admin_results.append((status, elapsed))
                else:
                    other_results.append((other_futures[fut], status, elapsed))

        autosave_statuses, autosave_latencies = zip(*autosave_results) if autosave_results else ([], [])
        admin_statuses, admin_latencies = zip(*admin_results) if admin_results else ([], [])

        other_by_service = {}
        for name, status, elapsed in other_results:
            other_by_service.setdefault(name, {"statuses": [], "latencies": []})
            other_by_service[name]["statuses"].append(status)
            other_by_service[name]["latencies"].append(elapsed)
        other_stats = {name: _stats(v["latencies"], v["statuses"]) for name, v in other_by_service.items()}

        return (
            _stats(list(autosave_latencies), list(autosave_statuses)),
            _stats(list(admin_latencies), list(admin_statuses)),
            other_stats,
        )

    def _scenario_submit_rush(self, attempts_by_student, workers):
        def worker(pair):
            student, attempt_id = pair
            return _request("POST", f"/api/essay/student/attempts/{attempt_id}/submit/", token=student["token"])
        return self._run_concurrent(worker, attempts_by_student, workers)

    def _run_concurrent(self, fn, items, workers):
        statuses, latencies = [], []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(fn, item) for item in items]
            for fut in as_completed(futures):
                status, elapsed = fut.result()
                statuses.append(status)
                latencies.append(elapsed)
        return _stats(latencies, statuses)

    def _check_other_services(self):
        results = {}
        for name, url in OTHER_SERVICE_HEALTH_URLS.items():
            status, elapsed = _request("GET", "", None, None, 10, base=url)
            results[name] = {"status": status, "latency_ms": round(elapsed * 1000, 1)}
        return results

    # ── LLM-evaluation queue drain (Non-Negotiable Constraint §5 / ADR 004 §3) ──

    def _measure_llm_queue_drain(self, assignment, n, timeout_seconds=120, poll_interval=2):
        """Polls Redis's real queue depth and Postgres's real submission
        status counts until the dispatched evaluate_essay/check_text_similarity
        backlog drains or timeout_seconds elapses — never assumed instant.
        Honest caveat, stated here and in the results doc: this dev
        platform has no OPENAI_API_KEYS configured (ADR 004 Section 3's own
        disclosed, still-open item), so every evaluate_essay dispatched
        here hits LLMPermanentError immediately (no real network call, no
        retry) rather than a genuine multi-second LLM round trip — this
        measures queue/DB throughput under load, not real LLM latency,
        which cannot be measured on this platform until a real tier is
        provisioned."""
        import redis
        from django.conf import settings
        from essays.models import EssaySubmission

        r = redis.from_url(settings.REDIS_URL)
        start = time.monotonic()
        samples = []
        while time.monotonic() - start < timeout_seconds:
            depth = r.llen(settings.CELERY_TASK_DEFAULT_QUEUE)
            pending = EssaySubmission.objects.filter(
                attempt__assignment=assignment, status__in=["PENDING", "LLM_PROCESSING"],
            ).count()
            samples.append({"t": round(time.monotonic() - start, 1), "queue_depth": depth, "pending_submissions": pending})
            if depth == 0 and pending == 0:
                break
            time.sleep(poll_interval)
        drained = samples[-1]["queue_depth"] == 0 and samples[-1]["pending_submissions"] == 0
        return {
            "drained": drained,
            "drain_time_seconds": samples[-1]["t"] if drained else None,
            "timed_out": not drained,
            "sample_count": len(samples),
            "first_sample": samples[0] if samples else None,
            "last_sample": samples[-1] if samples else None,
        }

    # ── Verification ─────────────────────────────────────────────────────

    def _verify_data_integrity(self, assignment, n):
        from essays.models import EssayAttempt, EssaySubmission, ATTEMPT_STATUS_SUBMITTED
        attempts = EssayAttempt.objects.filter(assignment=assignment).count()
        submitted = EssayAttempt.objects.filter(assignment=assignment, status=ATTEMPT_STATUS_SUBMITTED).count()
        submissions = EssaySubmission.objects.filter(attempt__assignment=assignment).count()
        self.stdout.write(
            f"Data integrity: {attempts} attempts created, {submitted} submitted, "
            f"{submissions} EssaySubmission rows (expect submissions == submitted, both <= {n})."
        )
        if submissions != submitted:
            self.stdout.write(self.style.ERROR(
                f"MISMATCH: {submissions} submissions vs {submitted} submitted attempts — investigate before trusting these numbers."
            ))
        # No duplicate EssaySubmission per attempt — the actual ET4-shaped
        # invariant (OneToOneField already enforces this at the DB level;
        # this is a live confirmation, not just trusting the constraint).
        from django.db.models import Count
        dupes = (
            EssaySubmission.objects.filter(attempt__assignment=assignment)
            .values("attempt_id").annotate(c=Count("id")).filter(c__gt=1)
        )
        if dupes.exists():
            self.stdout.write(self.style.ERROR(f"DUPLICATE EssaySubmission rows found for {dupes.count()} attempt(s)!"))
        else:
            self.stdout.write(self.style.SUCCESS("No duplicate EssaySubmission rows — held under real concurrent load."))

    def _print(self, label, stats):
        self.stdout.write(f"\n--- {label} ---")
        self.stdout.write(json.dumps(stats, indent=2, default=str))
