import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from content.models import ContentNode, ContentQuestion, ContentQuestionUsage
from tests.conftest import INSTITUTION_A, ADMIN_USER_ID, _make_token

BASE = "/api/practice/content"
OPTS = [
    {"option_text": "Alpha", "is_correct": True},
    {"option_text": "Beta", "is_correct": False},
    {"option_text": "Gamma", "is_correct": False},
]


@pytest.fixture(autouse=True)
def bank_enabled():
    with override_settings(CONTENT_BANK_ENABLED=True):
        yield


@pytest.fixture
def super_client(db):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {_make_token(uuid.uuid4(), 'super_admin', INSTITUTION_A)}")
    return client


def _create_subject(client, name="Reasoning"):
    r = client.post(f"{BASE}/nodes/", {"name": name}, format="json")
    assert r.status_code == 201, r.json()
    return r.json()["data"]["id"]


def _create_topic(client, parent_id, name="Puzzles"):
    r = client.post(f"{BASE}/nodes/", {"name": name, "parent_id": parent_id}, format="json")
    assert r.status_code == 201, r.json()
    return r.json()["data"]["id"]


def _publish_node(client, node_id):
    assert client.post(f"{BASE}/nodes/{node_id}/publish/", format="json").status_code == 200


def _create_question(client, topic_id, text="What is 2+2?"):
    r = client.post(f"{BASE}/questions/", {"node_id": topic_id, "text": text, "options": OPTS}, format="json")
    assert r.status_code == 201, r.json()
    return r


@pytest.fixture
def topic(admin_client, db):
    subject = _create_subject(admin_client)
    _publish_node(admin_client, subject)
    t = _create_topic(admin_client, subject)
    _publish_node(admin_client, t)
    return t


# ── smoke and flag ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestFeatureFlag:
    def test_all_endpoints_404_when_flag_off(self, admin_client):
        with override_settings(CONTENT_BANK_ENABLED=False):
            assert admin_client.get(f"{BASE}/nodes/").status_code == 404
            assert admin_client.post(f"{BASE}/nodes/", {"name": "x"}, format="json").status_code == 404
            assert admin_client.get(f"{BASE}/questions/").status_code == 404

    def test_practice_routes_unaffected(self, admin_client):
        assert admin_client.get("/api/practice/").status_code == 200

    def test_health_of_practice_unchanged(self, anon_client):
        resp = anon_client.get("/api/practice/health/")
        assert resp.status_code == 200
        assert set(resp.json()["data"].keys()) >= {"status", "service", "db", "redis"}


# ── authorization and isolation ─────────────────────────────────────────────

@pytest.mark.django_db
class TestAuthorization:
    def test_anonymous_is_401(self, anon_client):
        assert anon_client.get(f"{BASE}/nodes/").status_code == 401

    def test_student_is_403_on_every_admin_endpoint(self, student_client):
        assert student_client.get(f"{BASE}/nodes/").status_code == 403
        assert student_client.get(f"{BASE}/questions/").status_code == 403
        assert student_client.post(f"{BASE}/nodes/", {"name": "x"}, format="json").status_code == 403

    def test_audit_is_super_admin_only(self, admin_client, super_client):
        assert admin_client.get(f"{BASE}/audit/").status_code == 403
        assert super_client.get(f"{BASE}/audit/").status_code == 200

    def test_cross_institution_node_is_404_not_403(self, admin_client, admin_b_client):
        subject = _create_subject(admin_client)
        assert admin_b_client.get(f"{BASE}/nodes/{subject}/").status_code == 404

    def test_cross_institution_question_is_404(self, admin_client, admin_b_client, topic):
        q = _create_question(admin_client, topic["id"] if isinstance(topic, dict) else topic)
        qid = q.json()["data"]["id"]
        assert admin_b_client.get(f"{BASE}/questions/{qid}/").status_code == 404
        assert admin_b_client.patch(f"{BASE}/questions/{qid}/", {"text": "x"}, format="json",
                                    HTTP_IF_MATCH=q.headers["ETag"]).status_code == 404

    def test_audit_has_no_update_or_delete_route(self, super_client):
        assert super_client.patch(f"{BASE}/audit/", {}, format="json").status_code == 405
        assert super_client.delete(f"{BASE}/audit/").status_code == 405


# ── nodes ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestNodeEndpoints:
    def test_create_root_201_and_list(self, admin_client):
        _create_subject(admin_client, "Alpha")
        r = admin_client.get(f"{BASE}/nodes/?parent_id=null")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1 and body["results"][0]["name"] == "Alpha"

    def test_duplicate_name_409_with_code(self, admin_client):
        _create_subject(admin_client, "Alpha")
        r = admin_client.post(f"{BASE}/nodes/", {"name": "alpha"}, format="json")
        assert r.status_code == 409 and r.json()["code"] == "duplicate_name"
        assert r.json()["success"] is False

    def test_invalid_parent_id_400(self, admin_client):
        r = admin_client.post(f"{BASE}/nodes/", {"name": "x", "parent_id": "not-a-uuid"}, format="json")
        assert r.status_code == 400

    def test_mass_assignment_ignored(self, admin_client):
        r = admin_client.post(f"{BASE}/nodes/", {"name": "x", "status": "published",
                                                 "institution_id": str(uuid.uuid4())}, format="json")
        assert r.status_code == 201
        assert r.json()["data"]["status"] == "draft"
        assert ContentNode.objects.get(pk=r.json()["data"]["id"]).institution_id == INSTITUTION_A

    def test_publish_retire_restore_actions(self, admin_client):
        sid = _create_subject(admin_client)
        assert admin_client.post(f"{BASE}/nodes/{sid}/publish/", format="json").json()["data"]["status"] == "published"
        assert admin_client.post(f"{BASE}/nodes/{sid}/retire/", format="json").json()["data"]["status"] == "retired"
        assert admin_client.post(f"{BASE}/nodes/{sid}/restore/", format="json").json()["data"]["status"] == "published"

    def test_unknown_action_404(self, admin_client):
        sid = _create_subject(admin_client)
        assert admin_client.post(f"{BASE}/nodes/{sid}/explode/", format="json").status_code == 404

    def test_delete_non_empty_node_409(self, admin_client, topic):
        parent = ContentNode.objects.get(pk=topic["id"] if isinstance(topic, dict) else topic).parent_id
        r = admin_client.delete(f"{BASE}/nodes/{parent}/")
        assert r.status_code == 409 and r.json()["code"] == "node_not_empty"

    def test_node_reorder_endpoint(self, admin_client):
        a = _create_subject(admin_client, "A")
        b = _create_subject(admin_client, "B")
        r = admin_client.post(f"{BASE}/nodes/reorder/", {"parent_id": None, "node_ids": [b, a]}, format="json")
        assert r.status_code == 200
        bad = admin_client.post(f"{BASE}/nodes/reorder/", {"parent_id": None, "node_ids": [a]}, format="json")
        assert bad.status_code == 409 and bad.json()["code"] == "set_mismatch"


# ── questions and concurrency ───────────────────────────────────────────────

def _topic_id(topic):
    return topic["id"] if isinstance(topic, dict) else topic


@pytest.mark.django_db
class TestQuestionEndpoints:
    def test_create_201_with_etag_and_no_mass_assignment(self, admin_client, topic):
        r = admin_client.post(f"{BASE}/questions/", {"node_id": _topic_id(topic), "text": "Q?",
                                                     "options": OPTS, "status": "published"}, format="json")
        assert r.status_code == 201
        assert r.json()["data"]["status"] == "draft"
        assert r.headers.get("ETag")

    def test_list_hides_answer_key_detail_shows_it_to_admin(self, admin_client, topic):
        qid = _create_question(admin_client, _topic_id(topic)).json()["data"]["id"]
        listing = admin_client.get(f"{BASE}/questions/?node_id={_topic_id(topic)}").json()["results"][0]
        assert all("is_correct" not in o for o in listing["editable_version"]["options"])
        detail = admin_client.get(f"{BASE}/questions/{qid}/").json()["data"]
        assert any(o["is_correct"] for o in detail["editable_version"]["options"])

    def test_patch_without_if_match_428(self, admin_client, topic):
        q = _create_question(admin_client, _topic_id(topic))
        qid = q.json()["data"]["id"]
        r = admin_client.patch(f"{BASE}/questions/{qid}/", {"text": "New?"}, format="json")
        assert r.status_code == 428 and r.json()["code"] == "precondition_required"

    def test_patch_with_stale_etag_412_then_fresh_ok(self, admin_client, topic):
        q = _create_question(admin_client, _topic_id(topic))
        qid = q.json()["data"]["id"]
        stale = q.headers["ETag"]
        ok = admin_client.patch(f"{BASE}/questions/{qid}/", {"text": "First?"}, format="json", HTTP_IF_MATCH=stale)
        assert ok.status_code == 200 and ok.headers["ETag"] != stale
        r = admin_client.patch(f"{BASE}/questions/{qid}/", {"text": "Second?"}, format="json", HTTP_IF_MATCH=stale)
        assert r.status_code == 412 and r.json()["code"] == "stale_version"
        assert "current_etag" in r.json()["errors"]

    def test_publish_then_repeat_is_idempotent_200(self, admin_client, topic):
        q = _create_question(admin_client, _topic_id(topic))
        qid = q.json()["data"]["id"]
        etag = q.headers["ETag"]
        first = admin_client.post(f"{BASE}/questions/{qid}/publish/", format="json", HTTP_IF_MATCH=etag)
        assert first.status_code == 200 and first.json()["data"]["status"] == "published"
        again = admin_client.post(f"{BASE}/questions/{qid}/publish/", format="json", HTTP_IF_MATCH=etag)
        assert again.status_code == 200

    def test_publish_validation_errors_listed(self, admin_client, topic):
        r = admin_client.post(f"{BASE}/questions/", {"node_id": _topic_id(topic), "text": "Q?",
                                                     "options": [{"option_text": "A", "is_correct": True}]},
                              format="json")
        qid = r.json()["data"]["id"]
        pub = admin_client.post(f"{BASE}/questions/{qid}/publish/", format="json", HTTP_IF_MATCH=r.headers["ETag"])
        assert pub.status_code == 400 and pub.json()["code"] == "validation_error"
        assert "options" in pub.json()["errors"]

    def test_invalid_question_action_404(self, admin_client, topic):
        qid = _create_question(admin_client, _topic_id(topic)).json()["data"]["id"]
        assert admin_client.post(f"{BASE}/questions/{qid}/teleport/", format="json").status_code == 404

    def test_delete_used_question_409_retire_message(self, admin_client, topic):
        q = _create_question(admin_client, _topic_id(topic))
        qid = q.json()["data"]["id"]
        ContentQuestionUsage.objects.create(question_id=qid, version_no=1, usage_type="generated_paper",
                                            usage_ref_id=uuid.uuid4())
        r = admin_client.delete(f"{BASE}/questions/{qid}/")
        assert r.status_code == 409 and r.json()["code"] == "used_question"
        assert ContentQuestion.objects.filter(pk=qid).exists()

    def test_question_reorder_missing_id_409(self, admin_client, topic):
        a = _create_question(admin_client, _topic_id(topic), "a?").json()["data"]["id"]
        _create_question(admin_client, _topic_id(topic), "b?")
        r = admin_client.post(f"{BASE}/questions/reorder/",
                              {"node_id": _topic_id(topic), "question_ids": [a]}, format="json")
        assert r.status_code == 409 and r.json()["code"] == "set_mismatch"

    def test_discard_draft_endpoint(self, admin_client, topic):
        q = _create_question(admin_client, _topic_id(topic))
        qid = q.json()["data"]["id"]
        etag = q.headers["ETag"]
        admin_client.post(f"{BASE}/questions/{qid}/publish/", format="json", HTTP_IF_MATCH=etag)
        published = admin_client.get(f"{BASE}/questions/{qid}/").headers["ETag"]
        admin_client.patch(f"{BASE}/questions/{qid}/", {"text": "Draft?"}, format="json", HTTP_IF_MATCH=published)
        current = admin_client.get(f"{BASE}/questions/{qid}/").headers["ETag"]
        r = admin_client.post(f"{BASE}/questions/{qid}/discard-draft/", format="json", HTTP_IF_MATCH=current)
        assert r.status_code == 200
        assert r.json()["data"]["editable_version"]["state"] == "published"


# ── versions ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestVersionEndpoints:
    def test_version_list_and_read(self, admin_client, topic):
        q = _create_question(admin_client, _topic_id(topic))
        qid = q.json()["data"]["id"]
        admin_client.post(f"{BASE}/questions/{qid}/publish/", format="json", HTTP_IF_MATCH=q.headers["ETag"])
        listing = admin_client.get(f"{BASE}/questions/{qid}/versions/").json()["data"]
        assert listing[0]["version_no"] == 1 and listing[0]["state"] == "published"
        one = admin_client.get(f"{BASE}/questions/{qid}/versions/1/").json()["data"]
        assert one["question_text"] == "What is 2+2?"

    def test_missing_version_404(self, admin_client, topic):
        qid = _create_question(admin_client, _topic_id(topic)).json()["data"]["id"]
        assert admin_client.get(f"{BASE}/questions/{qid}/versions/99/").status_code == 404


# ── pagination and audit ────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPaginationAndAudit:
    def test_list_envelope_matches_practice_pagination(self, admin_client, topic):
        _create_question(admin_client, _topic_id(topic))
        body = admin_client.get(f"{BASE}/questions/").json()
        assert {"count", "total_pages", "current_page", "next", "previous", "results"} <= set(body.keys())

    def test_audit_lists_events_for_super_admin(self, admin_client, super_client, topic):
        _create_question(admin_client, _topic_id(topic))
        body = super_client.get(f"{BASE}/audit/").json()
        assert body["count"] >= 1
        assert all("summary" in row for row in body["results"])
