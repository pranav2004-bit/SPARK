"""
Tests for the IT Dashboard stats endpoint (student/batch/section half —
auth-service's own ITDashboardStatsView covers departments/admins/
super_admins; the frontend composes both).

Endpoint: GET /api/users/it/dashboard-stats/ — IT only. Deliberately
uncached (user decision, 2026-11-14): must reflect the real database
state on every single request.
"""
import uuid
import pytest

from users.models import Batch, Student
from .conftest import INSTITUTION_A, INSTITUTION_B

URL = "/api/users/it/dashboard-stats/"


def _batch(name, institution_id=INSTITUTION_A):
    return Batch.objects.create(batch_name=name, institution_id=institution_id)


def _student(batch, department, section, institution_id=INSTITUTION_A, is_active=True, student_id=None):
    return Student.objects.create(
        user_id=uuid.uuid4(),
        student_id=student_id or f"S{uuid.uuid4().hex[:8]}",
        institution_id=institution_id,
        department=department,
        section=section,
        batch=batch,
        is_active=is_active,
    )


# ── Access control ───────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_it_can_access(it_client):
    resp = it_client.get(URL)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.django_db
def test_admin_forbidden(admin_client):
    resp = admin_client.get(URL)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_super_admin_forbidden(super_admin_client):
    resp = super_admin_client.get(URL)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_student_forbidden(student_client):
    resp = student_client.get(URL)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_anon_unauthorized(anon_client):
    resp = anon_client.get(URL)
    assert resp.status_code == 401


# ── Counts ────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_overall_student_counts(it_client):
    batch = _batch("2023-27")
    _student(batch, "CSE", "A", is_active=True)
    _student(batch, "CSE", "A", is_active=True)
    _student(batch, "ECE", "B", is_active=False)

    data = it_client.get(URL).json()["data"]
    assert data["students"]["total"] == 3
    assert data["students"]["active"] == 2
    assert data["students"]["inactive"] == 1


@pytest.mark.django_db
def test_students_by_department(it_client):
    batch = _batch("2023-27")
    _student(batch, "CSE", "A", is_active=True)
    _student(batch, "CSE", "A", is_active=False)
    _student(batch, "CSE", "B", is_active=True)
    _student(batch, "ECE", "A", is_active=True)

    data = it_client.get(URL).json()["data"]

    by_dept = {row["department"]: row for row in data["students"]["by_department"]}
    assert by_dept["CSE"] == {"department": "CSE", "total": 3, "active": 2, "inactive": 1}
    assert by_dept["ECE"] == {"department": "ECE", "total": 1, "active": 1, "inactive": 0}

    # No global, cross-department section tally (removed 2026-11-14, user
    # decision) — a bare "Section A" count that silently lumps CSE-A with
    # ECE-A together was never a meaningful number.
    assert "by_section" not in data["students"]


@pytest.mark.django_db
def test_sections_per_department_has_real_counts_not_just_letters(it_client):
    batch = _batch("2023-27")
    _student(batch, "CSE", "A", is_active=True)
    _student(batch, "CSE", "A", is_active=False)
    _student(batch, "CSE", "B", is_active=True)
    _student(batch, "ECE", "A", is_active=True)  # same letter "A" as CSE's — must not merge with it

    data = it_client.get(URL).json()["data"]
    by_dept = {row["department"]: row for row in data["sections_per_department"]}

    cse = by_dept["CSE"]
    assert cse["section_count"] == 2
    cse_sections = {row["section"]: row for row in cse["sections"]}
    assert cse_sections["A"] == {"section": "A", "total": 2, "active": 1, "inactive": 1}
    assert cse_sections["B"] == {"section": "B", "total": 1, "active": 1, "inactive": 0}

    ece = by_dept["ECE"]
    assert ece["section_count"] == 1
    ece_sections = {row["section"]: row for row in ece["sections"]}
    # ECE's own "A" is counted separately from CSE's "A" — the whole point
    # of this being scoped per department rather than a flat global tally.
    assert ece_sections["A"] == {"section": "A", "total": 1, "active": 1, "inactive": 0}


@pytest.mark.django_db
def test_every_batch_listed_including_empty_ones(it_client):
    populated = _batch("2023-27")
    empty = _batch("2024-28")
    _student(populated, "CSE", "A")

    data = it_client.get(URL).json()["data"]
    by_name = {row["batch_name"]: row for row in data["batches"]}

    assert by_name["2023-27"]["total"] == 1
    assert by_name["2024-28"]["total"] == 0
    assert by_name["2024-28"]["by_department"] == []


@pytest.mark.django_db
def test_per_batch_breakdown_is_scoped_to_that_batch_only(it_client):
    batch_a = _batch("2023-27")
    batch_b = _batch("2024-28")
    _student(batch_a, "CSE", "A", is_active=True)
    _student(batch_a, "CSE", "A", is_active=False)
    _student(batch_b, "ECE", "C", is_active=True)

    data = it_client.get(URL).json()["data"]
    by_name = {row["batch_name"]: row for row in data["batches"]}

    a = by_name["2023-27"]
    assert a["total"] == 2 and a["active"] == 1 and a["inactive"] == 1
    assert a["by_department"] == [{
        "department": "CSE", "total": 2, "active": 1, "inactive": 1,
        "sections": [{"section": "A", "total": 2, "active": 1, "inactive": 1}],
    }]

    b = by_name["2024-28"]
    assert b["total"] == 1
    assert b["by_department"] == [{
        "department": "ECE", "total": 1, "active": 1, "inactive": 0,
        "sections": [{"section": "C", "total": 1, "active": 1, "inactive": 0}],
    }]


@pytest.mark.django_db
def test_per_batch_sections_are_scoped_to_their_own_department_not_a_flat_tally(it_client):
    # Two departments share the same section letter "A", both within the
    # SAME batch — each department's own row must carry only its own count
    # for "A", never a combined/global one (same requirement as the
    # institution-wide sections_per_department, 2026-11-14 user decision).
    batch = _batch("2023-27")
    _student(batch, "CSE", "A", is_active=True)
    _student(batch, "CSE", "A", is_active=False)
    _student(batch, "ECE", "A", is_active=True)

    data = it_client.get(URL).json()["data"]
    batch_row = data["batches"][0]
    by_dept = {row["department"]: row for row in batch_row["by_department"]}

    cse_sections = {row["section"]: row for row in by_dept["CSE"]["sections"]}
    assert cse_sections["A"] == {"section": "A", "total": 2, "active": 1, "inactive": 1}

    ece_sections = {row["section"]: row for row in by_dept["ECE"]["sections"]}
    assert ece_sections["A"] == {"section": "A", "total": 1, "active": 1, "inactive": 0}


@pytest.mark.django_db
def test_scoped_to_callers_own_institution(it_client):
    mine = _batch("Mine", institution_id=INSTITUTION_A)
    theirs = _batch("Theirs", institution_id=INSTITUTION_B)
    _student(mine, "CSE", "A", institution_id=INSTITUTION_A)
    _student(theirs, "ECE", "B", institution_id=INSTITUTION_B)

    data = it_client.get(URL).json()["data"]
    assert data["students"]["total"] == 1
    batch_names = {row["batch_name"] for row in data["batches"]}
    assert batch_names == {"Mine"}


@pytest.mark.django_db
def test_reflects_the_real_current_state_not_a_stale_cache(it_client):
    # The explicit "100% accuracy, updates automatically" requirement —
    # verified directly: create something new between two calls and
    # confirm the second call sees it, proving there's no cache.
    before = it_client.get(URL).json()["data"]
    assert before["students"]["total"] == 0

    batch = _batch("2023-27")
    _student(batch, "CSE", "A")
    after = it_client.get(URL).json()["data"]
    assert after["students"]["total"] == 1
