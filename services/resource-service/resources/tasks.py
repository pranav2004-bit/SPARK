import logging
from celery import shared_task
from core.storage import delete_file

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def async_delete_file(self, file_key: str) -> None:
    try:
        delete_file(file_key)
        logger.info("async_delete_file: deleted key=%s", file_key)
    except Exception as exc:
        logger.error("async_delete_file: failed for key=%s — %s", file_key, exc)
        raise self.retry(exc=exc)


_SCAN_MODELS = {}  # populated lazily to avoid app-registry-not-ready import errors


def _resolve_scan_model(model_name: str):
    if not _SCAN_MODELS:
        from .models import Upload, ModuleUpload
        _SCAN_MODELS["Upload"] = Upload
        _SCAN_MODELS["ModuleUpload"] = ModuleUpload
    return _SCAN_MODELS[model_name]


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def scan_uploaded_file(self, upload_pk: str, model_name: str) -> None:
    """
    Malware-scans a just-confirmed file upload via ClamAV (clamd INSTREAM)
    and updates scan_status accordingly. Fails closed: any outcome other
    than a confirmed "clean" verdict leaves the record hidden from students
    (see scan_status filtering in views.py). Transient clamd connectivity
    issues are retried; a confirmed infection deletes both the storage
    object and the record immediately.
    """
    from django.conf import settings

    model_cls = _resolve_scan_model(model_name)
    try:
        instance = model_cls.objects.get(pk=upload_pk)
    except model_cls.DoesNotExist:
        logger.warning("scan_uploaded_file: %s %s no longer exists, skipping.", model_name, upload_pk)
        return

    if not settings.CLAMAV_HOST:
        logger.info(
            "scan_uploaded_file: CLAMAV_HOST not configured — leaving %s %s as pending.",
            model_name, upload_pk,
        )
        return

    import clamd
    from core.storage import get_object_stream, delete_file

    try:
        body = get_object_stream(instance.file_url)
        cd = clamd.ClamdNetworkSocket(host=settings.CLAMAV_HOST, port=settings.CLAMAV_PORT, timeout=180)
        result = cd.instream(body)
    except (clamd.ConnectionError, OSError) as exc:
        logger.error("scan_uploaded_file: clamd unreachable for %s %s — %s", model_name, upload_pk, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            model_cls.objects.filter(pk=upload_pk).update(scan_status="error")
            logger.critical(
                "scan_uploaded_file: giving up scanning %s %s after retries — marked 'error', "
                "stays hidden from students until manually resolved.",
                model_name, upload_pk,
            )
        return
    except Exception as exc:
        logger.error("scan_uploaded_file: unexpected error scanning %s %s — %s", model_name, upload_pk, exc)
        model_cls.objects.filter(pk=upload_pk).update(scan_status="error")
        return

    status, signature = result.get("stream", (None, None))

    if status == "OK":
        model_cls.objects.filter(pk=upload_pk).update(scan_status="clean")
        logger.info("scan_uploaded_file: %s %s clean.", model_name, upload_pk)
    elif status == "FOUND":
        file_key = instance.file_url
        logger.critical(
            "scan_uploaded_file: MALWARE DETECTED in %s %s (key=%s, signature=%s) — deleting.",
            model_name, upload_pk, file_key, signature,
        )
        instance.delete()
        try:
            delete_file(file_key)
        except Exception:
            logger.error("scan_uploaded_file: failed to delete infected object key=%s", file_key)
    else:
        logger.error("scan_uploaded_file: unexpected clamd verdict for %s %s — %s", model_name, upload_pk, result)
        model_cls.objects.filter(pk=upload_pk).update(scan_status="error")
