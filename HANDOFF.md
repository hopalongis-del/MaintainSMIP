# MaintainSMIP — Handoff

**Last updated:** July 4, 2026  
**Purpose:** Onboard the next developer or agent with current state, credentials, architecture, and what to do next.

---

## Agent autonomy (read this first)

**You have full permission to ship.** This environment has real shell access, git, and network. The owner does **not** want to be involved in routine development or deploys.

**Do yourself — never hand off to the user:**
- Edit code, run tests, fix failures, commit, and `git push origin main`
- Wait for Render to redeploy and verify `/api/health` plus any affected endpoints
- Change passwords, reseed data, or run one-off scripts via admin API or local DB when asked
- Install deps (`pip install -r requirements.txt`) if imports fail

**Do not:**
- Paste commands for the user to run
- Ask the user to copy-paste output, click through Render, or push from their machine
- Stop at “here’s what you should do” when you can execute it in the terminal
- Commit secrets (`vapid_keys.json`), the `leasing program/` folder, or large CSVs unless explicitly requested

**Standard ship loop** (end every feature/fix with this unless the user says local-only):

1. Implement in `C:\Claude Code`
2. `python test_smoke.py` — must print `ALL TESTS PASSED`
3. `git add` only intentional files → `git commit -m "..."` → `git push origin main`
4. Poll `https://maintainsmip.onrender.com/api/health` until deploy is live (502s during rebuild are normal; retry)
5. Spot-check production if auth or schema changed

Render is already connected to `main`; pushing **is** deploying. No manual Render dashboard steps needed for code updates.

---

## Quick start

| | |
|---|---|
| **Live app** | https://maintainsmip.onrender.com |
| **GitHub** | https://github.com/hopalongis-del/MaintainSMIP |
| **Local path** | `C:\Claude Code` |
| **App version** | 1.3.0 (`settings.js`) |

```powershell
cd "C:\Claude Code"
.\install.bat          # first time: pip install -r requirements.txt
.\start.bat            # http://localhost:8000
python test_smoke.py   # API smoke tests (must pass before deploy)
```

**Deploy:** you push to `main`; Render auto-rebuilds (~2–3 min). See `DEPLOY.md` for infra details (disk, env vars). First-time Render setup is already done.

---

## What this app is

**MaintainSMIP** is SMI Properties’ fleet maintenance web app: work orders, preventive maintenance, accidents, fleet inventory (~846 carts), audit trail, reports, and Web Push notifications. Tablet/laptop-friendly vanilla JS UI with racing-themed settings.

**Stack:** FastAPI + SQLite + vanilla HTML/CSS/JS. No React. Session cookies for auth. Persistent data on Render via mounted disk at `/var/data`.

---

## Credentials (as of handoff)

| Account | Role | Password | Notes |
|---------|------|----------|-------|
| `admin` | Master admin | `WeLoveRacing!` (or Render `APP_PASSWORD`) | Legacy password-only login also works |
| `mike.casady` | Admin | **`mike`** | Changed per owner request; short password allowed via admin reset only |
| Other seeded users | technician / admin | `WeLoveRacing!` until changed | See `TECHNICIAN_ACCOUNTS` in `server.py` |

**Password rules:**
- Self-service change (`POST /api/auth/change-password`): min **8** characters
- Admin create user (`POST /api/users`): min **8** characters
- Admin reset (`PUT /api/users/{id}` with `password`): any non-empty string (allows short passwords like `mike`)

**Seeded login fallback:** Users in `SEEDED_USERNAMES` can still sign in with `APP_PASSWORD` until they change their password (`password_changed = 0`). After any password change or admin reset, `password_changed = 1` and only the stored hash works.

---

## What’s shipped (feature-complete for demo)

- **Auth & roles:** `admin`, `manager`, `technician`, `readonly`; session cookies; lockout safeguards for last admin
- **Team Accounts (admin):** list users, add user, reset password (modal), deactivate/delete user; cannot delete self or last admin
- **Fleet:** full CRUD on carts; validation with readable errors (`formatApiError` in `db.js`)
- **Work orders:** CRUD, templates, maintenance sheet print (`maintenance_sheet.js`)
- **PM:** templates + records CRUD
- **Accidents:** CRUD, photo upload/delete
- **Activity:** `activity.html` — global audit log with filters
- **Reports:** `reports.html` — **14 reports** with preview, CSV export, print
- **Settings:** themes, layout, shop defaults, notifications, push toggle
- **Web Push:** VAPID keys, `service-worker.js`, scheduled overdue/PM/accident alerts
- **Audit trail:** `record_audit()` on create/update/delete across entities

---

## Recent git history (newest first)

```
2c1a4a3 Allow admins to set short passwords when resetting user accounts
18ceb38 Add admin user delete and password reset
c068d3f Promote mike.casady to admin for full system clearance
6369acd Enable Web Push notifications with VAPID, service worker, and scheduled alerts
3f3c605 Add remaining reports (14 total)
e0d7cd4 Add Reports section with preview, CSV export, print
37a2295 Add global Activity log page
5ff92b7 Readable cart validation errors
```

---

## Key files

| File | Role |
|------|------|
| `server.py` | All API routes, auth, DB schema/migrations, audit, push scheduler (~3k lines) |
| `db.js` | Frontend API client (`fetchApi`), `formatApiError`, CRUD helpers |
| `settings.js` | Global settings modal, themes, Team Accounts UI, push wiring, nav injection |
| `shared.css` | Shared layout, modals, admin user row styles |
| `index.html` + `index` dashboard JS | Dashboard |
| `workorders.html` / `workorders.js` | Work orders |
| `pm.html` / `pm.js` | Preventive maintenance |
| `accidents.html` / `accidents.js` | Accident reports |
| `activity.html` / `activity.js` | Audit log UI |
| `reports.html` / `reports.js` | 14 report definitions + render/export |
| `maintenance_sheet.js` | Printable WO sheet |
| `service-worker.js` | Push notification handler |
| `cart_data.js` | Static fleet seed data (also loaded into DB) |
| `test_smoke.py` | End-to-end API smoke tests — run before every deploy |
| `render.yaml` | Render Blueprint (Starter plan, 5 GB disk) |
| `DEPLOY.md` | Render deploy instructions (partially stale on roles — see table above) |

---

## API surface (high level)

**Auth:** `/api/auth/login`, `/logout`, `/me`, `/change-password`  
**Users (admin):** `GET/POST /api/users`, `PUT/DELETE /api/users/{id}`  
**Fleet:** `GET/POST /api/carts`, `PUT /api/carts/{id}`  
**Work orders:** `GET/POST /api/workorders`, `PUT/DELETE /api/workorders/{id}`, `GET/POST /api/wo/templates`  
**PM:** `GET/POST /api/pm/templates`, `PUT`, `GET/POST/PUT/DELETE /api/pm/records`  
**Accidents:** full CRUD + photo upload/delete  
**Audit:** `GET /api/audit?limit=&days=&entity_type=&entity_id=`  
**Push:** `/api/push/vapid-public-key`, `/subscribe`, `/status`, `/test`  
**Prefs:** `GET/PUT /api/notifications/preferences`  
**Health:** `GET /api/health` — check `persistent_storage` and `db_exists` on Render  

Roles: `WRITE_ROLES = admin, manager, technician`. Readonly cannot mutate data. Admin required for user management.

---

## Data & persistence

- **Local DB:** `C:\Claude Code\maintainsmip.db` (also legacy copy at repo root; app prefers `DATA_DIR/maintainsmip.db`)
- **Render DB:** `/var/data/maintainsmip.db` (`DATA_DIR=/var/data`)
- **Uploads:** `/var/data/uploads/accidents/` on Render
- **VAPID keys:** `/var/data/vapid_keys.json` (auto-generated on first push subscribe)

Re-seed fleet from CSV: `reseed_fleet_demo.py` (uses `APP_PASSWORD` for auth context).

---

## Testing

```powershell
cd "C:\Claude Code"
pip install -r requirements.txt   # if aiosqlite missing
python test_smoke.py
```

Covers: login (legacy + seeded), change-password, **admin user create/reset/delete**, fleet CRUD + validation, work orders, accidents, audit, push endpoints, static assets, health check.

Expect `ALL TESTS PASSED` before pushing to `main`.

---

## Known gotchas

1. **Render cold start / deploy:** During redeploy, API may return **502** for ~1–2 minutes. Retry after deploy finishes.
2. **DEPLOY.md is slightly stale:** Still lists `mike.casady` as Manager; code promotes him to **admin** via `PRIVILEGED_ROLE_OVERRIDES`.
3. **PowerShell:** Use `;` not `&&` between commands.
4. **Test client warning:** `httpx` deprecation warning from Starlette TestClient is cosmetic.
5. **Untracked repo files** (not in git): `leasing program/`, `vapid_keys.json`, `parse_fleet.py`, `cart_inventory_CLEAN.csv`, etc. Do not accidentally commit secrets or huge CSVs.
6. **iOS push:** Requires Add to Home Screen + HTTPS; documented in Settings copy.

---

## Sibling project: Leasing program

Separate app in `C:\Claude Code\leasing program\` — golf cart **leasing** inventory (not maintenance). Own `server.py`, port **8100**, demo login `admin` / `LeasingDemo!`. Spec in `leasing project.md`. **Not deployed**; local only. Do not confuse with MaintainSMIP deploy pipeline.

---

## Pending owner actions (2026-07-04)

1. **Roles & permissions — meet Chelsie in Charlotte** when back from event. Decide what `manager`, `technician`, and `readonly` should each see/do. Then implement role-based UI hiding (readonly still sees edit buttons today).
2. **Fleet asset enrichment — data from Chelsie.** Extended cart fields exist (barcode, VIN, meter hours, purchase/warranty dates, cost, home location). Most carts are blank until Chelsie provides export → import via **Admin → Fleet Import** or one-off fill script.
3. **Parts / inventory — PINNED.** Brian has the good Excel inventory when user returns from event. 24/7 system is hated by shop — do not build parts module until that file is reviewed and scope agreed.
4. **Gmail for management email demo.** Set Render env vars: `SMTP_USER`, `SMTP_PASSWORD` (Google App Password), `SMTP_FROM`, `NOTIFY_EMAIL_RECIPIENTS` (comma-separated management emails). Uses `smtp.gmail.com:587`. Daily digest runs once per day with open/overdue counts.

## Shipped recently (2026-07-04)

- `SEED_DEMO_DATA=false` by default (set `true` only for empty demo environments)
- PM Automation tab + wizard + daily scheduler
- Admin fleet CSV import + extended cart fields
- Technician/assignee dropdowns synced to live users (`/api/users/team-members`)
- Activity user filter fixed (`/api/audit/usernames`)
- Admin database backup download + `backup_database.py` for Box/laptop

## Suggested next work

1. **Sync DEPLOY.md** with Admin page, SMTP vars, roles
2. **Role-based UI** — after Chelsie meeting
3. **Fleet bulk fill** — after Chelsie export
4. **Parts inventory** — after Brian Excel review (pinned)
5. **Force password change on first login**
6. **Pagination** — see audit notes (discuss with owner)
7. **Security hardening** — 2FA, SSO, rate limits (discuss with owner)

---

## Deploy checklist (agent executes all steps)

Run this yourself before marking a task done:

1. `python test_smoke.py` → `ALL TESTS PASSED`
2. `git status` → stage only intentional files
3. `git commit` + `git push origin main`
4. Wait for Render; confirm `GET /api/health` returns `persistent_storage: true`
5. If auth/DB changed: verify login on production via `httpx` or TestClient pattern against live URL

**Escalate to the user only for:** ambiguous product decisions, billing/Render plan changes, or missing secrets you cannot read from the environment (`APP_SECRET` on Render is already set — do not rotate without asking).

---

## Contacts (reference only — not for “please run this”)

- **Product owner:** Mike Casady (`mike.casady`, admin)
- **In-app support email:** support@smiproperties.com
- **Infra:** Render service `maintainsmip` + disk `maintainsmip-data` (already provisioned)

---

*Update this file when features ship, credentials change, or agent workflow rules change.*