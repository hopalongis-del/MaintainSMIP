# MaintainSMIP + Open WebUI Setup

Purpose-built local AI for MaintainSMIP development — like `monday-guru` and `logistics-guru`, but for this app.

---

## 1. Project location

All work happens in **`C:\MaintainSMIP`** (migrated from `C:\Claude Code`).

```powershell
cd C:\MaintainSMIP
.\install.bat    # first time
.\start.bat      # http://localhost:8000
python test_smoke.py
```

---

## 2. Recommended model: `maintainsmip-guru`

| | |
|---|---|
| **Base** | `maxwell1500/ornith-35b:IQ3_M` (15 GB) |
| **Why** | Ornith is coding/agentic-tuned (MoE 35B) — reads code first, minimal diffs, error recovery |
| **Ollama name** | `maintainsmip-guru:latest` |

### Build it (one time)

```powershell
cd C:\MaintainSMIP
ollama create maintainsmip-guru -f ollama\Modelfile
```

### Alternatives

| Model | Size | When to use |
|-------|------|-------------|
| `maxwell1500/ornith-35b:IQ3_M` | 15 GB | **Default** — agentic coding, tools + thinking |
| `qwen2.5-coder:14b` | 9 GB | Lighter fallback if VRAM is tight |
| `qwen2.5:32b` | 19 GB | Same family as logistics-guru / monday-guru |

To rebuild on a different base, edit `ollama/Modelfile` line 1 (`FROM ...`) and run `ollama create` again.

---

## 3. Open WebUI configuration

### Create the model in Open WebUI

1. Open Open WebUI → **Workspace** → **Models**
2. You should see **maintainsmip-guru** after `ollama create` (Ollama sync)
3. If not: **Admin** → **Connections** → confirm Ollama URL is `http://127.0.0.1:11434`

### Create a dedicated chat / workspace

1. **New Chat** → select model **maintainsmip-guru**
2. **Workspace** → **Knowledge** → **Create Collection** named `MaintainSMIP`
3. Upload these files to the collection:
   - `HANDOFF.md`
   - `OPENWEBUI.md`
   - `DEPLOY.md`
   - `ollama/Modelfile` (optional — shows the agent rules)
4. In chat settings, attach the **MaintainSMIP** knowledge collection
5. Pin this as a favorite or save as a **Preset** named "MaintainSMIP Dev"

### Suggested preset system add-on (optional)

If Open WebUI lets you add a per-chat system message on top of the model, paste:

```text
Read HANDOFF.md from knowledge before coding. Work in C:\MaintainSMIP. Run test_smoke.py before every push.
```

---

## 4. What the local model can vs cannot do

| Can do well | Needs help |
|-------------|------------|
| Explain codebase, suggest patches | Auto-apply edits without a code tool |
| Write Modelfile / HANDOFF updates | Push to GitHub unless shell tool enabled |
| Debug from pasted errors/logs | Full Cursor-style agent loop out of the box |
| Plan features, review diffs | Browse production without you pasting output |

**For full autonomy** (edit → test → commit → push like today), pair Open WebUI with:
- **Code execution / terminal tool** (if enabled in your Open WebUI build), or
- Keep Cursor/Grok for deploys and use **maintainsmip-guru** for planning, patches, and HANDOFF updates.

---

## 5. Quick test prompt

After setup, try:

```text
Read HANDOFF.md. What is the current APP_VERSION, where is the project root, and what is the standard ship loop?
```

Expected: mentions `C:\MaintainSMIP`, `test_smoke.py`, `git push origin main`, Render health check.

---

## 6. Updating the guru

When HANDOFF.md or architecture changes materially:

1. Edit `ollama/Modelfile` SYSTEM block if rules changed
2. `ollama create maintainsmip-guru -f ollama\Modelfile`
3. Re-upload changed docs to the Open WebUI Knowledge collection