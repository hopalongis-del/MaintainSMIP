(function () {
  const SETTINGS_KEY = 'maintainsmip-settings';
  const LEGACY_THEME_KEY = 'maintainsmip-theme';
  const CUSTOM_THEME_ID = 'custom';

  const RACING_THEMES = [
    {
      id: 'dale-earnhardt',
      name: 'Dale Earnhardt #3',
      subtitle: 'Intimidator Black',
      swatches: ['#0a0a0a', '#1f1f1f', '#c41e3a', '#c0c0c0'],
    },
    {
      id: 'jeff-gordon',
      name: 'Jeff Gordon #24',
      subtitle: 'Rainbow Warrior',
      swatches: ['#003087', '#ffd100', '#e4002b', '#00a651'],
    },
    {
      id: 'richard-petty',
      name: 'Richard Petty #43',
      subtitle: 'STP Blue & Red',
      swatches: ['#1e40af', '#dc2626', '#f8fafc', '#0f172a'],
    },
    {
      id: 'daytona-night',
      name: 'Daytona Night',
      subtitle: 'Black & Gold',
      swatches: ['#0b0b0f', '#171717', '#f5c518', '#f8fafc'],
    },
    {
      id: 'smi-racing',
      name: 'SMI Racing',
      subtitle: 'Classic RaceDay Red',
      swatches: ['#0a0e1a', '#1a1f35', '#e11d29', '#e2e8f0'],
    },
    {
      id: 'jimmie-johnson',
      name: 'Jimmie Johnson #48',
      subtitle: 'Lowe\'s Blue & Gold',
      swatches: ['#061528', '#0c2d5c', '#ffd100', '#eff6ff'],
    },
    {
      id: 'tony-stewart',
      name: 'Tony Stewart #14',
      subtitle: 'Smoke Orange',
      swatches: ['#0a0806', '#1a140f', '#f97316', '#faf5f0'],
    },
    {
      id: 'kyle-busch',
      name: 'Kyle Busch #18',
      subtitle: 'M&M Interstate',
      swatches: ['#1a0508', '#3d0f18', '#eab308', '#dc2626'],
    },
    {
      id: 'bill-elliott',
      name: 'Bill Elliott #9',
      subtitle: 'Thunderbird Red & Blue',
      swatches: ['#0a1028', '#152a5c', '#dc2626', '#2563eb'],
    },
    {
      id: 'mark-martin',
      name: 'Mark Martin #6',
      subtitle: 'Valvoline Gold',
      swatches: ['#12100a', '#2a2418', '#ca8a04', '#b91c1c'],
    },
  ];

  const DEFAULT_CUSTOM_THEME = {
    name: 'My Custom Theme',
    colors: {
      bg: '#0a0e1a',
      panel: '#1a1f35',
      accent: '#e11d29',
      text: '#e2e8f0',
    },
  };

  const THEME_CSS_VARS = [
    '--bg',
    '--panel',
    '--panel-strong',
    '--text',
    '--muted',
    '--accent',
    '--accent-2',
    '--accent-soft',
    '--accent-border',
    '--border',
    '--shadow',
    '--success',
    '--warning',
    '--bg-glow',
    '--bg-top',
    '--input-bg',
    '--modal-overlay',
    '--eyebrow-text',
    '--surface',
    '--surface-hover',
    '--surface-border',
  ];

  function parseHex(hex) {
    const raw = String(hex || '').replace('#', '').trim();
    if (raw.length === 3) {
      return raw.split('').map((ch) => ch + ch).join('');
    }
    return raw.slice(0, 6);
  }

  function hexToRgb(hex) {
    const value = parseHex(hex);
    if (value.length !== 6) return { r: 10, g: 14, b: 26 };
    return {
      r: parseInt(value.slice(0, 2), 16),
      g: parseInt(value.slice(2, 4), 16),
      b: parseInt(value.slice(4, 6), 16),
    };
  }

  function rgbToHex(r, g, b) {
    return `#${[r, g, b]
      .map((channel) => Math.round(Math.max(0, Math.min(255, channel))).toString(16).padStart(2, '0'))
      .join('')}`;
  }

  function mixHex(a, b, weight) {
    const source = hexToRgb(a);
    const target = hexToRgb(b);
    const ratio = Math.max(0, Math.min(1, weight));
    return rgbToHex(
      source.r * (1 - ratio) + target.r * ratio,
      source.g * (1 - ratio) + target.g * ratio,
      source.b * (1 - ratio) + target.b * ratio,
    );
  }

  function darken(hex, amount) {
    return mixHex(hex, '#000000', amount);
  }

  function lighten(hex, amount) {
    return mixHex(hex, '#ffffff', amount);
  }

  function rgbaHex(hex, alpha) {
    const { r, g, b } = hexToRgb(hex);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function normalizeCustomTheme(customTheme) {
    const base = customTheme && typeof customTheme === 'object' ? customTheme : {};
    const colors = base.colors && typeof base.colors === 'object' ? base.colors : {};
    return {
      name: String(base.name || DEFAULT_CUSTOM_THEME.name).trim() || DEFAULT_CUSTOM_THEME.name,
      colors: {
        bg: colors.bg || DEFAULT_CUSTOM_THEME.colors.bg,
        panel: colors.panel || DEFAULT_CUSTOM_THEME.colors.panel,
        accent: colors.accent || DEFAULT_CUSTOM_THEME.colors.accent,
        text: colors.text || DEFAULT_CUSTOM_THEME.colors.text,
      },
    };
  }

  function buildCssVarsFromPalette(colors) {
    const palette = normalizeCustomTheme({ colors }).colors;
    const { bg, panel, accent, text } = palette;
    const panelStrong = darken(panel, 0.14);
    const accent2 = lighten(accent, 0.12);
    const muted = mixHex(text, bg, 0.45);
    const bgTop = lighten(bg, 0.08);
    const eyebrow = lighten(accent, 0.42);

    return {
      '--bg': bg,
      '--panel': panel,
      '--panel-strong': panelStrong,
      '--text': text,
      '--muted': muted,
      '--accent': accent,
      '--accent-2': accent2,
      '--accent-soft': rgbaHex(accent, 0.18),
      '--accent-border': rgbaHex(accent, 0.3),
      '--border': rgbaHex(text, 0.1),
      '--shadow': '0 22px 45px rgba(0, 0, 0, 0.42)',
      '--success': '#34d399',
      '--warning': '#fbbf24',
      '--bg-glow': rgbaHex(accent, 0.14),
      '--bg-top': bgTop,
      '--input-bg': rgbaHex(darken(panel, 0.06), 0.96),
      '--modal-overlay': rgbaHex(darken(bg, 0.04), 0.82),
      '--eyebrow-text': eyebrow,
      '--surface': rgbaHex(text, 0.05),
      '--surface-hover': rgbaHex(text, 0.08),
      '--surface-border': rgbaHex(text, 0.1),
    };
  }

  // All presets with CSS in shared.css — keep in sync when adding themes.
  const PRESET_THEME_IDS = new Set(RACING_THEMES.map((theme) => theme.id));

  function isPresetTheme(themeId) {
    return PRESET_THEME_IDS.has(themeId);
  }

  function resolveThemeId(themeId, customTheme) {
    if (themeId === CUSTOM_THEME_ID && customTheme) return CUSTOM_THEME_ID;
    if (themeId && PRESET_THEME_IDS.has(themeId)) return themeId;
    return 'smi-racing';
  }

  function clearCustomThemeVars(root) {
    THEME_CSS_VARS.forEach((name) => root.style.removeProperty(name));
  }

  function applyCustomThemeVars(root, customTheme) {
    const vars = buildCssVarsFromPalette(normalizeCustomTheme(customTheme).colors);
    Object.entries(vars).forEach(([name, value]) => root.style.setProperty(name, value));
  }

  function readBootSettings() {
    try {
      const raw = localStorage.getItem(SETTINGS_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        return {
          theme: parsed.theme || localStorage.getItem(LEGACY_THEME_KEY) || 'smi-racing',
          layout: parsed.layout === 'phone' ? 'phone' : 'laptop',
          customTheme: parsed.customTheme || null,
        };
      }
    } catch (err) {
      /* ignore malformed settings */
    }

    const legacyTheme = localStorage.getItem(LEGACY_THEME_KEY);
    return {
      theme: legacyTheme || 'smi-racing',
      layout: 'laptop',
      customTheme: null,
    };
  }

  function applyDocumentTheme(settings = readBootSettings()) {
    const root = document.documentElement;
    const theme = resolveThemeId(settings.theme, settings.customTheme);
    const layout = settings.layout === 'phone' ? 'phone' : 'laptop';

    root.setAttribute('data-theme', theme);
    root.setAttribute('data-layout', layout);

    if (theme === CUSTOM_THEME_ID) {
      applyCustomThemeVars(root, settings.customTheme);
    } else {
      clearCustomThemeVars(root);
    }
  }

  window.MaintainSMIPThemes = {
    RACING_THEMES,
    CUSTOM_THEME_ID,
    DEFAULT_CUSTOM_THEME,
    THEME_CSS_VARS,
    normalizeCustomTheme,
    buildCssVarsFromPalette,
    isPresetTheme,
    resolveThemeId,
    applyDocumentTheme,
    readBootSettings,
  };

  applyDocumentTheme(readBootSettings());
})();