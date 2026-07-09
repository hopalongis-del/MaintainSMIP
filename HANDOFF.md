# MaintainSMIP — Handoff

**Last updated:** July 9, 2026  
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

1. Implement in `C:\MaintainSMIP`
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
| **Local path** | `C:\MaintainSMIP` |
| **Local AI** | `maintainsmip-guru` — prompt: `ollama/SYSTEM_PROMPT.md`, updates: `ollama/MODEL_UPDATES.md` |
| **App version** | 1.7.1 (`settings.js`) |

```powershell
cd "C:\MaintainSMIP"
.\install.bat          # first time: pip install -r requirements.txt
.\start.bat            # http://localhost:8000
python test_smoke.py   # API smoke tests (must pass before deploy)
```

**Deploy:** you push to `main`; Render auto-rebuilds (~2–3 min). See `DEPLOY.md` for infra details (disk, env vars). First-time Render setup is already done.

---

## Local copy vs production

**Yes — a complete, up-to-date app copy exists locally.** `C:\MaintainSMIP` is the single source for shipped code; production deploys from `main` on GitHub.

| | Local | Production |
|---|---|---|
| **App code** | `C:\MaintainSMIP` @ `APP_VERSION` in `settings.js` | https://maintainsmip.onrender.com (auto-deploy from `main`) |
| **Git** | `main` should match `origin/main` | Same commit as local after push |
| **Database** | `C:\MaintainSMIP\maintainsmip.db` (your machine’s data) | `/var/data/maintainsmip.db` on Render (separate) |
| **Run locally** | `.\start.bat` → http://localhost:8000 | N/A |

**Verify local is current:**

```powershell
cd C:\MaintainSMIP
git status -sb          # expect: ## main...origin/main (no ahead/behind)
git log --oneline -1    # should match latest commit on GitHub
```

Check `APP_VERSION` in `settings.js` matches the version in the Quick start table above.

**In git (deployed app)** — everything needed to run and ship: `server.py`, HTML/JS/CSS, `test_smoke.py`, `data/nascar_standings_snapshot.json`, etc.

**Local-only (not on Render / do not commit unless asked):**

| Kind | Examples | Notes |
|------|----------|--------|
| Modified, uncommitted | `ollama/` (guru model, `num_ctx`), `OPENWEBUI_SETUP_CHECKLIST.md`, some `scripts/` | Local AI setup; may differ from last commit |
| Untracked | `vapid_keys.json`, `*.db.pre-restore-*.bak`, `open-webui-tools/`, large CSVs, `parse_fleet.py` | Secrets, backups, Open WebUI helpers |
| Sibling project | `C:\Claude Code\leasing program\` | Different app — not MaintainSMIP |

Local guru/Open WebUI files are **extras** for development assistance, not a second out-of-date app tree. If `git status` shows `main...origin/main` with no ahead/behind, the **MaintainSMIP web app** matches production even when `ollama/` has local edits.

---

## What this app is

**MaintainSMIP** is a golf cart fleet maintenance web app: work orders, preventive maintenance, accidents, fleet inventory, audit trail, reports, parts/procurement, and Web Push notifications. Tablet/laptop-friendly vanilla JS UI with racing-themed settings. **Not tied to SMI Properties** (deal did not close; customer data purged in v1.7.1).

**Stack:** FastAPI + SQLite + vanilla HTML/CSS/JS. No React. Session cookies for auth. Persistent data on Render via mounted disk at `/var/data`.

---

## Credentials (as of handoff)

| Account | Role | Password | Notes |
|---------|------|----------|-------|
| `admin` | Master admin | `WeLoveRacing!` (or Render `APP_PASSWORD`) | Legacy password-only login also works |
| `mike.casady` | Admin | **`mike`** | Changed per owner request; short password allowed via admin reset only |
| Other seeded users | — | — | Only `admin` + `mike.casady` seed; former customer techs removed |

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
- **Activity:** `activity.html` — global audit log with filters; **all logged-in roles** (including readonly) — API uses `require_authenticated_user` only, not `require_write_access`
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
| `parts.html` / `parts.js` / `parts.css` | Parts inventory, vendors, purchase orders |
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
**Parts:** `GET/POST /api/parts`, `PUT /api/parts/{id}`, `POST /api/parts/{id}/adjust`, `DELETE` (deactivate)  
**Vendors:** `GET/POST /api/vendors`, `PUT/DELETE /api/vendors/{id}`  
**Purchase orders:** `GET/POST /api/purchase-orders`, `PUT /api/purchase-orders/{id}`, `POST /api/purchase-orders/from-reorder`  
**Parts stats:** `GET /api/parts/stats`  
**Audit:** `GET /api/audit?limit=&days=&entity_type=&entity_id=`  
**Push:** `/api/push/vapid-public-key`, `/subscribe`, `/status`, `/test`  
**Prefs:** `GET/PUT /api/notifications/preferences`  
**Health:** `GET /api/health` — check `persistent_storage` and `db_exists` on Render  

Roles: `WRITE_ROLES = admin, manager, technician`. Readonly cannot mutate data (API 403 on writes). Readonly **can** view Activity, Reports, and fleet read-only. Admin required for user management and Admin page.

| Area | admin | manager | technician | readonly |
|------|-------|---------|------------|----------|
| View Activity / Reports | yes | yes | yes | yes |
| Create/edit WO, PM, accidents, fleet | yes | yes | yes | no (API) |
| Admin page, user management | yes | no | no | no |

---

## Data & persistence

- **Local DB:** `C:\MaintainSMIP\maintainsmip.db` (also legacy copy at repo root; app prefers `DATA_DIR/maintainsmip.db`)
- **Render DB:** `/var/data/maintainsmip.db` (`DATA_DIR=/var/data`)
- **Uploads:** `/var/data/uploads/accidents/` on Render
- **VAPID keys:** `/var/data/vapid_keys.json` (auto-generated on first push subscribe)

Re-seed fleet from CSV: `reseed_fleet_demo.py` (uses `APP_PASSWORD` for auth context).

---

## Testing

```powershell
cd "C:\MaintainSMIP"
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

## Pending work (master list — July 4, 2026)

### Done / confirmed

| # | Item | Status |
|---|------|--------|
| 1 | Disable demo seed (`SEED_DEMO_DATA=false`) | Shipped |
| 3 | PM automation wizard + daily scheduler | Shipped |
| 4 | Extended fleet fields + cart modal + CSV import UI | Shipped (data mostly empty) |
| 6 | Gmail management email digest | User configured; `smtp_configured: true` |
| 7 | Admin fleet CSV import | Shipped |
| 8 | Technician/assignee dropdown sync | Shipped |
| 9 | Activity user filter fix | Shipped |
| — | Admin page separate from Settings | Shipped |
| — | DB backup download + `backup_database.py` | Shipped |
| — | Password show/hide toggles | Shipped |
| — | Force password change on first login | Shipped (v1.4.1) |
| — | PM dedup (no double-book open PM per cart+template) | Shipped (v1.4.1) |
| — | `DEPLOY.md` synced | Shipped (v1.4.1) |

### Blocked — waiting on people / data

| # | Item | Blocker | Notes |
|---|------|---------|-------|
| 2 | Roles & permissions UI | **Chelsie meeting (Charlotte)** | Decide manager/technician/readonly behavior. Readonly still sees edit buttons on WO/PM/accidents (only fleet uses `userCanWrite()` today). |
| 4b | Fleet bulk data fill | **Chelsie export** | Import via **Admin → Fleet Import** or one-off script when export arrives. |
| 5 | Parts / inventory module | Brian can refine UI/fields | **Shipped v1.7.0** — inventory, vendors, draft POs, stock adjust, reorder draft. AvidXchange auto-submit still Phase 3. |
| 7b | Box daily backup automation | **Production commitment** | Script exists; schedule Task Scheduler when you commit to production use. |

### Discuss later (audit items 10–12 + Tier 2–4)

| Item | Notes |
|------|-------|
| **Pagination** (audit #10) | Client loads full datasets today; fine at ~850 carts. Discuss before building server-side pagination. |
| **Security hardening** (audit #11) | 2FA, SSO, rate limits, session revoke — discuss scope. |
| **SQLite restore UI** (audit #12) | Shipped v1.5.0 — Admin restore with validation, pre-restore `.bak`, audit log. |
| **Per-cart history page** (Tier 2) | Timeline of WO + PM + accidents for one cart. |
| **Manager role meaning** (Tier 2) | Tied to Chelsie meeting. |
| **Barcode scan** (Tier 3) | Tablet cart lookup — leasing app has pattern. |
| **Cost tracking** (Tier 3) | Parts/labor/vendor rollups. |
| **Cosmetic pile** (Tier 4) | Nav injection, skeletons, phone polish, PDF export, dashboard charts. |

---

## Parts / procurement + AvidXchange (v1.7.0 shipped)

**Shipped:** Parts UI (inventory / vendors / POs), full CRUD APIs, stock adjust, draft PO from low stock, human approve → submit → received (received adjusts on-hand). Tables: `vendors`, `parts`, `purchase_orders` (with `avid_*` stubs).

**Still pending:**
| Phase | Scope | Status |
|-------|-------|--------|
| 2 | Auto reorder scheduler (`reorder_loop`) | Not started |
| 3 | AvidXchange adapter + OAuth + idempotency | Not started (needs API docs from owner) |

**Policy:** draft PO → human approve → submit (NOT auto-submit to AP).

## Shipped recently (2026-07-09)

- **Unbrand + purge SMIP customer data (v1.7.1)** — remove SMI Properties branding; empty fleet seed; one-time DB purge of carts/WO/PM/accidents/parts and former team logins; product seeds only `admin` + `mike.casady`
- **Parts module v1.7.0** — real inventory UI replaces zen placeholder; vendors; purchase orders; smoke tests

## Shipped recently (2026-07-06)

- Responsive UI fixes across phone + laptop (v1.6.3):
  - Dashboard stat cards were collapsing to a sliver with the number/label overflowing — the `<a class="stat-card">` inside `.dashboard-widget` defaulted to `display:inline`. Made the widget a flex column and its card/panel fill the cell (`dashboard_widgets.css`).
  - Fleet table now renders as stacked, labeled cards on phone (via `data-label` + `html[data-layout='phone']` CSS in `index.html`) instead of hiding Status/Actions behind horizontal scroll. Desktop still uses the normal table.
  - Admin Team Accounts rows wrap on phone so the Reset Password/Delete buttons no longer overflow the viewport (`shared.css`).
  - PM tab controls (Schedule/Templates/Automation) wrap cleanly; `.top-strip` wraps so tabs drop to their own row instead of overflowing (`pm.css`).
- Simplify dashboard widgets — remove custom website embeds; weather + NASCAR Cup only (v1.6.2)
- Phone nav as tap-friendly buttons; auto-detect phone vs laptop layout (v1.6.2)
- Fix dashboard stuck on loading — `woList` ReferenceError broke all dashboard JS (v1.6.1)
- Customizable dashboard widgets — stat cards, weather, NASCAR Cup top 10 (v1.6.0)
- Parts placeholder page — ocean zen “enjoy the zen while we build” + nav link (v1.5.4)
- Fix missing Settings button — restore `settings.js` nav injection (`injectSettingsButton`, team accounts, push) gutted in v1.5.2 (v1.5.3)

## Shipped recently (2026-07-05)

- Hidden Nokia Snake easter egg — Settings → click Dale Earnhardt #3 theme 5× quickly (v1.5.1)
- Admin database restore: `POST /api/admin/restore` with SQLite validation, integrity check, pre-restore backup, audit trail (v1.5.0)
- Open WebUI source bundle: `scripts/sync-open-webui-knowledge.ps1` + `open-webui-knowledge/` for guru code search
- Training case (open bug): theme resets on Admin — see `training/TRAINING-theme-admin-reset.md`

## Shipped recently (2026-07-04)

- `SEED_DEMO_DATA=false` by default (set `true` only for empty demo environments)
- PM Automation tab + wizard + daily scheduler
- Admin fleet CSV import + extended cart fields
- Technician/assignee dropdowns synced to live users (`/api/users/team-members`)
- Activity user filter fixed (`/api/audit/usernames`)
- Admin database backup download + `backup_database.py` for Box/laptop
- Gmail SMTP daily digest (management demo)
- Force password change on first login (`password_changed` flag)
- PM record dedup on create / Apply to Fleet
- `DEPLOY.md` updated (Admin page, SMTP, roles, backup)

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
- **Infra:** Render service `maintainsmip` + disk `maintainsmip-data` (already provisioned)

---

*Update this file when features ship, credentials change, or agent workflow rules change.*