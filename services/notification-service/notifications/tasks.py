from celery import shared_task
from django.utils import timezone
from datetime import timedelta


@shared_task
def expire_old_notifications():
    """Soft-delete notifications older than 90 days. Runs nightly at 03:00 UTC."""
    from .models import Notification

    cutoff = timezone.now() - timedelta(days=90)
    updated = Notification.objects.filter(
        created_at__lt=cutoff, is_deleted=False
    ).update(is_deleted=True)
    return {"expired": updated}
