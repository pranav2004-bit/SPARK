# Content Bank (practice-service)

The content bank is the admin tool for building the question bank: subjects, topics, multiple-choice questions, and question images. It lives in `services/practice-service/content/` and is mounted at `/api/practice/content/`. The admin UI is at `/admin/content`.

Specification: `LIVETRACKER4.md` section 2. This document summarizes what is built.

## Feature flag and rollout

- `CONTENT_BANK_ENABLED` (default `False`). While off, every content endpoint and the admin nav entry return 404 or are hidden. Existing practice features are not affected.
- Frontend: `NEXT_PUBLIC_CONTENT_BANK_ENABLED=true` shows the "Content" entry in the admin sidebar.
- Rollback: set the flag to `False` and redeploy. Data is kept; nothing is deleted. Re-enabling restores access to the same data.

## Concepts

- **Nodes** form a tree. Subjects are roots. Topics sit under subjects. Questions sit under topics only (`invalid_parent` otherwise). Tree depth is flexible (minimum two levels).
- **Questions** have versions. A published version is immutable. Editing a published question creates a new draft version by copying the latest published one. Version numbers are never reused.
- **One open version** per question at a time: a draft or an in-review version. Enforced by a partial unique index.
- **Options**: multiple choice only, 2 to 6 options (`CONTENT_OPTION_MIN`/`MAX`). Exactly one correct answer, checked at publish. Option minimum is enforced at publish, maximum at every save.

## State machines

Node and question status: `draft` → `published` → `retired` → `published` (restore). A draft node or question can also be deleted.

Version state: `draft` → `in_review` (submit) → `draft` (withdraw) → `published` (publish). Published is terminal.

All transitions are idempotent: repeating an action that already happened returns 200 with the current state.

## Delete rules (D6, D10)

- A question can be deleted only if no exam has used it. If it has been used, the API returns `used_question` and the only option is retire.
- A node can be deleted only when empty (no child nodes, no questions). Otherwise `node_not_empty`.

## Concurrency

- Every draft write needs `If-Match` with the ETag from the last read. Missing header: 428 `precondition_required`. Stale ETag: 412 `stale_version`. The UI shows a reload prompt.
- ETag = sha256 of the version number and last update time.
- Publish runs in one transaction with a row lock and writes an audit row.

## Images (question media)

1. `POST questions/{id}/image/presign/` with filename and content type (needs `If-Match`). Returns a presigned upload URL under `uploads/content/`.
2. The client PUTs the file directly to storage. The API is not in the upload path.
3. `POST questions/{id}/image/confirm/` with the file key and alt text (alt text required). The server verifies magic bytes, scans for malware (ClamAV), and attaches the image to the draft.
4. `DELETE questions/{id}/image/` removes it.

Accepted types: JPEG, PNG, WebP, GIF, AVIF. Size limit: 5 MB (shared upload constraints). Rejected objects are deleted. A storage or scanner outage returns 503 and keeps the object. Objects that cannot be released are recorded in `content_media_orphan` (see the operations runbook).

## API reference

Base path: `/api/practice/content/`. All endpoints need an admin JWT. The audit endpoint needs super-admin.

| Method | Path | Purpose |
|---|---|---|
| GET, POST | `nodes/` | List children of `parent_id` (`null` for subjects); create |
| GET, PATCH, DELETE | `nodes/{id}/` | Read; rename; delete (empty only) |
| POST | `nodes/{id}/publish/`, `retire/`, `restore/` | Node status transitions |
| POST | `nodes/reorder/` | Body: `parent_id`, `node_ids` (full set) |
| GET, POST | `questions/` | List by `node_id`; create (with version 1) |
| GET, PATCH, DELETE | `questions/{id}/` | Read; save draft (needs `If-Match`); delete |
| POST | `questions/{id}/submit-review/`, `withdraw-review/`, `publish/`, `discard-draft/` | Version transitions (`If-Match`) |
| POST | `questions/{id}/retire/`, `restore/` | Question status transitions |
| POST | `questions/reorder/` | Body: `node_id`, `question_ids` (full set) |
| GET | `questions/{id}/versions/` | Version list |
| GET | `questions/{id}/versions/{n}/` | One version (read only) |
| POST | `questions/{id}/image/presign/`, `image/confirm/` | Image upload |
| DELETE | `questions/{id}/image/` | Remove image |
| GET | `audit/` | Audit events (super-admin); filters `entity_type`, `entity_id`; paged |
| GET | `health/` | Module health (no auth) |

Success responses use the platform envelope `{success, message, data}`. Lists are paged (`page`, `page_size`, max 200) and returned as `{count, total_pages, current_page, next, previous, results}`.

Error responses: `{success: false, message, code, errors?, request_id}`. The `X-Request-ID` response header carries the same id. Codes:

`duplicate_name`, `node_not_empty`, `node_retired`, `invalid_parent`, `used_question`, `stale_version`, `precondition_required`, `invalid_transition`, `storage_unavailable`, `image_rejected`, `image_type_unsupported`, `dependency_unavailable`, `set_mismatch`, `validation_error`, `not_found`.

No response includes answer keys for non-admin callers, and no stack traces.

## Security controls

- Admin-only permission class from practice-service (`IsAdminUser`); audit is `IsSuperAdminUser`.
- Tenant isolation: every query is filtered by the caller's institution. Cross-institution ids return 404.
- Mass assignment: serializers use explicit field allow-lists.
- Rate limits: inherited practice throttles (300/min user, 60/min anonymous). Fail-open on Redis error, with a warning log.
- Audit: every write records an audit event in the same transaction. Summaries never contain question or option text.
- No text in logs: request and audit log lines contain ids, codes and counts only.

## Caching

- Keys: `content:institution:{id}:v{n}:{digest}`. Only the `content:` prefix is used. No practice keys are read or written.
- A successful write bumps the institution's version, which invalidates all of that institution's cached content lists.
- A cache failure falls through to the database. Writes still succeed.
- TTL: `CONTENT_CACHE_TTL_SECONDS` (default 60).

## Frontend

- `/admin/content`: subjects, create, publish, retire, restore.
- `/admin/content/nodes/[node_id]`: topics or questions, create, rename, publish, retire, restore, delete, reorder (up and down buttons, keyboard operable).
- `/admin/content/questions/[question_id]`: editor, save draft, review, publish, retire, restore, discard, delete, image upload and removal, version list.
- `/admin/content/questions/[question_id]/versions/[n]`: read-only version.
- API client: `frontend/src/lib/contentApi.ts`.

## Testing

Backend: `services/practice-service/tests/test_content_*.py`. Concurrency tests run only on PostgreSQL (`core/test_settings_pg.py`). Frontend: `frontend/src/tests/adminContent*.test.tsx` and `contentApiErrors.test.ts`.

## Load test

`python manage.py content_load_test --questions 2000 --workers 50 --requests-per-worker 20` seeds data and reports p50/p95 per endpoint kind, error count, and an SLO verdict. Run it against a non-production database only.

See `docs/content-bank-operations.md` for the operations queries, alerts, and runbooks.
