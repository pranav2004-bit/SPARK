from unittest.mock import patch

import pytest
from django.db import OperationalError
from django.test import override_settings
from rest_framework.test import APIClient

from content import services as svc
from content.models import ContentQuestion, ContentQuestionVersion
from tests.conftest import INSTITUTION_A, ADMIN_USER_ID
from tests.test_content_api import BASE, OPTS, _create_subject, _create_topic, _publish_node, _create_question


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


@pytest.mark.django_db
class TestSecurityExtras:
    def test_script_payload_stored_and_returned_as_plain_text(self, admin_client, topic):
        payload = "<script>alert(1)</script>"
        q = _create_question(admin_client, topic, payload)
        assert q.json()["data"]["editable_version"]["question_text"] == payload
        assert ContentQuestionVersion.objects.filter(question_text=payload).exists()

    def test_cookie_only_request_is_rejected(self, db):
        client = APIClient()
        client.cookies["sessionid"] = "anything"
        assert client.get(f"{BASE}/nodes/").status_code == 401

    def test_page_size_is_capped_by_practice_pagination(self, admin_client, topic):
        for i in range(3):
            _create_question(admin_client, topic, f"q{i}?")
        body = admin_client.get(f"{BASE}/questions/?page_size=100000").json()
        assert body["count"] == 3
        assert len(body["results"]) <= 200

    def test_admin_list_responses_never_include_answer_key(self, admin_client, topic):
        _create_question(admin_client, topic)
        body = admin_client.get(f"{BASE}/questions/?node_id={topic}").content.decode()
        assert "is_correct" not in body


@pytest.mark.django_db
class TestResilience:
    def test_database_outage_returns_503_not_500(self, admin_client, topic):
        with patch("content.services.get_node", side_effect=OperationalError("db down")):
            r = admin_client.get(f"{BASE}/nodes/{topic}/")
        assert r.status_code == 503 and r.json()["code"] == "dependency_unavailable"

    def test_publish_crash_mid_way_rolls_back_everything(self, admin_client, topic):
        created = _create_question(admin_client, topic)
        qid = created.json()["data"]["id"]
        etag = created.headers["ETag"]
        with patch("content.services.write_audit", side_effect=RuntimeError("crash after freeze")):
            with pytest.raises(RuntimeError):
                svc.publish_question(institution_id=INSTITUTION_A, actor_id=ADMIN_USER_ID,
                                     question_id=qid, if_match=etag)
        q = ContentQuestion.objects.get(pk=qid)
        assert q.status == "draft" and q.published_version_no is None
        assert ContentQuestionVersion.objects.get(question=q, version_no=1).state == "draft"

    def test_retry_after_crash_succeeds(self, admin_client, topic):
        created = _create_question(admin_client, topic)
        qid = created.json()["data"]["id"]
        etag = created.headers["ETag"]
        with patch("content.services.write_audit", side_effect=RuntimeError("crash")):
            with pytest.raises(RuntimeError):
                svc.publish_question(institution_id=INSTITUTION_A, actor_id=ADMIN_USER_ID,
                                     question_id=qid, if_match=etag)
        r = admin_client.post(f"{BASE}/questions/{qid}/publish/", format="json", HTTP_IF_MATCH=etag)
        assert r.status_code == 200 and r.json()["data"]["status"] == "published"

    def test_double_click_publish_is_idempotent(self, admin_client, topic):
        created = _create_question(admin_client, topic)
        qid = created.json()["data"]["id"]
        etag = created.headers["ETag"]
        a = admin_client.post(f"{BASE}/questions/{qid}/publish/", format="json", HTTP_IF_MATCH=etag)
        b = admin_client.post(f"{BASE}/questions/{qid}/publish/", format="json", HTTP_IF_MATCH=etag)
        assert a.status_code == 200 and b.status_code == 200
        assert ContentQuestionVersion.objects.filter(question_id=qid, version_no=1, state="published").count() == 1
