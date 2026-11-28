# BUGTRACKER
> Read this before debugging anything. The fix may already be here.

---

## BUG-001 — Docker Daemon Crashes / CLI Freezes

**Symptoms:** `docker compose ps` hangs, 500 errors on pipe, `RAM 0.00 GB CPU 0.00%` in Docker Desktop.

**Root Cause:** WSL2 ran out of memory → daemon killed.

**Fix:**
```powershell
Get-Process | Where-Object {$_.Name -like "*docker*"} | Stop-Process -Force
wsl --shutdown
```
Reopen Docker Desktop → wait for real RAM/CPU numbers → `docker compose up -d`

**Permanent Fix:** `C:\Users\pranavnath\.wslconfig`
```ini
[wsl2]
memory=2GB
processors=2
swap=2GB
```

---

## BUG-002 — Port 9000 Conflict on Every Restart

**Symptoms:** `Bind for 0.0.0.0:9000 failed: port is already allocated` — killing the PID doesn't permanently fix it.

**Root Cause:** Another project (aptlogic/clap) is running in the background holding port 9000.

**Fix:**
1. Docker Desktop → Containers tab → check if multiple projects are running
2. Stop non-active projects:
```powershell
cd "C:\Users\pranavnath\OneDrive\Desktop\CLAP"
docker compose down

cd "C:\Users\pranavnath\OneDrive\Desktop\spark"
docker compose -p aptlogic down
```
3. Kill remaining PIDs:
```powershell
netstat -ano | findstr :9000
taskkill /PID <PID> /F
```
4. `docker compose up -d`

**Rule:** Always check Containers tab first — if multiple projects listed, stop them before anything else.

---

## BUG-003 — CPU 100% / Docker Engine Unresponsive

**Symptoms:** Docker Desktop shows 98-100% CPU constantly. Engine crashes immediately after restart.

**Root Cause:** Multiple projects running simultaneously — combined CPU/RAM exhausted the WSL2 VM.

**Fix:**
1. Docker Desktop → Containers tab → stop all non-active projects
2. If engine already crashed:
```powershell
Get-Process | Where-Object {$_.Name -like "*docker*"} | Stop-Process -Force
wsl --shutdown
```
3. Reopen Docker Desktop → wait for CPU to drop → `docker compose up -d`

**Rule:** Never run more than one Docker project at a time on this machine.

---

## BUG-004 — Frontend Infinite Reload Loop / Turbopack Panics

**Symptoms:** Browser loops on `localhost:3000`. Terminal shows `FATAL: An unexpected Turbopack error occurred` on every request.

**Root Cause:** `.next` cache has stale paths — happens after folder rename or move.

**Fix:**
```powershell
Remove-Item -Recurse -Force "frontend\.next"
```
Then `npm run dev` — rebuilds clean, panics stop.

**Rule:** Always delete `.next` after renaming or moving the project folder.

---

## BUG-005 — Frontend Loads With Zero Styling (Unstyled/Raw HTML)

**Symptoms:** Page renders real content (text, forms) but with no layout, spacing,
or colour — looks like plain unstyled HTML. `_next/static/css/app/layout.css`
returns `200 OK` and is a plausible size, but contains only CSS custom
properties / `@theme` variables and the hand-written rules from `globals.css`
— zero generated Tailwind utility classes (no `.flex`, `.grid`, `.p-4`, etc.).

**Root Cause:** `frontend/postcss.config.mjs` (registers `@tailwindcss/postcss`,
required for Tailwind's JIT engine to run) is never copied into the dev
container. `Dockerfile.dev` only `COPY`s `package.json`/`package-lock.json`,
and `infra/docker-compose.dev.yml` only bind-mounts `src/`, `public/`,
`tsconfig.json`, `next.config.ts` — `postcss.config.mjs` falls through both.
Without it, Next's default CSS pipeline still resolves `@import "tailwindcss"`
(so the stylesheet 200s and looks non-empty) but never runs the Tailwind
plugin, so no utility classes get generated. Only surfaces on a from-scratch
image build with no stale layer/cache carrying an old copy of the file —
e.g. right after cloning or moving the repo to a new machine.

**Fix:** Already patched in both places — `Dockerfile.dev` now copies
`postcss.config.mjs` alongside the package files, and
`infra/docker-compose.dev.yml` bind-mounts it into the frontend container.
If this regresses (e.g. the bind mount gets removed), restore the line:
```yaml
- ../frontend/postcss.config.mjs:/app/postcss.config.mjs:ro
```
then `docker compose -f infra/docker-compose.dev.yml up -d frontend` to
recreate the container.

**Rule:** Any frontend config file the build depends on (postcss, eslint,
etc.) needs an explicit `COPY` in `Dockerfile.dev` or a bind mount in
`docker-compose.dev.yml` — don't assume it's covered by `src/`.

---

## BUG-006 — Containers Can't Reach the Internet (RDS, or anywhere) After a Wi-Fi/Network Change

**Symptoms:** Backend services (auth-service, user-service, practice-service,
etc.) hang forever on startup — stuck on `python manage.py migrate` with
**zero log output**, container status stays `health: starting` then flips to
`unhealthy`, never recovers on its own. `docker logs` on PgBouncer shows
`client_login_timeout (server down)` for every `*_db`. Looks exactly like an
RDS security-group problem, but is usually NOT — see the two checks below
before touching AWS.

**Root Cause:** The host machine's Wi-Fi/network changed (new network, VPN
toggled, router restart). The *Windows host* still has a fine network path,
but Docker Desktop's WSL2 VM keeps using the old network route internally and
never recovers on its own. Result: the host can reach the internet fine, but
**every container's outbound connection hangs indefinitely** — not just to
RDS, to anywhere (confirmed by testing a container against an unrelated
HTTPS site). DNS resolution inside the container still works and is
instant, which is what rules out a DNS problem and points at the network
route instead.

**How to tell this apart from an actual RDS security-group block (look-alike cause):**
1. From the **host** (not a container): `curl -s --max-time 10 https://checkip.amazonaws.com`
   — this is the IP that needs to be in the RDS security group's inbound
   rule (`spark-rds-sg`, port 5432). If it changed since the rule was last
   set, that alone can cause the same PgBouncer errors — fix the AWS rule
   first (see RULE below) and retest.
2. From **inside a container** on the stack's network, with generous
   timeouts (cold containers can take 8–10s just to start, don't use a tight
   timeout or you'll get a false positive):
   ```bash
   export MSYS_NO_PATHCONV=1
   docker run --rm --network infra_spark-internal --entrypoint python \
     infra-practice-service:latest -c "
   import socket, time
   t0=time.time()
   try:
       s = socket.create_connection(('checkip.amazonaws.com', 443), timeout=8)
       print('OK', round(time.time()-t0,2)); s.close()
   except Exception as e:
       print('FAIL', round(time.time()-t0,2), type(e).__name__, e)
   "
   ```
   If this hangs/times out against an **unrelated public site** (not RDS),
   it's this bug, not an AWS rule — fixing the security group will not help
   until this is fixed.

**Fix:**
```powershell
wsl --shutdown
```
Then reopen Docker Desktop and wait for "Engine running". A plain
"Restart" from the Docker Desktop UI is **not enough** — it did not fix
this the first time; the full `wsl --shutdown` (which force-stops the VM
completely) was required. After it comes back:
```bash
cd infra
docker compose -f docker-compose.dev.yml -f docker-compose.content-live.yml up -d
```
Dependent services (anything `depends_on: condition: service_healthy` a
service that was mid-recovery) may report
`dependency failed to start: container X is unhealthy` on the first `up -d`
even though X is actually fine by then — Docker's health status needs a
few more passing check cycles to catch up after a run of earlier failures.
Re-run `docker compose up -d` once those settle (check with
`docker ps --format "{{.Names}}\t{{.Status}}"`), or verify a specific
service directly:
```bash
docker exec <container> python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/<service>/health/', timeout=10).read())"
```

**Rule:** After *any* host network change (new Wi-Fi, VPN on/off, router
restart), assume this bug before assuming an AWS problem. Run the
container-level connectivity check above first — it takes 15 seconds and
tells you which of the two problems (or both) you actually have.

---

## BUG-007 — Students on `www.spark.sanjivo.com` Got "No Internet Connection" at Login

**Problem:** `gateway/nginx.conf`'s `$cors_origin` map only matched
`~^https://spark\.sanjivo\.com$`. `https://www.spark.sanjivo.com` is a real,
live production URL (same Vercel deployment, DNS confirmed) that students
were actually using, but it never matched that regex.

**Symptom:** Any student on the `www.` URL saw "No internet connection" on
the login screen. Server logs showed the `OPTIONS` preflight always
returning 204, but the real `POST /api/auth/login/` never arrived — because
nginx sent back `Access-Control-Allow-Origin: ""` for the unmatched origin,
so the browser blocked the request itself and never sent it. Looked
network/institution-WiFi related (it correlated with whichever URL form a
given institution was given), but reproduced from any network once the
`www.` URL was used.

**Fix:** Broadened the regex to `~^https://(www\.)?spark\.sanjivo\.com$`
(`gateway/nginx.conf`'s `map $http_origin $cors_origin` block). `nginx.dev.conf`
needs no change — local dev only ever deals with `localhost:3000`. No
Vercel-side change needed — confirmed both domains already serve identical
content there. Verified live: a preflight with `Origin: https://www.spark.sanjivo.com`
against `api.spark.sanjivo.com` now returns that same origin in
`Access-Control-Allow-Origin` instead of an empty value.

**Rule:** Any time a new production domain/alias is added (www, a redirect
domain, a new Vercel custom domain), it must be added to this same
`$cors_origin` map explicitly — nothing here falls back to a wildcard, by
design, so a missed alias fails silently as a client-side "network error"
with no server-side error to grep for.

---
## BUG-008 — Assignments List 500s For Any Student With An Old Closed Exam

**Symptoms:** `GET /api/assessments/student/assignments/` returned a 500
for any student who had at least one old, closed exam in their history —
breaking the entire assignments list on the student home page, not just
that one assignment.

**Root Cause:** `assessments/views.py`'s student-assignments endpoint read
`alloc.set.total_marks()` and `alloc.set.questions.count()` unconditionally.
`StudentSetAllocation.set_id` is `None` for 3,566 of 9,286 rows in
production — confirmed identical on the original AWS RDS database (same
counts, pre-dating the VPS migration entirely — this was not caused by the
infra migration). All 22 distinct affected assignments are `status=CLOSED`,
spanning August–November 2026.

**Fix:** Guard both fields against a missing allocation instead of assuming
one always exists:
```python
"total_marks": alloc.set.total_marks() if alloc.set else None,
"question_count": alloc.set.questions.count() if alloc.set else None,
```
(PR #47, commit `44922d3`.)

**Rule:** Never assume a FK on a model tied to *closed/historical* records
is populated just because newer/active records always populate it at
creation time — old rows can predate a field becoming mandatory in
practice. Check real production data before assuming a crash means bad
data, not bad code.

---

## BUG-009 — Every File Read Broken On Self-Hosted Storage (404/"Page not found")

**Symptoms:** Every resource PDF, practice-question image, and any other
uploaded file returned "Page not found" on the frontend when opened. The
API itself returned 200 — the problem was the `file_url`/`read_url` field
in the response: a bare storage key (e.g. `uploads/pdf/<uuid>.pdf`) with no
domain at all, which the frontend's router then tried (and failed) to
resolve as one of its own pages.

**Root Cause:** `core/storage.py`'s `get_cdn_url()` concatenates
`AWS_S3_CDN_DOMAIN` + the file key — a pattern that only makes sense for
real AWS production, which serves reads straight off a public-read bucket
behind a CDN (no signature needed). Self-hosted deployments deliberately
set `AWS_S3_CDN_DOMAIN=""` (there is no CDN in front of SeaweedFS), and
`get_cdn_url()` silently fell back to returning the bare key — this was a
known, documented gap ("self-hosted has no CDN concept") that was never
actually closed with a working alternative.

Confirmed directly (not assumed): an unauthenticated `GET` against
SeaweedFS's S3 gateway returns `403`. Unlike the old CDN+public-bucket
model, SeaweedFS requires every single request to be signed — reads
included, not just writes.

**Fix:** Added `generate_presigned_read_url()` (the GET counterpart to the
existing `generate_presigned_upload_url()`) to all three affected services'
`core/storage.py` (resource-service, practice-service, assessment-service —
each has its own near-identical copy of this file). `get_cdn_url()` now
calls it whenever `AWS_S3_ENDPOINT_URL` is set, then swaps the internal
`seaweedfs:8333` host prefix for a new `AWS_S3_PUBLIC_MEDIA_BASE_URL`
setting, leaving the signed path+query string untouched. A new `/media/`
location in `gateway/nginx.conf` proxies those requests straight through to
SeaweedFS, explicitly force-setting the `Host` header back to
`seaweedfs:8333` — the exact host the AWS SigV4 signature was computed
against — regardless of the public `Host` header the browser sent, since
that's what SeaweedFS validates the signature against. (PR #48, merged,
branch `feat/selfhosted-media-presigned-reads`, commit `714cb1a`; tests +
docs added in `5877d1a`.)

**Follow-up fix (same bug, found during deploy validation):** The new
`/media/` location initially used a static `proxy_pass http://seaweedfs:8333;`
-- inconsistent with every other backend in `gateway/nginx.conf`, which
resolves its upstream through a `map $host $X_backend` variable instead of
a literal hostname. A static proxy_pass target is resolved once, at nginx
config-load time, and nginx refuses to start if that hostname isn't
resolvable yet -- confirmed directly via `nginx -t`, which failed with
"host not found in upstream seaweedfs" the first time this was tested in
isolation. Fixed by adding `map $host $seaweedfs_backend { default
seaweedfs:8333; }` alongside the existing backend maps and changing
`proxy_pass` to use it -- `proxy_set_header Host seaweedfs:8333;` was left
unchanged, since that literal value (not the map mechanism) is what the
AWS SigV4 signature was computed against. (PR #49, merged, branch
`fix/nginx-media-proxy-map-backend`, commit `787d876`.)

**Verified end-to-end (2026-11-28):** All three affected services rebuilt
and redeployed on the VPS, `nginx -t` passes, and a real resource PDF was
opened directly in the browser through `https://api.spark.sanjivo.com/media/...`
and rendered correctly (16-page PDF, full content). This is now a closed
bug, not a code-reviewed-but-unverified fix.

**Rule:** A "self-hosted has no CDN concept, falls back to X" comment next
to a silent fallback is a red flag, not a resolution — it documents a gap,
it doesn't close one. Any code path that can silently return a
syntactically-valid-looking-but-functionally-broken value (a bare key that
looks like it could be a relative URL) needs an explicit test exercising
the self-hosted branch, not just the real-AWS branch — this gap shipped
because nothing had ever actually tried to open a file on the self-hosted
deployment end-to-end before a real user did.

## BUG-010 -- Image Upload Broken On Self-Hosted Storage (Mixed Content / Unreachable Host)

**Symptoms:** Uploading a new question image (or any other image/file) in
the admin paper editor failed with "Image upload failed. Please try
again." Browser console showed a blocked mixed-content request: the page
was loaded over HTTPS, but the upload's presigned PUT URL pointed at
`http://seaweedfs:8333/...` -- the internal-only Docker hostname, over
plain HTTP.

**Root Cause:** BUG-009 fixed the READ side (`get_cdn_url`) by rewriting a
presigned URL's internal SeaweedFS host to the public `/media/` proxy
route, but `generate_presigned_upload_url` (the WRITE side, used for
direct browser-to-storage PUT uploads) was never touched -- its docstring
claimed "real S3 has no internal vs. browser-facing endpoint distinction
to work around," which is true for real AWS but false for self-hosted
SeaweedFS, the exact same gap BUG-009 closed on the read side. This went
unnoticed because no new image had actually been uploaded against
self-hosted storage since the migration -- the existing image on the
question used to discover this (via BUG-009 testing) predated the
self-hosted cutover entirely, so only the READ path had been exercised,
never the WRITE path.

**Fix:** Extracted the host-rewrite logic BUG-009 added inline in
`get_cdn_url` into a shared `_rewrite_to_public_media_url()` helper, used
by both `get_cdn_url` (reads) and `generate_presigned_upload_url` (writes)
in all three affected services' `core/storage.py` (resource-service,
practice-service, assessment-service). No nginx change was needed --
`gateway/nginx.conf`'s existing `/media/` location already proxies any
HTTP method through to SeaweedFS with the correct `Host` header restored,
and the server-level CORS headers (including the OPTIONS preflight
short-circuit) are inherited automatically since this location defines no
`add_header` of its own. (Branch `fix/selfhosted-upload-presign-host`.)

**Rule:** A read-side fix and a write-side fix for the same underlying
constraint (self-hosted storage has a real internal/public endpoint split
that real-AWS code never had to handle) are two separate code paths and
two separate bugs until both are verified -- fixing `get_cdn_url` alone
left a stale, now-incorrect comment on `generate_presigned_upload_url`
asserting the exact problem that still existed there. Whenever a
self-hosted-specific assumption is fixed in one function, grep for every
other function carrying the same assumption in its own docstring before
declaring the class of bug closed.

---
