# MaintainSMIP source bundle for Open WebUI

Open WebUI **cannot read `C:\MaintainSMIP` on its own**. Upload this folder to a Knowledge collection so `maintainsmip-guru` can answer from real code.

## Setup (one time)

1. Open WebUI → **Workspace** → **Knowledge** → **Create Collection**
2. Name it **`MaintainSMIP-Source`**
3. Upload **all files** in this folder (after each sync)

Keep **`MaintainSMIP`** collection for HANDOFF.md only (living docs).

## Refresh after code changes

```powershell
cd C:\MaintainSMIP
.\scripts\sync-open-webui-knowledge.ps1
```

Then re-upload changed files to the **MaintainSMIP-Source** collection in Open WebUI (delete old copy first, or replace).

## What gets synced

Frontend: `settings.js`, `themes.js`, `db.js`, `admin.js`, key HTML pages  
Backend: `server.py` (API auth, audit, themes static paths)  
Docs: `HANDOFF.md` snapshot for cross-reference