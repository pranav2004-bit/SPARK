"""LIVETRACKER4 Phase F and G checklist tests not covered elsewhere.

F3: inherited throttles (429 + Retry-After) and fail-open on Redis error.
F4: audit read endpoint filters and paging.
G1: no question/option text in any content log line.
G2: write actions emit counter lines on the content.audit logger.
G3: practice health characterization (exact keys, no content block).
G4: alert thresholds match section 2.15.
"""
import json
import logging
import pathlib
from unittest.mock import patch

import pytest
import redis.exceptions
from django.core.cache import cache
from django.test import override_settings
from rest_framework.throttling import SimpleRateThrottle

from core.throttling_resilience import ResilientUserRateThrottle
from tests.test_content_api import BASE, _create_subject, _create_topic, _publish_node, _create_question
from tests.test_content_api import super_client  # noqa: F401  (pytest fixture)


@pytest.fixture(autouse=True)
def bank_enabled():
    with override_settings(CONTENT_BANK_ENABLED=True):
        yield


@pytest.fixture
def topic(admin_client, db):
    subject = _create_subject(admin_client)
    _publish_node(admin_client, subject)
    t = _create_topic(admin_client, subject)
    _publish_node(admin_client, t)
    return t


# ── F3: inherited throttles ───────────────────────────────────────────────────

@pytest.mark.django_db
class TestThrottles:
    def test_user_limit_returns_429_with_retry_after(self, admin_client):
        cache.clear()
        with patch.dict(ResilientUserRateThrottle.THROTTLE_RATES, {"user": "2/min"}):
            statuses = [admin_client.get(f"{BASE}/nodes/?parent_id=null").status_code for _ in range(3)]
        assert statuses[:2] == [200, 200]
        assert statuses[2] == 429
        with patch.dict(ResilientUserRateThrottle.THROTTLE_RATES, {"user": "2/min"}):
            blocked = admin_client.get(f"{BASE}/nodes/?parent_id=null")
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) > 0

    def test_under_limit_is_allowed(self, admin_client):
        cache.clear()
        with patch.dict(ResilientUserRateThrottle.THROTTLE_RATES, {"user": "100/min"}):
            assert admin_client.get(f"{BASE}/nodes/?parent_id=null").status_code == 200

    def test_redis_error_fails_open_and_logs_warning(self, admin_client, caplog):
        with patch.object(SimpleRateThrottle, "allow_request",
                          side_effect=redis.exceptions.ConnectionError("redis down")):
            with caplog.at_level(logging.WARNING, logger="core.throttling_resilience"):
                resp = admin_client.get(f"{BASE}/nodes/?parent_id=null")
        assert resp.status_code == 200
        assert any("failing open" in r.getMessage() for r in caplog.records)


# ── F4: audit read endpoint ───────────────────────────────────────────────────

@pytest.mark.django_db
class TestAuditRead:
    def test_filter_by_entity_type_returns_only_that_type(self, super_client, admin_client, topic):
        url = f"{BASE}/audit/?entity_type=node"
        resp = super_client.get(url)
        assert resp.status_code == 200
        rows = resp.json()["results"]
        assert rows and all(r["entity_type"] == "node" for r in rows)

    def test_filter_by_entity_id_returns_only_that_entity(self, super_client, admin_client, topic):
        entity_id = str(topic["id"]) if isinstance(topic, dict) else str(topic)
        resp = super_client.get(f"{BASE}/audit/?entity_id={entity_id}")
        assert resp.status_code == 200
        rows = resp.json()["results"]
        assert rows and all(r["entity_id"] == entity_id for r in rows)

    def test_bad_entity_id_is_400(self, super_client, topic):
        assert super_client.get(f"{BASE}/audit/?entity_id=not-a-uuid").status_code == 400

    def test_paging_returns_next_page(self, super_client, admin_client, topic):
        resp = super_client.get(f"{BASE}/audit/?page_size=1")
        data = resp.json()
        assert resp.status_code == 200
        assert len(data["results"]) == 1
        assert data["count"] >= 2 and data["next"] is not None


# ── G1, G2: logs and counter lines ───────────────────────────────────────────

@pytest.mark.django_db
class TestLogsAndCounters:
    def test_no_question_or_option_text_in_any_content_log(self, admin_client, topic, caplog):
        secret_q = "PRIVATE-QUESTION-5521"
        secret_o = "PRIVATE-OPTION-9034"
        with caplog.at_level(logging.DEBUG):
            created = admin_client.post(f"{BASE}/questions/", {
                "node_id": str(topic["id"]) if isinstance(topic, dict) else str(topic),
                "text": secret_q,
                "options": [
                    {"label": "A", "option_text": secret_o, "is_correct": True, "display_order": 1},
                    {"label": "B", "option_text": "other", "is_correct": False, "display_order": 2},
                ],
                "explanation": "",
            }, format="json")
        assert created.status_code == 201
        content_lines = [r.getMessage() for r in caplog.records if r.name.startswith("content")]
        assert content_lines
        assert all(secret_q not in line and secret_o not in line for line in content_lines)

    def test_write_actions_emit_counter_lines(self, admin_client, topic, caplog):
        with caplog.at_level(logging.INFO, logger="content.audit"):
            q = _create_question(admin_client, topic)
            qid = q.json()["data"]["id"]
            etag = q.headers["ETag"]
            admin_client.post(f"{BASE}/questions/{qid}/publish/", format="json", HTTP_IF_MATCH=etag)
            admin_client.delete(f"{BASE}/questions/{qid}/")
        lines = [r.getMessage() for r in caplog.records if r.name == "content.audit"]
        for action in ("question.create", "question.publish", "question.delete"):
            assert any(f"action={action} " in line for line in lines), action


# ── G3: practice health characterization ──────────────────────────────────────

@pytest.mark.django_db
class TestPracticeHealthUnchanged:
    def test_practice_health_keys_are_exactly_the_original_set(self, anon_client):
        resp = anon_client.get("/api/practice/health/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert set(data.keys()) == {"status", "service", "db", "redis"}
        assert data["service"] == "practice-service"
        assert "content" not in data


# ── G4: alert thresholds ──────────────────────────────────────────────────────

class TestAlertThresholds:
    def test_thresholds_match_section_2_15(self):
        path = pathlib.Path(__file__).resolve().parent.parent / "content" / "ops_alerts.json"
        alerts = {a["name"]: a["condition"] for a in json.loads(path.read_text(encoding="utf-8"))["alerts"]}
        assert "> 1%" in alerts["content_5xx_rate_high"] and "5 minutes" in alerts["content_5xx_rate_high"]
        assert "> 100" in alerts["content_orphan_growth"] and "24h" in alerts["content_orphan_growth"]
        assert "> 1 second" in alerts["content_publish_latency_high"]
        assert "15 minutes" in alerts["content_publish_latency_high"]
        assert "5 minutes" in alerts["content_health_dependency_down"]


class TestDashboardDefinition:
    def test_dashboard_panels_reference_only_defined_alerts(self):
        base = pathlib.Path(__file__).resolve().parent.parent / "content"
        alert_names = {a["name"] for a in json.loads((base / "ops_alerts.json").read_text(encoding="utf-8"))["alerts"]}
        dash = json.loads((base / "ops_dashboard.json").read_text(encoding="utf-8"))
        referenced = {p["alert"] for p in dash["panels"] if "alert" in p}
        assert referenced and referenced <= alert_names
        assert all(p.get("query") for p in dash["panels"])


# ── I7: errors carry a request id (LIVETRACKER4 I7) ──────────────────────────

@pytest.mark.django_db
class TestRequestId:
    def test_error_body_and_header_echo_client_request_id(self, admin_client):
        resp = admin_client.post(f"{BASE}/nodes/", {"name": ""}, format="json", HTTP_X_REQUEST_ID="client-rid-1")
        assert resp.status_code == 400
        assert resp.json()["request_id"] == "client-rid-1"
        assert resp["X-Request-ID"] == "client-rid-1"

    def test_generated_request_id_when_client_sends_none(self, admin_client):
        resp = admin_client.post(f"{BASE}/nodes/", {"name": ""}, format="json")
        rid = resp.json()["request_id"]
        assert rid and resp["X-Request-ID"] == rid

    def test_success_body_has_no_request_id_field(self, admin_client):
        resp = admin_client.get(f"{BASE}/nodes/?parent_id=null")
        assert resp.status_code == 200 and "request_id" not in resp.json()


# ── H5 follow-up: list endpoint must not issue one query per question ─────────

@pytest.mark.django_db
class TestListQueryCount:
    def test_list_query_count_does_not_grow_with_questions(self, admin_client, topic):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        topic_id = str(topic["id"]) if isinstance(topic, dict) else str(topic)

        def list_query_count():
            with CaptureQueriesContext(connection) as ctx:
                resp = admin_client.get(f"{BASE}/questions/?node_id={topic_id}")
            assert resp.status_code == 200
            return len(ctx.captured_queries)

        for _ in range(2):
            _create_question(admin_client, topic)
        small = list_query_count()
        for _ in range(6):
            _create_question(admin_client, topic)
        large = list_query_count()
        assert large == small


# ── K5: every CONTENT_* setting is documented in .env.example ─────────────────

class TestEnvExampleComplete:
    def test_every_content_setting_appears_in_env_example(self):
        import re
        root = pathlib.Path(__file__).resolve().parent.parent
        settings_src = (root / "core" / "settings.py").read_text(encoding="utf-8")
        env_src = (root / ".env.example").read_text(encoding="utf-8")
        names = set(re.findall(r"\bCONTENT_[A-Z_]+\b", settings_src))
        assert names
        missing = {n for n in names if not re.search(rf"^#?\s*{n}=", env_src, re.MULTILINE)}
        assert missing == set()


# ── H4 / section 2.14: explicit S3 timeout; timeouts are 503 and keep the object ─

@pytest.mark.django_db
class TestS3Timeouts:
    def test_content_timeout_is_applied_to_the_client_config(self):
        from core.storage import _get_client
        with override_settings(AWS_STORAGE_BUCKET_NAME="bucket-x", AWS_DEFAULT_REGION="ap-south-1"):
            short = _get_client(timeout=5)
            default = _get_client()
        assert short.meta.config.connect_timeout == 5 and short.meta.config.read_timeout == 5
        assert default.meta.config.connect_timeout != 5

    def test_botocore_timeout_during_verify_is_503_and_object_kept(self, admin_client, draft_question):
        from botocore.exceptions import ReadTimeoutError
        qid, etag = draft_question
        with patch("content.images.verify_uploaded_image",
                   side_effect=ReadTimeoutError(endpoint_url="https://s3.example")), \
             patch("content.images._delete_rejected") as rejected:
            r = admin_client.post(f"{BASE}/questions/{qid}/image/confirm/",
                                  {"file_key": "uploads/content/slow.png", "image_alt_text": "x"},
                                  format="json", HTTP_IF_MATCH=etag)
        assert r.status_code == 503 and r.json()["code"] == "storage_unavailable"
        rejected.assert_not_called()

    def test_confirm_passes_configured_timeout_to_verification(self, admin_client, draft_question):
        qid, etag = draft_question
        with override_settings(CONTENT_S3_TIMEOUT_SECONDS=7), \
             patch("content.images.verify_uploaded_image", return_value=(None, "Image was not found in storage. Upload it before saving.")) as verify:
            admin_client.post(f"{BASE}/questions/{qid}/image/confirm/",
                              {"file_key": "uploads/content/t.png", "image_alt_text": "x"},
                              format="json", HTTP_IF_MATCH=etag)
        assert verify.call_args.kwargs["timeout"] == 7


# ── L6: rollback rehearsal (flag off and on, data kept) ──────────────────────

@pytest.mark.django_db
class TestRollbackRehearsal:
    def test_flag_off_hides_content_and_flag_on_restores_it_with_no_data_loss(self, admin_client):
        with override_settings(CONTENT_BANK_ENABLED=True):
            subject = _create_subject(admin_client, name="Rollback subject")
            _publish_node(admin_client, subject)
        with override_settings(CONTENT_BANK_ENABLED=False):
            assert admin_client.get(f"{BASE}/nodes/?parent_id=null").status_code == 404
            assert admin_client.get(f"{BASE}/health/").status_code == 404
        with override_settings(CONTENT_BANK_ENABLED=True):
            listing = admin_client.get(f"{BASE}/nodes/?parent_id=null").json()["results"]
        assert [n["name"] for n in listing] == ["Rollback subject"]
        assert listing[0]["status"] == "published"


@pytest.fixture
def draft_question(admin_client, db):
    subject = _create_subject(admin_client)
    _publish_node(admin_client, subject)
    t = _create_topic(admin_client, subject)
    _publish_node(admin_client, t)
    q = _create_question(admin_client, t)
    return q.json()["data"]["id"], q.headers["ETag"]


# ── subject names: any text, digits and symbols; no control characters; unique per parent ──

@pytest.mark.django_db
class TestSubjectNames:
    def test_symbols_digits_and_text_are_accepted(self, admin_client):
        resp = admin_client.post(f"{BASE}/nodes/", {"name": "Maths 101 !@#$%^&*()_+ café"}, format="json")
        assert resp.status_code == 201

    def test_control_characters_are_refused(self, admin_client):
        resp = admin_client.post(f"{BASE}/nodes/", {"name": "Bad\x00name"}, format="json")
        assert resp.status_code == 400 and "name" in resp.json()["errors"]

    def test_line_break_in_name_is_refused(self, admin_client):
        resp = admin_client.post(f"{BASE}/nodes/", {"name": "Line\nBreak"}, format="json")
        assert resp.status_code == 400

    def test_duplicate_subject_name_is_refused_regardless_of_case(self, admin_client):
        assert admin_client.post(f"{BASE}/nodes/", {"name": "Physics"}, format="json").status_code == 201
        resp = admin_client.post(f"{BASE}/nodes/", {"name": "  PHYSICS "}, format="json")
        assert resp.status_code == 409 and resp.json()["code"] == "duplicate_name"
