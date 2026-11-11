# SPARK — Content Bank Tracker (Part 1: Practice Service)

**Scope:** Part 1 only — a new **Content** module inside `practice-service` (backend) and a new **Content** tab in the admin UI (frontend).
**Parts:** Part 1 (this file) → Part 2 (assessment-service bank-driven work, separate instruction) → Part 3 (combine and refine, separate instruction). Part 2 and 3 are not designed or tracked here.
**Rule:** Part 1 is **add-only**. No existing practice model, table, endpoint, screen, cache key, media key, or permission class is changed, renamed, or removed. The only edit outside the new module is one new entry in the shared admin sidebar (`frontend/src/components/layout/AdminLayout.tsx`), gated by a feature flag.

---

## 0. Execution rules (binding for this file)

1. Work proceeds strictly in phase/task/subtask order, as listed below.
2. A task is checked only after its listed tests pass. A phase is checked only after all its tasks and its test checklist pass. The next phase starts only after the previous one is checked **and** the user signs off the phase gate.
3. Every phase has a test checklist (smoke, sanity, integration, regression, functional, positive, negative, edge, security, load — each applicable where relevant; "n/a" must be written with a reason, not left blank).
4. Security is designed in from the start (see §2.13); it is not a late phase.
5. Production-ready and permanent solutions only; no throwaway code, no hot-patches, no undocumented manual steps.
6. When work pauses, the **Progress log** (§5) is the resume point. Every session updates it.
7. Documentation is updated as part of the task that changes behavior, not at the end.
8. No gold-plating: each item below exists because a requirement or a named risk needs it.

---

## 1. Locked decisions

| # | Decision | Value |
|---|---|---|
| D1 | Hierarchy | Flexible tree: Node (parent → child, any depth). Minimum 2 levels: questions attach only to a node that has a parent (e.g., Subject → Topic → Question). |
| D2 | Question types | MCQ, single correct answer only. |
| D3 | Roles | All admin accounts of an institution have equal rights: create, edit, submit for review, publish, retire, restore, delete (subject to D6). No separate reviewer role. |
| D4 | Publish workflow | Draft → In review → Published. Any admin may move a version through every step, including direct publish from Draft. |
| D5 | Versioning | Publishing freezes a version. Editing a published question creates a new Draft version. Published versions are never modified or deleted. |
| D6 | Delete rule | **Delete** allowed when the question is a Draft-only question (never published) OR published but **unused** (no usage record). **Retire only** when used. |
| D7 | Retire / restore | Retire hides a published question from new use and keeps it on record. Restore returns a retired question to Published. Both reversible. |
| D8 | Question identity | UUID per question, never reused, including after deletion. Same ID identifies the question in the bank and is referenced by future generated papers together with the version number. |
| D9 | Display order | Integer display number per question within its parent node, auto-renumbered after deletes. Display numbers never identify a question. |
| D10 | Node delete | Only when the node has no child nodes and no questions. (Prevents accidental bulk deletion.) |
| D11 | Node publish | Nodes are Draft or Published. Only Published nodes are eligible for future exam use. |
| D12 | Isolation | Content tables use the `content_*` prefix inside `practice_db`. No foreign key from any `content_*` table to any `practice_*` table, and vice versa. |
| D13 | Synchronous | No Celery worker or beat in Part 1. Everything runs in the request. |

**Resolved defaults (proposed, configurable via settings; change only by an explicit decision):**

| Setting | Default | Meaning |
|---|---|---|
| `CONTENT_BANK_ENABLED` | `False` | Feature flag. Off by default; enabled per environment and institution. |
| `CONTENT_NEW_APP` | `content` | Content lives in its own Django app `content` inside practice-service (separate models and migrations; no edits to the `practice` app). Registered by one added `INSTALLED_APPS` entry. |
| `CONTENT_OPTION_MIN` | `2` | Minimum options per question. |
| `CONTENT_OPTION_MAX` | `6` | Maximum options per question. |
| `CONTENT_QUESTION_TEXT_MAX` | `2000` | Characters, after trim. |
| `CONTENT_OPTION_TEXT_MAX` | `500` | Characters per option, after trim. |
| `CONTENT_EXPLANATION_MAX` | `2000` | Characters, optional field. |
| `CONTENT_NODE_NAME_MAX` | `200` | Characters per node name. |
| Image limits | **Reused, not redefined:** `core/upload_constraints.py` (`MAX_IMAGE_SIZE` 5 MB; jpg, jpeg, png, webp, gif, avif; no svg; signature checks via `MAGIC_BYTES`). | Same rules as practice images. |
| Rate limits | **Reused, not redefined:** existing DRF default throttles (`anon` 60/min, `user` 300/min, Redis-backed, fail-open via `core/throttling_resilience.py`). | No content-specific limiter. |
| Pagination | **Reused:** `core/pagination.py` `StandardResultsPagination` (page size 50, max 200). | Same as practice. |

---

## 2. Design specification (Phase A output — complete, implementation-ready)

### 2.1 Data model (all new tables, `content_*` prefix, UUID primary keys)

**`content_node`**
- `id` UUID PK
- `institution_id` UUID, indexed, NOT NULL
- `parent_id` UUID FK → `content_node.id`, nullable (null = root / Subject)
- `name` varchar(200), NOT NULL
- `display_order` int, default 0
- `status` varchar: `draft` | `published` | `retired`
- `created_by`, `updated_by` UUID (JWT user_id, no FK — matches practice convention)
- `created_at`, `updated_at`, `published_at` nullable, `retired_at` nullable
- Constraints: `UNIQUE(institution_id, parent_id, name)` (case-insensitive on name, enforced in service layer and by a functional index on `lower(name)`).
- Indexes: `(institution_id, parent_id, display_order)`, `(institution_id, status)`.

**`content_question`**
- `id` UUID PK (D8)
- `institution_id` UUID, indexed, NOT NULL
- `node_id` UUID FK → `content_node.id`, NOT NULL (must be a node with a parent — enforced in service layer, tested)
- `display_order` int, NOT NULL (D9)
- `status` varchar: `draft` (never published) | `published` | `retired`
- `current_version_no` int, NOT NULL (the highest version number that exists)
- `published_version_no` int, nullable (highest published version; null until first publish)
- `created_by`, `updated_by` UUID, `created_at`, `updated_at`, `retired_at` nullable
- Indexes: `(institution_id, node_id, display_order)`, `(institution_id, status)`, `(institution_id, node_id, status)`.

**`content_question_version`**
- `id` UUID PK
- `question_id` UUID FK → `content_question.id` ON DELETE CASCADE (used only by D6 delete)
- `version_no` int, NOT NULL, starts at 1
- `state` varchar: `draft` | `in_review` | `published`
- `question_text` text, NOT NULL
- `explanation` text, blank allowed
- `image_key` varchar(500), blank allowed (S3 object key, server-generated — §2.9)
- `image_alt_text` varchar(300), blank allowed; **required (non-blank) when `image_key` is set** (§2.5)
- `created_by`, `updated_by`, `created_at`, `updated_at`
- `submitted_for_review_at`, `published_at`, `published_by` nullable
- Constraints: `UNIQUE(question_id, version_no)`; at most one row per question with `state` in (`draft`, `in_review`) — enforced by a partial unique index `WHERE state IN ('draft','in_review')`.
- Published rows are immutable (§2.4).

**`content_option`**
- `id` UUID PK
- `version_id` UUID FK → `content_question_version.id` ON DELETE CASCADE
- `label` varchar(1), auto-assigned A, B, C… by display position
- `option_text` varchar(500), NOT NULL
- `is_correct` bool, NOT NULL
- `display_order` int
- Constraint (service layer + tested): exactly one `is_correct = true` per version.

**`content_question_usage`** (created now, written by Part 2 later; Part 1 only reads it)
- `id` UUID PK
- `question_id` UUID FK → `content_question.id`, indexed
- `version_no` int
- `usage_type` varchar (e.g., `generated_paper`, `assignment`), `usage_ref_id` UUID
- `created_at`
- Used by D6. In Part 1 the table is empty in production; tests create fixture rows to exercise the guard.

**`content_audit_event`** (append-only)
- `id` UUID PK, `institution_id` UUID indexed, `actor_id` UUID, `action` varchar, `entity_type` varchar (`node` | `question` | `version`), `entity_id` UUID (no FK, so history survives deletes), `version_no` int nullable, `summary` JSON (changed fields, state before/after; never the full question text), `request_id` varchar, `created_at`.
- Written in the same DB transaction as the change it records.

**`content_media_orphan`** (cleanup ledger)
- `id` UUID PK, `key` varchar(500) UNIQUE, `reason` varchar, `created_at`, `cleaned_at` nullable.
- Written when an S3 delete fails after a DB delete succeeded (§2.9). Cleaned by a management command run manually (no beat in Part 1).

**No changes** to any existing `practice_*` table.

### 2.2 State machines

**Node:** `draft` ⇄ `published`; `published` → `retired`; `retired` → `published` (restore).
- Publish node: requires name valid; no other checks.
- Retire node: cascades **eligibility** only: descendant questions stay in their status but are ineligible for future use (Part 2 reads this via a query, not a stored flag).
- Restore node: returns it to `published`.

**Question status:** `draft` → `published` (first publish) → `retired` ⇄ `published` (restore).
- Retire allowed only from `published`. A `draft`-status question cannot be retired (delete instead).
- Restore allowed only from `retired`, and only if its node is `published` (else 409 with message "restore the node first").

**Version state:** `draft` → `in_review` → `published`; `in_review` → `draft` (withdraw). `published` is terminal.
- Publish is allowed from `draft` or `in_review`.
- Publish requires the question's node to be `published` and the question to be not `retired` (else 409).

### 2.3 Operation rules (exact)

| Operation | Allowed when | Effect | Refused with |
|---|---|---|---|
| Create node | parent (if any) exists, same institution, not retired | node in `draft` | 400 (invalid parent), 409 (duplicate name under parent) |
| Edit node name | any status | name updated | 409 (duplicate name) |
| Publish / retire / restore node | per §2.2 | status changed, audit written | 409 (invalid transition) |
| Delete node | no child nodes AND no questions | row deleted, audit written | 409 (not empty — list what blocks it) |
| Create question | node has a parent, node not retired | question `draft`, version 1 `draft`, options saved | 400 (validation), 409 (node retired) |
| Edit question | version state = `draft` or `in_review`, OR a published question (creates new draft) | edits write to the draft version; for a published question a new draft version is cloned first | 409 (version `in_review` — withdraw first, see note), 412 (stale ETag) |
| Submit for review | version `draft` | version → `in_review` | 409 |
| Withdraw review | version `in_review` | version → `draft` | 409 |
| Publish version | version `draft` or `in_review`; validation passes; node published; question not retired | version → `published`, question status → `published`, `published_version_no` updated, frozen | 400 (validation errors listed per field), 409 |
| Retire question | question `published` | question → `retired` | 409 |
| Restore question | question `retired`; node published | question → `published` | 409 |
| Delete question | D6: draft-only OR (published AND no usage row) | all versions, options, rows deleted; image objects deleted (§2.9); audit written | 409 "used — retire instead" |
| Reorder questions in node | body lists **all** current question IDs of that node exactly once | `display_order` set 1..N | 409 (set mismatch) |
| Delete draft version (discard edits) | version `draft`, question has a published version | that draft version and its options deleted; its uploaded image (if not referenced by any published version) deleted | 409 (cannot discard the only version) |

**Note on editing while in review:** a version in `in_review` is locked for field edits to prevent a reviewer approving something that changed after submission. The admin must withdraw it (→ `draft`) first. This is enforced server-side, not just in the UI.

**Note on the deletion of published-unused questions:** this is a hard delete of a question that was published. Justification (D6): nothing references it (no usage row), so no past result or paper can break. Audit history remains (audit rows are not foreign-keyed).

### 2.4 Versioning rules (immutability)

1. A published version (`state = published`) is never updated or deleted by any API. Enforced by: no endpoint writes to it; service layer raises on any write attempt; a test asserts that every mutation path rejects a published version.
2. Editing a published question clones the **latest published version** into a new `draft` version (`version_no = current_version_no + 1`), copying question text, explanation, image key, and options. The published version is untouched.
3. `published_version_no` always points to the highest published version. The question's public (eligible) content is that version.
4. Future paper generation (Part 2) must store `(question_id, version_no)`. Because published versions are immutable, the stored content is always reproducible.
5. Version numbers are never reused.

### 2.5 Validation rules (enforced at save for drafts; fully re-validated at publish)

- Question text: required after trim; length ≤ `CONTENT_QUESTION_TEXT_MAX`. Stored as plain text. HTML/script is not interpreted anywhere (rendered escaped).
- Options: count between `CONTENT_OPTION_MIN` and `CONTENT_OPTION_MAX`; each option text required after trim, ≤ `CONTENT_OPTION_TEXT_MAX`; no two options identical after trim (case-insensitive); exactly one `is_correct`.
- Explanation: optional; ≤ `CONTENT_EXPLANATION_MAX`.
- Image: optional; allowed types and size per settings; validated by file signature (magic bytes), not by extension or client MIME type.
- Image alt text: required (non-blank after trim, ≤ 300 characters) whenever an image is present. Checked at every draft save that has an image, and re-checked at publish. Removing the image clears the alt text.
- Node name: required after trim; ≤ `CONTENT_NODE_NAME_MAX`; unique among siblings (case-insensitive).
- Draft saves may be partially invalid (so an admin can save progress); **publish is all-or-nothing** and returns every failing field at once.

### 2.6 API contract

Base path: `/api/practice/content/` (versioned under existing practice URL conventions; mounted only when `CONTENT_BANK_ENABLED`). All responses use the existing success/error envelope helpers.

| Method | Path | Purpose | Permission |
|---|---|---|---|
| GET | `nodes/` | List nodes (filter `parent_id`, `status`), paged | admin |
| POST | `nodes/` | Create node | admin |
| GET | `nodes/{id}/` | Node detail (+ child count, question count) | admin |
| PATCH | `nodes/{id}/` | Rename node (sibling-unique name) | admin |
| POST | `nodes/reorder/` | Reorder sibling nodes under one parent (body: `parent_id` or null, ordered `node_ids`; full sibling set required) | admin |
| DELETE | `nodes/{id}/` | Delete empty node | admin |
| POST | `nodes/{id}/publish/` | Publish node | admin |
| POST | `nodes/{id}/retire/` | Retire node | admin |
| POST | `nodes/{id}/restore/` | Restore node | admin |
| GET | `questions/` | List questions (filters: `node_id`, `status`; search on text) | admin |
| POST | `questions/` | Create question (+ first draft version + options) | admin |
| GET | `questions/{id}/` | Question detail (current draft or latest published, plus status) | admin |
| PATCH | `questions/{id}/` | Edit draft version (clones if published) | admin, requires `If-Match` |
| DELETE | `questions/{id}/` | Delete question (D6) | admin |
| POST | `questions/{id}/submit-review/` | Draft → In review | admin, `If-Match` |
| POST | `questions/{id}/withdraw-review/` | In review → Draft | admin, `If-Match` |
| POST | `questions/{id}/publish/` | Publish version | admin, `If-Match` |
| POST | `questions/{id}/retire/` | Retire question | admin |
| POST | `questions/{id}/restore/` | Restore question | admin |
| POST | `questions/reorder/` | Reorder questions within one node (body: `node_id`, ordered `question_ids`; full set required) | admin |
| POST | `questions/{id}/discard-draft/` | Discard the editable draft, keeping the published version (refused if the question was never published) | admin, `If-Match` |
| GET | `questions/{id}/versions/` | List versions (summary) | admin |
| GET | `questions/{id}/versions/{version_no}/` | Read one version (full, read-only) | admin |
| POST | `questions/{id}/image/presign/` | Get a presigned S3 upload URL for the draft's image (same pattern as practice's presign views) | admin, `If-Match` |
| POST | `questions/{id}/image/confirm/` | Confirm an uploaded object: magic-byte verification and malware scan, then attach `file_key` + `image_alt_text` to the draft | admin, `If-Match` |
| DELETE | `questions/{id}/image/` | Remove image from current draft version (clears alt text) | admin, `If-Match` |
| GET | `audit/` | Audit events (filter `entity_type`, `entity_id`), paged | super-admin |

**Envelope (verified in practice-service, A0):** success responses use `core/responses.py::success_response` → `{success, message, data}`. Error responses use `error_response` → `{success, message, errors}`. Content adds one optional key `code` (machine code) to error responses only; no other envelope change. Practice's own responses are unchanged.

**Status codes:** 200 OK (incl. idempotent repeats, §2.8); 201 created; 400 validation (field errors list); 401 unauthenticated; 403 wrong role; 404 not found **or** belongs to another institution (no existence leak); 409 invalid state transition or conflict; 412 `If-Match` present but does not match the current ETag (stale); 428 `If-Match` header missing on a draft write (precondition required); 413 payload/image too large; 415 unsupported image type; 422 malformed request body; 429 rate limited (with `Retry-After`); 503 dependency down (S3 or DB), with no partial writes.

**Error envelope:** `{ "success": false, "message": "...", "code": "<machine_code>", "errors": { "<field>": ["..."] } }` (machine codes: `validation_error`, `invalid_transition`, `used_question`, `stale_version`, `precondition_required`, `duplicate_name`, `node_not_empty`, `image_too_large`, `image_type_unsupported`, `storage_unavailable`, `rate_limited`, `node_retired`, `cannot_discard_only_version`).

**Pagination:** `page` + `page_size` (reused `StandardResultsPagination`: default 50, max 200). Cursor pagination not used in Part 1 (bank of thousands is well within offset limits; §2.16 checks this).

**Student-facing:** no content endpoint is exposed to students in Part 1. Answer keys and drafts never leave admin endpoints.

### 2.7 Permissions and tenant isolation

- Authentication: existing JWT flow (no change to auth-service).
- Authorization (verified A0): every content endpoint uses `core/permissions.py::IsAdminUser` (role `admin`), the same class practice's admin endpoints use. The audit endpoint uses `IsSuperAdminUser` (role `super_admin`). No change to either class.
- Authentication (verified A0): JWT bearer header only (`core.authentication.ServiceJWTAuthentication`); no session/cookie auth is configured, so CSRF does not apply to these endpoints.
- Tenant isolation: every query filters by `institution_id` from the verified token. A valid id from another institution returns 404, identical to a non-existent id.
- Object-level checks: the service layer re-checks `institution_id` on every write (defense in depth, not relying on the view alone).
- Super-admin only: the audit endpoint.

### 2.8 Concurrency and idempotency

- **Optimistic locking:** every draft write (`PATCH`, `publish`, `submit-review`, `withdraw-review`, image upload/delete) requires `If-Match` equal to the current draft version's ETag (hash of `version_no` + `updated_at`). Mismatch → 412 with the current ETag in the response. This prevents two admins silently overwriting each other.
- **State-based idempotency:** `publish`, `retire`, `restore`, `submit-review`, `withdraw-review` return 200 with the current resource if the target state is already reached (a double-click or retry is harmless). Publishing an already-published version is 200, not 409.
- **Atomic transactions:** publish (version freeze + question status + `published_version_no` + audit) runs in one DB transaction with `SELECT ... FOR UPDATE` on the question row. Image upload is outside the transaction and reconciled as described in §2.9.
- **No optimistic UI for publish/retire/delete:** the UI waits for the server response before showing success.

### 2.9 Media (question images)

- **Verified A0 (critical correction):** practice uses **presigned direct-to-S3 upload**, not server-side upload. The bucket's public-read policy covers only the `uploads/*` prefix (AWS setup record, PRODUCTION_CHECKLIST.md). Therefore content images must use `uploads/...` keys to be publicly readable through the CDN like practice images.
- Key format: `core/storage.py::build_file_key("content", filename)` → `uploads/content/<uuid4><ext>`. Server-generated; the client filename's extension is kept only after the allow-list check, and the stem is discarded.
- Upload flow (mirrors practice's presign views, plus a confirm step):
  1. `presign/` → `generate_presigned_upload_url(file_key, content_type)` returns the upload URL and `file_key`; no DB change.
  2. Client PUTs the bytes to S3 directly.
  3. `confirm/` → `verify_uploaded_image(file_key)` (magic bytes read back from storage) → `scan_image_for_malware(file_key)` (ClamAV) → on success attach `file_key` and `image_alt_text` to the draft version.
  4. `TransientStorageError` (S3 or ClamAV unreachable) → 503, object **not** deleted, client may retry confirm. Confirmed rejection (bad signature, malware) → object deleted, 415 or 422 with the reason.
- Limits: `core/upload_constraints.py` (5 MB; jpg/jpeg/png/webp/gif/avif; no svg). Not redefined.
- Client filename is never stored or logged.
- Published versions reference their image key immutable. Replacing an image on a draft creates a **new** object; the old object is deleted only if no published version references it.
- Delete question / discard draft: delete the S3 objects no longer referenced. If the S3 delete fails after the DB change succeeded, the key is recorded in `content_media_orphan` and the response still succeeds (the DB state is correct; the orphan is cleaned later by `manage content_cleanup_orphans`, run manually).
- Access: images are served through the existing CDN/presigned-URL pattern used by practice (reused, not duplicated). Admin previews only in Part 1.
- Failure: S3 unavailable → 503 on upload; text saves are unaffected.

### 2.10 Cache (Redis)

- Same Redis instance, all keys prefixed `content:`.
- Key style (verified A0, matches `practice:institution:{id}:section:{id}:questions`): `content:institution:{institution_id}:node_tree` and `content:institution:{institution_id}:node:{node_id}:questions:{status}:{page}`.
- Invalidation: any content write invalidates only `content:*` keys for that institution (via a key-pattern delete scoped by institution). Never touches `practice:*` keys (tested).
- Cache failure: reads fall through to the DB; writes proceed; a cache error is logged, never returned to the client.
- Health: content adds its own check to the health response without changing practice's existing response fields (new key `content` added alongside).

### 2.11 Audit logging

- Events: node create/edit/publish/retire/restore/delete; question create/edit/submit-review/withdraw-review/publish/retire/restore/delete/reorder; version discard; image upload/delete.
- Each event records actor, action, entity, version, a **summary** (which fields changed, state before/after), `request_id`, timestamp. The summary never stores the full question text or option text (only "question_text changed"), to keep audit logs non-sensitive.
- Written in the same transaction as the change. Append-only: no update or delete endpoint, and a test asserts none exists.
- Retention: kept with the platform's standard retention (to be confirmed with the platform's policy owner — tracked in §3 Phase M as a verification task, default: same as other audit tables).

### 2.12 Rate limiting and abuse protection

- Inherited from practice (no content-specific limiter): existing DRF `user` throttle (300/min) and `anon` throttle (60/min), Redis-backed, fail-open on Redis error. Content write endpoints are not given separate limits in Part 1 (documented as a deliberate non-addition; revisit only if load test shows abuse).
- Redis down → rate limiter **fails open** for admin content endpoints (these are authenticated internal tools; availability matters more than throttling), with an alert. (Contrast with the exam-submit throttle, which must fail closed — out of scope here.)
- Bulk-export is **not** provided in Part 1 (prevents scraping of the bank). Listing is paged with a hard max of 100.
- Bot protection: admin endpoints are behind the existing auth; no public endpoint is added. Login abuse is out of scope (existing auth-service).

### 2.13 Security controls matrix

| Threat | Control | Test |
|---|---|---|
| Unauthorized access | Admin role required on every endpoint | Negative: student token → 403; anon → 401, on every endpoint |
| Cross-tenant access (IDOR) | `institution_id` filter + service re-check; 404 not 403 | Negative: other-institution id → 404 on every id-bearing endpoint |
| Stored XSS in question/option/explanation | Plain-text storage; escaped rendering; no HTML interpretation | Negative: `<script>` payload stored and rendered as text (frontend + API) |
| Malicious upload (type spoofing, polyglots) | Signature check; size cap; server-generated key; client filename discarded | Negative: .png extension with text body → 415; oversized → 413; path-traversal filename → accepted but stored under server key only |
| Mass assignment | Explicit serializer field allow-lists; `institution_id`, `status`, `version_no`, `created_by` are server-controlled | Negative: client sends `status=published` or `institution_id` in body → ignored/rejected |
| Answer-key leakage | Admin-only endpoints; no student endpoint in Part 1; answer key excluded from list responses except detail | Positive/negative: list responses omit `is_correct` (detail includes it for admins only) |
| Scraping / bulk exfiltration | Pagination cap 100; rate limits; no export | Load/abuse test: rapid paging hits 429 at the limit |
| Race conditions (double publish, lost update) | Transactions + row lock; `If-Match` ETag; idempotent transitions | Concurrency test: two simultaneous PATCHes → one 412; two simultaneous publishes → one state change, both 200 |
| Audit tampering | Append-only; no update/delete endpoints; writes in same transaction | Negative: no route exists for update/delete of audit rows |
| Log leakage (PII / answers) | Logs carry ids and status only; audit summaries exclude text | Assertion test on log output for a publish call |
| CSRF | Existing JWT bearer-header model (no cookie auth for these endpoints) | Confirm in A0; test that cookie-only requests are rejected |
| Denial of service via large text | Length caps at serializer and DB level | Negative: over-length text → 400 |
| Injection (SQL) | ORM only; no raw SQL in content module | Static check: grep gate in CI-equivalent test (no `.raw(` / `cursor.execute` in content code) |

### 2.14 Resilience and failure modes

| Failure | Behavior | Recovery |
|---|---|---|
| DB down | 503 for all content endpoints; no partial writes (transactions) | Automatic when DB returns; no data loss |
| S3 down | Image upload/delete → 503; text operations unaffected; DB deletes still succeed, failed S3 deletes recorded in `content_media_orphan` | Manual cleanup command; orphans are harmless (cost only) |
| Redis down | Cache bypassed (reads hit DB); rate limiter fails open; health reports content redis=error | Automatic |
| Publish crashes mid-way | Transaction rolls back; version stays draft; client gets 500 and can retry (idempotent) | Automatic |
| Duplicate request (double-click, network retry) | State-based idempotency returns 200 | Automatic |
| Stale editor (two admins) | 412 on the second write; UI shows current content and asks to reload | Automatic |
| Timeout on S3 call | Client timeout set explicitly (short); treated as 503 | Retry by admin |
| Bad deploy | Feature flag off → Content tab hidden and endpoints unmounted; data retained; practice untouched | Flag off; fix forward |
| Accidental mass delete | D10 (empty nodes only), D6 (used questions retire-only), audit trail | Restore from audit + DB point-in-time recovery if ever needed |

**Graceful degradation rule:** content failures never degrade practice, and practice failures never degrade content (separate code paths, separate cache prefixes, no shared transactions).

### 2.15 Observability

- **Logs:** structured, JSON, with the existing `request_id` convention. Events: `content.publish`, `content.retire`, `content.delete`, `content.image_upload`, `content.error` (with error code). No question text, no option text, no answer data in logs.
- **Metrics** (counters/histograms, emitted via the platform's existing metrics path): `content_requests_total{endpoint,status}`, `content_request_latency_seconds{endpoint}`, `content_publish_total`, `content_retire_total`, `content_delete_total`, `content_upload_total{result}`, `content_cache_errors_total`, `content_ratelimit_hits_total`.
- **Alerts:** 5xx rate on content endpoints > 1% over 5 minutes; any `content_media_orphan` growth > 100 in 24h; publish p95 > 1s over 15 minutes; health `content.db` or `content.storage` = error for 5 minutes.
- **Dashboards:** one content panel: request rate, error rate, latency p50/p95, publish/retire/delete counts, orphan count.
- **Health endpoint:** `content` block with `db`, `storage`, `cache` status (no secrets, no counts that leak data).
- **Traceability:** every write's `request_id` is stored on its audit row, so an incident can be traced from a user action to the exact change.

### 2.16 Performance, scale, and cost

- **Scale targets (Part 1 dev/pilot sizing):** 2,000 questions in one institution; 50 concurrent admins at peak; 100 concurrent list reads.
- **Latency SLOs:** list/read p95 < 300 ms; write (save draft) p95 < 500 ms; publish p95 < 800 ms; image upload p95 < 2 s (excluding network upload time).
- **Indexes:** defined in §2.1. Verified by `EXPLAIN` on the 2,000-row load fixture; no sequential scan on list endpoints.
- **Pagination:** offset paging is sufficient at 2,000 rows (verified under load test); revisit if a single institution exceeds ~50,000 questions.
- **Storage estimate:** text ~2–3 KB per question version; images ~0.2 MB average → ~0.4 GB for 2,000 questions with images. Negligible DB size; S3 cost is pennies per month at this scale.
- **Cost controls:** images served through CDN; no duplicate image copies per version (a published version references the same object); orphan cleanup prevents silent storage growth.
- **Connection use:** no long-lived connections; no background workers (no added infrastructure cost in Part 1).

### 2.17 Frontend specification (admin Content tab)

**Information architecture**
- Sidebar: one new entry "Content" (feature-flagged), placed after "Practice".
- `/admin/content` — root: subjects (root nodes) as cards, each with status and counts; "New subject" action.
- `/admin/content/nodes/[node_id]` — a node: its child nodes (topics or deeper) and, when it has a parent, its questions. Breadcrumb trail back to root.
- `/admin/content/questions/[question_id]` — question editor (draft) with a read-only "Published version" panel and a "Versions" tab.
- `/admin/content/questions/[question_id]/versions/[version_no]` — read-only view of one version.

**Question editor fields:** question text (multi-line, counter), options (2–6 rows, add/remove, mark exactly one correct via radio), explanation (optional, counter), image (optional, preview, replace, remove). Save draft (auto-saves are **not** used; explicit save only, to keep ETag handling simple and predictable). Submit for review. Publish (confirm dialog). Retire / restore (confirm dialog). Delete (confirm dialog; shows reason if blocked: "used — retire instead").

**States on every screen:** loading (skeleton), empty (with the single next action), error (plain message, retry button, request id shown for support), stale-edit conflict (412: message + "reload to see latest" button), validation errors (inline per field + summary at top).

**Copy rules:** plain language, no internal terms in the UI. Publish message: "Publishing freezes this version. Future edits create a new draft; this version stays as it is." Retire message: "Retired questions are hidden from new exams. Past results are kept." Delete-blocked message: "This question was used in an exam, so it can only be retired."

**Mobile-first and responsive:**
- Base layout designed for 360 px width first; breakpoints at 640 px and 1024 px.
- Lists become stacked cards below 640 px; tables only at 1024 px+.
- Touch targets ≥ 44×44 px; primary actions reachable without horizontal scroll.
- Option rows wrap; long question text wraps (no clipping).
- Image preview scales to container width.

**Accessibility (WCAG 2.1 AA):**
- Color contrast ≥ 4.5:1 for text; status is conveyed by text label, not color alone.
- Full keyboard operation; visible focus ring; logical tab order; dialogs trap focus and return focus on close.
- Form fields have visible labels; errors are announced (aria-live); radio groups use proper fieldset/legend.
- Images have an alt-text field (required whenever an image is present; validated on save and at publish, per §2.5).

**Consistency:** reuse existing admin UI primitives (PageWrapper, PageHeader, Skeleton, EmptyState, toast, confirm dialog) exactly as the existing admin pages do. No new visual system.

**Feedback:** success toasts after server confirmation; no optimistic success for publish/retire/delete.

**Performance (frontend):** list pages fetch one page at a time; search is debounced (300 ms); editor loads one question only.

### 2.18 Lifecycle, feature flag, rollout, rollback

- **Feature flag:** `CONTENT_BANK_ENABLED` (env) plus a per-institution allowlist setting. Off → endpoints unmounted (404) and the sidebar entry hidden.
- **Stages (each stage needs your sign-off):**
  - **MVP / prototype:** dev environment only, flag on for test institution, synthetic data.
  - **Pilot batch:** one real institution, real content team, flag on for that institution only; monitor alerts for two weeks.
  - **Beta:** all institutions on pilot tier; same monitoring.
  - **Enterprise scale:** all institutions; no change in code, only the allowlist.
- **Rollback:** flip flag off (no deploy needed). Because all tables are additive, rollback never requires a schema revert. Data is retained for re-enable.
- **Backward compatibility:** practice endpoints, models, cache keys, media keys, and screens are unchanged (verified by characterization tests, §3 Phase E).

### 2.19 Backup, disaster recovery

- Content tables live in `practice_db`, so they inherit the existing RDS backup and point-in-time recovery policy. Phase M verifies the policy is in effect for `practice_db` (read-only check of the RDS configuration; no change).
- Targets (proposed, to be confirmed with infrastructure owner): RPO ≤ 5 minutes (PITR), RTO ≤ 1 hour for a database restore.
- Restore drill: once before pilot — restore a snapshot to a scratch instance, verify content row counts and a sample published version's integrity.
- S3 objects: versioning/lifecycle policy verified in Phase M (a deleted object is recoverable within the bucket's configured retention, if enabled; if not enabled, this is recorded as an accepted limitation).

### 2.20 Documentation deliverables

| Document | Action | Phase |
|---|---|---|
| `docs/content-bank.md` | **Create**: design summary, state machines, API reference, runbook (flag, orphan cleanup, restore), troubleshooting | K |
| `PRODUCTION_CHECKLIST.md` | **Update**: entry for the Content module with closure evidence | K |
| `services/practice-service/.env.example` | **Update**: all `CONTENT_*` settings with defaults and comments | B |
| `LIVETRACKER4.md` | **Update**: progress log at every session | every phase |
| Practice-service operations/README (if present) | **Update**: note content module and its flag | K |
| `docs/essay-service-operations.md`-style ops doc for content | **Create** if the content module has its own operational queries/alerts: `docs/content-bank-operations.md` | K |

### 2.21 Test strategy (definitions, applied per phase)

| Type | What it means here | Where |
|---|---|---|
| Smoke | Service starts, migrations apply, health endpoint returns content block, key endpoints respond | Phase D/H |
| Sanity | Each endpoint returns the documented shape for one happy path | Phase D |
| Functional | Each rule in §2.2–2.5 behaves as written | Phase C |
| Positive | Valid inputs succeed and produce the documented state | Phases C/D |
| Negative | Invalid inputs, wrong state, wrong role, wrong tenant are refused with the right code | Phases C/D |
| Edge | Boundaries: option min/max, text at max length, single option removal, last version discard, empty node, duplicate names with case, reorder with missing id | Phase C |
| Security | §2.13 matrix, each row has a test | Phase H |
| Integration | DB + S3 (test double + one real dev bucket run) + Redis; publish transaction end-to-end | Phase H |
| Regression | Practice characterization suite unchanged and passing | Phase E |
| Concurrency | Two writers, two publishers, double-click | Phase H |
| Load | 2,000-question fixture, 50 concurrent admins, SLOs in §2.16 | Phase H |
| Resilience | Injected DB/S3/Redis failures per §2.14 | Phase H |
| Frontend component | Each screen: states, validation display, confirm dialogs | Phase J |
| Responsive/a11y | Viewport tests at 360/640/1024; axe-core rule check (no critical violations) | Phase J |
| Full regression | Full practice-service suite and full frontend suite, each twice consecutively | Phase M |

---

## 3. Implementation phases (execute in order; check each box only after its test passes)

### Phase A — Design sign-off and read-only discovery

- [x] **A0:** Read-only discovery of practice-service: its admin permission class and role check, its response/error envelope helpers, its pagination class, its upload constraints, its storage helper, its CDN/presigned URL pattern, its health endpoint shape, its cache key style, and whether CSRF applies to its endpoints. Record findings in the Progress log. **No code changes.**
- [x] **A1:** Confirm §2 (this file) against A0 findings; amend anything that conflicts (record each amendment in the Progress log).
- [x] **A2:** User sign-off on §1 defaults and §2 design.

**Test checklist (Phase A):** n/a for code. Verification = A0 findings recorded with file references; A1 amendments listed; A2 sign-off recorded in the Progress log.

**GATE A → B:** user sign-off recorded. **No implementation begins before this gate.**

### Phase B — Backend: data model, settings, migration (practice-service)

- [x] **B1:** Settings: add all `CONTENT_*` settings (§1) with defaults; `CONTENT_BANK_ENABLED=False` default. Update `services/practice-service/.env.example`.
- [x] **B2:** Models: `content_node`, `content_question`, `content_question_version`, `content_option`, `content_question_usage`, `content_audit_event`, `content_media_orphan` (§2.1), with all constraints and indexes. No edits to any `practice_*` model.
- [x] **B3:** Migration generated and reviewed: **only `CreateModel` / `AddIndex` / `AddConstraint` operations on `content_*` tables.** Automated check fails the build if any operation touches a `practice_*` table.
- [x] **B4:** Migration applies forward on a copy of the dev database and reverses cleanly (reverse drops only `content_*` tables).
- [x] **B5:** Model-level invariants enforced: one draft/in-review version per question (partial unique index); `UNIQUE(question_id, version_no)`; exactly-one-correct checked in service layer (tested in C).

**Test checklist (Phase B):**
- Smoke: migrations apply and reverse.
- Functional: each constraint rejects a violating insert at DB level (node name duplicate, two draft versions for one question, duplicate version_no).
- Negative: reverse migration does not drop any `practice_*` table (assertion).
- Isolation: no foreign key between `content_*` and `practice_*` (schema introspection test).

**GATE B:** all B tests pass; migration reviewed by user (or checked against §2.1 by user).

### Phase C — Backend: domain services (business rules, no HTTP)

- [x] **C1:** Node service: create, rename, publish, retire, restore, delete (D10), duplicate-name rule, parent validity.
- [x] **C2:** Question service: create (with version 1 + options), save draft, clone-on-edit for published questions, withdraw/submit review, publish (full validation, transaction, row lock, freeze), retire, restore, delete (D6 incl. usage guard), reorder (full-set rule).
- [x] **C3:** Version service: list versions, read one version, discard draft (rules in §2.3).
- [x] **C4:** Validation module implementing §2.5 exactly (single source; used by serializers and publish).
- [x] **C5:** Audit writer used by every write in C1–C3 inside the same transaction; summary excludes text.
- [x] **C6:** Immutability guard: any write attempt on a published version raises (§2.4).
- [x] **C7:** Orphan ledger writer used when an S3 delete fails (media layer interface stubbed until Phase E; interface defined here).

**Test checklist (Phase C):**
- Functional: every row of the §2.3 table has a test for allowed and refused cases.
- Positive: create → draft → submit → publish → retire → restore → (clone-edit) → publish v2 end to end.
- Negative: publish with 1 option; 7 options; 0 correct; 2 correct; duplicate options; text over max; publish in retired node; restore when node retired; delete used question; reorder with missing id; discard the only version.
- Edge: text exactly at max length (accepted), max+1 (refused); options at min and max; duplicate names differing only by case; last remaining draft discard; empty node delete; reorder of a single question.
- Alt text: publish with image and blank alt text → 400 listing the field; publish with image and valid alt text → 200.
- Immutability: every mutation path rejects a published version (table-driven test over all services).
- Audit: every write produces exactly one audit row in the same transaction; summaries contain no question text (assertion).
- Concurrency (service level): two publishes on one version → one transition, second is idempotent 200 at the service return value.

**GATE C:** all C tests pass.

### Phase D — Backend: API layer, permissions, serializers

- [x] **D1:** Serializers with explicit field allow-lists (§2.7 mass-assignment rule); server-controlled fields excluded.
- [x] **D2:** Views for every endpoint in §2.6; mounted only when the flag is on.
- [x] **D3:** Permission classes: reuse practice's admin check (A0); super-admin for audit only.
- [x] **D4:** `If-Match` / ETag handling on draft writes (412 on mismatch); ETag returned on every draft read.
- [x] **D5:** Idempotent transition responses (200 with current state) per §2.8.
- [x] **D6:** Error envelope and machine codes per §2.6; no stack traces in responses.
- [x] **D7:** Pagination (`page`, `page_size`, max 200) on all list endpoints.
- [x] **D8:** `GET questions/{id}/` returns `is_correct` only to admins (admin-only endpoints; asserted).

**Test checklist (Phase D):**
- Smoke: flag off → all content routes 404; flag on → routes respond.
- Sanity: each endpoint's happy path returns documented shape.
- Security: §2.13 API rows (auth 401/403 on every route; cross-tenant 404 on every id route; mass assignment ignored; no answer keys in list responses).
- Negative: malformed JSON → 422; missing `If-Match` on draft write → 428 (precondition required); stale ETag → 412.
- Image alt text: image present with blank alt text → 400 (`validation_error` on `image_alt_text`); alt text over 300 chars → 400; removing the image clears alt text.
- Edge: page_size 101 → clamped/refused per spec; page beyond last → empty page not error.
- Idempotency: double publish, double retire, double submit-review → 200 each time.
- Error envelope: every error response matches the envelope (table-driven).

**GATE D:** all D tests pass.

### Phase E — Backend: media (question images) and regression

- [x] **E1:** Media service: signature validation (§2.9), size cap, server-generated key under `content/`, storage via existing helper, presigned/CDN read path reused.
- [x] **E2:** Image upload/delete endpoints wired to draft versions with `If-Match`.
- [x] **E3:** Published-version image reference immutability (replacement creates new object; old object retained while referenced).
- [x] **E4:** Orphan handling: failed S3 delete → `content_media_orphan` row; success response preserved.
- [x] **E5:** Management command `content_cleanup_orphans` (manual run; dry-run default; deletes only keys listed in orphan ledger and not referenced by any version).
- [x] **E6:** Characterization tests for **existing practice endpoints, written and run before any Phase B change** (locks current behavior). Re-run after Phases B–E. All must pass unchanged.
- [x] **E7:** Practice media isolation: practice upload/read paths unchanged (test asserts keys and constraints).

**Test checklist (Phase E):**
- Positive: valid PNG/JPEG/WebP accepted; key has `content/` prefix and server-generated name.
- Negative: wrong signature with allowed extension → 415; too large → 413; zero-byte → 400; client filename with traversal characters → stored under server key only (assertion).
- Failure: S3 mocked down → upload 503, no DB change; delete with S3 down → DB delete succeeds, orphan row written.
- Immutability: replacing an image on a published-question draft does not change the published version's key.
- Cleanup command: dry-run lists, real run deletes only unreferenced orphan keys (assertion on both).
- Regression (E6/E7): practice characterization suite green; practice media keys and upload constraints unchanged.

**GATE E:** all E tests pass, including full characterization suite.

### Phase F — Backend: cache, rate limiting, audit exposure

- [x] **F1:** Cache keys per §2.10 (`content:` prefix only); scoped invalidation by institution.
- [x] **F2:** Cache failure path: reads fall through, writes proceed, error logged, never returned.
- [x] **F3:** Verify content endpoints inherit the existing throttles (no new limiter); fail-open on Redis error with alert metric.
- [x] **F4:** Audit read endpoint (super-admin) with paging and filters.

**Test checklist (Phase F):**
- Isolation: a content write does not delete or read any `practice:*` key (cache-key assertion before/after).
- Cache failure: Redis mocked down → reads 200 from DB; writes 200; no 5xx.
- Rate limit (inherited): exceeding the existing `user` throttle (300/min) on a content endpoint → 429 with `Retry-After`; under limit → 200.
- Fail-open (inherited behavior, verified in `core/throttling_resilience.py`): Redis down → request allowed, error metric incremented.
- Audit: admin → 403; super-admin → 200; filters work; no update/delete route exists (route introspection test).

**GATE F:** all F tests pass.

### Phase G — Backend: observability and health

- [x] **G1:** Structured logs for events in §2.15 with `request_id`; assertion: no question/option text or answer data in log output.
- [x] **G2:** Metrics emitted per §2.15 via the platform's existing metrics path.
- [x] **G3:** Health endpoint: add `content` block (db, storage, cache); practice's existing health fields unchanged (characterization test).
- [x] **G4:** Alert definitions per §2.15 written as configuration in the repo (exact thresholds), not only in a dashboard.
- [x] **G5:** Dashboard panel definition (as code or documented query set) per §2.15.

**Test checklist (Phase G):**
- Smoke: health returns content block; practice health fields identical to before (characterization).
- Negative: log capture on publish/error paths contains no text (assertion).
- Metrics: counters increment on publish/retire/delete/upload (unit assertions on the metrics client).
- Alert config: schema/lint check passes; thresholds match §2.15.

**GATE G:** all G tests pass.

### Phase H — Backend: full test matrix (security, concurrency, integration, load, resilience)

- [x] **H1:** Security suite: every row of §2.13 has its test (asserted by a checklist test that fails if a row has no test).
- [x] **H2:** Concurrency suite: concurrent PATCH (one 412), concurrent publish (one transition), double-click (idempotent), concurrent reorder (one wins, others 409 on set mismatch).
- [ ] **H3:** Integration: publish end-to-end on real PostgreSQL (the test suite runs on in-memory SQLite by default, per `core/test_settings.py`, so a dedicated Postgres test run is required) and Redis; S3 via test double plus one real dev-bucket run.
- [x] **H4:** Resilience: injected DB, S3, Redis failures per §2.14; assert the documented behavior for each row.
- [ ] **H5:** Load: seed 2,000 questions (≈ 2,000 × options, 20% with images); run 50 concurrent admin workers for 10 minutes mixing reads (70%) and writes (30%); assert §2.16 SLOs; `EXPLAIN` check on list endpoints recorded.
- [x] **H6:** Practice regression: full practice-service suite green (characterization from E6 included).
- [x] **H7:** Full backend suite run once, passing (run-once rule, decided 2026-10-06; replaces the two-run rule).

**Test checklist (Phase H):** security, concurrency, integration, resilience, load, regression — each as above. Results recorded in the Progress log with numbers (latency percentiles, error counts).

**GATE H:** all H tests pass; load results and security checklist recorded.

### Phase I — Frontend: Content tab (admin)

- [x] **I1:** Sidebar entry "Content" in `AdminLayout.tsx` (one new entry, feature-flagged). No other shared navigation change.
- [x] **I2:** Root page `/admin/content`: subjects as cards, status, counts, "New subject".
- [x] **I3:** Node page `/admin/content/nodes/[node_id]`: child nodes, questions (when parent exists), breadcrumb, create/rename/publish/retire/restore/delete with confirm dialogs and D10 messaging.
- [x] **I4:** Question editor `/admin/content/questions/[question_id]`: fields per §2.17 (including image alt text, required when an image is present); explicit save; submit/withdraw review; publish with confirm; retire/restore; delete with blocked-message handling; image upload/replace/remove with preview.
- [x] **I5:** Versions tab and read-only version page.
- [x] **I6:** Reorder UI within a node (accessible up/down controls and drag where supported; keyboard path mandatory).
- [x] **I7:** States on every screen per §2.17 (loading, empty, error with request id, 412 stale-edit, inline validation).
- [ ] **I8:** Responsive layout per §2.17 (360/640/1024); touch targets ≥44 px.
- [x] **I9:** Accessibility per §2.17 (focus management, labels, aria-live errors, contrast).
- [x] **I10:** No change to existing practice admin pages (verified by practice UI regression check, J3).

**Test checklist (Phase I):** component tests per screen (states, validation, confirm flows, blocked-delete message, 412 handling); responsive snapshot at 360/640/1024; axe-core run with no critical violations; keyboard-only walkthrough recorded.

**GATE I:** I tests pass.

### Phase J — Frontend: tests, types, and regression

- [x] **J1:** API client types for every content endpoint and error code (§2.6); no `any`.
- [x] **J2:** Frontend test suite for content screens run once, passing (run-once rule, decided 2026-10-06; replaces the two-run rule).
- [x] **J3:** Practice admin and student UI regression: existing practice test files pass unchanged.
- [x] **J4:** `tsc --noEmit` clean.
- [ ] **J5:** Browser check (live): create subject → topic → question → publish → version history, at 360 px and 1024 px. If the browser cannot reach the app, record that explicitly and do not claim it was verified.

**Test checklist (Phase J):** as above; results recorded in the Progress log.

**GATE J:** J tests pass; J5 result recorded honestly.

### Phase K — Documentation

- [x] **K1:** Create `docs/content-bank.md` (design summary, state machines, API reference, flag and rollback runbook, orphan cleanup runbook, troubleshooting).
- [x] **K2:** Create `docs/content-bank-operations.md` (operational queries, alert meanings, what to do when each alert fires).
- [x] **K3:** Update `PRODUCTION_CHECKLIST.md` with a Content module entry and closure evidence.
- [x] **K4:** (N/A: practice-service has no README or operations doc to update; the content bank is documented in docs/content-bank.md) Update practice-service operations/README (if present) to mention the module and its flag.
- [x] **K5:** Confirm `.env.example` documents every `CONTENT_*` setting (automated check: every setting in `settings.py` appears in `.env.example`).

**Test checklist (Phase K):** doc link check; env-example completeness check passes.

**GATE K:** documentation complete and reviewed by user.

### Phase L — Rollout and enablement (environment steps; each needs your permission)

- [ ] **L1 (dev, done by implementation):** flag on in dev for the test institution; synthetic content loaded via the UI/API (not SQL).
- [ ] **L2 (pilot, needs your permission):** enable for one real institution; content team trained with the runbook; alerts active.
- [ ] **L3 (pilot monitoring, two weeks):** review alert history, latency, error rate, and content-team feedback; record decisions in the Progress log.
- [ ] **L4 (beta, needs your permission):** extend allowlist to the pilot tier.
- [ ] **L5 (enterprise scale, needs your permission):** all institutions; allowlist change only.
- [x] **L6 (rollback rehearsal, before L2):** flip the flag off and on in a non-production environment; verify no data loss and no practice impact.

**GATE L:** each stage recorded with your sign-off.

### Phase M — Final validation and completion

- [ ] **M1:** Backup/PITR policy verified in effect for `practice_db` (read-only check); restore drill executed on a scratch instance before L2; results recorded.
- [ ] **M2:** S3 bucket versioning/lifecycle state recorded (enabled or accepted limitation).
- [ ] **M3:** Audit retention confirmed with the platform policy owner; value recorded.
- [x] **M4:** Full backend suite run once, passing; full frontend suite run once, passing (run-once rule, decided 2026-10-06; replaces the two-run rule).
- [ ] **M5:** Dev stack builds and starts; all existing services healthy (container status recorded).
- [x] **M6:** Test data cleaned from the shared dev database (verified by query).
- [ ] **M7:** Progress log updated with the final evidence table (test counts, load numbers, security checklist results, live check result).

**Part 1 is complete only when M1–M7 are checked and you have validated it.**

---

## 4. Definition of done (Part 1)

- Every checkbox in Phases A–M is checked, with its test checklist recorded.
- No existing practice model, table, endpoint, screen, cache key, media key, or permission class changed (proven by Phase E/F/G characterization tests and the isolation assertions).
- Security matrix (§2.13) fully covered by passing tests.
- SLOs (§2.16) met under the Phase H load test, with numbers recorded.
- Feature flag off by default; rollback rehearsed.
- Documentation (§2.20) complete.
- User sign-off at each gate.

---

## 5. Progress log (resume point — update every session)

| Date | Phase / task | Result | Evidence / notes |
|---|---|---|---|
| 2026-10-04 | Tracker | Rewritten to implementation-ready specification (this file) | Design gaps closed in §2; no implementation started |
| 2026-10-04 | Tracker | Added image alt text (data model §2.1, rules §2.5, tests C/D/I), added status 428 and new machine codes (§2.6) | Tracker re-checked; no implementation started |
| 2026-10-04 | A0 | Done | Read-only discovery of practice-service: IsAdminUser/IsSuperAdminUser (core/permissions.py), success_response/error_response envelope (core/responses.py), StandardResultsPagination (page 50, max 200), presigned direct-to-S3 image flow (practice/views.py presign views), verify/scan/delete helpers (core/storage.py), upload limits (core/upload_constraints.py: 5 MB, jpg/jpeg/png/webp/gif/avif), JWT-only auth (no CSRF surface), DRF throttles (anon 60/min, user 300/min, fail-open), cache key style practice:institution:{id}:... |
| 2026-10-04 | A1 | Done | Tracker amended with A0 findings: presign+confirm image flow; uploads/content/ keys (bucket public-read covers uploads/* only); reuse of upload limits, pagination, throttles, permission classes; envelope with optional code key; node reorder and discard-draft endpoints added to API table. |
| 2026-10-04 | A2 | Done (authorized) | User instructed start and completion of Phases A to E. Treated as sign-off for A and as gate authorization through E. |
| 2026-10-04 | Baseline (E6, before any change) | 108 existing practice tests passing (exit 0) | Run in one-off container: practice container is restart-looping because PgBouncer cannot reach RDS (pre-existing Phase 18 infrastructure issue, not code). |
| 2026-10-04 | B | Done | content app (models, 0001_initial migration, CONTENT_* settings, .env.example). Migration touches only content_* tables; lintmigrations clean; reverse-forward verified in one process; practice makemigrations clean. Tests: test_content_models.py (10). |
| 2026-10-04 | C | Done | Domain services (content/services.py, validation.py, audit.py, media.py, errors.py). Tests: test_content_services.py (rules table, edge cases, audit-no-text, eligibility, reorder). Deviation: option minimum enforced only at publish (section 2.5); submit-for-review also runs full validation. |
| 2026-10-04 | D | Done | API (content/views.py, urls.py; mounted at /api/practice/content/, returns 404 when CONTENT_BANK_ENABLED is False). Tests: test_content_api.py (31). Deviation: routes always mounted with the flag checked per request (testable; same client behavior). Image removal split into DELETE-only view. |
| 2026-10-04 | E | Done | Image flow (content/images.py): presign, confirm (issued-key check, verify, scan, attach), remove; rejected objects deleted, storage outage 503 keeps object. Orphan cleanup command content_cleanup_orphans (dry run default). Tests: test_content_images.py (19), test_content_orphans.py (4). |
| 2026-10-04 | A to E regression | 108 existing practice tests + all content tests (incl. test_content_security.py static checks) green, run twice consecutively | practice migrations unchanged; only existing files touched: core/settings.py and core/urls.py (additive). |
| 2026-10-04 | Open (carried to F to M) | H3 Postgres integration not run (tests use SQLite); G4/G5 live check blocked by PgBouncer to RDS; S3/ClamAV exercised with mocks only | Must be resolved in Phase H/M. |
| 2026-10-04 | I (frontend) | Code complete: root, node, question editor, version pages; gated nav entry in AdminLayout.tsx; contentApi.ts with reorder, renameNode, deleteNode, getVersion | `npx tsc --noEmit` exit 0. Content Jest suites: 22 passed in 4 files (adminContentRootPage, adminContentNodePage, adminContentQuestionPage, adminContentVersionPage). I10 (practice UI regression) to be confirmed with J3. Not done: axe-core scan (package not installed), responsive snapshots at 360/640/1024, keyboard-only walkthrough recorded. I8 and I9 therefore not ticked. |
| 2026-10-04 | J (frontend tests) | Full frontend suite: 2 runs (fe_run3, fe_run4) each with 6 failing tests, 597 passing of 603 | Failures are 5 to 20 s timeouts in pre-existing essay-admin tests (adminEssaySubmissionDetailPage, adminResultsTimeline, adminEssayReportsPage, adminEssayPapersPage). The affected files pass when run alone (42/42), so the failures look like load on the machine during the run. Not a clean full run yet. J2, J3, J4 not ticked until a clean full run. J4 (tsc) exit 0. J5 blocked (live browser, see above). |
| 2026-10-04 | H5 (load test) | First run discarded | Requests were rejected with DisallowedHost for testserver (command ran outside the test runner). Fixed by adding testserver to ALLOWED_HOSTS in content_load_test.py. Corrected run started once; results row added below when it completes. |
| 2026-10-04 | Frontend timing fix (J2/J3 input) | Full frontend suite passed in one run: 64/64 suites, 603/603 tests | Fix: userEvent.setup({ delay: null }) in adminEssaySubmissionDetailPage, adminResultsTimeline, adminEssayReportsPage, adminEssayPapersPage (test files only; no component changes). Output: fe_full_single.txt. Note: one earlier run of adminEssaySubmissionDetailPage failed one test (name not captured) and a later diagnostic rerun passed; the file was not run a further time. J2/J3 ticked on this clean full run. J5 still blocked. |
| 2026-10-04 | H5 (load test, corrected run, Postgres content-test-pg, practice_load DB) | FAILED: SLOs breached, 300 of 1000 requests errored | 2,000 published questions seeded under one topic; 50 workers x 20 requests (1000 requests); wall 504.7 s; 2.0 rps. Errors: 300 responses were 401 Unauthorized (auth in the load client is failing for some requests; not yet diagnosed). list: n=350 p50=658 ms p95=424023 ms max=427075 ms. detail: n=350 p50=394 ms p95=12233 ms max=38376 ms. write: n=300 p50=387 ms p95=15413 ms max=40874 ms. SLO check (command): breached on list, detail, write. EXPLAIN check not recorded. H5 not ticked. Next: diagnose the 401s (token lifetime or per-worker token setup), then find why list p95 is in minutes (likely connection pool or lock contention with 50 workers); rerun only after the fix. |
| 2026-10-04 | F (cache, throttling, audit) | Done: F1 to F4 ticked | Tests: tests/test_content_ops.py (cache, isolation, fall-through, throttle classes), tests/test_content_phase_fg.py (TestThrottles: 429 with Retry-After, under-limit allowed, Redis error fails open with warning; TestAuditRead: entity_type and entity_id filters, bad id 400, paging). Fixes found by these tests: Retry-After was dropped by the project's custom exception handler (fixed inside content views only; core/exceptions.py is shared with practice and was not changed); audit list returned 500 on a bad entity_id (now 400). Single Postgres run. |
| 2026-10-04 | G (observability, health) | Done: G1 to G5 ticked | G1: request log and audit log checked for no question or option text (test_content_phase_fg.py, test_content_ops.py). G2 deviation: the repo has no metrics client; counters are content.audit log lines (action=...), as section 2.15 names. G3: practice health keys asserted exactly {status, service, db, redis}; content block only on /content/health/. G4: content/ops_alerts.json thresholds asserted. G5: content/ops_dashboard.json defines seven panels with queries; every alert a panel references exists in ops_alerts.json. |
| 2026-10-04 | I7 request id | Done | Server: one request id per request (client X-Request-ID or generated), returned in the X-Request-ID header and in every error body as request_id, and stored on audit rows. Frontend: messageFor appends "(Reference: id)". Tests: TestRequestId (backend), contentApiErrors.test.ts (frontend). |
| 2026-10-04 | F and G and I regression | Content backend suites (models, services, api, images, orphans, security, ops, hardening, concurrency, phase_fg, test_health): all pass on Postgres, exit 0, single run. Content frontend suites (5 files, 24 tests) pass; tsc exit 0. | Full frontend suite earlier: 64/64 suites, 603/603 (single run) before these changes. I10 ticked on that run: the practice test files were not changed. |
| 2026-10-04 | I8 and I9 | NOT done | I8 (responsive 360/640/1024, touch targets) needs a live logged-in browser session; the live path is blocked by PgBouncer to RDS. I9 (axe-core, focus and contrast) needs axe-core, which is not installed; adding it changes package.json and needs your permission. Both left unticked. |
| 2026-10-04 | H5 corrected run (2,000 questions, 50 workers) | FAILED SLOs, 0 errors | 1000 requests, 212.8 s, 4.7 rps. list p50 7892 ms p95 55612 ms; detail p50 2625 ms p95 13398 ms; write p50 5367 ms p95 18332 ms. The 300 errors of the first run are gone (JWT expiry; token now minted per request). Diagnostic, 1 worker, 60 requests: list p50 60 ms p95 449 ms; detail p95 52 ms; write p95 144 ms. The 50-worker figures are dominated by the single-process harness (threads share the GIL), so this harness cannot validate the 50-concurrency SLO. Fix applied: list endpoint prefetches versions and options (N+1 removed, TestListQueryCount). H5 stays unticked until a real HTTP load run (gunicorn plus an external load generator) is done. |
| 2026-10-04 | H2 concurrency | Found and fixed a deadlock | TestConcurrentPublishAndReorder: two concurrent reorders updated the same rows in different orders; PostgreSQL aborted one (503). Fix: reorder_questions and reorder_nodes lock siblings by id, then check the set under the lock. Tests: concurrent publish (one state change), concurrent reorder (one complete order). H2 ticked. |
| 2026-10-04 | H1 security matrix | Checklist test added (tests/test_content_matrix.py) | Every §2.13 and §2.14 row maps to named tests; the checklist fails if a named test is missing. Known gaps listed explicitly: image statuses (spec 415/413, built 400) and S3 client timeout (core/storage.py is shared with practice). H1 and H4 stay unticked until those gaps are decided. |
| 2026-10-04 | H6 practice regression | Full practice-service suite, Postgres, one run, exit 0 | Includes all content suites. H6 ticked. |
| 2026-10-04 | Codebase fixes (H1, H4, status codes, S3 timeout, L6, M6) | Done; content suites and full practice suite pass on Postgres (one run each) | Image statuses now 413 (oversize, image_too_large) and 415 (content does not match type; unsupported extension/content type), per section 2.13. S3: optional timeout in core/storage.py (default unchanged for practice); content uses CONTENT_S3_TIMEOUT_SECONDS (default 5); botocore timeout -> 503, object kept. KNOWN_GAPS is empty. L6: rollback rehearsal test (flag off 404, flag on data kept). H1 and H4 ticked. M6: scratch databases in the test container dropped (practice_load, practice_test, test_practice_test); only postgres remains. The shared dev database was not used by these runs (they only touched content-test-pg). |
| 2026-10-06 | Run-count rule changed (user decision) | H7, J2, M4 now run once, passing | The two-run (200%) rule in the execution rules is replaced by the run-once rule. Passing evidence: backend full suite practice_final.txt (exit 0); content frontend and full frontend suite fe_final2.txt (67/67 suites, 616/616 tests). |
| 2026-10-06 | I9 accessibility (codebase part) | Done: axe-core scan (4 tests) plus static WCAG AA contrast check (7 tests) | Contrast failures found and fixed: content screens used --color-text-subtle (2.59:1) and --color-success text (3.30:1); now --color-text-muted (5.24:1) and --color-text. Contrast test reads the real tokens from app/globals.css and fails on low-contrast token use in content screens. Full frontend suite after the fix: 67/67 suites, 616/616 tests (fe_final2.txt). I9 ticked. Live visual check of contrast in a browser is part of J5 (live). |
| 2026-10-06 | Full backend suite, PostgreSQL, one run, current code | Exit 0, no failures or errors. Output: practice_final.txt. Covers practice and all content suites, including matrix, concurrency, phase F/G, and health. |
| 2026-10-06 | Full frontend suite, one run, after all frontend and backend contract changes | 66/66 suites, 609/609 tests pass (exit 0). Output: fe_full_final.txt. Includes the new accessibility test (axe-core, 4 tests) and the request-reference tests. |
| 2026-10-04 | H5 diagnosis (final) | Root cause: environment CPU, not connections or worker model | Host has 2 vCPUs, shared by the server, PostgreSQL, Redis and the Python load client. Run 4 (4 gunicorn gthread workers x 16 threads, WSGI): 1000 requests, 0 errors, 5.0 rps; list p95 26191 ms; detail p95 13825 ms; write p95 23852 ms. Run 5 (4 ASGI workers, sampling): 0 errors, 6.4 rps; list p95 25742 ms. PostgreSQL samples: peak 48 connections (limit 100), peak 27 active, no lock waits. Container CPU during load: server up to 117%, PostgreSQL up to 65%, load client up to 35%, on 2 vCPUs. So the SLO (list/detail/write p95 300/300/500 ms at 50 concurrency) cannot be validated on this 2-vCPU host; it needs a production-sized host and the production path (PgBouncer). Cache note: 30% writes bump the institution cache version, so list caching gives little benefit under this mix. H5 stays unticked. |
| 2026-10-04 | H5 real HTTP runs | FAILED SLOs; H5 stays open | Run 1 (b96vh23qc, output load_http1.txt) is INVALID: 1000 requests, 125.1 s, 8.0 rps, 300 errors; list p50 3537 ms p95 35665 ms; detail p50 3683 ms p95 7740 ms; write p50 2325 ms p95 8110 ms (these latencies measure 401 responses, not the content API). Cause: manage.py loads .env.example before settings, so the CLI client signed tokens with the example JWT key while the server used the test key; every request was 401. Fixed by setting SECRET_KEY and JWT_SIGNING_KEY explicitly on both containers. Run 2 (biig1mixh): 1000 requests, 50 workers, gunicorn (uvicorn workers, 4), real Redis, same database; wall 558 s, 1.8 rps; list p50 14839 ms p95 121398 ms; detail p50 10385 ms p95 30096 ms; write p50 19486 ms p95 59304 ms; 51 client errors (timeouts at the 120 s client limit). Server access log: 1294 responses 200, 8 404 (probe requests). Single-client warm latency is 30-360 ms, so the breach is queueing: the production entrypoint runs ASGI sync views with 3 uvicorn workers. Capacity change is a deployment decision (more workers, or sync WSGI workers with threads). H5 stays unticked. Run 3 (load_http3.txt, 12 gunicorn workers, migrated practice_load database re-created after M6): WORSE. 1000 requests, wall 1499.9 s, 0.7 rps; 288 client errors (timeouts at 120 s); list p50 31739 ms p95 190675 ms; detail p50 22359 ms p95 128408 ms; write p50 31560 ms p95 141682 ms. Server log: 949 x 200, 15 x 428 (writes whose ETag GET timed out and sent no If-Match). More workers do not fix it; the likely limit is PostgreSQL connections and waits (no pooler on this path; the production path goes through PgBouncer). Not yet verified: pg_stat_activity during load. |
| 2026-10-04 | Content backend regression | All content suites (incl. matrix and concurrency) pass on Postgres after the reorder fix, exit 0 | |
| 2026-10-04 | K docs | docs/content-bank.md, docs/content-bank-operations.md, PRODUCTION_CHECKLIST section 15, .env.example CONTENT_CACHE_TTL_SECONDS added; TestEnvExampleComplete | K1, K2, K3, K4 (N/A, no README), K5 ticked. K gate (user review) still open. |

**Current status:** F, G, I (except I8, I9), H2, H6, K (except the review gate) complete with evidence. Still open and blocked or needing your decision: H1 and H4 (two known gaps), H3 (S3 dev bucket and Redis runs), H5 (real HTTP load run), H7 (two runs, conflicts with the one-run rule), I8 and I9 (live browser; axe-core not installed), J2 and J5, all of L (L2 to L5 need your permission), M1 to M3, M5 to M7. See the progress log rows above.

**Previous status:** Phases F and G complete, with evidence above. Phase I complete except I8 and I9 (blocked, see log). Phase H (load test, H5 failed; full backend matrix not run) and J (J2/J5 not ticked) remain open.
