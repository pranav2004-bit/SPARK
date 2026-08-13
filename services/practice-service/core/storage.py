import os
import uuid
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_IMAGE_TYPES = {"image"}


class TransientStorageError(Exception):
    """Verification/scanning could not complete because a dependency (R2/MinIO,
    ClamAV) was unreachable — the object was never actually examined, let
    alone found bad. Callers must NOT delete the object on this path: unlike
    a confirmed rejection (invalid format, malware found), deleting here
    would destroy a perfectly good upload just because a checker hiccuped,
    forcing the admin to re-upload instead of simply retrying."""
    pass


def build_file_key(upload_type: str, original_filename: str) -> str:
    ext = os.path.splitext(original_filename)[1].lower()
    return f"uploads/{upload_type}/{uuid.uuid4()}{ext}"


def get_cdn_url(file_key: str) -> str:
    cdn_domain = getattr(settings, "R2_CDN_DOMAIN", "")
    if not cdn_domain:
        return file_key
    if cdn_domain.startswith("localhost") or cdn_domain.startswith("127."):
        return f"http://{cdn_domain}/{file_key}"
    return f"https://{cdn_domain}/{file_key}"


def _get_client():
    from botocore.client import Config

    access_key = getattr(settings, "R2_ACCESS_KEY_ID", "")
    if not access_key:
        raise RuntimeError("Storage credentials not configured.")

    import boto3
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def verify_uploaded_image(file_key: str):
    """
    Ground-truth check against the object that actually landed in storage —
    never trust the client-declared content_type or an unverified file_key.
    Returns (real_size_bytes, error_message); error_message is None on
    success. Raises RuntimeError if storage isn't configured (mirrors
    generate_presigned_upload_url so callers get a 503, not a false pass).
    """
    from core.upload_constraints import MAX_IMAGE_SIZE, MAGIC_BYTES, MAGIC_BYTES_READ_LEN
    from botocore.exceptions import ClientError

    client = _get_client()
    bucket = settings.R2_BUCKET_NAME

    try:
        head = client.head_object(Bucket=bucket, Key=file_key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return None, "Image was not found in storage. Upload it before saving."
        logger.error("head_object failed for key=%s: %s", file_key, exc)
        raise TransientStorageError("Could not verify the uploaded image. Please try again.") from exc

    real_size = head["ContentLength"]
    if real_size > MAX_IMAGE_SIZE:
        return None, f"Image exceeds the {MAX_IMAGE_SIZE // (1024*1024)} MB limit."

    try:
        read_len = max(offset + len(prefix) for offset, prefix in MAGIC_BYTES)
        read_len = max(read_len, MAGIC_BYTES_READ_LEN)
        obj = client.get_object(Bucket=bucket, Key=file_key, Range=f"bytes=0-{read_len - 1}")
        head_bytes = obj["Body"].read()
    except ClientError as exc:
        logger.error("get_object (magic-byte check) failed for key=%s: %s", file_key, exc)
        raise TransientStorageError("Could not verify the uploaded image's contents. Please try again.") from exc

    matched = any(
        head_bytes[offset:offset + len(prefix)] == prefix
        for offset, prefix in MAGIC_BYTES
    )
    if not matched:
        return None, "Image contents do not match a supported image format."

    return real_size, None


def get_object_stream(file_key: str):
    """Streaming body for an object — caller reads it (used by the malware scan)."""
    client = _get_client()
    obj = client.get_object(Bucket=settings.R2_BUCKET_NAME, Key=file_key)
    return obj["Body"]


def scan_image_for_malware(file_key: str):
    """
    Synchronous ClamAV scan (INSTREAM) — this service has no async worker,
    and images are small enough (<=5MB) that scanning inline at PATCH time
    is fast. Returns an error message, or None if clean.
    Raises RuntimeError if CLAMAV_HOST is unset (caller should 503, not
    silently skip the scan — fail closed, not open).
    """
    clamav_host = getattr(settings, "CLAMAV_HOST", "")
    if not clamav_host:
        raise RuntimeError("Malware scanning is not configured.")

    import clamd

    try:
        body = get_object_stream(file_key)
        cd = clamd.ClamdNetworkSocket(host=clamav_host, port=settings.CLAMAV_PORT, timeout=30)
        result = cd.instream(body)
    except (clamd.ConnectionError, OSError) as exc:
        logger.error("scan_image_for_malware: clamd unreachable for key=%s — %s", file_key, exc)
        raise TransientStorageError("Could not scan the uploaded image right now. Please try again.") from exc
    except Exception as exc:
        logger.error("scan_image_for_malware: unexpected error for key=%s — %s", file_key, exc)
        raise TransientStorageError("Could not scan the uploaded image right now. Please try again.") from exc

    status, signature = result.get("stream", (None, None))
    if status == "FOUND":
        logger.critical(
            "scan_image_for_malware: MALWARE DETECTED key=%s signature=%s — rejecting.",
            file_key, signature,
        )
        return "This image failed a security scan and cannot be used."
    if status != "OK":
        logger.error("scan_image_for_malware: unexpected clamd verdict for key=%s — %s", file_key, result)
        return "Could not verify the uploaded image is safe."
    return None


def delete_file(file_key: str) -> None:
    from botocore.exceptions import ClientError

    client = _get_client()
    try:
        client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=file_key)
        logger.info("R2 object deleted: %s", file_key)
    except ClientError as exc:
        logger.error("Failed to delete R2 object key=%s: %s", file_key, exc)
        raise


def generate_presigned_upload_url(file_key: str, content_type: str, expires_in: int = None) -> str:
    from botocore.client import Config
    from botocore.exceptions import ClientError

    if expires_in is None:
        expires_in = getattr(settings, "R2_PRESIGNED_URL_EXPIRY", 3600)

    access_key = getattr(settings, "R2_ACCESS_KEY_ID", "")
    if not access_key:
        raise RuntimeError("Storage credentials not configured.")

    import boto3
    endpoint = getattr(settings, "R2_PUBLIC_ENDPOINT_URL", None) or settings.R2_ENDPOINT_URL
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )
    try:
        return client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.R2_BUCKET_NAME,
                "Key": file_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
    except ClientError as exc:
        logger.error("Failed to generate presigned URL for key=%s: %s", file_key, exc)
        raise
