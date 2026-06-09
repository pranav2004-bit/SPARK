import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="authentication.test_celery")
def test_celery_task(self):
    """Smoke-test task to verify Celery worker is operational."""
    logger.info("Celery test task executed successfully. Task ID: %s", self.request.id)
    return {"status": "ok", "task_id": self.request.id}
