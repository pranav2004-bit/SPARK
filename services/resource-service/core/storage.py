import os
import uuid
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_FILE_UPLOAD_TYPES = {"pdf", "audio", "video", "image"}


def is_file_type(upload_type: str) -> bool:
    return upload_type in _FILE_UPLOAD_TYPES


def build_file_key(upload_type: str, original_filename: str) -> str:
    ext = os.path.splitext(original_filename)[1].lower()
    return f"uploads/{upload_type}/{uuid.uuid4()}{ext}"


def _rewrite_to_public_media_url(signed_url: str) -> str:
    """Self-hosted deployments only (AWS_S3_ENDPOINT_URL set): a presigned
    URL from _get_client() is signed against the INTERNAL endpoint (e.g.
    http://seaweedfs:8333), which a browser can neither resolve nor reach,
    and which gets blocked as mixed content on an HTTPS page regardless.
    gateway/nginx.conf's /media/ location proxies straight through to that
    internal endpoint, explicitly restoring the exact Host header the
    signature was computed against — so swapping only the host prefix here
    is safe: path and query string (including the signature) pass through
    byte-for-byte, and the signature still validates server-side no matter
    what public Host the browser actually sent. Shared by both the read
    side (get_cdn_url) and the write side (generate_presigned_upload_url)
    — BUG-010 was exactly this helper missing from the write side after
    BUG-009 added it for reads only."""
    endpoint_url = getattr(settings, "AWS_S3_ENDPOINT_URL", "")
    public_base = getattr(settings, "AWS_S3_PUBLIC_MEDIA_BASE_URL", "")
    if not public_base:
        raise RuntimeError(
            "AWS_S3_PUBLIC_MEDIA_BASE_URL must be set when AWS_S3_ENDPOINT_URL "
            "is configured (self-hosted storage) — there is no way to serve a "
            "browser-facing URL (read or upload) without it."
        )
    return signed_url.replace(endpoint_url.rstrip("/"), public_base.rstrip("/"), 1)


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
        signed_url = generate_presigned_read_url(file_key)
        return _rewrite_to_public_media_url(signed_url)

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
    if not getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""):
        raise RuntimeError("Storage bucket not configured.")

    try:
        import boto3
        from botocore.client import Config
    except ImportError:
        raise RuntimeError("boto3 is not installed.")

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
        config=Config(s3={"addressing_style": addressing_style}),
    )


def generate_presigned_upload_url(file_key: str, content_type: str, expires_in: int = None) -> str:
    """BUG-010 (2026-11-28): this docstring used to claim real S3 has no
    "internal vs. browser-facing" endpoint distinction to work around —
    true for real AWS, but self-hosted (SeaweedFS) very much has that
    distinction, same as the read side already handled in get_cdn_url.
    That stale claim is exactly why this function shipped unpatched
    alongside BUG-009's read-side fix and went unnoticed until a real
    browser upload against self-hosted storage actually failed (mixed
    content: http://seaweedfs:8333 on an HTTPS page). Self-hosted now gets
    the identical host-rewrite treatment as get_cdn_url, via the same
    shared helper."""
    from botocore.exceptions import ClientError

    if expires_in is None:
        expires_in = getattr(settings, "AWS_S3_PRESIGNED_URL_EXPIRY", 3600)

    client = _get_client()
    try:
        signed_url = client.generate_presigned_url(
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

    endpoint_url = getattr(settings, "AWS_S3_ENDPOINT_URL", "")
    if endpoint_url:
        return _rewrite_to_public_media_url(signed_url)
    return signed_url


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


def verify_uploaded_object(file_key: str, upload_type: str):
    """
    Ground-truth check against the object that actually landed in storage —
    never trust what the client claims about size/type. Returns
    (real_size_bytes, error_message). error_message is None on success;
    on failure real_size_bytes is None and the caller should reject the
    confirm request (and clean up the orphaned object, if any).

    Raises RuntimeError if storage isn't configured (mirrors
    generate_presigned_upload_url so callers handle it the same way — a 503,
    not a false "verification passed").
    """
    from core.upload_constraints import MAX_FILE_SIZES, MAGIC_BYTES, MAGIC_BYTES_READ_LEN
    from botocore.exceptions import ClientError

    client = _get_client()
    bucket = settings.AWS_STORAGE_BUCKET_NAME

    try:
        head = client.head_object(Bucket=bucket, Key=file_key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return None, "File was not found in storage. Upload it before confirming."
        logger.error("head_object failed for key=%s: %s", file_key, exc)
        return None, "Could not verify the uploaded file."

    real_size = head["ContentLength"]
    max_size = MAX_FILE_SIZES.get(upload_type)
    if max_size and real_size > max_size:
        return None, f"File exceeds the {max_size // (1024*1024)} MB limit for '{upload_type}'."

    magic_specs = MAGIC_BYTES.get(upload_type, [])
    if magic_specs:
        try:
            read_len = max(offset + len(prefix) for offset, prefix in magic_specs)
            read_len = max(read_len, MAGIC_BYTES_READ_LEN)
            obj = client.get_object(Bucket=bucket, Key=file_key, Range=f"bytes=0-{read_len - 1}")
            head_bytes = obj["Body"].read()
        except ClientError as exc:
            logger.error("get_object (magic-byte check) failed for key=%s: %s", file_key, exc)
            return None, "Could not verify the uploaded file's contents."

        matched = any(
            head_bytes[offset:offset + len(prefix)] == prefix
            for offset, prefix in magic_specs
        )
        if not matched:
            return None, f"File contents do not match the expected format for '{upload_type}'."

    return real_size, None


def get_object_stream(file_key: str):
    """Streaming body for an object — caller reads it (used by the malware-scan task)."""
    client = _get_client()
    obj = client.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=file_key)
    return obj["Body"]


def delete_file(file_key: str) -> None:
    # AWS_STORAGE_BUCKET_NAME, not AWS_ACCESS_KEY_ID — same guard as
    # _get_client() above, for the same reason (2026-09-15 fix): production
    # deliberately runs with no AWS_ACCESS_KEY_ID set, relying on the EC2
    # instance's IAM role instead, so gating on that env var being present
    # made every deletion silently no-op there — the DB record would be
    # deleted while the actual S3 object was orphaned forever.
    if not getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""):
        logger.debug("Storage not configured, skipping deletion of %s", file_key)
        return

    from botocore.exceptions import ClientError

    client = _get_client()
    try:
        client.delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=file_key)
        logger.info("S3 object deleted: %s", file_key)
    except ClientError as exc:
        logger.error("Failed to delete S3 object key=%s: %s", file_key, exc)
        raise
