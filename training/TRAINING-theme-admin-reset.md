# Training case: theme resets on Admin tab

**Status:** Open — for `maintainsmip-guru` to diagnose and fix. Do not read the answer key until you have a proposed fix.

## Reported behavior

1. Open MaintainSMIP dashboard — Settings shows **10** racing themes (+ custom).
2. Select **Mark Martin** — theme applies correctly.
3. Navigate to **Admin** tab — theme reverts to default (SMI Racing).
4. Open Settings again — only **5** themes listed.

## Your job

1. Search **`MaintainSMIP-Source`** knowledge (or local `C:\MaintainSMIP`) — read `settings.js`, `themes.js`, `admin.html`, `index.html`.
2. Find the **root cause** in code (not guesses from HANDOFF alone).
3. Propose a minimal fix.
4. If you can run shell: implement, bump `APP_VERSION`, update `HANDOFF.md`, run `python test_smoke.py`, commit.

## Hints (only if stuck)

- Themes are stored in **localStorage** (`maintainsmip-settings`, `maintainsmip-theme`).
- Preset themes are defined in **`themes.js`**; settings UI in **`settings.js`**.
- Compare script tags and load order on **index.html** vs **admin.html**.
- Check `applySettings`, `applyDocumentTheme`, `resolveThemeId`, `buildThemeOptions`.
- Consider **browser cache** of `.js` files across page navigations.

## Success criteria

- Mark Martin (or any of the 10 presets) persists after visiting Admin.
- Settings always shows all presets + custom slot.
- No regression on smoke tests.

---

## Answer key

See `training/TRAINING-theme-admin-reset.ANSWER.md` (instructor / after attempt).