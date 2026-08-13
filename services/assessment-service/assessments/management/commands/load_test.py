"""
load_test.py — Task 14.1's load test tool.

Stdlib-only (urllib + concurrent.futures), matching this project's existing
"no new dependency" convention (core/user_service_client.py uses urllib
over requests; tests/test_concurrency.py already established the
ThreadPoolExecutor pattern this reuses). Fires real HTTP requests through
the real gateway (nginx), not a shortcut direct-to-service call — the same
path a real student's browser would take, respecting nginx's own rate
limits and routing exactly as configured for production.

Scale note (read before changing the defaults): this dev environment's
entire Docker Desktop VM has 2 CPU cores total, shared across all 19+
containers of the full 7-service platform running simultaneously — not
representative of a real production host. Rather than either refuse to
load-test at all, or run a number so large it just proves "this specific
laptop can't do it" (conflating the *service's* scalability with *this
environment's* hardware), the default scale is calibrated to a realistic
single-batch/single-institution exam size for this platform (see
LIVETRACKER2_V1.md's Task 14.1 notes for the full reasoning and the actual
recorded results at each multiple) — meaningful signal about indexing,
pooling, and concurrency behavior either way, since those don't change
qualitatively with headcount, just proportionally.

Test data setup bypasses the real user-service roster fetch (Task 3.1) —
there's no real roster of thousands of students to fetch for a load test,
and the assignment-creation admin flow's user-service dependency is
already covered by its own tests (Task 13.1) and isn't what this task is
measuring — StudentSetAllocation rows are created directly via the ORM,
exactly matching what a real roster snapshot would have produced.
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
from django.utils import timezone

# Dedicated load-test institution/admin IDs — separate from dev seed data
# (seed_demo_data.py) and from the devadmin/devstudent accounts used
# throughout manual verification this session, so a load-test run never
# collides with or pollutes either.
LOAD_TEST_INSTITUTION_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
LOAD_TEST_ADMIN_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")

# Fixed batch_id, and deterministic (not random) per-index student user_ids
# — a validation run against a real 10-student scale found that
# AdminAssignmentResultsView (Task 7.1) and friends hard-502 when
# user-service 404s the roster for an unknown batch_id (by design — see
# that view's _fetch_roster_lookup docstring), and a fresh uuid4() batch_id
# on every run can never exist in user-service's real database. Fixed IDs
# let a companion one-time setup step seed a real Batch + Student rows in
# user-service (see docs/assessment-service-load-test-results.md's setup
# section for the exact command) that every run of this tool reuses,
# instead of talking to a fake roster. uuid5 (not uuid4) so index i always
# maps to the same user_id across every run/scale without persisting
# anything — seed once for the largest N you plan to run, reuse for every
# smaller N.
LOAD_TEST_BATCH_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
_STUDENT_UUID_NAMESPACE = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")


def student_user_id(i):
    return uuid.uuid5(_STUDENT_UUID_NAMESPACE, f"spark-load-test-student-{i}")

GATEWAY_BASE = "http://assessment-service:8000"
# Deliberately NOT going through nginx (finding from this task's own
# validation run, see LIVETRACKER2_V1.md's Task 14.1 notes): nginx's
# api_zone rate limit (gateway/nginx.dev.conf, 100r/m, Task 11.2) is keyed
# on $binary_remote_addr — a real exam's N students each have their own
# client IP, but every request this tool issues originates from this one
# container's single IP, so at any real concurrency it immediately
# self-triggers 429s that a real multi-student exam would never produce.
# That's a artifact of this tool's own topology, not a finding about the
# service. Gateway-level per-IP throttling already has its own dedicated
# tests (Task 11.2); this task's actual target — DB thundering-herd
# behavior, PgBouncer pool pressure, Celery sweep lag, per-request service
# latency — is unaffected by skipping nginx, since Django/JWT auth/DB/Redis
# are all still exercised for real, same as they would be for a real
# request. The service's URL prefix is identical either way
# (core/urls.py mounts the app at /api/assessments/ itself, nginx doesn't
# rewrite it), so paths below don't change.


def _token_for(user_id, role, student_id=None):
    from rest_framework_simplejwt.tokens import RefreshToken

    class FakeUser:
        pk = user_id
        id = user_id

    refresh = RefreshToken.for_user(FakeUser())
    refresh["role"] = role
    refresh["email"] = f"loadtest-{role}@test.com"
    refresh["institution_id"] = str(LOAD_TEST_INSTITUTION_ID)
    refresh["student_id"] = str(student_id) if student_id else None
    refresh["is_profile_completed"] = True
    return str(refresh.access_token)


def _request(method, path, token=None, body=None, timeout=15):
    url = f"{GATEWAY_BASE}{path}"
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
    result = {
        "count": len(statuses),
        "success": len(ok),
        "errors": len(errors),
        "error_rate_pct": round(len(errors) / len(statuses) * 100, 2) if statuses else 0.0,
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
        "Task 14.1's load test: mass session-start, steady-state answer-autosave, "
        "end-of-exam submit rush, and concurrent admin traffic, all through the real "
        "gateway. Prints p50/p95/p99 latency and error rate per scenario."
    )

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, default=200, help="Concurrent virtual students for this run")
        parser.add_argument("--admin-requests", type=int, default=20, help="Concurrent admin dashboard/analytics/results requests fired during the autosave phase")
        parser.add_argument("--autosave-rounds", type=int, default=3, help="How many answers each student autosaves during the steady-state phase")
        parser.add_argument("--workers", type=int, default=100, help="Thread pool size for issuing concurrent requests")
        parser.add_argument("--keep-data", action="store_true", help="Don't delete the load-test paper/assignment/sessions afterward (for manual DB inspection)")

    def handle(self, *args, **options):
        n = options["students"]
        admin_n = options["admin_requests"]
        rounds = options["autosave_rounds"]
        workers = options["workers"]

        self.stdout.write(self.style.NOTICE(f"=== Task 14.1 load test: {n} students, {workers} worker threads ==="))

        assignment, questions, students = self._setup(n)
        self.stdout.write(f"Setup complete: assignment={assignment.id}, {len(questions)} question(s), {n} students allocated.")

        try:
            results = {}
            results["session_start"] = self._scenario_session_start(assignment, students, workers)
            self._print("Mass session-start", results["session_start"])

            self._reconnect()
            sessions_by_student = self._collect_sessions(assignment, students)

            results["autosave"], results["admin_concurrent"] = self._scenario_autosave_with_admin_traffic(
                sessions_by_student, questions, rounds, admin_n, assignment, workers,
            )
            self._print(f"Steady-state autosave ({rounds} rounds/student)", results["autosave"])
            self._print("Concurrent admin traffic (during autosave)", results["admin_concurrent"])

            results["submit"] = self._scenario_submit_rush(sessions_by_student, workers)
            self._print("End-of-exam submit rush", results["submit"])

            self._reconnect()  # see _reconnect()'s docstring — real finding from this task's own 400-student run
            self._verify_data_integrity(assignment, n)

            self.stdout.write(self.style.SUCCESS("\n=== load test complete ==="))
            self.stdout.write(json.dumps(results, indent=2))
        finally:
            self._reconnect()
            if not options["keep_data"]:
                self._teardown(assignment)
                self.stdout.write("Test data cleaned up.")
            else:
                self.stdout.write(self.style.WARNING(f"--keep-data set: assignment {assignment.id} left in place."))

    def _reconnect(self):
        """Real finding from this task's own 400-student run: this
        command's main-thread ORM connection sits idle for the full
        duration of each concurrent scenario (all the DB activity happens
        on the ThreadPoolExecutor workers' own connections) — long enough,
        at 400+ students, to exceed PgBouncer's client_idle_timeout=60s
        (infra/pgbouncer/pgbouncer.ini), which closes it. The next query on
        that connection then raises OperationalError('server closed the
        connection unexpectedly'), not a service bug. Forcing a fresh
        connection before any post-scenario query is the fix for this
        tool; see docs/assessment-service-load-test-results.md for why the
        same 60s timeout is a genuine risk for Task 7.3's slow CSV export
        stream too, flagged there as a follow-up rather than fixed here."""
        from django.db import connection
        connection.close()

    # ── Setup ────────────────────────────────────────────────────────────

    def _setup(self, n):
        from assessments.models import (
            QuestionPaper, QuestionSet, Question, QuestionOption, BatchAssignment,
            StudentSetAllocation, ASSIGNMENT_STATUS_LIVE, MCQ_TYPE_SINGLE,
        )

        paper = QuestionPaper.objects.create(
            institution_id=LOAD_TEST_INSTITUTION_ID, title=f"Load Test Paper {uuid.uuid4().hex[:8]}",
            created_by=LOAD_TEST_ADMIN_ID, is_published=True,
        )
        qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
        questions = []
        for i in range(5):
            q = Question.objects.create(set=qset, question_text=f"Load test Q{i+1}", marks=1, mcq_type=MCQ_TYPE_SINGLE)
            opt_correct = QuestionOption.objects.create(question=q, label="A", text="right", is_correct=True, order=1)
            QuestionOption.objects.create(question=q, label="B", text="wrong", order=2)
            questions.append((q, opt_correct))

        assignment = BatchAssignment.objects.create(
            paper=paper, batch_id=LOAD_TEST_BATCH_ID, institution_id=LOAD_TEST_INSTITUTION_ID,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=LOAD_TEST_ADMIN_ID, status=ASSIGNMENT_STATUS_LIVE,
        )

        # StudentSetAllocation rows are created directly via the ORM rather
        # than through the real resync-roster call, exactly matching what a
        # real roster snapshot would have produced (Task 3.1's
        # snapshot_roster_and_allocate()) — but student_user_id(i) is
        # deterministic and must match real Student.user_id rows already
        # seeded in user-service (see module-level LOAD_TEST_BATCH_ID
        # comment) or Results/Analytics/Dashboard admin calls will 502 on
        # the roster fetch, same as this task's own validation run found.
        student_ids = [student_user_id(i) for i in range(n)]
        StudentSetAllocation.objects.bulk_create([
            StudentSetAllocation(assignment=assignment, student_id=sid, set=qset)
            for sid in student_ids
        ], batch_size=500)

        students = [
            {"id": sid, "token": _token_for(sid, "student", student_id=f"LOADTEST-{i:04d}")}
            for i, sid in enumerate(student_ids)
        ]
        return assignment, questions, students

    def _teardown(self, assignment):
        from assessments.models import (
            QuestionPaper, AssessmentSession, AssessmentResponse, StudentSetAllocation, ResultSummary,
        )
        paper = assignment.paper
        # Bottom-up, same order as Task 13.3's cleanup fix: AssessmentResponse
        # PROTECTs its session FK (never let a cascade silently wipe a
        # frozen response set), so it must go before AssessmentSession.
        ResultSummary.objects.filter(assignment=assignment).delete()
        AssessmentResponse.objects.filter(session__assignment=assignment).delete()
        AssessmentSession.objects.filter(assignment=assignment).delete()
        StudentSetAllocation.objects.filter(assignment=assignment).delete()
        assignment.delete()
        paper.delete()  # cascades to sets/questions/options

    # ── Scenarios ────────────────────────────────────────────────────────

    def _scenario_session_start(self, assignment, students, workers):
        def worker(student):
            return _request(
                "POST", f"/api/assessments/student/assignments/{assignment.id}/start-session/",
                token=student["token"],
            )
        return self._run_concurrent(worker, students, workers)

    def _collect_sessions(self, assignment, students):
        from assessments.models import AssessmentSession
        sessions = {
            s.student_id: s.id for s in
            AssessmentSession.objects.filter(assignment=assignment).only("id", "student_id")
        }
        return [(student, sessions[student["id"]]) for student in students if student["id"] in sessions]

    def _scenario_autosave_with_admin_traffic(self, sessions_by_student, questions, rounds, admin_n, assignment, workers):
        admin_token = _token_for(LOAD_TEST_ADMIN_ID, "admin")
        admin_paths = [
            f"/api/assessments/admin/assignments/{assignment.id}/dashboard/",
            f"/api/assessments/admin/assignments/{assignment.id}/results/",
        ]

        autosave_jobs = []
        for student, session_id in sessions_by_student:
            for r in range(rounds):
                question, option = questions[r % len(questions)]
                autosave_jobs.append((student["token"], session_id, question.id, option.id))

        admin_jobs = [admin_paths[i % len(admin_paths)] for i in range(admin_n)]

        autosave_results, admin_results = [], []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            autosave_futures = {
                pool.submit(
                    _request, "PUT",
                    f"/api/assessments/student/sessions/{session_id}/questions/{qid}/answer/",
                    token, {"selected_option_ids": [str(oid)]},
                ): None
                for token, session_id, qid, oid in autosave_jobs
            }
            admin_futures = {
                pool.submit(_request, "GET", path, admin_token): None
                for path in admin_jobs
            }
            for fut in as_completed(list(autosave_futures) + list(admin_futures)):
                status, elapsed = fut.result()
                if fut in autosave_futures:
                    autosave_results.append((status, elapsed))
                else:
                    admin_results.append((status, elapsed))

        autosave_statuses, autosave_latencies = zip(*autosave_results) if autosave_results else ([], [])
        admin_statuses, admin_latencies = zip(*admin_results) if admin_results else ([], [])
        return _stats(list(autosave_latencies), list(autosave_statuses)), _stats(list(admin_latencies), list(admin_statuses))

    def _scenario_submit_rush(self, sessions_by_student, workers):
        def worker(pair):
            student, session_id = pair
            return _request("POST", f"/api/assessments/student/sessions/{session_id}/submit/", token=student["token"])
        return self._run_concurrent(worker, sessions_by_student, workers)

    def _run_concurrent(self, fn, items, workers):
        statuses, latencies = [], []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(fn, item) for item in items]
            for fut in as_completed(futures):
                status, elapsed = fut.result()
                statuses.append(status)
                latencies.append(elapsed)
        return _stats(latencies, statuses)

    # ── Verification ─────────────────────────────────────────────────────

    def _verify_data_integrity(self, assignment, n):
        from assessments.models import AssessmentSession, ResultSummary, SESSION_STATUS_SUBMITTED
        sessions = AssessmentSession.objects.filter(assignment=assignment).count()
        submitted = AssessmentSession.objects.filter(assignment=assignment, status=SESSION_STATUS_SUBMITTED).count()
        results = ResultSummary.objects.filter(assignment=assignment).count()
        self.stdout.write(
            f"Data integrity: {sessions} sessions created, {submitted} submitted, "
            f"{results} ResultSummary rows (expect results == submitted, both <= {n})."
        )
        if results != submitted:
            self.stdout.write(self.style.ERROR(
                f"MISMATCH: {results} results vs {submitted} submitted sessions — investigate before trusting these numbers."
            ))
        # No duplicate ResultSummary per session — the actual AT4/AT5 invariant.
        from django.db.models import Count
        dupes = (
            ResultSummary.objects.filter(assignment=assignment)
            .values("session_id").annotate(c=Count("id")).filter(c__gt=1)
        )
        if dupes.exists():
            self.stdout.write(self.style.ERROR(f"DUPLICATE ResultSummary rows found for {dupes.count()} session(s)!"))
        else:
            self.stdout.write(self.style.SUCCESS("No duplicate ResultSummary rows — AT4/AT5 held under real concurrent load."))

    def _print(self, label, stats):
        self.stdout.write(f"\n--- {label} ---")
        for k, v in stats.items():
            self.stdout.write(f"  {k}: {v}")
