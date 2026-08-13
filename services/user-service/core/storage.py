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
        raise RuntimeError("boto3 is not installed. Add it to requirements.txt.")

    access_key = getattr(settings, "R2_ACCESS_KEY_ID", "")
    if not access_key:
        raise RuntimeError(
            "Storage credentials not configured. "
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


def generate_presigned_upload_url(file_key: str, content_type: str, expires_in: int = None) -> str:
    import boto3
    from botocore.client import Config
    from botocore.exceptions import ClientError

    if expires_in is None:
        expires_in = getattr(settings, "R2_PRESIGNED_URL_EXPIRY", 900)

    public_endpoint = getattr(settings, "R2_PUBLIC_ENDPOINT_URL", None)
    access_key = getattr(settings, "R2_ACCESS_KEY_ID", "")
    if not access_key:
        raise RuntimeError("Storage credentials not configured.")

    public_client = boto3.client(
        "s3",
        endpoint_url=public_endpoint or settings.R2_ENDPOINT_URL,
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
        logger.error("Failed to generate presigned upload URL for key=%s: %s", file_key, exc)
        raise


def delete_file(file_key: str) -> None:
    from botocore.exceptions import ClientError

    client = _get_client()
    try:
        client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=file_key)
        logger.info("R2 object deleted: %s", file_key)
    except ClientError as exc:
        logger.error("Failed to delete R2 object key=%s: %s", file_key, exc)
        raise
