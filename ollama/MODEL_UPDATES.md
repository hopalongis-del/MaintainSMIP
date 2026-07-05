# maintainsmip-guru — How and Where to Update Everything

This folder (`C:\MaintainSMIP\ollama\`) owns the local AI model. Use this guide when rules, base model, or project context change.

---

## File map

| File | Purpose | Edit when… |
|------|---------|------------|
| **`SYSTEM_PROMPT.md`** | Canonical system prompt (source of truth) | Rules, workflow, architecture facts, or tone change |
| **`Modelfile`** | Ollama model recipe (auto-generated) | **Do not edit by hand** — run `build.ps1` |
| **`build.ps1`** | Rebuilds Modelfile + runs `ollama create` | Build script itself breaks |
| **`MODEL_UPDATES.md`** | This guide | You add a new place that needs syncing |

Related files **outside** this folder:

| File | Purpose | Edit when… |
|------|---------|------------|
| `HANDOFF.md` | Full project state, credentials, pending work | Features ship, passwords change, workflow changes |
| `OPENWEBUI.md` | Open WebUI setup overview | Setup steps change |
| `DEPLOY.md` | Render infra reference | Env vars, disk, deploy process changes |
| `settings.js` → `APP_VERSION` | UI/cache-bust version | Any shipped frontend change |
| `smi_events.js` | 2026 event dropdown list | Schedule changes (from Logistics Guru export) |
| `themes.js` | Preset racing themes | New theme presets added |

Open WebUI (not in repo):

| Place | Purpose | Edit when… |
|-------|---------|------------|
| **Knowledge → MaintainSMIP collection** | RAG context for chats | `HANDOFF.md`, `DEPLOY.md`, or prompt docs change |
| **Preset "MaintainSMIP Dev"** | Saved chat + model + knowledge | Model name or knowledge collection changes |

---

## Update workflows

### A. Change what the model knows (rules, paths, hard rules)

1. Edit **`ollama/SYSTEM_PROMPT.md`** — only the text **below the `---` line**.
2. Run rebuild:

   ```powershell
   cd C:\MaintainSMIP
   .\ollama\build.ps1
   ```

3. In Open WebUI, start a **new chat** with `maintainsmip-guru` (existing chats keep old context).
4. If project facts also changed, update **`HANDOFF.md`** and re-upload to the Open WebUI Knowledge collection.

### B. Change base model (e.g. different Ornith quant or fallback)

1. Edit the `FROM` line at the top of **`ollama/build.ps1`** (variable `$BaseModel`) or the generated `Modelfile` template section in `build.ps1`.
2. Adjust `PARAMETER` values in `build.ps1` if needed (`$Parameters` block).
3. Run `.\ollama\build.ps1`.
4. Confirm: `ollama show maintainsmip-guru`

Current default base: `maxwell1500/ornith-35b:IQ3_M`

### C. Ship a code change to production (the app, not the model)

This is separate from the Ollama model. Follow **`HANDOFF.md`** ship loop:

```powershell
cd C:\MaintainSMIP
python test_smoke.py
git add <files>
git commit -m "..."
git push origin main
```

Then verify `https://maintainsmip.onrender.com/api/health`.

Bump **`APP_VERSION`** in `settings.js` when you change HTML/CSS/JS.

### D. Update Open WebUI knowledge (RAG)

When any of these change, re-upload to the **MaintainSMIP** knowledge collection:

- `HANDOFF.md`
- `DEPLOY.md`
- `OPENWEBUI.md`
- `ollama/SYSTEM_PROMPT.md`
- `ollama/MODEL_UPDATES.md`

Steps: Open WebUI → **Workspace** → **Knowledge** → **MaintainSMIP** → delete old file → upload new version (or use collection sync if configured).

### E. Update HANDOFF for other agents (Cursor, Grok, etc.)

`HANDOFF.md` is shared context. When you update:

- Local path → `C:\MaintainSMIP`
- App version
- Pending work / shipped features
- Credentials (careful — file is in git)

Commit and push HANDOFF so GitHub and other tools stay aligned:

```powershell
git add HANDOFF.md
git commit -m "Update HANDOFF"
git push origin main
```

---

## Rebuild command reference

```powershell
# Full rebuild (Modelfile + ollama create)
cd C:\MaintainSMIP
.\ollama\build.ps1

# Manual equivalent
ollama create maintainsmip-guru -f ollama\Modelfile

# Verify
ollama show maintainsmip-guru
ollama list | findstr maintainsmip
```

---

## Quick test after any model update

In Open WebUI, new chat with **maintainsmip-guru**:

```text
What is the project root, current APP_VERSION location, and standard ship loop?
```

Expected:

- Root: `C:\MaintainSMIP`
- Version: from `settings.js`
- Loop: `test_smoke.py` → `git push origin main` → health check

---

## What NOT to sync into the model prompt

Keep these out of `SYSTEM_PROMPT.md` (they belong in HANDOFF only or nowhere in git):

- Rotating production secrets
- Full credential tables (point to HANDOFF instead)
- Huge file contents or CSV data

---

## Checklist: "I changed something — what do I update?"

| I changed… | Update | Rebuild model? | Re-upload knowledge? | Git push? |
|------------|--------|----------------|----------------------|-----------|
| Agent rules / tone | `SYSTEM_PROMPT.md` | Yes (`build.ps1`) | Optional | Yes |
| Base LLM | `build.ps1` `$BaseModel` | Yes | No | Yes |
| Credentials / pending work | `HANDOFF.md` | No | Yes | Yes |
| Render env / disk | `DEPLOY.md` | No | Yes | Yes |
| 2026 events list | `smi_events.js` | No | No | Yes (+ bump APP_VERSION) |
| New racing theme | `themes.js` + `shared.css` | No | No | Yes (+ bump APP_VERSION) |
| UI/settings behavior | code + `HANDOFF.md` + `APP_VERSION` bump | No | If HANDOFF changed | Yes |
| Any production ship | `HANDOFF.md` + version per `SYSTEM_PROMPT.md` | No | Re-upload HANDOFF | Yes |