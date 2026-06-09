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
