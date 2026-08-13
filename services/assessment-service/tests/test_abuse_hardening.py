"""
Task 12.2's "standard API abuse hardening" subtask: request size limits and
malformed-payload rejection across the service.

MaxBodySizeMiddleware (core/middleware.py) exists because this task's own
audit found Django's built-in DATA_UPLOAD_MAX_MEMORY_SIZE guard does not
actually engage in this service's deployment — verified with real
end-to-end requests through the live gateway before writing any fix: a 6MB
JSON body reached full application-level processing every time, never
rejected at the transport layer. Root cause not fully pinned down (this
service runs under `uvicorn core.asgi:application`, and something in how
Django's ASGI handling or DRF's Request wrapping reads the body bypasses
the check that works under classic WSGI) — rather than keep excavating
Django/ASGI internals, the fix is a small, directly-verifiable middleware
instead of a framework default nobody had ever actually confirmed worked.
"""
from rest_framework.test import APIClient

from .conftest import _make_token, INSTITUTION_A, STUDENT_USER_ID


class TestMaxBodySize:
    def test_oversized_payload_rejected_cleanly(self, db):
        token = _make_token(STUDENT_USER_ID, "student", INSTITUTION_A, student_id=STUDENT_USER_ID)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # 3MB, comfortably over MaxBodySizeMiddleware's 2MB cap.
        huge_payload = {"selected_option_ids": ["x" * 3_000_000]}
        resp = client.put(
            "/api/assessments/student/sessions/00000000-0000-0000-0000-000000000000"
            "/questions/00000000-0000-0000-0000-000000000000/answer/",
            huge_payload, format="json",
        )
        assert resp.status_code == 400
        assert "too large" in resp.json()["message"].lower()

    def test_normal_payload_unaffected(self, db):
        # A payload comfortably within the cap must reach the view
        # normally — this fixture-free anonymous request should 401/403
        # (no valid session to answer), never a size-limit rejection, i.e.
        # the middleware must not be over-triggering on legitimate traffic.
        client = APIClient()
        resp = client.put(
            "/api/assessments/student/sessions/00000000-0000-0000-0000-000000000000"
            "/questions/00000000-0000-0000-0000-000000000000/answer/",
            {"selected_option_ids": ["11111111-1111-1111-1111-111111111111"]}, format="json",
        )
        assert resp.status_code in (401, 403)

    def test_missing_content_length_not_rejected(self, db):
        # A request with no body at all (GET) must never be rejected —
        # confirms the middleware only acts when Content-Length is present
        # and actually over the cap, not on every request indiscriminately.
        client = APIClient()
        resp = client.get("/api/assessments/health/")
        assert resp.status_code == 200
