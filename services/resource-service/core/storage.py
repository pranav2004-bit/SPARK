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
    cdn_domain = getattr(settings, "R2_CDN_DOMAIN", "")
    if not cdn_domain:
        return file_key
    if cdn_domain.startswith("localhost") or cdn_domain.startswith("127."):
        return f"http://{cdn_domain}/{file_key}"
    return f"https://{cdn_domain}/{file_key}"


def _get_client():
    try:
        import boto3
        from botocore.client import Config
    except ImportError:
        raise RuntimeError("boto3 is not installed.")

    access_key = getattr(settings, "R2_ACCESS_KEY_ID", "")
    if not access_key:
        raise RuntimeError("Storage credentials not configured.")

    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def generate_presigned_upload_url(file_key: str, content_type: str, expires_in: int = None) -> str:
    import boto3
    from botocore.client import Config
    from botocore.exceptions import ClientError

    if expires_in is None:
        expires_in = getattr(settings, "R2_PRESIGNED_URL_EXPIRY", 3600)

    access_key = getattr(settings, "R2_ACCESS_KEY_ID", "")
    if not access_key:
        raise RuntimeError("Storage credentials not configured.")

    public_endpoint = getattr(settings, "R2_PUBLIC_ENDPOINT_URL", None) or settings.R2_ENDPOINT_URL
    public_client = boto3.client(
        "s3",
        endpoint_url=public_endpoint,
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
        return url
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
    bucket = settings.R2_BUCKET_NAME

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
    obj = client.get_object(Bucket=settings.R2_BUCKET_NAME, Key=file_key)
    return obj["Body"]


def delete_file(file_key: str) -> None:
    access_key = getattr(settings, "R2_ACCESS_KEY_ID", "")
    if not access_key:
        logger.debug("Storage not configured, skipping deletion of %s", file_key)
        return

    from botocore.exceptions import ClientError

    client = _get_client()
    try:
        client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=file_key)
        logger.info("R2 object deleted: %s", file_key)
    except ClientError as exc:
        logger.error("Failed to delete R2 object key=%s: %s", file_key, exc)
        raise
