import logging

from django.conf import settings
from django.db import transaction

from core.storage import _get_client

from .models import ContentMediaOrphan

logger = logging.getLogger(__name__)


def _delete_object(key):
    # Same client and bucket as core/storage.py. core.storage.delete_file()
    # swallows S3 errors, so it cannot report failure to the orphan ledger;
    # this path lets the failure surface and be recorded.
    _get_client(timeout=settings.CONTENT_S3_TIMEOUT_SECONDS).delete_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key)


def release_keys_after_commit(keys, reason):
    """Delete S3 objects only after the DB change that orphaned them has committed.
    A failed S3 delete is recorded in the orphan ledger; the DB change stands."""
    keys = [k for k in dict.fromkeys(keys) if k]
    if not keys:
        return

    def _release():
        for key in keys:
            try:
                _delete_object(key)
            except Exception:
                logger.exception("content: S3 delete failed; recording orphan (reason=%s)", reason)
                ContentMediaOrphan.objects.get_or_create(key=key, defaults={"reason": reason})

    transaction.on_commit(_release)
