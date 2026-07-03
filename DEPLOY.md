# Deploy MaintainSMIP to Render (~$7/mo)

## 1. Push to GitHub

```powershell
cd "C:\Claude Code"
git init
git add .
git commit -m "MaintainSMIP demo ready for Render"
```

Repo: **https://github.com/hopalongis-del/MaintainSMIP**

Push updates:

```powershell
cd "C:\Claude Code"
git add .
git commit -m "Your message here"
git push origin main
```

## 2. Deploy on Render

1. Go to [render.com](https://render.com) and sign up (GitHub login is easiest).
2. **New** → **Blueprint** → connect your GitHub repo.
3. Render reads `render.yaml` automatically.
4. Confirm the **Starter** plan (~$7/mo, always on — no cold starts).
5. In the Blueprint review screen, set these **secret** environment variables (they are not stored in git):
   - `APP_PASSWORD` — demo sign-in password (e.g. `WeLoveRacing!`)
   - `APP_SECRET` — long random string for session cookies
6. Click **Apply** and wait ~2–3 minutes for the build.

Your URL will look like: `https://maintainsmip.onrender.com`

### Persistent data (Phase 0)

`render.yaml` attaches a **5 GB disk** at `/var/data`. The app stores:

- SQLite database: `/var/data/maintainsmip.db`
- Accident photo uploads: `/var/data/uploads/accidents/`

Work orders, PM records, accidents, and uploaded photos **survive redeploys** as long as you do not delete the disk.

Verify after deploy:

```text
GET https://maintainsmip.onrender.com/api/health
```

Look for `"persistent_storage": true` and `"db_exists": true`.

**Do not delete** the `maintainsmip-data` disk in Render unless you intend to wipe all live data.

## 3. Before the management demo

- Open the URL on your phone (cellular, not home Wi‑Fi) to confirm it loads.
- Click through Dashboard, Work Orders, and PM once.
- PM templates seed automatically on first boot; add a work order if you want more on-screen data.

## 4. When you're done

Render dashboard → your service → **Settings** → **Delete Web Service** (billing stops).

## Local dev (unchanged)

```powershell
cd "C:\Claude Code"
.\start.bat
```

Then open `http://localhost:8000`