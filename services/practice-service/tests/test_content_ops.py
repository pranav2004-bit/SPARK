import json
import logging
import pathlib
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from content import cache as content_cache
from content.views import ContentQuestionListCreateView, ContentNodeListCreateView
from core.throttling_resilience import ResilientUserRateThrottle
from tests.test_content_api import BASE, OPTS, _create_subject, _create_topic, _publish_node, _create_question
from tests.conftest import INSTITUTION_A


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


# ── F1, F2: cache keys, invalidation, failure path ─────────────────────────

@pytest.mark.django_db
class TestCache:
    def test_list_is_served_from_cache_on_second_read(self, admin_client, topic):
        _create_question(admin_client, topic)
        first = admin_client.get(f"{BASE}/questions/?node_id={topic}")
        with patch("content.services.get_question") as never:
            second = admin_client.get(f"{BASE}/questions/?node_id={topic}")
        assert second.json() == first.json()
        never.assert_not_called()

    def test_write_invalidates_cached_lists_for_institution(self, admin_client, topic):
        admin_client.get(f"{BASE}/questions/?node_id={topic}")
        _create_question(admin_client, topic, "fresh?")
        listing = admin_client.get(f"{BASE}/questions/?node_id={topic}").json()
        assert listing["count"] == 1

    def test_content_writes_never_touch_practice_keys(self, admin_client, topic):
        cache.set("practice:institution:aaa:section:bbb:questions", ["kept"], 300)
        _create_question(admin_client, topic)
        assert cache.get("practice:institution:aaa:section:bbb:questions") == ["kept"]

    def test_cache_read_failure_falls_through_to_database(self, admin_client, topic):
        _create_question(admin_client, topic)
        broken = MagicMock()
        broken.get.side_effect = RuntimeError("redis down")
        with patch("content.cache.cache", broken):
            resp = admin_client.get(f"{BASE}/questions/?node_id={topic}")
        assert resp.status_code == 200 and resp.json()["count"] == 1

    def test_cache_write_failure_still_returns_200(self, admin_client, topic):
        half = MagicMock()
        half.get.return_value = 1
        half.set.side_effect = RuntimeError("redis down")
        with patch("content.cache.cache", half):
            resp = admin_client.get(f"{BASE}/nodes/?parent_id=null")
        assert resp.status_code == 200

    def test_failed_write_does_not_invalidate(self, admin_client, topic):
        first = admin_client.get(f"{BASE}/questions/?node_id={topic}").json()
        admin_client.post(f"{BASE}/questions/", {"node_id": topic, "text": "", "options": []}, format="json")
        assert admin_client.get(f"{BASE}/questions/?node_id={topic}").json() == first


# ── F3: throttling inherited from practice ─────────────────────────────────

@pytest.mark.django_db
class TestThrottling:
    def test_content_views_use_practice_default_throttles(self):
        for view_cls in (ContentQuestionListCreateView, ContentNodeListCreateView):
            types = [type(t) for t in view_cls().get_throttles()]
            assert ResilientUserRateThrottle in types


# ── G1, G2: logs, metrics source, no text leakage ─────────────────────────

@pytest.mark.django_db
class TestObservability:
    def test_request_log_has_endpoint_status_latency_and_request_id(self, admin_client, topic, caplog):
        with caplog.at_level(logging.INFO, logger="content.api"):
            admin_client.get(f"{BASE}/nodes/?parent_id=null", HTTP_X_REQUEST_ID="req-42")
        line = next(r.getMessage() for r in caplog.records if r.name == "content.api")
        assert "method=GET" in line and "status=200" in line and "latency_ms=" in line and "request_id=req-42" in line

    def test_audit_log_counts_each_write_action_without_text(self, admin_client, topic, caplog):
        secret = "PRIVATE-TEXT-7731"
        with caplog.at_level(logging.INFO, logger="content.audit"):
            _create_question(admin_client, topic, f"Question {secret}?")
        lines = [r.getMessage() for r in caplog.records if r.name == "content.audit"]
        assert any("action=question.create" in line for line in lines)
        assert all(secret not in line for line in lines)

    def test_health_reports_content_block(self, anon_client):
        resp = anon_client.get(f"{BASE}/health/")
        data = resp.json()["data"]
        assert resp.status_code == 200
        assert data["module"] == "content" and data["db"] == "ok" and data["cache"] == "ok"
        assert data["storage"] in ("configured", "not_configured")

    def test_health_404_when_flag_off(self, anon_client):
        with override_settings(CONTENT_BANK_ENABLED=False):
            assert anon_client.get(f"{BASE}/health/").status_code == 404

    def test_alert_definitions_cover_section_2_15(self):
        path = pathlib.Path(__file__).resolve().parent.parent / "content" / "ops_alerts.json"
        names = {a["name"] for a in json.loads(path.read_text(encoding="utf-8"))["alerts"]}
        assert names == {"content_5xx_rate_high", "content_orphan_growth",
                         "content_publish_latency_high", "content_health_dependency_down"}
