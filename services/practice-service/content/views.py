"""Content bank HTTP layer (LIVETRACKER4.md section 2.6).

Thin views: parse and allow-list input, call content.services, shape output.
Every endpoint returns 404 while settings.CONTENT_BANK_ENABLED is False.
"""
import logging
import time
import uuid

from django.conf import settings
from django.db import InterfaceError, OperationalError
from django.db.models import Prefetch
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, Throttled
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import StandardResultsPagination
from core.permissions import IsAdminUser, IsSuperAdminUser
from core.responses import success_response
from core.storage import get_cdn_url

from . import cache as content_cache
from . import services as svc
from .errors import ContentError
from .models import (
    ContentAuditEvent, ContentNode, ContentQuestion, ContentQuestionVersion,
)


# ── plumbing ─────────────────────────────────────────────────────────────────

logger = logging.getLogger("content.api")
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _institution(request):
    inst = getattr(request.user, "institution_id", None)
    if not inst:
        raise PermissionDenied("Your account is not linked to an institution.")
    return inst


def _actor(request):
    return request.user.id


def _request_id(request):
    return getattr(request, "content_request_id", "")


def _parse_uuid(value, field):
    if value in (None, ""):
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ContentError(f"{field} must be a valid id.", "validation_error", 400, {field: ["Invalid id."]})


def _if_match(request):
    return request.headers.get("If-Match", "")


def _error_envelope(err):
    payload = {"success": False, "message": err.message, "code": err.code}
    if err.errors is not None:
        payload["errors"] = err.errors
    return Response(payload, status=err.status)


class ContentAPIView(APIView):
    permission_classes = [IsAdminUser]
    _started = None

    def initial(self, request, *args, **kwargs):
        self._started = time.monotonic()
        # One id per request: the client's X-Request-ID when sent, otherwise generated.
        # It is logged, stored on audit rows, returned in the header and in error bodies.
        request.content_request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        if not settings.CONTENT_BANK_ENABLED:
            raise Http404
        super().initial(request, *args, **kwargs)

    def handle_exception(self, exc):
        if isinstance(exc, ContentError):
            return _error_envelope(exc)
        if isinstance(exc, (OperationalError, InterfaceError)):
            logger.error("content: database unavailable: %s", exc.__class__.__name__)
            return _error_envelope(ContentError(
                "The service is temporarily unavailable. Please try again.", "dependency_unavailable", 503))
        response = super().handle_exception(exc)
        if isinstance(exc, Throttled) and exc.wait:
            # The project's custom exception handler rebuilds the body and drops DRF's
            # headers, so set Retry-After here (section 2.12).
            response["Retry-After"] = "%d" % exc.wait
        return response

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if request.method in WRITE_METHODS and response.status_code < 400:
            inst = getattr(request.user, "institution_id", None)
            if inst:
                content_cache.bump(inst)
        rid = _request_id(request)
        if rid:
            response["X-Request-ID"] = rid
            if isinstance(response.data, dict) and response.data.get("success") is False:
                response.data["request_id"] = rid
        if self._started is not None:
            latency_ms = int((time.monotonic() - self._started) * 1000)
            logger.info("content_request method=%s endpoint=%s status=%s latency_ms=%s request_id=%s",
                        request.method, self.__class__.__name__, response.status_code, latency_ms, rid)
        return response

    def paginate(self, request, queryset, serialize):
        inst = getattr(request.user, "institution_id", None)
        suffix = "list:" + request.get_full_path()
        if inst:
            cached = content_cache.get(inst, suffix)
            if cached is not None:
                return Response(cached)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        response = paginator.get_paginated_response([serialize(obj) for obj in page])
        if inst:
            content_cache.set(inst, suffix, response.data)
        return response


def _options_payload(version):
    # .all() + sort in Python so a prefetch is used; order_by() would bypass it.
    options = sorted(version.options.all(), key=lambda o: o.display_order)
    return [
        {"label": o.label, "option_text": o.option_text, "is_correct": o.is_correct, "display_order": o.display_order}
        for o in options
    ]


def _version_payload(version, *, include_answers=True):
    data = {
        "version_no": version.version_no,
        "state": version.state,
        "question_text": version.question_text,
        "explanation": version.explanation,
        "image_key": version.image_key,
        "image_url": get_cdn_url(version.image_key) if version.image_key else "",
        "image_alt_text": version.image_alt_text,
        "published_at": version.published_at,
        "published_by": version.published_by,
        "options": _options_payload(version),
    }
    if not include_answers:
        for opt in data["options"]:
            opt.pop("is_correct", None)
    return data


def _node_payload(node):
    return {
        "id": str(node.id),
        "parent_id": str(node.parent_id) if node.parent_id else None,
        "name": node.name,
        "display_order": node.display_order,
        "status": node.status,
        "child_count": node.children.count(),
        "question_count": node.questions.count(),
        "published_at": node.published_at,
        "retired_at": node.retired_at,
    }


def _question_payload(question, *, include_answers=True):
    editable = svc.editable_version(question)
    return {
        "id": str(question.id),
        "node_id": str(question.node_id),
        "display_order": question.display_order,
        "status": question.status,
        "current_version_no": question.current_version_no,
        "published_version_no": question.published_version_no,
        "editable_version": _version_payload(editable, include_answers=include_answers) if editable else None,
    }


def _with_etag(response, version):
    if version is not None:
        response["ETag"] = svc.etag_for(version)
    return response


def _as_dict(body, key="body"):
    if not isinstance(body, dict):
        raise ContentError(f"{key} must be a JSON object.", "validation_error", 422)
    return body


def _as_list(value, field):
    if not isinstance(value, list):
        raise ContentError(f"{field} must be a list.", "validation_error", 400, {field: ["Must be a list."]})
    return value


# ── nodes ────────────────────────────────────────────────────────────────────

class ContentNodeListCreateView(ContentAPIView):
    def get(self, request):
        inst = _institution(request)
        qs = ContentNode.objects.filter(institution_id=inst)
        parent_id = request.query_params.get("parent_id")
        if parent_id == "null" or parent_id == "":
            qs = qs.filter(parent_id__isnull=True)
        elif parent_id:
            qs = qs.filter(parent_id=_parse_uuid(parent_id, "parent_id"))
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        qs = qs.order_by("display_order", "created_at")
        return self.paginate(request, qs, _node_payload)

    def post(self, request):
        inst = _institution(request)
        body = _as_dict(request.data)
        node = svc.create_node(
            institution_id=inst, actor_id=_actor(request), name=body.get("name", ""),
            parent_id=_parse_uuid(body.get("parent_id"), "parent_id"), request_id=_request_id(request),
        )
        return success_response(data=_node_payload(node), message="Node created.", status_code=201)


class ContentNodeDetailView(ContentAPIView):
    def get(self, request, pk):
        node = svc.get_node(_institution(request), pk)
        return success_response(data=_node_payload(node))

    def patch(self, request, pk):
        body = _as_dict(request.data)
        node = svc.update_node(institution_id=_institution(request), actor_id=_actor(request),
                               node_id=pk, name=body.get("name"), request_id=_request_id(request))
        return success_response(data=_node_payload(node), message="Node updated.")

    def delete(self, request, pk):
        svc.delete_node(institution_id=_institution(request), actor_id=_actor(request),
                        node_id=pk, request_id=_request_id(request))
        return success_response(message="Node deleted.")


class ContentNodeActionView(ContentAPIView):
    ACTIONS = {
        "publish": svc.publish_node,
        "retire": svc.retire_node,
        "restore": svc.restore_node,
    }

    def post(self, request, pk, action):
        handler = self.ACTIONS.get(action)
        if handler is None:
            raise Http404
        node = handler(institution_id=_institution(request), actor_id=_actor(request),
                       node_id=pk, request_id=_request_id(request))
        return success_response(data=_node_payload(node), message=f"Node {action}ed.")


class ContentNodeReorderView(ContentAPIView):
    def post(self, request):
        body = _as_dict(request.data)
        ids = _as_list(body.get("node_ids", []), "node_ids")
        svc.reorder_nodes(
            institution_id=_institution(request), actor_id=_actor(request),
            parent_id=_parse_uuid(body.get("parent_id"), "parent_id"),
            ordered_ids=[_parse_uuid(i, "node_ids") for i in ids], request_id=_request_id(request),
        )
        return success_response(message="Nodes reordered.")


# ── questions ────────────────────────────────────────────────────────────────

class ContentQuestionListCreateView(ContentAPIView):
    def get(self, request):
        inst = _institution(request)
        qs = ContentQuestion.objects.filter(institution_id=inst)
        node_id = request.query_params.get("node_id")
        if node_id:
            qs = qs.filter(node_id=_parse_uuid(node_id, "node_id"))
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(versions__question_text__icontains=search).distinct()
        qs = qs.order_by("display_order", "created_at").prefetch_related(
            Prefetch("versions", queryset=ContentQuestionVersion.objects.prefetch_related("options")))
        return self.paginate(request, qs, lambda q: _question_payload(q, include_answers=False))

    def post(self, request):
        inst = _institution(request)
        body = _as_dict(request.data)
        options = _as_list(body.get("options", []), "options")
        question, version = svc.create_question(
            institution_id=inst, actor_id=_actor(request),
            node_id=_parse_uuid(body.get("node_id"), "node_id"),
            text=body.get("text", ""), options=options,
            explanation=body.get("explanation", ""), request_id=_request_id(request),
        )
        question = ContentQuestion.objects.get(pk=question.pk)
        response = success_response(data=_question_payload(question), message="Question created.", status_code=201)
        return _with_etag(response, version)


class ContentQuestionDetailView(ContentAPIView):
    def get(self, request, pk):
        question = svc.get_question(_institution(request), pk)
        response = success_response(data=_question_payload(question))
        return _with_etag(response, svc.editable_version(question))

    def patch(self, request, pk):
        body = _as_dict(request.data)
        changes = {}
        for key in ("text", "explanation"):
            if key in body:
                changes[key] = body[key]
        if "options" in body:
            changes["options"] = _as_list(body["options"], "options")
        question, draft = svc.update_draft(
            institution_id=_institution(request), actor_id=_actor(request), question_id=pk,
            if_match=_if_match(request), changes=changes, request_id=_request_id(request),
        )
        response = success_response(data=_question_payload(question), message="Draft saved.")
        return _with_etag(response, draft)

    def delete(self, request, pk):
        svc.delete_question(institution_id=_institution(request), actor_id=_actor(request),
                            question_id=pk, request_id=_request_id(request))
        return success_response(message="Question deleted.")


class ContentQuestionActionView(ContentAPIView):
    NEEDS_IF_MATCH = {"submit-review", "withdraw-review", "publish", "discard-draft"}

    def post(self, request, pk, action):
        inst = _institution(request)
        actor = _actor(request)
        rid = _request_id(request)
        if action == "submit-review":
            question, version = svc.submit_review(institution_id=inst, actor_id=actor, question_id=pk,
                                                  if_match=_if_match(request), request_id=rid)
        elif action == "withdraw-review":
            question, version = svc.withdraw_review(institution_id=inst, actor_id=actor, question_id=pk,
                                                    if_match=_if_match(request), request_id=rid)
        elif action == "publish":
            question, version = svc.publish_question(institution_id=inst, actor_id=actor, question_id=pk,
                                                     if_match=_if_match(request), request_id=rid)
        elif action == "retire":
            question = svc.retire_question(institution_id=inst, actor_id=actor, question_id=pk, request_id=rid)
            version = None
        elif action == "restore":
            question = svc.restore_question(institution_id=inst, actor_id=actor, question_id=pk, request_id=rid)
            version = None
        elif action == "discard-draft":
            question = svc.discard_draft(institution_id=inst, actor_id=actor, question_id=pk,
                                         if_match=_if_match(request), request_id=rid)
            version = svc.editable_version(question)
        else:
            raise Http404
        response = success_response(data=_question_payload(question), message=f"Question {action} done.")
        return _with_etag(response, version or svc.editable_version(question))


class ContentQuestionReorderView(ContentAPIView):
    def post(self, request):
        body = _as_dict(request.data)
        ids = _as_list(body.get("question_ids", []), "question_ids")
        svc.reorder_questions(
            institution_id=_institution(request), actor_id=_actor(request),
            node_id=_parse_uuid(body.get("node_id"), "node_id"),
            ordered_ids=[_parse_uuid(i, "question_ids") for i in ids], request_id=_request_id(request),
        )
        return success_response(message="Questions reordered.")


# ── versions ─────────────────────────────────────────────────────────────────

class ContentVersionListView(ContentAPIView):
    def get(self, request, pk):
        question = svc.get_question(_institution(request), pk)
        versions = question.versions.order_by("-version_no")
        return success_response(data=[
            {"version_no": v.version_no, "state": v.state, "published_at": v.published_at,
             "published_by": v.published_by}
            for v in versions
        ])


class ContentVersionDetailView(ContentAPIView):
    def get(self, request, pk, version_no):
        question = svc.get_question(_institution(request), pk)
        version = ContentQuestionVersion.objects.filter(question=question, version_no=version_no).first()
        if version is None:
            raise ContentError("Version not found.", "not_found", 404)
        return success_response(data=_version_payload(version))


# ── audit (super admin only) ─────────────────────────────────────────────────

class ContentAuditListView(APIView):
    permission_classes = [IsSuperAdminUser]

    def initial(self, request, *args, **kwargs):
        if not settings.CONTENT_BANK_ENABLED:
            raise Http404
        super().initial(request, *args, **kwargs)

    def handle_exception(self, exc):
        if isinstance(exc, ContentError):
            return _error_envelope(exc)
        return super().handle_exception(exc)

    def get(self, request):
        inst = _institution(request)
        qs = ContentAuditEvent.objects.filter(institution_id=inst)
        entity_type = request.query_params.get("entity_type")
        if entity_type:
            qs = qs.filter(entity_type=entity_type)
        entity_id = request.query_params.get("entity_id")
        if entity_id:
            qs = qs.filter(entity_id=_parse_uuid(entity_id, "entity_id"))
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        rows = [
            {"id": str(e.id), "actor_id": str(e.actor_id), "action": e.action, "entity_type": e.entity_type,
             "entity_id": str(e.entity_id), "version_no": e.version_no, "summary": e.summary,
             "request_id": e.request_id, "created_at": e.created_at}
            for e in page
        ]
        return paginator.get_paginated_response(rows)


# ── question images (section 2.9) ────────────────────────────────────────────

class ContentQuestionImagePresignView(ContentAPIView):
    def post(self, request, pk):
        from . import images
        body = _as_dict(request.data)
        result = images.presign_draft_image(
            institution_id=_institution(request), question_id=pk, if_match=_if_match(request),
            filename=body.get("filename", ""), content_type=body.get("content_type", ""),
        )
        return success_response(data=result, message="Upload URL issued.")


class ContentQuestionImageConfirmView(ContentAPIView):
    def post(self, request, pk):
        from . import images
        body = _as_dict(request.data)
        question, draft = images.confirm_draft_image(
            institution_id=_institution(request), actor_id=_actor(request), question_id=pk,
            if_match=_if_match(request), file_key=body.get("file_key", ""),
            image_alt_text=body.get("image_alt_text", ""), request_id=_request_id(request),
        )
        response = success_response(data=_question_payload(question), message="Image attached.")
        return _with_etag(response, draft)



class ContentQuestionImageRemoveView(ContentAPIView):
    http_method_names = ["delete", "options"]

    def delete(self, request, pk):
        from . import images
        question, draft = images.remove_draft_image(
            institution_id=_institution(request), actor_id=_actor(request), question_id=pk,
            if_match=_if_match(request), request_id=_request_id(request),
        )
        response = success_response(data=_question_payload(question), message="Image removed.")
        return _with_etag(response, draft)


class ContentHealthView(APIView):
    permission_classes = []
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        from django.db import connection
        from django.core.cache import cache as django_cache
        if not settings.CONTENT_BANK_ENABLED:
            raise Http404
        db_ok = cache_ok = False
        try:
            connection.ensure_connection()
            db_ok = True
        except Exception:
            pass
        try:
            django_cache.set("content:health", "ok", 5)
            cache_ok = django_cache.get("content:health") == "ok"
        except Exception:
            pass
        storage_configured = bool(getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""))
        overall = "ok" if (db_ok and cache_ok) else "degraded"
        return success_response(data={
            "status": overall,
            "module": "content",
            "db": "ok" if db_ok else "error",
            "cache": "ok" if cache_ok else "error",
            "storage": "configured" if storage_configured else "not_configured",
        })
