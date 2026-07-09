# MaintainSMIP — Deploy & Infra

**Live:** https://maintainsmip.onrender.com  
**Repo:** https://github.com/hopalongis-del/MaintainSMIP  
**Local path:** `C:\MaintainSMIP`  
**App version:** 1.4.5 (`settings.js`)

---

## For agents: routine deploys

Infrastructure is **already live**. For normal code changes you do **not** need the user or the Render dashboard.

```powershell
cd "C:\MaintainSMIP"
python test_smoke.py
git add <files>
git commit -m "Describe the change"
git push origin main
```

Render watches `main` and redeploys automatically (~2–3 minutes). After push, verify:

```text
GET https://maintainsmip.onrender.com/api/health
```

Expect `"status": "ok"`, `"persistent_storage": true`, `"db_exists": true`, `"seed_demo_data": false`. During rebuild you may see **502** — wait and retry.

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

**Env vars** (set in Render dashboard; do not commit secrets):

| Variable | Purpose |
|----------|---------|
| `APP_PASSWORD` | Master admin password; seeds team accounts on first boot |
| `APP_SECRET` | Session cookie signing |
| `DATA_DIR` | `/var/data` (from `render.yaml`) |
| `SEED_DEMO_DATA` | `false` in production — demo WO/PM/accident seed only when `true` |
| `VAPID_EMAIL` | Push notifications contact |
| `SMTP_HOST` | Mail server (Gmail: `smtp.gmail.com`) |
| `SMTP_PORT` | Mail port (Gmail TLS: `587`) |
| `SMTP_USER` | Gmail address (e.g. `maintainsmip@gmail.com`) |
| `SMTP_PASSWORD` | Gmail **App Password** (not the account login password) |
| `SMTP_FROM` | From address shown on digest emails |
| `NOTIFY_EMAIL_RECIPIENTS` | Comma-separated management emails for daily digest |
| `BACKUP_TOKEN` | Optional — required query param for scripted backup downloads |

**Persistent paths on Render:**

- SQLite: `/var/data/maintainsmip.db`
- Accident photos: `/var/data/uploads/accidents/`
- VAPID keys: `/var/data/vapid_keys.json`

Data survives redeploys. **Do not delete** the `maintainsmip-data` disk unless intentionally wiping production.

**Off-server backups:** use `backup_database.py` with `backup_config.example.json` (Box sync folder on laptop). Admin page also offers one-click DB download.

---

## User accounts & roles

Seeded on first boot (`TECHNICIAN_ACCOUNTS` + `admin` in `server.py`):

| Username | Role | Initial password |
|----------|------|------------------|
| `admin` | Master admin | `APP_PASSWORD` (demo: `WeLoveRacing!`) |
| `mike` | **Admin** | **`mike`** (product owner; simple username) |

Former SMI Properties team accounts were removed in v1.7.1 (customer deal did not close).

**Roles:** `admin`, `manager`, `technician`, `readonly`. Write access: admin, manager, technician. Readonly is API-blocked; UI hiding is pending product decisions.

**First-login password:** users with `password_changed = 0` must set a personal password (8+ chars) before using the app. Seeded accounts can still sign in with `APP_PASSWORD` until they change it.

**Lockout safeguards**

- No users → master `admin` auto-created
- All admins deactivated → master `admin` restored from `APP_PASSWORD`
- Login as `admin` with `APP_PASSWORD` resets master password to env value
- Legacy password-only login (no username) signs in as `admin`

**Team Accounts** (`admin.html`, admin only): add users, reset passwords, deactivate/delete accounts. Last active admin cannot be removed. Settings is app preferences only — not admin tools.

---

## Local dev

```powershell
cd "C:\MaintainSMIP"
.\install.bat    # once
.\start.bat      # http://localhost:8000
python test_smoke.py
```

Local DB: `maintainsmip.db` in repo root (or `DATA_DIR` if set).

---

## One-time Render provisioning (historical)

Only needed if rebuilding from scratch:

1. Render → **New** → **Blueprint** → connect GitHub repo
2. Set secret env vars (`APP_PASSWORD`, `APP_SECRET`, SMTP vars if using email digest)
3. Apply; wait for build

Day-to-day updates are **git push only**.

---

## Teardown

Render dashboard → service → **Delete Web Service** (stops billing). Only do this if the user explicitly requests shutdown.