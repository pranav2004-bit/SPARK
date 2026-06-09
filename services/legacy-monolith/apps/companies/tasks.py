import logging
from celery import shared_task
from core.storage import delete_file

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def async_delete_file(self, file_key: str) -> None:
    """
    Asynchronously delete a stored file (local filesystem or R2).
    Works with whichever STORAGE_BACKEND is active.
    Retries up to 3 times with a 60-second delay on failure.
    """
    try:
        delete_file(file_key)
        logger.info("async_delete_file: deleted key=%s", file_key)
    except Exception as exc:
        logger.error("async_delete_file: failed for key=%s — %s", file_key, exc)
        raise self.retry(exc=exc)
