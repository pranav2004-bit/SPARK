# Pending — Structured Logging Missing in 3 Services

**Found:** 2026-09-23, while fixing the `control_exchange`/`worker_hijack_root_logger` Celery bugs (see `LIVETRACKER3_V1.md` Phase 17, Task 17.2).
**Status:** Not fixed. Documented for later.

## What's missing

`essay-service` and `assessment-service` both have a structured JSON logging system: every log line is tagged with a `request_id` — nginx's own `$request_id`, forwarded as the `X-Request-ID` header — so one request can be traced end-to-end across the gateway, the Django app, and any Celery task it triggers, just by grepping that one ID.

`analytics-service`, `notification-service`, and `resource-service` have **none of this**. Confirmed by direct inspection:
- No `core/logging_utils.py` in any of the three.
- No `LOGGING` dict in any of their `core/settings.py`.
- Real log output from their worker containers is plain, unlabeled Celery text (`[timestamp: LEVEL/Worker] message`) — no JSON, no request ID, nothing greppable by request.

Not a bug — nothing crashes. It's a missing capability: no way to trace one request's full story across these 3 services' logs.

## What already happened (2026-09-23)

`app.conf.worker_hijack_root_logger = False` was added to all 3 services' `core/celery.py` (correct value, matches essay-service/assessment-service) — but it's currently a no-op there, since there's no JSON formatter for it to protect yet. Left in place; do not remove.

## Reference implementation to copy (already working, don't reinvent)

`services/essay-service/core/logging_utils.py` — the whole mechanism: `CorrelationIdMiddleware`, `JSONFormatter`, `CorrelationIdLogFilter`, `get_request_id()`/`bind_request_id()`.

`services/essay-service/core/settings.py`:
- `MIDDLEWARE` — add `"core.logging_utils.CorrelationIdMiddleware"` near the top of the list, before Django's own `SecurityMiddleware`/`CommonMiddleware` (essay-service also has an unrelated `MaxBodySizeMiddleware` ahead of it — that's a separate feature, not needed for this).
- `LOGGING` dict (~line 356) — `json` formatter, `correlation_id` filter, `console` handler, wired to `root` + `django`/`botocore`/`urllib3` loggers.

## To do, per service

**analytics-service, notification-service** (checked: neither dispatches a Celery task from any HTTP view — tasks-only-from-periodic-schedule, same shape as `assessment-service`):
1. Copy `core/logging_utils.py` from `essay-service`, adjust nothing (it's generic).
2. Add `CorrelationIdMiddleware` to that service's own `MIDDLEWARE` list.
3. Add the same `LOGGING` dict to that service's own `settings.py`.
4. Rebuild service + worker + beat (all 3 build as separate images, same gotcha documented in `docs/essay-service-operations.md`).
5. Verify live: dispatch a real task, confirm `docker logs <worker>` shows JSON with a `request_id` field (not the plain Celery format).
6. Full test suite, twice, clean (this platform's 200% Rule).

**resource-service** — steps 1-6 above, **plus one extra piece essay-service's own Task 17.2 had to build**: this service dispatches Celery tasks directly from HTTP views (`resources/views.py:162,422,738` — `scan_uploaded_file.delay(...)`, `async_delete_file.delay(...)`), so a plain `bind_request_id(self.request.id)` in the task (Celery's own task ID) would **not** trace back to the actual HTTP request that triggered it — only to itself. To get genuine request→task correlation here (not just JSON logs with an unrelated ID), thread the request's own ID through explicitly as an extra argument at each of those 3 dispatch call sites, matching the `correlation_id` pattern in `services/essay-service/essays/scoring.py`'s `_create_and_dispatch_submissions` and `services/essay-service/essays/tasks.py`'s `evaluate_essay`.
