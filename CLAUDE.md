# MaintainSMIP — agent guide

SMI Properties fleet-maintenance web app (FastAPI + SQLite + vanilla JS), deployed
on Render from `main`. Full onboarding, architecture, credentials location, and
pending work live in **`handoff.md`** — read it first.

## Credential policy (READ THIS — non-negotiable)

Secrets are worked on by AI often, so the rule is simple: **AI works with secret
*references*, never secret *values*.**

1. **Never read secret files.** Do not open, `cat`, `type`, or otherwise print
   `.env`, `.env.*` (except `.env.example`), `vapid_keys.json`, anything under
   `secrets/`, or `*.pem` / `*.key`. Local `.claude/settings.json` also blocks
   these via `permissions.deny`, but treat the rule as binding even where the
   block doesn't reach (e.g. `Bash`/PowerShell). Do not dump the process
   environment (`printenv`, `env`, `Get-ChildItem Env:`, `os.environ` printing)
   to read secret values.

2. **Read secrets only from the environment, with NO hardcoded fallback.**
   New secret-backed config must be `os.environ["NAME"]` (fail loud if missing) —
   never `os.environ.get("NAME", "some-default")`. A default value IS a committed
   secret. (The existing `APP_SECRET` / `APP_PASSWORD` fallbacks in `server.py`
   predate this rule; leave them unless explicitly asked to rotate.)

3. **Real values live in exactly two places:** the Render dashboard (production)
   and, if truly needed, a gitignored local `.env` on a trusted machine that only
   the owner's local model touches. They must never enter the repo, code,
   handoff.md, chat, or committed config.

4. **New env vars → add the NAME to `.env.example`** (no value) so the next
   session knows to wire it up.

5. **If a secret is ever exposed** (seen by a cloud AI, committed, pasted): treat
   it as burned — rotate it and update Render. Note it in `handoff.md`.

## AvidXchange parts/procurement module

In progress, **local only — do not deploy until Brian signs off** (see handoff.md).
The adapter reads `AVID_*` env vars only; build and test against a MockAdapter so
real AvidXchange creds are never required to develop.

## Ship loop

`python test_smoke.py` must print `ALL TESTS PASSED` before any commit. Stage only
intentional files (never secrets or large CSVs). Push to `main` deploys to Render.
Update `handoff.md` whenever features ship, credentials location changes, or agent
rules change. PowerShell: use `;` not `&&`.
