"""
One-time (idempotent) companion setup for assessment-service's
load_test.py management command (LIVETRACKER2_V1.md Task 14.1) — run this
against user-service, not assessment-service, since it writes to
user-service's own database.

Creates a real Batch + N Student rows in user-service matching the exact
deterministic user_id scheme load_test.py's student_user_id(i) helper
uses, so the admin Results/Analytics/Dashboard endpoints' roster-fetch
(Task 7.1) resolves against real data instead of 404ing on a synthetic
batch_id — found as a real gap during Task 14.1's own validation run, see
docs/assessment-service-load-test-results.md.

Usage: docker exec -i infra-user-service-1 python manage.py shell < infra/scripts/seed_load_test_roster.py
"""
import uuid

from users.models import Batch, Student

LOAD_TEST_INSTITUTION_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
LOAD_TEST_BATCH_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
_STUDENT_UUID_NAMESPACE = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
N = 600  # the safety-margin (3x) scale — every smaller run (200/400) reuses the same first-N rows


def student_user_id(i):
    return uuid.uuid5(_STUDENT_UUID_NAMESPACE, f"spark-load-test-student-{i}")


batch, created = Batch.objects.get_or_create(
    id=LOAD_TEST_BATCH_ID,
    defaults={"batch_name": "SPARK Load Test Batch (Task 14.1)", "institution_id": LOAD_TEST_INSTITUTION_ID},
)
print("batch:", batch.id, "created" if created else "already existed")

existing = set(Student.objects.filter(batch=batch).values_list("user_id", flat=True))
to_create = []
for i in range(N):
    uid = student_user_id(i)
    if uid in existing:
        continue
    to_create.append(Student(
        user_id=uid,
        student_id=f"LOADTEST-{i:04d}",
        institution_id=LOAD_TEST_INSTITUTION_ID,
        fullname=f"Load Test Student {i:04d}",
        department="Load Test",
        batch=batch,
        is_active=True,
        is_profile_completed=True,
    ))

if to_create:
    Student.objects.bulk_create(to_create, batch_size=500)
print(f"students: {Student.objects.filter(batch=batch).count()} total, {len(to_create)} newly created")
