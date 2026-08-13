# Resource Upload Policy

Source of truth: `core/upload_constraints.py` (backend) and `frontend/src/lib/constants.ts`
(frontend) — keep both in sync when changing any value below.

## Allowed formats & size limits

| Upload Type | Allowed Formats | Max Size |
|---|---|---|
| PDF | `.pdf` | 25 MB |
| Audio | `.mp3`, `.aac`, `.m4a`, `.ogg` | 100 MB |
| Video | `.mp4`, `.webm` | 500 MB |
| Image | `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp` | 5 MB |
| Video Link | Any valid URL | N/A (no file) |
| External Link | Any valid URL | N/A (no file) |

**Deliberately excluded:** `.svg` (inline `<script>` = stored-XSS vector), `.wav` (uncompressed,
blows through the audio cap in minutes), `.avi`/`.mov`/`.mkv` (don't play in-browser the way this
app serves files).

Per-section storage quota: **2 GB total** (`MAX_BYTES_PER_SECTION`), enforced at confirm.

## Security controls

| Control | What it does |
|---|---|
| Access control | `IsAdminUser` on all upload endpoints |
| Multi-tenant isolation | Section lookup scoped by `institution_id`; cross-institution access 404s |
| Extension validation | Checked client-side and server-side; server is authoritative |
| MIME-type validation | `content_type` cross-checked against `upload_type` allowlist at presign |
| File size enforcement | Real server-side `HEAD` check against storage — client-reported size is never trusted |
| Content verification | Magic-byte check on the first bytes read back from storage — catches renamed/mislabeled files |
| Malware scanning | ClamAV scans every confirmed file upload async; hidden from students until verdict is "clean"; infected files are deleted from storage + DB immediately |
| Storage key safety | Server-generated UUID key, not user-supplied — no path traversal |
| Upload credentials | Short-lived (1hr) presigned PUT URL scoped to one exact key |
| CORS | Upload proxy (port 9002) restricted to an origin allowlist, not `*` |
| Delete handling | Async via Celery task queue |
| Rate limiting | 100 req/min on `/api/resources/*` at the gateway |

## Scan status lifecycle

`scan_status` on `Upload` / `ModuleUpload`: `pending` → `clean` | `infected` | `error`

- Links (`video_link`, `external_link`) skip scanning — set `clean` immediately (no file bytes).
- File uploads start `pending`, hidden from students until a scan confirms `clean`.
- `infected` → object + record deleted immediately, never shown anywhere.
- `error` (ClamAV unreachable after retries) → stays hidden from students; visible to admins with
  a "Scan failed" badge.
- Uploads that existed before this system was added were grandfathered to `clean`
  (see migration `0006_add_scan_status.py`) — nothing already live disappeared.
