# MaintainSMIP — Deploy & Infra

**Live:** https://maintainsmip.onrender.com  
**Repo:** https://github.com/hopalongis-del/MaintainSMIP  
**Local path:** `C:\Claude Code`

---

## For agents: routine deploys

Infrastructure is **already live**. For normal code changes you do **not** need the user or the Render dashboard.

```powershell
cd "C:\Claude Code"
python test_smoke.py
git add <files>
git commit -m "Describe the change"
git push origin main
```

Render watches `main` and redeploys automatically (~2–3 minutes). After push, verify:

```text
GET https://maintainsmip.onrender.com/api/health
```

Expect `"status": "ok"`, `"persistent_storage": true`, `"db_exists": true`. During rebuild you may see **502** — wait and retry.

**Never** give the user a list of commands to run. Execute the loop yourself. See `HANDOFF.md` → *Agent autonomy*.

---

## Render setup (already done — reference only)

| Item | Value |
|------|-------|
| Plan | Starter (~$7/mo, always on) |
| Blueprint | `render.yaml` |
| Disk | `maintainsmip-data`, 5 GB at `/var/data` |
| Health check | `/api/health` |
| Start command | `uvicorn server:app --host 0.0.0.0 --port $PORT` |

**Env vars** (set in Render dashboard on first deploy; do not commit):

| Variable | Purpose |
|----------|---------|
| `APP_PASSWORD` | Master admin password; seeds team accounts on first boot |
| `APP_SECRET` | Session cookie signing |
| `DATA_DIR` | `/var/data` (from `render.yaml`) |
| `VAPID_EMAIL` | Push notifications contact |

**Persistent paths on Render:**

- SQLite: `/var/data/maintainsmip.db`
- Accident photos: `/var/data/uploads/accidents/`
- VAPID keys: `/var/data/vapid_keys.json`

Data survives redeploys. **Do not delete** the `maintainsmip-data` disk unless intentionally wiping production.

---

## User accounts

Seeded on first boot (`TECHNICIAN_ACCOUNTS` + `admin` in `server.py`):

| Username | Role | Initial password |
|----------|------|------------------|
| `admin` | Master admin | `APP_PASSWORD` (demo: `WeLoveRacing!`) |
| `mike.casady` | **Admin** | `APP_PASSWORD` until changed — **currently `mike`** on production |
| `dusty.hixson`, `brian.lachance`, `chelsie` | Admin | `APP_PASSWORD` until changed |
| `gavin.weinmeister`, `kevin.stellman`, etc. | Technician | `APP_PASSWORD` until changed |

**Lockout safeguards**

- No users → master `admin` auto-created
- All admins deactivated → master `admin` restored from `APP_PASSWORD`
- Login as `admin` with `APP_PASSWORD` resets master password to env value
- Legacy password-only login (no username) signs in as `admin`

**Team Accounts** (Settings, admin only): add users, reset passwords, deactivate accounts. Last active admin cannot be removed.

---

## Local dev

```powershell
cd "C:\Claude Code"
.\install.bat    # once
.\start.bat      # http://localhost:8000
```

Local DB: `maintainsmip.db` in repo root (or `DATA_DIR` if set).

---

## One-time Render provisioning (historical)

Only needed if rebuilding from scratch:

1. Render → **New** → **Blueprint** → connect GitHub repo
2. Set secret env vars `APP_PASSWORD` and `APP_SECRET`
3. Apply; wait for build

Day-to-day updates are **git push only**.

---

## Teardown

Render dashboard → service → **Delete Web Service** (stops billing). Only do this if the user explicitly requests shutdown.