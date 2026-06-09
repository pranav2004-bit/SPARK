import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aptlogic.settings.development")

app = Celery("aptlogic")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Celery debug task executed. Request: %r", self.request)
