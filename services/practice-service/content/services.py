"""Content bank business rules (LIVETRACKER4.md sections 2.2 to 2.4 and 2.8).

No HTTP in this module. Views call these functions and tests call them directly.
Every write runs inside one transaction together with its audit row.
"""
import hashlib

from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone

from .audit import write_audit
from .errors import ContentError
from .media import release_keys_after_commit
from .models import (
    ContentNode, ContentQuestion, ContentQuestionVersion, ContentOption, ContentQuestionUsage,
    NODE_DRAFT, NODE_PUBLISHED, NODE_RETIRED,
    QUESTION_DRAFT, QUESTION_PUBLISHED, QUESTION_RETIRED,
    VERSION_DRAFT, VERSION_IN_REVIEW, VERSION_PUBLISHED, OPEN_VERSION_STATES,
    AUDIT_ENTITY_NODE, AUDIT_ENTITY_QUESTION, AUDIT_ENTITY_VERSION,
)
from .validation import validate_node_name, validate_question_fields


# ── helpers ──────────────────────────────────────────────────────────────────

def etag_for(version):
    raw = f"{version.version_no}:{version.updated_at.isoformat()}"
    return '"' + hashlib.sha256(raw.encode()).hexdigest()[:32] + '"'


def get_node(institution_id, node_id):
    node = ContentNode.objects.filter(pk=node_id, institution_id=institution_id).first()
    if node is None:
        raise ContentError("Node not found.", "not_found", 404)
    return node


def get_question(institution_id, question_id, *, lock=False):
    qs = ContentQuestion.objects.filter(pk=question_id, institution_id=institution_id)
    if lock:
        qs = qs.select_for_update()
    question = qs.first()
    if question is None:
        raise ContentError("Question not found.", "not_found", 404)
    return question


def open_version(question):
    return question.versions.filter(state__in=OPEN_VERSION_STATES).first()


def latest_published(question):
    return question.versions.filter(state=VERSION_PUBLISHED).order_by("-version_no").first()


def editable_version(question):
    # Reads question.versions.all() (not filter()) so a list view can prefetch versions
    # and their options in two queries. At most one open version exists (partial unique index).
    versions = list(question.versions.all())
    for version in versions:
        if version.state in OPEN_VERSION_STATES:
            return version
    published = [v for v in versions if v.state == VERSION_PUBLISHED]
    return max(published, key=lambda v: v.version_no) if published else None


def check_precondition(version, if_match):
    if not if_match:
        raise ContentError("If-Match header is required for this change.", "precondition_required", 428)
    current = etag_for(version)
    if if_match != current:
        raise ContentError(
            "This draft changed since you loaded it. Reload and try again.",
            "stale_version", 412, errors={"current_etag": [current]},
        )


def _ancestors_published(node):
    cursor = node.parent
    while cursor is not None:
        if cursor.status != NODE_PUBLISHED:
            return False
        cursor = cursor.parent
    return True


def is_eligible(question):
    """Part 2 reads this: published question, not retired, every ancestor node published."""
    if question.status != QUESTION_PUBLISHED:
        return False
    if question.node.status != NODE_PUBLISHED:
        return False
    return _ancestors_published(question.node)


def _lock_sibling_scope(institution_id, parent_id):
    """Serialise name checks for one parent's children. On PostgreSQL this is a transaction-scoped
    advisory lock, released at commit, so two concurrent creates or renames with the same name
    cannot both pass the duplicate check. Other databases run the check without the lock."""
    if connection.vendor != "postgresql":
        return
    key = f"content-node:{institution_id}:{parent_id or 'root'}"
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [key])


def _sibling_name_taken(institution_id, parent_id, name, exclude_id=None):
    qs = ContentNode.objects.filter(institution_id=institution_id, parent_id=parent_id, name__iexact=name)
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def _write_options(version, options):
    version.options.all().delete()
    for idx, opt in enumerate(options):
        ContentOption.objects.create(
            version=version,
            label=chr(ord("A") + idx),
            option_text=(opt.get("option_text") or "").strip(),
            is_correct=bool(opt.get("is_correct")),
            display_order=idx + 1,
        )


def _option_dicts(version):
    return [
        {"option_text": o.option_text, "is_correct": o.is_correct}
        for o in version.options.order_by("display_order")
    ]


def _full_validate(version):
    return validate_question_fields(
        text=version.question_text, options=_option_dicts(version),
        explanation=version.explanation, image_key=version.image_key,
        image_alt_text=version.image_alt_text, full=True,
    )


# ── nodes (subjects and topics; flexible tree) ───────────────────────────────

def create_node(*, institution_id, actor_id, name, parent_id=None, request_id=""):
    cleaned, errors = validate_node_name(name)
    if errors:
        raise ContentError("Validation failed.", "validation_error", 400, errors)
    parent = None
    if parent_id is not None:
        parent = get_node(institution_id, parent_id)
        if parent.status == NODE_RETIRED:
            raise ContentError("Cannot add under a retired node.", "node_retired", 409)
    with transaction.atomic():
        _lock_sibling_scope(institution_id, parent_id)
        if _sibling_name_taken(institution_id, parent_id, cleaned):
            raise ContentError("A node with this name already exists here.", "duplicate_name", 409)
        siblings_max = ContentNode.objects.filter(
            institution_id=institution_id, parent_id=parent_id,
        ).aggregate(m=Max("display_order"))["m"] or 0
        node = ContentNode.objects.create(
            institution_id=institution_id, parent=parent, name=cleaned,
            display_order=siblings_max + 1, created_by=actor_id, updated_by=actor_id,
        )
        write_audit(institution_id=institution_id, actor_id=actor_id, action="node.create",
                    entity_type=AUDIT_ENTITY_NODE, entity_id=node.id, request_id=request_id,
                    summary={"parent_id": str(parent_id) if parent_id else None})
    return node


def update_node(*, institution_id, actor_id, node_id, name=None, request_id=""):
    node = get_node(institution_id, node_id)
    if name is not None:
        cleaned, errors = validate_node_name(name)
        if errors:
            raise ContentError("Validation failed.", "validation_error", 400, errors)
        with transaction.atomic():
            _lock_sibling_scope(institution_id, node.parent_id)
            if _sibling_name_taken(institution_id, node.parent_id, cleaned, exclude_id=node.id):
                raise ContentError("A node with this name already exists here.", "duplicate_name", 409)
            node.name = cleaned
            node.updated_by = actor_id
            node.save(update_fields=["name", "updated_by", "updated_at"])
            write_audit(institution_id=institution_id, actor_id=actor_id, action="node.rename",
                        entity_type=AUDIT_ENTITY_NODE, entity_id=node.id, request_id=request_id,
                        summary={"fields": ["name"]})
    return node


def publish_node(*, institution_id, actor_id, node_id, request_id=""):
    node = get_node(institution_id, node_id)
    if node.status == NODE_PUBLISHED:
        return node
    if node.status == NODE_RETIRED:
        raise ContentError("A retired node must be restored, not published.", "invalid_transition", 409)
    with transaction.atomic():
        node.status = NODE_PUBLISHED
        node.published_at = timezone.now()
        node.updated_by = actor_id
        node.save(update_fields=["status", "published_at", "updated_by", "updated_at"])
        write_audit(institution_id=institution_id, actor_id=actor_id, action="node.publish",
                    entity_type=AUDIT_ENTITY_NODE, entity_id=node.id, request_id=request_id,
                    summary={"from": NODE_DRAFT, "to": NODE_PUBLISHED})
    return node


def retire_node(*, institution_id, actor_id, node_id, request_id=""):
    node = get_node(institution_id, node_id)
    if node.status == NODE_RETIRED:
        return node
    if node.status != NODE_PUBLISHED:
        raise ContentError("Only a published node can be retired.", "invalid_transition", 409)
    with transaction.atomic():
        node.status = NODE_RETIRED
        node.retired_at = timezone.now()
        node.updated_by = actor_id
        node.save(update_fields=["status", "retired_at", "updated_by", "updated_at"])
        write_audit(institution_id=institution_id, actor_id=actor_id, action="node.retire",
                    entity_type=AUDIT_ENTITY_NODE, entity_id=node.id, request_id=request_id,
                    summary={"from": NODE_PUBLISHED, "to": NODE_RETIRED})
    return node


def restore_node(*, institution_id, actor_id, node_id, request_id=""):
    node = get_node(institution_id, node_id)
    if node.status == NODE_PUBLISHED:
        return node
    if node.status != NODE_RETIRED:
        raise ContentError("Only a retired node can be restored.", "invalid_transition", 409)
    if not _ancestors_published(node):
        raise ContentError("Restore the parent node first.", "invalid_transition", 409)
    with transaction.atomic():
        node.status = NODE_PUBLISHED
        node.retired_at = None
        node.updated_by = actor_id
        node.save(update_fields=["status", "retired_at", "updated_by", "updated_at"])
        write_audit(institution_id=institution_id, actor_id=actor_id, action="node.restore",
                    entity_type=AUDIT_ENTITY_NODE, entity_id=node.id, request_id=request_id,
                    summary={"from": NODE_RETIRED, "to": NODE_PUBLISHED})
    return node


def delete_node(*, institution_id, actor_id, node_id, request_id=""):
    node = get_node(institution_id, node_id)
    blockers = []
    if node.children.exists():
        blockers.append("child nodes")
    if node.questions.exists():
        blockers.append("questions")
    if blockers:
        raise ContentError(
            "This node still has " + " and ".join(blockers) + ". Remove or move them first.",
            "node_not_empty", 409, errors={"blockers": blockers},
        )
    with transaction.atomic():
        write_audit(institution_id=institution_id, actor_id=actor_id, action="node.delete",
                    entity_type=AUDIT_ENTITY_NODE, entity_id=node.id, request_id=request_id,
                    summary={})
        node.delete()


# ── questions (MCQ) ──────────────────────────────────────────────────────────

def create_question(*, institution_id, actor_id, node_id, text, options=None, explanation="",
                    image_key="", image_alt_text="", request_id=""):
    node = get_node(institution_id, node_id)
    if node.parent_id is None:
        raise ContentError("Questions must sit under a topic, not directly under a subject.",
                           "invalid_parent", 400)
    if node.status == NODE_RETIRED:
        raise ContentError("Cannot add questions to a retired node.", "node_retired", 409)
    cleaned_text, cleaned_expl, cleaned_alt = validate_question_fields(
        text=text, options=options or [], explanation=explanation,
        image_key=image_key, image_alt_text=image_alt_text, full=False,
    )
    if not cleaned_text:
        raise ContentError("Validation failed.", "validation_error", 400,
                           {"question_text": ["Question text is required."]})

    with transaction.atomic():
        order = (ContentQuestion.objects.filter(institution_id=institution_id, node=node)
                 .aggregate(m=Max("display_order"))["m"] or 0) + 1
        question = ContentQuestion.objects.create(
            institution_id=institution_id, node=node, display_order=order,
            status=QUESTION_DRAFT, current_version_no=1,
            created_by=actor_id, updated_by=actor_id,
        )
        version = ContentQuestionVersion.objects.create(
            question=question, version_no=1, state=VERSION_DRAFT, question_text=cleaned_text,
            explanation=cleaned_expl, image_key=image_key or "", image_alt_text=cleaned_alt,
            created_by=actor_id, updated_by=actor_id,
        )
        _write_options(version, options or [])
        write_audit(institution_id=institution_id, actor_id=actor_id, action="question.create",
                    entity_type=AUDIT_ENTITY_QUESTION, entity_id=question.id, version_no=1,
                    request_id=request_id, summary={"fields": ["question_text", "options"]})
    return question, version


def update_draft(*, institution_id, actor_id, question_id, if_match, changes, request_id=""):
    """Saves field changes to the editable draft. For a published question, first clones the
    latest published version into a new draft. Refused while the draft is in review."""
    with transaction.atomic():
        question = get_question(institution_id, question_id, lock=True)
        if question.status == QUESTION_RETIRED:
            raise ContentError("Restore the question before editing it.", "invalid_transition", 409)
        draft = open_version(question)
        if draft is not None and draft.state == VERSION_IN_REVIEW:
            raise ContentError("Withdraw the review before editing this question.", "invalid_transition", 409)
        if draft is None:
            base = latest_published(question)
            if base is None:
                raise ContentError("This question has no editable version.", "invalid_transition", 409)
            check_precondition(base, if_match)
            new_no = question.current_version_no + 1
            draft = ContentQuestionVersion.objects.create(
                question=question, version_no=new_no, state=VERSION_DRAFT,
                question_text=base.question_text, explanation=base.explanation,
                image_key=base.image_key, image_alt_text=base.image_alt_text,
                created_by=actor_id, updated_by=actor_id,
            )
            _write_options(draft, _option_dicts(base))
            question.current_version_no = new_no
            question.updated_by = actor_id
            question.save(update_fields=["current_version_no", "updated_by", "updated_at"])
        else:
            check_precondition(draft, if_match)

        text = changes.get("text", draft.question_text)
        explanation = changes.get("explanation", draft.explanation)
        image_key = changes.get("image_key", draft.image_key)
        image_alt = changes.get("image_alt_text", draft.image_alt_text)
        options = changes.get("options", _option_dicts(draft))
        cleaned_text, cleaned_expl, cleaned_alt = validate_question_fields(
            text=text, options=options, explanation=explanation,
            image_key=image_key, image_alt_text=image_alt, full=False,
        )
        old_key = draft.image_key
        draft.question_text = cleaned_text
        draft.explanation = cleaned_expl
        draft.image_key = image_key or ""
        draft.image_alt_text = cleaned_alt if image_key else ""
        draft.updated_by = actor_id
        draft.save()
        if "options" in changes:
            _write_options(draft, options)
        if old_key and old_key != draft.image_key:
            release_keys_after_commit([old_key], "image_replaced")
        write_audit(institution_id=institution_id, actor_id=actor_id, action="question.edit_draft",
                    entity_type=AUDIT_ENTITY_QUESTION, entity_id=question.id,
                    version_no=draft.version_no, request_id=request_id,
                    summary={"fields": sorted(changes.keys())})
    return question, draft


def submit_review(*, institution_id, actor_id, question_id, if_match, request_id=""):
    with transaction.atomic():
        question = get_question(institution_id, question_id, lock=True)
        draft = open_version(question)
        if draft is None:
            raise ContentError("Nothing to submit. Edit the question first.", "invalid_transition", 409)
        if draft.state == VERSION_IN_REVIEW:
            return question, draft
        check_precondition(draft, if_match)
        _full_validate(draft)
        draft.state = VERSION_IN_REVIEW
        draft.submitted_for_review_at = timezone.now()
        draft.updated_by = actor_id
        draft.save()
        write_audit(institution_id=institution_id, actor_id=actor_id, action="question.submit_review",
                    entity_type=AUDIT_ENTITY_QUESTION, entity_id=question.id,
                    version_no=draft.version_no, request_id=request_id, summary={})
    return question, draft


def withdraw_review(*, institution_id, actor_id, question_id, if_match, request_id=""):
    with transaction.atomic():
        question = get_question(institution_id, question_id, lock=True)
        draft = open_version(question)
        if draft is None:
            raise ContentError("Nothing to withdraw.", "invalid_transition", 409)
        if draft.state == VERSION_DRAFT:
            return question, draft
        check_precondition(draft, if_match)
        draft.state = VERSION_DRAFT
        draft.submitted_for_review_at = None
        draft.updated_by = actor_id
        draft.save()
        write_audit(institution_id=institution_id, actor_id=actor_id, action="question.withdraw_review",
                    entity_type=AUDIT_ENTITY_QUESTION, entity_id=question.id,
                    version_no=draft.version_no, request_id=request_id, summary={})
    return question, draft


def publish_question(*, institution_id, actor_id, question_id, if_match, request_id=""):
    with transaction.atomic():
        question = get_question(institution_id, question_id, lock=True)
        if question.status == QUESTION_RETIRED:
            raise ContentError("Restore the question before publishing it.", "invalid_transition", 409)
        if question.node.status != NODE_PUBLISHED:
            raise ContentError("Publish the topic before publishing its questions.", "invalid_transition", 409)
        draft = open_version(question)
        if draft is None:
            published = latest_published(question)
            if published is not None and published.version_no == question.published_version_no:
                return question, published  # idempotent repeat
            raise ContentError("Nothing to publish. Edit the question first.", "invalid_transition", 409)
        check_precondition(draft, if_match)
        _full_validate(draft)
        draft.state = VERSION_PUBLISHED
        draft.published_at = timezone.now()
        draft.published_by = actor_id
        draft.updated_by = actor_id
        draft.save()
        question.status = QUESTION_PUBLISHED
        question.published_version_no = draft.version_no
        question.updated_by = actor_id
        question.save(update_fields=["status", "published_version_no", "updated_by", "updated_at"])
        write_audit(institution_id=institution_id, actor_id=actor_id, action="question.publish",
                    entity_type=AUDIT_ENTITY_QUESTION, entity_id=question.id,
                    version_no=draft.version_no, request_id=request_id,
                    summary={"from": VERSION_DRAFT, "to": VERSION_PUBLISHED})
    return question, draft


def retire_question(*, institution_id, actor_id, question_id, request_id=""):
    with transaction.atomic():
        question = get_question(institution_id, question_id, lock=True)
        if question.status == QUESTION_RETIRED:
            return question
        if question.status != QUESTION_PUBLISHED:
            raise ContentError("Only a published question can be retired. Delete a draft instead.",
                               "invalid_transition", 409)
        question.status = QUESTION_RETIRED
        question.retired_at = timezone.now()
        question.updated_by = actor_id
        question.save(update_fields=["status", "retired_at", "updated_by", "updated_at"])
        write_audit(institution_id=institution_id, actor_id=actor_id, action="question.retire",
                    entity_type=AUDIT_ENTITY_QUESTION, entity_id=question.id, request_id=request_id,
                    summary={"from": QUESTION_PUBLISHED, "to": QUESTION_RETIRED})
    return question


def restore_question(*, institution_id, actor_id, question_id, request_id=""):
    with transaction.atomic():
        question = get_question(institution_id, question_id, lock=True)
        if question.status == QUESTION_PUBLISHED:
            return question
        if question.status != QUESTION_RETIRED:
            raise ContentError("Only a retired question can be restored.", "invalid_transition", 409)
        if question.node.status != NODE_PUBLISHED:
            raise ContentError("Restore the topic first.", "invalid_transition", 409)
        question.status = QUESTION_PUBLISHED
        question.retired_at = None
        question.updated_by = actor_id
        question.save(update_fields=["status", "retired_at", "updated_by", "updated_at"])
        write_audit(institution_id=institution_id, actor_id=actor_id, action="question.restore",
                    entity_type=AUDIT_ENTITY_QUESTION, entity_id=question.id, request_id=request_id,
                    summary={"from": QUESTION_RETIRED, "to": QUESTION_PUBLISHED})
    return question


def _renumber(institution_id, node_id):
    remaining = list(ContentQuestion.objects.filter(institution_id=institution_id, node_id=node_id)
                     .order_by("display_order", "created_at").values_list("id", flat=True))
    for position, qid in enumerate(remaining, start=1):
        ContentQuestion.objects.filter(pk=qid).update(display_order=position)


def delete_question(*, institution_id, actor_id, question_id, request_id=""):
    """Decision D6: allowed only when no generated paper or assignment references the question."""
    with transaction.atomic():
        question = get_question(institution_id, question_id, lock=True)
        if ContentQuestionUsage.objects.filter(question=question).exists():
            raise ContentError("This question was used in an exam, so it can only be retired.",
                               "used_question", 409)
        keys = list(question.versions.exclude(image_key="").values_list("image_key", flat=True))
        node_id = question.node_id
        write_audit(institution_id=institution_id, actor_id=actor_id, action="question.delete",
                    entity_type=AUDIT_ENTITY_QUESTION, entity_id=question.id, request_id=request_id,
                    summary={"status_before": question.status})
        question.delete()
        _renumber(institution_id, node_id)
    release_keys_after_commit(keys, "question_deleted")


def discard_draft(*, institution_id, actor_id, question_id, if_match, request_id=""):
    with transaction.atomic():
        question = get_question(institution_id, question_id, lock=True)
        draft = open_version(question)
        if draft is None:
            raise ContentError("No draft to discard.", "invalid_transition", 409)
        if question.published_version_no is None:
            raise ContentError(
                "A question that was never published has no other version to return to. Delete it instead.",
                "cannot_discard_only_version", 409)
        check_precondition(draft, if_match)
        released = []
        if draft.image_key:
            still_used = question.versions.filter(state=VERSION_PUBLISHED, image_key=draft.image_key).exists()
            if not still_used:
                released.append(draft.image_key)
        version_no = draft.version_no
        draft.delete()
        write_audit(institution_id=institution_id, actor_id=actor_id, action="version.discard",
                    entity_type=AUDIT_ENTITY_VERSION, entity_id=question.id,
                    version_no=version_no, request_id=request_id, summary={})
    release_keys_after_commit(released, "draft_discarded")
    return question


def reorder_questions(*, institution_id, actor_id, node_id, ordered_ids, request_id=""):
    node = get_node(institution_id, node_id)
    ids = [str(i) for i in ordered_ids]
    with transaction.atomic():
        # Lock every sibling in one fixed order (by id), then check the set under the lock.
        # Without this, two concurrent reorders update the same rows in different orders and
        # PostgreSQL aborts one with a deadlock (found by the H2 concurrency test).
        locked = ContentQuestion.objects.select_for_update().filter(
            institution_id=institution_id, node=node).order_by("id").values_list("id", flat=True)
        current = {str(i) for i in locked}
        if len(ids) != len(set(ids)) or current != set(ids):
            raise ContentError("The list must contain every question in this topic exactly once.",
                               "set_mismatch", 409)
        for position, qid in enumerate(ids, start=1):
            ContentQuestion.objects.filter(pk=qid, institution_id=institution_id).update(display_order=position)
        write_audit(institution_id=institution_id, actor_id=actor_id, action="question.reorder",
                    entity_type=AUDIT_ENTITY_NODE, entity_id=node.id, request_id=request_id,
                    summary={"count": len(ids)})
    return node


def reorder_nodes(*, institution_id, actor_id, parent_id, ordered_ids, request_id=""):
    """Reorder sibling nodes under one parent (or the root subjects when parent_id is None).
    The list must contain every sibling exactly once, same rule as question reorder."""
    ids = [str(i) for i in ordered_ids]
    with transaction.atomic():
        # Same locking rule as reorder_questions: lock siblings by id, then check the set.
        locked = ContentNode.objects.select_for_update().filter(
            institution_id=institution_id, parent_id=parent_id).order_by("id").values_list("id", flat=True)
        current = {str(i) for i in locked}
        if len(ids) != len(set(ids)) or current != set(ids):
            raise ContentError("The list must contain every sibling exactly once.", "set_mismatch", 409)
        for position, nid in enumerate(ids, start=1):
            ContentNode.objects.filter(pk=nid, institution_id=institution_id).update(display_order=position)
        write_audit(institution_id=institution_id, actor_id=actor_id, action="node.reorder",
                    entity_type=AUDIT_ENTITY_NODE, entity_id=parent_id or institution_id,
                    request_id=request_id, summary={"count": len(ids)})
