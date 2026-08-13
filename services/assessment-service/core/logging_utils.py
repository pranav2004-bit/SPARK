"""
logging_utils.py — Task 13.2's structured (JSON) logging + correlation ID.

The correlation ID is nginx's own $request_id (gateway/nginx.conf,
nginx.dev.conf's proxy_params.conf already does `proxy_set_header
X-Request-ID $request_id;`, and the gateway's own JSON access log already
records the same value) — Django doesn't invent a new ID, it just picks up
the one nginx already generated and put in every access log line, so a
single request is traceable end-to-end: nginx access log -> this service's
logs -> the X-Request-ID response header the client actually received ->
(when Sentry is enabled) the Sentry event's own tag, all sharing one value.

A contextvar (not a plain global/thread-local) so this is safe under both
sync Django views and any future async code path without extra plumbing.
Celery tasks aren't HTTP-triggered in this service (the two sweep tasks are
periodic, not per-request — see assessments/tasks.py), so there's no
request to inherit an ID from; CorrelationIdLogFilter falls back to
Celery's own task_id there instead, which is the equivalent "what single
unit of work produced this log line" identifier for a task run.
"""
import contextvars
import json
import logging
import uuid

_request_id_var: contextvars.ContextVar = contextvars.ContextVar("request_id", default=None)

# Standard LogRecord attributes — anything else set via logger.info(...,
# extra={...}) is assumed to be intentional structured context and gets
# folded into the JSON output.
_RESERVED_RECORD_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
})


def get_request_id():
    return _request_id_var.get()


def new_request_id() -> str:
    """Only used as a fallback (direct internal traffic bypassing nginx,
    or a Celery task with no request context) — normal traffic always
    carries nginx's own X-Request-ID through."""
    return str(uuid.uuid4())


class bind_request_id:
    """Context manager version of the same contextvar binding
    CorrelationIdMiddleware does for HTTP requests — used by
    assessments/tasks.py's sweep tasks so every log line inside one sweep
    run (including nested calls into scoring.py) shares that run's own
    Celery task_id as its correlation ID, the task-run equivalent of an
    HTTP request's X-Request-ID."""

    def __init__(self, value):
        self.value = value
        self._token = None

    def __enter__(self):
        self._token = _request_id_var.set(self.value)
        return self

    def __exit__(self, *exc_info):
        _request_id_var.reset(self._token)


class CorrelationIdMiddleware:
    """First in MIDDLEWARE, right after MaxBodySizeMiddleware (Task 13.1) —
    reads nginx's X-Request-ID (or generates one, for traffic that reaches
    this service directly) and makes it available to every log line for
    the duration of this request via the contextvar above, and echoes it
    back on the response so the client/caller can quote it back for
    support (matches core/exceptions.py's error responses, which do not
    currently surface it — kept as a response header instead of the JSON
    body to avoid changing every error response's schema)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or new_request_id()
        token = _request_id_var.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            _request_id_var.reset(token)
        response["X-Request-ID"] = request_id
        return response


class CorrelationIdLogFilter(logging.Filter):
    """Attached to every handler (settings.py's LOGGING) — stamps
    record.request_id so the JSON formatter below can include it even for
    log lines emitted deep inside a view/task, not just at the
    request/task entry point."""

    def filter(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        return True


class JSONFormatter(logging.Formatter):
    """No new dependency (matches this project's existing "stdlib
    preferred" convention — e.g. core/user_service_client.py uses urllib,
    not requests) — a JSON log line needs nothing more than the stdlib
    logging + json modules."""

    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
