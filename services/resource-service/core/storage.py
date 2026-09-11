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


def get_cdn_url(file_key: str) -> str:
    cdn_domain = getattr(settings, "AWS_S3_CDN_DOMAIN", "")
    if not cdn_domain:
        return file_key
    if cdn_domain.startswith("localhost") or cdn_domain.startswith("127."):
        return f"http://{cdn_domain}/{file_key}"
    return f"https://{cdn_domain}/{file_key}"


def _get_client():
    """No explicit credentials: boto3.client("s3") already reads
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY from the environment on its
    own — this is also exactly what makes the later move to an EC2 instance
    role a zero-code change (see AWS_ACCESS_KEY_ID's own comment in
    settings.py).

    endpoint_url + virtual addressing_style ARE explicit here, not optional:
    boto3's presigned-URL generator otherwise falls back to the global
    "bucket.s3.amazonaws.com" host, which "opt-in" regions like ap-south-2
    reject outright (IllegalLocationConstraintException) since they only
    accept requests on their own regional endpoint."""
    if not getattr(settings, "AWS_ACCESS_KEY_ID", ""):
        raise RuntimeError("Storage credentials not configured.")

    try:
        import boto3
        from botocore.client import Config
    except ImportError:
        raise RuntimeError("boto3 is not installed.")

    region = settings.AWS_DEFAULT_REGION
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=Config(s3={"addressing_style": "virtual"}),
    )


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
    if not getattr(settings, "AWS_ACCESS_KEY_ID", ""):
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
