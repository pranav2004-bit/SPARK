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
