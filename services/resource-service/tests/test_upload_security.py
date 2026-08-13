import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "nope"}}, "HeadObject")


@pytest.mark.django_db
class TestVerifyUploadedObject:
    """core.storage.verify_uploaded_object — the ground-truth check against
    what actually landed in storage (never the client-reported size/type)."""

    def test_object_not_found_in_storage(self, settings):
        settings.R2_ACCESS_KEY_ID = "test-key"
        mock_client = MagicMock()
        mock_client.head_object.side_effect = _client_error("404")
        with patch("boto3.client", return_value=mock_client):
            from core.storage import verify_uploaded_object
            real_size, error = verify_uploaded_object("uploads/pdf/x.pdf", "pdf")
        assert real_size is None
        assert "not found" in error.lower()

    def test_rejects_oversized_object(self, settings):
        settings.R2_ACCESS_KEY_ID = "test-key"
        mock_client = MagicMock()
        mock_client.head_object.return_value = {"ContentLength": 100 * 1024 * 1024}  # 100MB > 25MB pdf cap
        with patch("boto3.client", return_value=mock_client):
            from core.storage import verify_uploaded_object
            real_size, error = verify_uploaded_object("uploads/pdf/x.pdf", "pdf")
        assert real_size is None
        assert "25 MB" in error

    def test_rejects_magic_byte_mismatch(self, settings):
        settings.R2_ACCESS_KEY_ID = "test-key"
        mock_client = MagicMock()
        mock_client.head_object.return_value = {"ContentLength": 1024}
        body = MagicMock()
        body.read.return_value = b"<html><script>alert(1)</script>"  # not a real PDF
        mock_client.get_object.return_value = {"Body": body}
        with patch("boto3.client", return_value=mock_client):
            from core.storage import verify_uploaded_object
            real_size, error = verify_uploaded_object("uploads/pdf/x.pdf", "pdf")
        assert real_size is None
        assert "do not match" in error.lower()

    def test_accepts_valid_pdf(self, settings):
        settings.R2_ACCESS_KEY_ID = "test-key"
        mock_client = MagicMock()
        mock_client.head_object.return_value = {"ContentLength": 2048}
        body = MagicMock()
        body.read.return_value = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3"
        mock_client.get_object.return_value = {"Body": body}
        with patch("boto3.client", return_value=mock_client):
            from core.storage import verify_uploaded_object
            real_size, error = verify_uploaded_object("uploads/pdf/x.pdf", "pdf")
        assert error is None
        assert real_size == 2048


@pytest.mark.django_db
class TestScanUploadedFileTask:
    def test_clamav_not_configured_leaves_status_unchanged(self, upload, settings):
        settings.CLAMAV_HOST = ""
        upload.scan_status = "pending"
        upload.save(update_fields=["scan_status"])
        from resources.tasks import scan_uploaded_file
        scan_uploaded_file(str(upload.pk), "Upload")
        upload.refresh_from_db()
        assert upload.scan_status == "pending"  # no-op — stays hidden from students until scanned

    @patch("core.storage.get_object_stream")
    def test_clean_verdict_marks_clean(self, mock_stream, upload, settings):
        settings.CLAMAV_HOST = "clamav"
        upload.scan_status = "pending"
        upload.save(update_fields=["scan_status"])
        mock_stream.return_value = MagicMock()
        with patch("clamd.ClamdNetworkSocket") as mock_cd_cls:
            mock_cd_cls.return_value.instream.return_value = {"stream": ("OK", None)}
            from resources.tasks import scan_uploaded_file
            scan_uploaded_file(str(upload.pk), "Upload")
        upload.refresh_from_db()
        assert upload.scan_status == "clean"

    @patch("core.storage.delete_file")
    @patch("core.storage.get_object_stream")
    def test_infected_verdict_deletes_object_and_record(self, mock_stream, mock_delete, upload, settings):
        settings.CLAMAV_HOST = "clamav"
        upload.scan_status = "pending"
        upload.save(update_fields=["scan_status"])
        upload_pk = upload.pk
        file_key = upload.file_url
        mock_stream.return_value = MagicMock()
        with patch("clamd.ClamdNetworkSocket") as mock_cd_cls:
            mock_cd_cls.return_value.instream.return_value = {"stream": ("FOUND", "Eicar-Test-Signature")}
            from resources.tasks import scan_uploaded_file
            scan_uploaded_file(str(upload_pk), "Upload")
        from resources.models import Upload
        assert not Upload.objects.filter(pk=upload_pk).exists()
        mock_delete.assert_called_once_with(file_key)
