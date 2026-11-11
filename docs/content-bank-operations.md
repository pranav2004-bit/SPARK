# Content Bank — Operations

Operational reference for the content bank. Design and API: `docs/content-bank.md`. Alert definitions: `services/practice-service/content/ops_alerts.json`. Dashboard panels: `services/practice-service/content/ops_dashboard.json`.

## Signals

| Signal | Where | Notes |
|---|---|---|
| Request log | logger `content.api`, line `content_request method=… endpoint=… status=… latency_ms=… request_id=…` | One line per request |
| Audit counter | logger `content.audit`, line `content_audit action=… entity_type=… request_id=…` | One line per write. Counter source for write metrics |
| Rate-limit fail-open | logger `core.throttling_resilience`, warning containing `failing open` | Non-zero means Redis is unavailable for throttling |
| Health | `GET /api/practice/content/health/` (no auth) | `status`, `db`, `cache`, `storage` |
| Audit table | `content_audit_event` (super-admin endpoint `audit/`) | Who did what, when; no text |

Log lines never contain question or option text, explanations, or answer data.

## Health

`GET /api/practice/content/health/` returns `status: ok` when the database and cache respond, otherwise `degraded`. `storage` shows `configured` or `not_configured`. It returns 404 while the flag is off.

## Alerts

Definitions and thresholds: `content/ops_alerts.json`.

| Alert | Condition | Severity |
|---|---|---|
| `content_5xx_rate_high` | 5xx share of `content_request` above 1% over 5 minutes | page |
| `content_orphan_growth` | more than 100 `content_media_orphan` rows created in 24 hours | ticket |
| `content_publish_latency_high` | p95 latency of publish endpoints above 1 second over 15 minutes | ticket |
| `content_health_dependency_down` | health `db` or `cache` is `error` for 5 minutes | page |

## Dashboard panels

Defined in `content/ops_dashboard.json`: requests per minute by status, 5xx rate, publish latency p95, writes by action, orphans created in 24 hours, dependency health, rate-limit fail-open events.

## Runbooks

### 5xx

1. Check `content_request` lines with `status>=500` and their `request_id`; search the same id in the application log for the traceback.
2. Check `GET /api/practice/content/health/`. If `db` is `error`, follow the database runbook first. If `cache` is `error`, reads are served from the database; check Redis.
3. If errors continue after dependencies recover, roll back with the flag (`CONTENT_BANK_ENABLED=False`) and open an incident.

### Orphans

Orphans are media objects that could not be deleted from storage after a rejected upload or a replaced image. They are recorded in `content_media_orphan`.

1. Dry run first (default): `python manage.py content_cleanup_orphans`. It lists keys that are in the ledger and not referenced by any version.
2. Review the list. Apply only after checking storage access: `python manage.py content_cleanup_orphans --apply`.
3. Only keys in the ledger and not referenced by a version are deleted.
4. If the ledger keeps growing, check storage credentials and the scanner (ClamAV) first; a storage outage is the usual cause.

### Latency

1. Find the slow endpoint from `content_request` latency values.
2. Check database load and connection count (PgBouncer). The list endpoint prefetches versions and options, so its query count does not grow with the number of questions on a page; a regression shows as failure of `TestListQueryCount`.
3. Check cache hit behaviour: a write bumps the institution's cache version, so bursts of writes reduce cache hits.

### Health

1. `db: error`: check PostgreSQL and PgBouncer reachability from the practice-service container.
2. `cache: error`: check Redis. Content reads fall through to the database, so users see slower responses, not errors.
3. `storage: not_configured`: image upload returns 503 `storage_unavailable` until the S3 settings are present.

## Common support questions

- "My save says the question changed." That is a 412: someone else saved in between. Reload the question and re-apply the edit.
- "I cannot delete a question." It was used in an exam. Retire it instead.
- "I cannot delete a topic." It still has questions or child topics. Move or delete them first.
- "An error shows a reference." Give the reference to the engineer; it is the `request_id` in the logs.

## Enabling and disabling

- Enable: set `CONTENT_BANK_ENABLED=True` (backend) and `NEXT_PUBLIC_CONTENT_BANK_ENABLED=true` (frontend build), then redeploy both.
- Disable: set `CONTENT_BANK_ENABLED=False` and redeploy. Content data is kept.
