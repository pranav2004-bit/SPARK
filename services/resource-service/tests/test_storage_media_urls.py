"""Tests for core.storage's self-hosted media read path (BUG-009,
2026-11-28). Every file read was broken on self-hosted storage because
get_cdn_url() silently fell back to a bare storage key when
AWS_S3_CDN_DOMAIN was empty — which is the deliberate, documented state for
self-hosted deployments (there is no CDN in front of SeaweedFS). Confirmed
live that SeaweedFS's S3 gateway rejects every unauthenticated GET with a
403, so self-hosted reads need a presigned URL exactly like uploads already
get via generate_presigned_upload_url().
"""
import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "nope"}}, "GetObject")


@pytest.mark.django_db
class TestGeneratePresignedReadUrl:
    """core.storage.generate_presigned_read_url — the read-side counterpart
    to generate_presigned_upload_url, added to fix BUG-009."""

    def test_calls_get_object_with_correct_params(self, settings):
        settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
        settings.AWS_S3_PRESIGNED_URL_EXPIRY = 1800
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = (
            "http://seaweedfs:8333/test-bucket/uploads/pdf/x.pdf?X-Amz-Signature=abc"
        )
        with patch("boto3.client", return_value=mock_client):
            from core.storage import generate_presigned_read_url
            url = generate_presigned_read_url("uploads/pdf/x.pdf")

        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-bucket", "Key": "uploads/pdf/x.pdf"},
            ExpiresIn=1800,
        )
        assert url == "http://seaweedfs:8333/test-bucket/uploads/pdf/x.pdf?X-Amz-Signature=abc"

    def test_uses_default_expiry_when_not_specified(self, settings):
        settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
        settings.AWS_S3_PRESIGNED_URL_EXPIRY = 3600
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "http://seaweedfs:8333/x"
        with patch("boto3.client", return_value=mock_client):
            from core.storage import generate_presigned_read_url
            generate_presigned_read_url("uploads/pdf/x.pdf")

        _, kwargs = mock_client.generate_presigned_url.call_args
        assert kwargs["ExpiresIn"] == 3600

    def test_propagates_client_error(self, settings):
        settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
        mock_client = MagicMock()
        mock_client.generate_presigned_url.side_effect = _client_error("500")
        with patch("boto3.client", return_value=mock_client):
            from core.storage import generate_presigned_read_url
            with pytest.raises(ClientError):
                generate_presigned_read_url("uploads/pdf/x.pdf")


@pytest.mark.django_db
class TestGetCdnUrlSelfHosted:
    """core.storage.get_cdn_url — self-hosted branch (AWS_S3_ENDPOINT_URL
    set). Confirmed live (2026-11-28) that SeaweedFS's S3 gateway returns
    403 on an unauthenticated GET, so this branch must produce a signed
    URL, not a bare key or an unsigned domain+key concatenation."""

    def test_rewrites_internal_host_to_public_base(self, settings):
        settings.AWS_S3_ENDPOINT_URL = "http://seaweedfs:8333"
        settings.AWS_S3_PUBLIC_MEDIA_BASE_URL = "https://api.spark.sanjivo.com/media"
        settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = (
            "http://seaweedfs:8333/test-bucket/uploads/pdf/x.pdf"
            "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=abc123"
        )
        with patch("boto3.client", return_value=mock_client):
            from core.storage import get_cdn_url
            url = get_cdn_url("uploads/pdf/x.pdf")

        assert url == (
            "https://api.spark.sanjivo.com/media/test-bucket/uploads/pdf/x.pdf"
            "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=abc123"
        )

    def test_preserves_signature_query_string_exactly(self, settings):
        """The whole point of the host-swap approach: path + query string
        (the actual signature) must pass through byte-for-byte, or the
        signature SeaweedFS validates against won't match what was signed."""
        settings.AWS_S3_ENDPOINT_URL = "http://seaweedfs:8333"
        settings.AWS_S3_PUBLIC_MEDIA_BASE_URL = "https://api.spark.sanjivo.com/media"
        settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
        signed_query = (
            "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=abc%2F20261128"
            "&X-Amz-Signature=deadbeef"
        )
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = (
            f"http://seaweedfs:8333/test-bucket/uploads/image/y.png{signed_query}"
        )
        with patch("boto3.client", return_value=mock_client):
            from core.storage import get_cdn_url
            url = get_cdn_url("uploads/image/y.png")

        assert url.endswith(signed_query)

    def test_raises_when_public_base_url_missing(self, settings):
        """Fail loudly at call time, not with a broken link silently handed
        to the frontend — exactly how BUG-009 went unnoticed (the bare-key
        fallback looked superficially like a valid value)."""
        settings.AWS_S3_ENDPOINT_URL = "http://seaweedfs:8333"
        settings.AWS_S3_PUBLIC_MEDIA_BASE_URL = ""
        settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
        from core.storage import get_cdn_url
        with pytest.raises(RuntimeError, match="AWS_S3_PUBLIC_MEDIA_BASE_URL"):
            get_cdn_url("uploads/pdf/x.pdf")


@pytest.mark.django_db
class TestGetCdnUrlRealAws:
    """core.storage.get_cdn_url — real-AWS branch (AWS_S3_ENDPOINT_URL
    empty), unchanged by the BUG-009 fix. Regression coverage only."""

    def test_concatenates_cdn_domain_and_key(self, settings):
        settings.AWS_S3_ENDPOINT_URL = ""
        settings.AWS_S3_CDN_DOMAIN = "media.example.com"
        from core.storage import get_cdn_url
        assert get_cdn_url("uploads/pdf/x.pdf") == "https://media.example.com/uploads/pdf/x.pdf"

    def test_localhost_cdn_domain_uses_http(self, settings):
        settings.AWS_S3_ENDPOINT_URL = ""
        settings.AWS_S3_CDN_DOMAIN = "localhost:9000"
        from core.storage import get_cdn_url
        assert get_cdn_url("uploads/pdf/x.pdf") == "http://localhost:9000/uploads/pdf/x.pdf"

    def test_falls_back_to_bare_key_when_cdn_domain_empty(self, settings):
        settings.AWS_S3_ENDPOINT_URL = ""
        settings.AWS_S3_CDN_DOMAIN = ""
        from core.storage import get_cdn_url
        assert get_cdn_url("uploads/pdf/x.pdf") == "uploads/pdf/x.pdf"
