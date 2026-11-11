"""Question image flow (LIVETRACKER4.md section 2.9).

presign -> client PUTs bytes to S3 -> confirm (verify, scan, attach) -> remove.
Mirrors practice-service's presign/verify/scan flow and its status codes:
rejected objects are deleted; storage outages return 503 and keep the object.
"""
import os

from botocore.exceptions import BotoCoreError
from django.conf import settings
from django.db import transaction

from core.storage import (
    build_file_key, generate_presigned_upload_url, verify_uploaded_image,
    scan_image_for_malware, TransientStorageError,
)
from core.upload_constraints import ALLOWED_IMAGE_EXTENSIONS, ALLOWED_IMAGE_MIME

from . import services as svc
from .audit import write_audit
from .errors import ContentError
from .media import _delete_object, release_keys_after_commit
from .models import AUDIT_ENTITY_QUESTION, OPEN_VERSION_STATES
from .validation import validate_question_fields

UPLOAD_PREFIX = "uploads/content/"


def _storage_unavailable(message):
    return ContentError(message, "storage_unavailable", 503)


def _delete_rejected(file_key):
    try:
        _delete_object(file_key)
    except Exception:
        import logging
        logging.getLogger(__name__).warning("content: could not delete rejected image key=%s", file_key)


def presign_draft_image(*, institution_id, question_id, if_match, filename, content_type):
    question = svc.get_question(institution_id, question_id)
    draft = svc.open_version(question)
    if draft is None:
        raise ContentError("Edit the question first so it has a draft to attach the image to.",
                           "invalid_transition", 409)
    svc.check_precondition(draft, if_match)

    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ContentError(f"Extension '{ext}' is not allowed.", "image_type_unsupported", 415,
                           {"filename": [f"Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"]})
    if not any((content_type or "").startswith(mime) for mime in ALLOWED_IMAGE_MIME):
        raise ContentError("Unsupported image format.", "image_type_unsupported", 415,
                           {"content_type": ["Allowed: JPEG, PNG, WebP, GIF, AVIF."]})

    file_key = build_file_key("content", filename)
    try:
        upload_url = generate_presigned_upload_url(file_key, content_type)
    except RuntimeError:
        raise _storage_unavailable("File storage is not configured.")
    return {"upload_url": upload_url, "file_key": file_key, "method": "PUT"}


def _verification_rejection(error: str) -> ContentError:
    """Map a storage verification message to the section 2.13 status.
    core.storage.verify_uploaded_image returns text only (shared module), so the
    wording is matched here. Size -> 413, content does not match its type -> 415,
    anything else -> 400."""
    if error.startswith("Image exceeds"):
        return ContentError(error, "image_too_large", 413)
    if "supported image format" in error:
        return ContentError(error, "image_type_unsupported", 415)
    return ContentError(error, "image_rejected", 400)


def confirm_draft_image(*, institution_id, actor_id, question_id, if_match, file_key, image_alt_text,
                        request_id=""):
    if not isinstance(file_key, str) or not file_key.startswith(UPLOAD_PREFIX):
        raise ContentError("Unknown upload key.", "image_rejected", 400, {"file_key": ["Not an issued key."]})
    if ".." in file_key or "\\" in file_key:
        raise ContentError("Unknown upload key.", "image_rejected", 400, {"file_key": ["Invalid key."]})
    validate_question_fields(text="x", options=None, explanation="", image_key=file_key,
                             image_alt_text=image_alt_text, full=False)

    try:
        _size, error = verify_uploaded_image(file_key, timeout=settings.CONTENT_S3_TIMEOUT_SECONDS)
    except RuntimeError:
        raise _storage_unavailable("File storage is not configured.")
    except (TransientStorageError, BotoCoreError) as exc:
        # BotoCoreError covers botocore connect/read timeouts (section 2.14): 503, object kept.
        raise _storage_unavailable("File storage is temporarily unavailable. Please try again.")
    if error:
        _delete_rejected(file_key)
        raise _verification_rejection(error)

    try:
        scan_error = scan_image_for_malware(file_key, timeout=settings.CONTENT_S3_TIMEOUT_SECONDS)
    except RuntimeError:
        raise _storage_unavailable("Malware scanning is not configured.")
    except (TransientStorageError, BotoCoreError) as exc:
        raise _storage_unavailable("Could not scan the uploaded image right now. Please try again.")
    if scan_error:
        _delete_rejected(file_key)
        raise ContentError(scan_error, "image_rejected", 400)

    with transaction.atomic():
        question = svc.get_question(institution_id, question_id, lock=True)
        draft = svc.open_version(question)
        if draft is None:
            release_keys_after_commit([file_key], "unattached_upload")
            raise ContentError("Edit the question first so it has a draft to attach the image to.",
                               "invalid_transition", 409)
        try:
            svc.check_precondition(draft, if_match)
        except ContentError:
            release_keys_after_commit([file_key], "unattached_upload")
            raise
        old_key = draft.image_key
        draft.image_key = file_key
        draft.image_alt_text = (image_alt_text or "").strip()
        draft.updated_by = actor_id
        draft.save()
        if old_key and old_key != file_key:
            release_keys_after_commit([old_key], "image_replaced")
        write_audit(institution_id=institution_id, actor_id=actor_id, action="question.image_attach",
                    entity_type=AUDIT_ENTITY_QUESTION, entity_id=question.id,
                    version_no=draft.version_no, request_id=request_id, summary={"fields": ["image"]})
    return question, draft


def remove_draft_image(*, institution_id, actor_id, question_id, if_match, request_id=""):
    with transaction.atomic():
        question = svc.get_question(institution_id, question_id, lock=True)
        draft = svc.open_version(question)
        if draft is None:
            raise ContentError("No draft to remove the image from.", "invalid_transition", 409)
        svc.check_precondition(draft, if_match)
        old_key = draft.image_key
        if not old_key:
            return question, draft
        draft.image_key = ""
        draft.image_alt_text = ""
        draft.updated_by = actor_id
        draft.save()
        write_audit(institution_id=institution_id, actor_id=actor_id, action="question.image_remove",
                    entity_type=AUDIT_ENTITY_QUESTION, entity_id=question.id,
                    version_no=draft.version_no, request_id=request_id, summary={"fields": ["image"]})
        still_referenced = question.versions.filter(image_key=old_key).exclude(pk=draft.pk).exists()
        if not still_referenced:
            release_keys_after_commit([old_key], "image_removed")
    return question, draft
