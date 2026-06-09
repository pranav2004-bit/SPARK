"""
Cloudflare R2 storage layer with CDN delivery.

Upload flow:
  1. Admin calls get-upload-url → backend generates a presigned S3 PUT URL
  2. Browser PUTs the file directly to R2 (backend never handles binary data)
  3. Admin calls confirm → backend creates the Upload DB record

Read flow:
  - Files are served via Cloudflare CDN: https://{R2_CDN_DOMAIN}/{file_key}
  - CDN caches at edge nodes globally — zero backend involvement, sub-100ms
    delivery for 20,000+ concurrent users

Delete flow:
  - Celery task calls delete_file() asynchronously after DB record is removed
"""
import os
import uuid
import logging

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger(__name__)

# Upload types that correspond to physical files stored in R2.
# video_link and external_link are plain URLs — never stored in R2.
_FILE_UPLOAD_TYPES = {"pdf", "audio", "video", "image"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def is_file_type(upload_type: str) -> bool:
    """Return True if this upload_type stores a physical file in R2."""
    return upload_type in _FILE_UPLOAD_TYPES


def build_file_key(upload_type: str, original_filename: str) -> str:
    """
    Generate a unique, collision-safe R2 object key.
    Format: uploads/{upload_type}/{uuid4}.{ext}
    Stored as Upload.file_url in the database.
    """
    ext = os.path.splitext(original_filename)[1].lower()
    return f"uploads/{upload_type}/{uuid.uuid4()}{ext}"


def get_cdn_url(file_key: str) -> str:
    """
    Return the public URL for a stored file.
    - MinIO dev:  http://localhost:9000/aptlogic/{file_key}
    - Cloudflare R2 prod: https://{cdn_domain}/{file_key}

    R2_CDN_DOMAIN format:
      MinIO dev:   localhost:9000/aptlogic   (http, includes bucket)
      Cloudflare:  pub-xxx.r2.dev            (https, no bucket)
    """
    cdn_domain = settings.R2_CDN_DOMAIN
    # MinIO dev domain contains the bucket name and needs http
    if cdn_domain.startswith("localhost") or cdn_domain.startswith("127."):
        return f"http://{cdn_domain}/{file_key}"
    return f"https://{cdn_domain}/{file_key}"


# ── R2 client ─────────────────────────────────────────────────────────────────

def _get_client():
    """
    Return a boto3 S3 client.
    Works with both MinIO (dev) and Cloudflare R2 (production) —
    the only difference is the endpoint URL set in .env.
    """
    if not settings.R2_ACCESS_KEY_ID:
        raise RuntimeError(
            "Storage credentials are not configured. "
            "Set R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, "
            "R2_ENDPOINT_URL, and R2_CDN_DOMAIN in your .env file."
        )
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_presigned_upload_url(
    file_key: str,
    content_type: str,
    expires_in: int = None,
) -> str:
    """
    Generate a presigned S3 PUT URL for direct browser → storage upload.

    Uses R2_PUBLIC_ENDPOINT_URL so the returned URL is reachable by the browser:
      - MinIO dev:  http://localhost:9000/... (host-accessible)
      - Cloudflare R2 prod: same as R2_ENDPOINT_URL

    The browser PUTs the raw file body to this URL — the backend never
    handles the file body.
    """
    if expires_in is None:
        expires_in = settings.R2_PRESIGNED_URL_EXPIRY

    # Use a client pointed at the PUBLIC endpoint so the presigned URL
    # contains a hostname the browser can actually reach.
    public_client = boto3.client(
        "s3",
        endpoint_url=settings.R2_PUBLIC_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )
    try:
        url = public_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.R2_BUCKET_NAME,
                "Key": file_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        logger.info("Generated presigned upload URL for key=%s", file_key)
        return url
    except ClientError as exc:
        logger.error("Failed to generate presigned upload URL for key=%s: %s", file_key, exc)
        raise


def delete_file(file_key: str) -> None:
    """
    Delete a single object from R2 by its key.
    Called from Celery task — raises on failure for retry logic.
    """
    client = _get_client()
    try:
        client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=file_key)
        logger.info("R2 object deleted: %s", file_key)
    except ClientError as exc:
        logger.error("Failed to delete R2 object key=%s: %s", file_key, exc)
        raise
