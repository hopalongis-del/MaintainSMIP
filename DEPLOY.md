# Deploy MaintainSMIP to Render (~$7/mo)

## 1. Push to GitHub

```powershell
cd "C:\Claude Code"
git init
git add .
git commit -m "MaintainSMIP demo ready for Render"
```

Create a new repo on GitHub (e.g. `maintainsmip`), then:

```powershell
git remote add origin https://github.com/YOUR_USER/maintainsmip.git
git branch -M main
git push -u origin main
```

## 2. Deploy on Render

1. Go to [render.com](https://render.com) and sign up (GitHub login is easiest).
2. **New** → **Blueprint** → connect your GitHub repo.
3. Render reads `render.yaml` automatically.
4. Confirm the **Starter** plan (~$7/mo, always on — no cold starts).
5. Click **Apply** and wait ~2–3 minutes for the build.

Your URL will look like: `https://maintainsmip.onrender.com`

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