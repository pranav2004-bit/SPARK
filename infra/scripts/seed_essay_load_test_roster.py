"""
One-time (idempotent) companion setup for essay-service's load_test.py
management command (LIVETRACKER3_V1.md Task 18.1) — run this against
user-service, not essay-service, since it writes to user-service's own
database. Mirrors infra/scripts/seed_load_test_roster.py's own pattern
(assessment-service's Task 14.1) exactly, with a distinct batch/institution
so the two services' load tests never collide or share state.

Creates a real Batch + N Student rows in user-service matching the exact
deterministic user_id scheme load_test.py's student_user_id(i) helper
uses, so essay-service's admin Results/Dashboard endpoints' roster-fetch
(core/user_service_client.py) resolves against real data instead of
502ing on a synthetic batch_id — the same real gap assessment-service's
own Task 14.1 found first.

Usage: docker exec -i infra-user-service-1 python manage.py shell < infra/scripts/seed_essay_load_test_roster.py
"""
import uuid

from users.models import Batch, Student

ESSAY_LOAD_TEST_INSTITUTION_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
ESSAY_LOAD_TEST_BATCH_ID = uuid.UUID("dddddddd-eeee-dddd-eeee-dddddddddddd")
_ESSAY_STUDENT_UUID_NAMESPACE = uuid.UUID("eeeeeeee-ffff-eeee-ffff-eeeeeeeeeeee")
N = 600  # the safety-margin (3x) scale — every smaller run (200/400) reuses the same first-N rows


def student_user_id(i):
    return uuid.uuid5(_ESSAY_STUDENT_UUID_NAMESPACE, f"spark-essay-load-test-student-{i}")


batch, created = Batch.objects.get_or_create(
    id=ESSAY_LOAD_TEST_BATCH_ID,
    defaults={"batch_name": "SPARK Essay Load Test Batch (Task 18.1)", "institution_id": ESSAY_LOAD_TEST_INSTITUTION_ID},
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
        student_id=f"ESSAYLOADTEST-{i:04d}",
        institution_id=ESSAY_LOAD_TEST_INSTITUTION_ID,
        fullname=f"Essay Load Test Student {i:04d}",
        department="Load Test",
        batch=batch,
        is_active=True,
        is_profile_completed=True,
    ))

if to_create:
    Student.objects.bulk_create(to_create, batch_size=500)
print(f"students: {Student.objects.filter(batch=batch).count()} total, {len(to_create)} newly created")
