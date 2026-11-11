import logging

from .models import ContentAuditEvent

logger = logging.getLogger("content.audit")


def write_audit(*, institution_id, actor_id, action, entity_type, entity_id, request_id="", version_no=None, summary=None):
    """Called inside the same transaction as the change it records.
    `summary` must never contain question or option text (LIVETRACKER4 section 2.11).
    The log line below is the counter source for content write metrics (section 2.15)."""
    event = ContentAuditEvent.objects.create(
        institution_id=institution_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        version_no=version_no,
        summary=summary or {},
        request_id=request_id or "",
    )
    logger.info("content_audit action=%s entity_type=%s request_id=%s", action, entity_type, request_id or "")
    return event
