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
