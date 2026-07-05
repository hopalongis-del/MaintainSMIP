# Answer key: theme resets on Admin tab

## Root cause

Two issues combine:

### 1. `applySettings` passes unresolved theme to `applyDocumentTheme`

In `settings.js`, `applySettings` computes `theme = resolveThemeId(...)` for UI toggles but calls:

```javascript
applyDocumentTheme({ theme: settings.theme, layout, customTheme: settings.customTheme });
```

It should pass the **resolved** `theme` variable. When `settings.theme` is `mark-martin` but a stale `resolveThemeId` / theme list rejects it, `applyDocumentTheme` re-resolves and may fall back to `smi-racing`.

### 2. Browser cache serves stale `settings.js` (5 inline themes) on some pages

Older `settings.js` had only **5** presets baked in. Newer code splits **10** presets into `themes.js`. After deploying, users can have:

- New `index.html` + `themes.js` → 10 themes work
- Cached old `settings.js` on navigation → `buildThemeOptions` shows 5; `mark-martin` invalid → reset

**Fix:** bump `APP_VERSION` and `?v=` on all HTML script tags; pass resolved theme in `applySettings`; optional stale-script banner if `MaintainSMIPThemes` missing.

## Files to change

- `settings.js` — `applyDocumentTheme({ theme, ... })` not `settings.theme`; guard if `!window.MaintainSMIPThemes`
- All `*.html` — sync `?v=APP_VERSION` on `themes.js`, `settings.js`, `shared.css`, `db.js`
- `HANDOFF.md` — version + shipped note

## Verify

1. Hard-refresh production once after deploy.
2. Select Mark Martin → Admin → theme still Mark Martin.
3. Settings shows 11 theme cards (10 + custom).