import os
import uuid
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_IMAGE_TYPES = {"image"}


class TransientStorageError(Exception):
    """Verification/scanning could not complete because a dependency (S3,
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
    """Public, directly-fetchable URL for a stored object.

    Real AWS production: a CDN domain in front of a public-read bucket —
    no signature needed, just concatenate domain + key (unchanged below).

    Self-hosted (AWS_S3_ENDPOINT_URL set, e.g. local SeaweedFS): there is no
    CDN and no public-read bucket — SeaweedFS's S3 gateway requires every
    request to be signed (confirmed 2026-11-28: an unauthenticated GET
    returns 403). Generate a presigned GET URL against the internal
    endpoint, then swap its host for the public /media/ proxy route
    (gateway/nginx.conf), which forwards the request straight through to
    SeaweedFS while explicitly restoring the Host header the signature was
    computed against — path and query string (including the signature)
    pass through byte-for-byte, so the signature still validates on the
    other side regardless of what public Host header the browser actually
    sent."""
    endpoint_url = getattr(settings, "AWS_S3_ENDPOINT_URL", "")
    if endpoint_url:
        public_base = getattr(settings, "AWS_S3_PUBLIC_MEDIA_BASE_URL", "")
        if not public_base:
            raise RuntimeError(
                "AWS_S3_PUBLIC_MEDIA_BASE_URL must be set when AWS_S3_ENDPOINT_URL "
                "is configured (self-hosted storage) — there is no way to serve a "
                "file read without it."
            )
        signed_url = generate_presigned_read_url(file_key)
        return signed_url.replace(endpoint_url.rstrip("/"), public_base.rstrip("/"), 1)

    cdn_domain = getattr(settings, "AWS_S3_CDN_DOMAIN", "")
    if not cdn_domain:
        return file_key
    if cdn_domain.startswith("localhost") or cdn_domain.startswith("127."):
        return f"http://{cdn_domain}/{file_key}"
    return f"https://{cdn_domain}/{file_key}"


def _get_client():
    """No explicit credentials: boto3.client("s3") already reads
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY from the environment when
    they're set, and falls back to an EC2 instance's attached IAM role
    automatically when they're not. Production (2026-09-12) runs on an EC2
    instance with role spark-backend-ec2-role attached and deliberately sets
    neither env var, so boto3 picks up short-lived, auto-rotating
    credentials from the instance itself instead of a long-lived static key
    — this is the zero-code-change move described when this file was
    written; it required relaxing the guard below, which used to (wrongly)
    require AWS_ACCESS_KEY_ID and would have blocked exactly this.

    endpoint_url + virtual addressing_style ARE explicit here, not optional:
    boto3's presigned-URL generator otherwise falls back to the global
    "bucket.s3.amazonaws.com" host, which "opt-in" regions like ap-south-2
    reject outright (IllegalLocationConstraintException) since they only
    accept requests on their own regional endpoint."""
    from botocore.client import Config

    if not getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""):
        raise RuntimeError("Storage bucket not configured.")

    import boto3
    region = settings.AWS_DEFAULT_REGION
    # AWS_S3_ENDPOINT_URL lets this point at an S3-compatible store (e.g.
    # self-hosted MinIO) instead of real AWS S3. Unset in production on AWS
    # (default ""), so behavior there is completely unchanged. MinIO/most
    # S3-compatible stores need path-style addressing, not virtual-hosted
    # style, since they do not own wildcard DNS for <bucket>.<host>.
    endpoint_url = getattr(settings, "AWS_S3_ENDPOINT_URL", "") or f"https://s3.{region}.amazonaws.com"
    addressing_style = "path" if getattr(settings, "AWS_S3_ENDPOINT_URL", "") else "virtual"
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=endpoint_url,
        # connect/read timeouts (Task 13.1 — every outbound call needs an
        # explicit, reasoned budget, not botocore's default 60s/60s, which
        # was never actually chosen for this service, just inherited).
        # Question/option images are small (<=5MB, matching
        # scan_image_for_malware's own "small enough to scan inline"
        # framing) — head_object/get_object/delete_object here are quick
        # metadata or small-range reads, not full-object transfers, so 5s
        # to connect and 15s to read is generous, not tight.
        config=Config(connect_timeout=5, read_timeout=15, s3={"addressing_style": addressing_style}),
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
    bucket = settings.AWS_STORAGE_BUCKET_NAME

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
    obj = client.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=file_key)
    return obj["Body"]


def scan_image_for_malware(file_key: str):
    """
    Synchronous ClamAV scan (INSTREAM), mirrors practice-service's pattern —
    images are small enough (<=5MB) that scanning inline at write time is
    fast, and this service's Celery worker is reserved for the timer sweep
    and log ingestion, not upload scanning. Returns an error message, or None
    if clean. Raises RuntimeError if CLAMAV_HOST is unset (caller should 503,
    not silently skip the scan — fail closed, not open).
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
        client.delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=file_key)
        logger.info("S3 object deleted: %s", file_key)
    except ClientError as exc:
        logger.error("Failed to delete S3 object key=%s: %s", file_key, exc)
        raise


def generate_presigned_upload_url(file_key: str, content_type: str, expires_in: int = None) -> str:
    """Same client as every other call here — unlike MinIO, real S3 has no
    separate "internal vs. browser-facing" endpoint distinction to work
    around."""
    from botocore.exceptions import ClientError

    if expires_in is None:
        expires_in = getattr(settings, "AWS_S3_PRESIGNED_URL_EXPIRY", 3600)

    client = _get_client()
    try:
        return client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                "Key": file_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
    except ClientError as exc:
        logger.error("Failed to generate presigned URL for key=%s: %s", file_key, exc)
        raise


def generate_presigned_read_url(file_key: str, expires_in: int = None) -> str:
    """Signed, time-limited GET URL for a stored object — the read-side
    counterpart to generate_presigned_upload_url() above. Only meaningful
    for self-hosted deployments (AWS_S3_ENDPOINT_URL set): real AWS
    production instead reads straight off a public-read bucket behind
    AWS_S3_CDN_DOMAIN, which needs no signature at all. SeaweedFS's S3
    gateway has no such public/CDN story and returns 403 on every
    unauthenticated request (confirmed 2026-11-28), so self-hosted reads
    need the exact same presigned-URL treatment uploads already get."""
    from botocore.exceptions import ClientError

    if expires_in is None:
        expires_in = getattr(settings, "AWS_S3_PRESIGNED_URL_EXPIRY", 3600)

    client = _get_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                "Key": file_key,
            },
            ExpiresIn=expires_in,
        )
    except ClientError as exc:
        logger.error("Failed to generate presigned read URL for key=%s: %s", file_key, exc)
        raise
