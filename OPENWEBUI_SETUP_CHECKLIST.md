# Open WebUI setup checklist — stop "I need the code" responses

## Diagnosed on your machine (2026-07-05)

Open WebUI database shows **MaintainSMIP knowledge has only 3 files**:

- `DEPLOY.md`, `HANDOFF.md`, `MODEL_UPDATES.md`

**No `settings.js`, `server.py`, or `CODEBASE_DIGEST.md`.** The model is right that knowledge has no code — you never uploaded it. Fix below.

Run diagnostic anytime:

```powershell
& "$env:APPDATA\open-webui\python\python.exe" C:\MaintainSMIP\scripts\inspect-open-webui-db.py
```

---

If maintainsmip-guru says it can't access code, **one of these is missing**. Fix all six.

## 1. Rebuild the model (after prompt changes)

```powershell
cd C:\MaintainSMIP
.\ollama\build.ps1
```

Restart Open WebUI or refresh model list. Use **maintainsmip-guru** (not raw Ornith).

## 2. Sync and upload SOURCE (not just docs)

```powershell
cd C:\MaintainSMIP
.\scripts\sync-open-webui-knowledge.ps1
```

Open WebUI → **Workspace → Knowledge → MaintainSMIP-Source**

Upload **entire** `C:\MaintainSMIP\open-webui-knowledge\` folder.

**Must include:** `CODEBASE_DIGEST.md`, `settings.js`, `themes.js`, `server.py`

**Do NOT upload only:** HANDOFF.md, DEPLOY.md (that's docs-only — guru will refuse correctly)

## 3. Attach knowledge ON THE CHAT (most common miss)

Starting a new chat is not enough. Per chat:

1. **Chat controls** (slider icon or `#` menu)
2. **Knowledge** → enable **MaintainSMIP-Source** AND **MaintainSMIP**
3. Confirm files appear in the collection before asking code questions

Save as preset **MaintainSMIP Dev** with both collections pre-attached.

## 4. Enable Open Terminal (local disk access)

Desktop app: **Settings → Open Terminal → Enabled**

Working directory: **`C:\MaintainSMIP`** (already set in config if you use Grok Open WebUI desktop)

The guru can run: `Get-Content settings.js`, `Select-String -Path server.py -Pattern audit`

## 5. Enable tool calling for the model

Chat → Model settings → ensure **Tools / Functions** are ON for maintainsmip-guru.

Ornith supports tools — if tools are off, the model can only talk, not search.

## 6. Import MaintainSMIP Source Reader tool (belt + suspenders)

Like your logistics guru's Excel/Fleet tools — gives the model **deterministic** disk + GitHub reads.

1. Open WebUI → **Workspace → Tools → Import**
2. Import `C:\MaintainSMIP\open-webui-tools\maintainsmip_source.py`
3. **Workspace → Models → MaintainSMIP** → enable tool **MaintainSMIP Source Reader**
4. Save model

Tools exposed: `list_source_files`, `read_local_file`, `grep_local`, `fetch_github_file`

The tool description tells the model it **must** call these before claiming no access.

---

## Test prompt (should show tool calls, not excuses)

```text
Who can see the Activity tab? Use grep_knowledge_files on CODEBASE_DIGEST.md for require_authenticated_user and injectActivityNavLink. Do not answer until you view the code.
```

**Pass:** tool call to `grep_local` or `read_local_file`, then cites `server.py` + `require_authenticated_user`  
**Fail:** "I need access to source code" → source not uploaded, Source Reader tool not attached, or tools off

---

## GitHub fallback (no upload needed)

Repo is public. Guru can fetch:

- https://raw.githubusercontent.com/hopalongis-del/MaintainSMIP/main/settings.js

Prompt must include tool use — rebuilt prompt bans "I need the code" without trying tools first.