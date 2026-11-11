from unittest.mock import patch

import pytest
from django.test import override_settings

from content.models import ContentQuestionVersion
from core.storage import TransientStorageError
from tests.test_content_api import BASE, OPTS, _create_subject, _create_topic, _publish_node, _create_question


@pytest.fixture(autouse=True)
def bank_enabled():
    with override_settings(CONTENT_BANK_ENABLED=True):
        yield


@pytest.fixture
def draft_question(admin_client, db):
    subject = _create_subject(admin_client)
    _publish_node(admin_client, subject)
    topic = _create_topic(admin_client, subject)
    _publish_node(admin_client, topic)
    q = _create_question(admin_client, topic)
    return q.json()["data"]["id"], q.headers["ETag"]


def _issued_key(name="abc.png"):
    return f"uploads/content/{name}"


@pytest.mark.django_db
class TestPresign:
    def test_presign_issues_content_key_and_url(self, admin_client, draft_question):
        qid, etag = draft_question
        with patch("content.images.generate_presigned_upload_url", return_value="https://s3/put"):
            r = admin_client.post(f"{BASE}/questions/{qid}/image/presign/",
                                  {"filename": "chart.png", "content_type": "image/png"},
                                  format="json", HTTP_IF_MATCH=etag)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["file_key"].startswith("uploads/content/") and data["file_key"].endswith(".png")
        assert data["upload_url"] == "https://s3/put" and data["method"] == "PUT"

    def test_disallowed_extension_400(self, admin_client, draft_question):
        qid, etag = draft_question
        r = admin_client.post(f"{BASE}/questions/{qid}/image/presign/",
                              {"filename": "bad.svg", "content_type": "image/svg+xml"},
                              format="json", HTTP_IF_MATCH=etag)
        assert r.status_code == 415 and r.json()["code"] == "image_type_unsupported"

    def test_disallowed_mime_400(self, admin_client, draft_question):
        qid, etag = draft_question
        r = admin_client.post(f"{BASE}/questions/{qid}/image/presign/",
                              {"filename": "x.png", "content_type": "application/octet-stream"},
                              format="json", HTTP_IF_MATCH=etag)
        assert r.status_code == 415 and r.json()["code"] == "image_type_unsupported"

    def test_storage_not_configured_503(self, admin_client, draft_question):
        qid, etag = draft_question
        with patch("content.images.generate_presigned_upload_url", side_effect=RuntimeError("no creds")):
            r = admin_client.post(f"{BASE}/questions/{qid}/image/presign/",
                                  {"filename": "a.png", "content_type": "image/png"},
                                  format="json", HTTP_IF_MATCH=etag)
        assert r.status_code == 503 and r.json()["code"] == "storage_unavailable"

    def test_presign_without_if_match_428(self, admin_client, draft_question):
        qid, _ = draft_question
        r = admin_client.post(f"{BASE}/questions/{qid}/image/presign/",
                              {"filename": "a.png", "content_type": "image/png"}, format="json")
        assert r.status_code == 428

    def test_presign_without_draft_409(self, admin_client, draft_question):
        qid, etag = draft_question
        admin_client.post(f"{BASE}/questions/{qid}/publish/", format="json", HTTP_IF_MATCH=etag)
        r = admin_client.post(f"{BASE}/questions/{qid}/image/presign/",
                              {"filename": "a.png", "content_type": "image/png"}, format="json")
        assert r.status_code == 409 and r.json()["code"] == "invalid_transition"


@pytest.mark.django_db
class TestConfirm:
    def _confirm(self, client, qid, etag, key, alt="A bar chart of sales"):
        return client.post(f"{BASE}/questions/{qid}/image/confirm/",
                           {"file_key": key, "image_alt_text": alt}, format="json", HTTP_IF_MATCH=etag)

    def test_clean_image_attaches_with_alt_text(self, admin_client, draft_question):
        qid, etag = draft_question
        key = _issued_key()
        with patch("content.images.verify_uploaded_image", return_value=(1234, None)), \
             patch("content.images.scan_image_for_malware", return_value=None), \
             patch("content.images._delete_rejected") as rejected:
            r = self._confirm(admin_client, qid, etag, key)
        assert r.status_code == 200
        assert r.json()["data"]["editable_version"]["image_key"] == key
        assert r.json()["data"]["editable_version"]["image_alt_text"] == "A bar chart of sales"
        rejected.assert_not_called()
        assert r.headers.get("ETag") and r.headers["ETag"] != etag

    def test_missing_alt_text_refused_before_any_storage_call(self, admin_client, draft_question):
        qid, etag = draft_question
        with patch("content.images.verify_uploaded_image") as verify:
            r = self._confirm(admin_client, qid, etag, _issued_key(), alt="   ")
        assert r.status_code == 400 and "image_alt_text" in r.json()["errors"]
        verify.assert_not_called()

    def test_key_not_issued_by_content_refused(self, admin_client, draft_question):
        qid, etag = draft_question
        with patch("content.images.verify_uploaded_image") as verify:
            r = self._confirm(admin_client, qid, etag, "uploads/image/practice-owned.png")
        assert r.status_code == 400 and r.json()["code"] == "image_rejected"
        verify.assert_not_called()

    def test_path_traversal_key_refused(self, admin_client, draft_question):
        qid, etag = draft_question
        r = self._confirm(admin_client, qid, etag, "uploads/content/../../practice/secret.png")
        assert r.status_code == 400 and r.json()["code"] == "image_rejected"

    def test_bad_contents_deleted_and_400(self, admin_client, draft_question):
        qid, etag = draft_question
        key = _issued_key("fake.png")
        with patch("content.images.verify_uploaded_image", return_value=(None, "Image contents do not match a supported image format.")), \
             patch("content.images._delete_rejected") as rejected:
            r = self._confirm(admin_client, qid, etag, key)
        assert r.status_code == 415 and r.json()["code"] == "image_type_unsupported"
        rejected.assert_called_once_with(key)

    def test_malware_deleted_and_400(self, admin_client, draft_question):
        qid, etag = draft_question
        key = _issued_key("virus.png")
        with patch("content.images.verify_uploaded_image", return_value=(10, None)), \
             patch("content.images.scan_image_for_malware", return_value="Malware detected."), \
             patch("content.images._delete_rejected") as rejected:
            r = self._confirm(admin_client, qid, etag, key)
        assert r.status_code == 400
        rejected.assert_called_once_with(key)

    def test_storage_outage_during_verify_is_503_and_object_kept(self, admin_client, draft_question):
        qid, etag = draft_question
        with patch("content.images.verify_uploaded_image", side_effect=TransientStorageError("s3 down")), \
             patch("content.images._delete_rejected") as rejected:
            r = self._confirm(admin_client, qid, etag, _issued_key())
        assert r.status_code == 503 and r.json()["code"] == "storage_unavailable"
        rejected.assert_not_called()

    def test_scanner_outage_is_503_and_object_kept(self, admin_client, draft_question):
        qid, etag = draft_question
        with patch("content.images.verify_uploaded_image", return_value=(10, None)), \
             patch("content.images.scan_image_for_malware", side_effect=TransientStorageError("clamav down")), \
             patch("content.images._delete_rejected") as rejected:
            r = self._confirm(admin_client, qid, etag, _issued_key())
        assert r.status_code == 503
        rejected.assert_not_called()

    def test_scanner_not_configured_is_503_not_silent_pass(self, admin_client, draft_question):
        qid, etag = draft_question
        with patch("content.images.verify_uploaded_image", return_value=(10, None)), \
             patch("content.images.scan_image_for_malware", side_effect=RuntimeError("no clamav")):
            r = self._confirm(admin_client, qid, etag, _issued_key())
        assert r.status_code == 503

    def test_stale_etag_on_confirm_412_and_orphan_released(self, admin_client, draft_question):
        qid, etag = draft_question
        admin_client.patch(f"{BASE}/questions/{qid}/", {"text": "Changed?"}, format="json", HTTP_IF_MATCH=etag)
        with patch("content.images.verify_uploaded_image", return_value=(10, None)), \
             patch("content.images.scan_image_for_malware", return_value=None), \
             patch("content.services.release_keys_after_commit") as release, \
             patch("content.images.release_keys_after_commit") as release_img:
            r = self._confirm(admin_client, qid, etag, _issued_key("late.png"))
        assert r.status_code == 412
        release_img.assert_called_once()
        assert "uploads/content/late.png" in release_img.call_args.args[0]

    def test_replacing_image_releases_old_key(self, admin_client, draft_question):
        qid, etag = draft_question
        with patch("content.images.verify_uploaded_image", return_value=(10, None)), \
             patch("content.images.scan_image_for_malware", return_value=None):
            r1 = self._confirm(admin_client, qid, etag, _issued_key("one.png"))
            etag2 = r1.headers["ETag"]
            with patch("content.images.release_keys_after_commit") as release:
                r2 = self._confirm(admin_client, qid, etag2, _issued_key("two.png"))
        assert r2.status_code == 200
        assert "uploads/content/one.png" in release.call_args.args[0]


@pytest.mark.django_db
class TestRemove:
    def test_remove_clears_key_and_alt_text(self, admin_client, draft_question):
        qid, etag = draft_question
        with patch("content.images.verify_uploaded_image", return_value=(10, None)), \
             patch("content.images.scan_image_for_malware", return_value=None):
            r1 = admin_client.post(f"{BASE}/questions/{qid}/image/confirm/",
                                   {"file_key": _issued_key("gone.png"), "image_alt_text": "x"},
                                   format="json", HTTP_IF_MATCH=etag)
        with patch("content.images.release_keys_after_commit") as release:
            r2 = admin_client.delete(f"{BASE}/questions/{qid}/image/", HTTP_IF_MATCH=r1.headers["ETag"])
        assert r2.status_code == 200
        version = r2.json()["data"]["editable_version"]
        assert version["image_key"] == "" and version["image_alt_text"] == ""
        assert "uploads/content/gone.png" in release.call_args.args[0]

    def test_image_route_rejects_post(self, admin_client, draft_question):
        qid, etag = draft_question
        r = admin_client.post(f"{BASE}/questions/{qid}/image/", {"file_key": _issued_key()}, format="json",
                              HTTP_IF_MATCH=etag)
        assert r.status_code == 405

    def test_published_version_keeps_its_image_key(self, admin_client, draft_question):
        qid, etag = draft_question
        with patch("content.images.verify_uploaded_image", return_value=(10, None)), \
             patch("content.images.scan_image_for_malware", return_value=None):
            r1 = admin_client.post(f"{BASE}/questions/{qid}/image/confirm/",
                                   {"file_key": _issued_key("keep.png"), "image_alt_text": "keep"},
                                   format="json", HTTP_IF_MATCH=etag)
        admin_client.post(f"{BASE}/questions/{qid}/publish/", format="json", HTTP_IF_MATCH=r1.headers["ETag"])
        pub = ContentQuestionVersion.objects.get(question_id=qid, version_no=1)
        assert pub.image_key == _issued_key("keep.png") and pub.state == "published"


@pytest.mark.django_db
class TestRejectionStatuses:
    """LIVETRACKER4 section 2.13: oversized file 413, wrong content for its type 415."""

    def test_oversized_image_is_413_and_object_deleted(self, admin_client, draft_question):
        qid, etag = draft_question
        key = _issued_key("big.png")
        with patch("content.images.verify_uploaded_image",
                   return_value=(None, "Image exceeds the 5 MB limit.")), \
             patch("content.images._delete_rejected") as rejected:
            r = admin_client.post(f"{BASE}/questions/{qid}/image/confirm/",
                                  {"file_key": key, "image_alt_text": "x"}, format="json", HTTP_IF_MATCH=etag)
        assert r.status_code == 413 and r.json()["code"] == "image_too_large"
        rejected.assert_called_once_with(key)
