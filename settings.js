const APP_VERSION = '1.9.0';
const APP_NAME = 'Fleet Maintain';
const LEGACY_THEME_KEY = 'maintainsmip-theme';
const SETTINGS_KEY = 'maintainsmip-settings';

const {
  RACING_THEMES,
  CUSTOM_THEME_ID,
  DEFAULT_CUSTOM_THEME,
  normalizeCustomTheme,
  resolveThemeId,
  applyDocumentTheme,
} = window.MaintainSMIPThemes;

const TECHNICIAN_FALLBACK = [
  'Mike',
];

let cachedTeamAssignees = null;

async function loadTeamAssignees() {
  if (typeof db === 'undefined') return TECHNICIAN_FALLBACK.map((display_name) => ({ display_name }));
  try {
    const members = await db.getTeamMembers();
    if (Array.isArray(members) && members.length) {
      cachedTeamAssignees = members;
      return members;
    }
  } catch (err) {
    /* fallback below */
  }
  cachedTeamAssignees = TECHNICIAN_FALLBACK.map((display_name) => ({ display_name, role: 'technician' }));
  return cachedTeamAssignees;
}

function getTeamAssigneeNames() {
  const members = cachedTeamAssignees || [];
  return members.map((member) => member.display_name).filter(Boolean);
}

async function populateAssigneeSelect(selectEl, { includeUnassigned = true, selected = '' } = {}) {
  if (!selectEl) return;
  const members = await loadTeamAssignees();
  const options = members
    .map((member) => `<option value="${member.display_name}">${member.display_name}</option>`)
    .join('');
  selectEl.innerHTML = `${includeUnassigned ? '<option value="">— Unassigned —</option>' : ''}${options}`;
  if (selected) selectEl.value = selected;
}

const DEFAULT_SETTINGS = {
  theme: 'smi-racing',
  customTheme: null,
  layout: 'laptop',
  layoutMode: 'auto',
  shopName: 'Fleet Shop',
  defaultLocation: '',
  defaultMechanic: '',
  defaultLandingPage: 'index.html',
  dateFormat: 'us',
  pmDueWindowDays: 7,
  defaultFleetLocation: 'all',
  defaultWoTemplateId: '',
  defaultPriority: 'medium',
  defaultServiceType: 'repair',
  sessionTimeoutMinutes: 30,
  notifyOverdueWo: true,
  notifyPmDue: true,
  notifyAccidents: true,
  dashboardWidgets: [],
};

function detectDeviceType() {
  const userAgent = navigator.userAgent || navigator.vendor || window.opera || '';
  const screenWidth = window.innerWidth || document.documentElement.clientWidth || 1024;
  const isMobileUA = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/i.test(userAgent);
  const isSmallScreen = screenWidth <= 768;
  const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  if (isMobileUA || (isSmallScreen && isTouchDevice)) return 'phone';
  return 'laptop';
}

function resolveLayout(settings = getSettings()) {
  const mode = settings.layoutMode || settings.layout || 'auto';
  if (mode === 'phone' || mode === 'laptop') return mode;
  return detectDeviceType();
}

function readStoredSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) {
      const parsed = { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
      if (!parsed.layoutMode && parsed.layout) parsed.layoutMode = parsed.layout;
      return parsed;
    }
  } catch (err) {
    /* ignore malformed settings */
  }

  const legacyTheme = localStorage.getItem(LEGACY_THEME_KEY);
  if (legacyTheme) {
    return { ...DEFAULT_SETTINGS, theme: legacyTheme };
  }

  return { ...DEFAULT_SETTINGS };
}

function getSettings() {
  return readStoredSettings();
}

function saveSettings(partial) {
  const next = { ...getSettings(), ...partial };
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
  localStorage.setItem(LEGACY_THEME_KEY, next.theme);
  applySettings(next);
  syncSettingsForm(next);
  window.dispatchEvent(new CustomEvent('maintainsmip-settings-changed', { detail: next }));
  return next;
}

function applyTheme(themeId) {
  if (themeId === CUSTOM_THEME_ID) {
    saveCustomTheme({ apply: true });
    return;
  }
  const valid = RACING_THEMES.some((theme) => theme.id === themeId);
  saveSettings({ theme: valid ? themeId : DEFAULT_SETTINGS.theme });
}

function applyLayout(layoutMode) {
  const mode = layoutMode === 'phone' || layoutMode === 'laptop' ? layoutMode : 'auto';
  saveSettings({ layoutMode: mode, layout: mode === 'auto' ? resolveLayout({ layoutMode: 'auto' }) : mode });
}

function applySettings(settings = getSettings()) {
  const theme = resolveThemeId(settings.theme, settings.customTheme);
  const layout = resolveLayout(settings);

  applyDocumentTheme({ theme, layout, layoutMode: settings.layoutMode, customTheme: settings.customTheme });

  document.querySelectorAll('[data-theme-option]').forEach((button) => {
    button.classList.toggle('active', button.dataset.themeOption === theme);
  });
  const activeLayoutMode = settings.layoutMode || 'auto';
  document.querySelectorAll('[data-layout-option]').forEach((button) => {
    button.classList.toggle('active', button.dataset.layoutOption === activeLayoutMode);
  });

  document.querySelectorAll('[data-settings-shop-name]').forEach((el) => {
    el.textContent = settings.shopName || DEFAULT_SETTINGS.shopName;
  });

  const footer = document.querySelector('[data-settings-footer]');
  if (footer) {
    const shop = settings.shopName || DEFAULT_SETTINGS.shopName;
    footer.textContent = shop && shop !== 'Fleet Shop'
      ? `${APP_NAME} · ${shop}`
      : `${APP_NAME} · Fleet Maintenance`;
  }
}

function formatAppDate(value) {
  if (!value) return 'N/A';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'N/A';
  const settings = getSettings();
  if (settings.dateFormat === 'iso') {
    return date.toISOString().slice(0, 10);
  }
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: '2-digit',
    year: 'numeric',
  });
}

function getPmDueWindowDays() {
  const days = Number(getSettings().pmDueWindowDays);
  return [7, 14, 30].includes(days) ? days : DEFAULT_SETTINGS.pmDueWindowDays;
}

function isPmDueSoon(dateValue) {
  if (!dateValue) return false;
  const date = new Date(dateValue);
  const now = new Date();
  const diffDays = Math.ceil((date - now) / (1000 * 60 * 60 * 24));
  return diffDays >= 0 && diffDays <= getPmDueWindowDays();
}

function getPmDueLabel() {
  const days = getPmDueWindowDays();
  if (days === 7) return 'PM Due This Week';
  return `PM Due (Next ${days} Days)`;
}

function getCustomThemePreview(settings = getSettings()) {
  return normalizeCustomTheme(settings.customTheme || DEFAULT_CUSTOM_THEME);
}

function buildThemeOptions() {
  const customTheme = getCustomThemePreview();
  const presetHtml = RACING_THEMES.map((theme) => `
    <button type="button" class="theme-option" data-theme-option="${theme.id}">
      <span class="theme-option-top">
        <strong>${theme.name}</strong>
        <span class="theme-option-sub">${theme.subtitle}</span>
      </span>
      <span class="theme-swatches">
        ${theme.swatches.map((color) => `<span style="background:${color}"></span>`).join('')}
      </span>
    </button>
  `).join('');

  const customSwatches = [
    customTheme.colors.bg,
    customTheme.colors.panel,
    customTheme.colors.accent,
    customTheme.colors.text,
  ];

  const customHtml = `
    <button type="button" class="theme-option" data-theme-option="${CUSTOM_THEME_ID}">
      <span class="theme-option-top">
        <strong>${customTheme.name}</strong>
        <span class="theme-option-sub">Your custom colors</span>
      </span>
      <span class="theme-swatches">
        ${customSwatches.map((color) => `<span style="background:${color}"></span>`).join('')}
      </span>
    </button>
  `;

  return `${presetHtml}${customHtml}`;
}

const DALE_EARNHARDT_THEME_ID = 'dale-earnhardt';
let daleEarnhardtClickCount = 0;
let daleEarnhardtClickTimer = null;

function launchSnakeEasterEgg() {
  if (window.MaintainSMIPSnake) {
    window.MaintainSMIPSnake.open();
    return;
  }
  const script = document.createElement('script');
  script.src = `snake.js?v=${APP_VERSION}`;
  script.onload = () => window.MaintainSMIPSnake?.open();
  document.head.appendChild(script);
}

function wireDaleEarnhardtEasterEgg() {
  document.querySelectorAll(`[data-theme-option="${DALE_EARNHARDT_THEME_ID}"]`).forEach((button) => {
    if (button.dataset.daleEggWired === 'true') return;
    button.dataset.daleEggWired = 'true';
    button.addEventListener('click', () => {
      daleEarnhardtClickCount += 1;
      clearTimeout(daleEarnhardtClickTimer);
      if (daleEarnhardtClickCount >= 5) {
        daleEarnhardtClickCount = 0;
        launchSnakeEasterEgg();
        return;
      }
      daleEarnhardtClickTimer = setTimeout(() => {
        daleEarnhardtClickCount = 0;
      }, 2000);
    });
  });
}

function refreshThemeGrid() {
  const grid = document.getElementById('theme-grid');
  if (!grid) return;
  grid.innerHTML = buildThemeOptions();
  document.querySelectorAll('[data-theme-option]').forEach((button) => {
    button.addEventListener('click', () => applyTheme(button.dataset.themeOption));
  });
  wireDaleEarnhardtEasterEgg();
  const activeTheme = resolveThemeId(getSettings().theme, getSettings().customTheme);
  document.querySelectorAll('[data-theme-option]').forEach((button) => {
    button.classList.toggle('active', button.dataset.themeOption === activeTheme);
  });
}

function syncCustomThemeForm(settings = getSettings()) {
  const customTheme = getCustomThemePreview(settings);
  const setValue = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.value = value ?? '';
  };
  setValue('custom-theme-name', customTheme.name);
  setValue('custom-theme-bg', customTheme.colors.bg);
  setValue('custom-theme-panel', customTheme.colors.panel);
  setValue('custom-theme-accent', customTheme.colors.accent);
  setValue('custom-theme-text', customTheme.colors.text);
}

function collectCustomThemeFromForm() {
  const readColor = (id, fallback) => {
    const value = document.getElementById(id)?.value?.trim();
    return value || fallback;
  };
  const base = getCustomThemePreview();
  return normalizeCustomTheme({
    name: document.getElementById('custom-theme-name')?.value || base.name,
    colors: {
      bg: readColor('custom-theme-bg', base.colors.bg),
      panel: readColor('custom-theme-panel', base.colors.panel),
      accent: readColor('custom-theme-accent', base.colors.accent),
      text: readColor('custom-theme-text', base.colors.text),
    },
  });
}

function saveCustomTheme({ apply = true } = {}) {
  const customTheme = collectCustomThemeFromForm();
  saveSettings({
    customTheme,
    theme: apply ? CUSTOM_THEME_ID : getSettings().theme,
  });
  refreshThemeGrid();
  syncCustomThemeForm();
  if (apply) flashSettingsSaved();
}

function wirePasswordVisibilityToggles(root = document) {
  root.querySelectorAll('input[type="password"]').forEach((input) => {
    if (input.closest('.password-toggle-wrap') || input.dataset.passwordToggleWired === 'true') {
      return;
    }
    input.dataset.passwordToggleWired = 'true';

    const wrap = document.createElement('div');
    wrap.className = 'password-toggle-wrap';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'password-toggle-btn';
    button.textContent = 'Show';
    button.setAttribute('aria-label', 'Show password');
    button.setAttribute('aria-pressed', 'false');
    button.addEventListener('click', () => {
      const revealing = input.type === 'password';
      input.type = revealing ? 'text' : 'password';
      button.textContent = revealing ? 'Hide' : 'Show';
      button.setAttribute('aria-label', revealing ? 'Hide password' : 'Show password');
      button.setAttribute('aria-pressed', revealing ? 'true' : 'false');
    });
    wrap.appendChild(button);
  });
}

function buildSettingsModal() {
  if (document.getElementById('settings-modal')) return;

  document.body.insertAdjacentHTML('beforeend', `
    <div class="modal hidden" id="settings-modal" aria-hidden="true">
      <div class="modal-panel card settings-panel">
        <div class="modal-header">
          <div>
            <span class="eyebrow">Settings</span>
            <h2>Customize ${APP_NAME}</h2>
          </div>
          <button class="btn ghost" type="button" id="settings-close" aria-label="Close settings">Close</button>
        </div>

        <section class="settings-section">
          <h3>Appearance</h3>
          <p class="hero-sub">Racing themes and layout tuned for how you use the app.</p>
          <div class="settings-subblock">
            <h4>Racing Theme</h4>
            <div class="theme-grid" id="theme-grid">${buildThemeOptions()}</div>
          </div>
          <div class="settings-subblock">
            <h4>Build Your Own</h4>
            <p class="hero-sub">Pick four colors and we’ll generate the full theme. Save it to add “My Custom Theme” to the list above.</p>
            <form class="settings-form custom-theme-form" id="custom-theme-form">
              <label>Theme Name
                <input type="text" id="custom-theme-name" placeholder="My Custom Theme" maxlength="48" />
              </label>
              <label>Background
                <input type="color" id="custom-theme-bg" value="#0a0e1a" />
              </label>
              <label>Panel
                <input type="color" id="custom-theme-panel" value="#1a1f35" />
              </label>
              <label>Accent
                <input type="color" id="custom-theme-accent" value="#e11d29" />
              </label>
              <label>Text
                <input type="color" id="custom-theme-text" value="#e2e8f0" />
              </label>
            </form>
            <div class="custom-theme-actions">
              <button type="button" class="btn primary" id="custom-theme-save-btn">Save &amp; Apply Custom Theme</button>
              <button type="button" class="btn secondary" id="custom-theme-preview-btn">Preview Without Saving</button>
            </div>
          </div>
          <div class="settings-subblock">
            <h4>Layout</h4>
            <p class="hero-sub">Auto detects phone vs laptop. Override if the app should always use one layout.</p>
            <div class="settings-toggle-group" id="layout-toggle">
              <button type="button" class="settings-toggle" data-layout-option="auto">Auto Detect</button>
              <button type="button" class="settings-toggle" data-layout-option="phone">Phone</button>
              <button type="button" class="settings-toggle" data-layout-option="laptop">Laptop</button>
            </div>
          </div>
        </section>

        <section class="settings-section">
          <h3>Shop</h3>
          <p class="hero-sub">Defaults for your track and crew.</p>
          <form class="settings-form" id="shop-settings-form">
            <label id="settings-shop-name-field">Shop Name
              <input type="text" id="settings-shop-name" placeholder="Fleet Shop" />
            </label>
            <p class="hero-sub hidden" id="settings-shop-name-note">Only admins can change the shop name.</p>
            <label>Default Event
              <select id="settings-default-location">
                <option value="">None</option>
              </select>
            </label>
            <label>Default Mechanic
              <select id="settings-default-mechanic">
                <option value="">None</option>
                ${getTeamAssigneeNames().map((name) => `<option value="${name}">${name}</option>`).join('')}
              </select>
            </label>
          </form>
        </section>

        <section class="settings-section">
          <h3>Work Orders</h3>
          <p class="hero-sub">Pre-fill new maintenance sheets and work order headers.</p>
          <form class="settings-form" id="wo-settings-form">
            <label>Default Template
              <select id="settings-default-template">
                <option value="">Use system default</option>
              </select>
            </label>
            <label>Default Priority
              <select id="settings-default-priority">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </label>
            <label>Default Service Type
              <select id="settings-default-service-type">
                <option value="full">Full</option>
                <option value="partial">Partial</option>
                <option value="repair">Repair</option>
              </select>
            </label>
          </form>
        </section>

        <section class="settings-section">
          <h3>Fleet &amp; PM</h3>
          <p class="hero-sub">Control how fleet and preventive maintenance views behave.</p>
          <form class="settings-form" id="fleet-settings-form">
            <label>PM Due Window
              <select id="settings-pm-window">
                <option value="7">Next 7 days</option>
                <option value="14">Next 14 days</option>
                <option value="30">Next 30 days</option>
              </select>
            </label>
            <label>Default Fleet Location Filter
              <select id="settings-fleet-location">
                <option value="all">All locations</option>
              </select>
            </label>
          </form>
        </section>

        <section class="settings-section">
          <h3>Dashboard</h3>
          <p class="hero-sub">Customize widgets from the dashboard with <strong>Customize Widgets</strong>. Add weather or NASCAR Cup standings alongside the fleet stat cards.</p>
        </section>

        <section class="settings-section">
          <h3>App Behavior</h3>
          <form class="settings-form" id="behavior-settings-form">
            <label>Default Landing Page
              <select id="settings-landing-page">
                <option value="index.html">Dashboard</option>
                <option value="workorders.html">Work Orders</option>
                <option value="pm.html">Preventive Maintenance</option>
              </select>
            </label>
            <label>Date Format
              <select id="settings-date-format">
                <option value="us">Mon DD, YYYY</option>
                <option value="iso">YYYY-MM-DD</option>
              </select>
            </label>
            <label>Session Timeout
              <select id="settings-session-timeout">
                <option value="15">15 minutes</option>
                <option value="30">30 minutes</option>
                <option value="60">60 minutes</option>
                <option value="0">Never</option>
              </select>
            </label>
          </form>
        </section>

        <section class="settings-section">
          <h3>Notifications</h3>
          <p class="hero-sub" id="push-status-copy">Checking push notification status…</p>
          <div class="settings-checklist">
            <label class="settings-check-row">
              <input type="checkbox" id="settings-notify-overdue-wo" />
              <span>Overdue work order alerts</span>
            </label>
            <label class="settings-check-row">
              <input type="checkbox" id="settings-notify-pm-due" />
              <span>PM due reminders</span>
            </label>
            <label class="settings-check-row">
              <input type="checkbox" id="settings-notify-accidents" />
              <span>New accident damage reports</span>
            </label>
          </div>
          <div class="settings-form" style="margin-top: 12px;">
            <button type="button" class="btn primary" id="enable-push-btn">Enable Push Notifications</button>
            <button type="button" class="btn secondary hidden" id="disable-push-btn">Turn Off Push</button>
            <button type="button" class="btn ghost hidden" id="test-push-btn">Send Test Alert</button>
            <p class="hero-sub" id="push-action-status"></p>
          </div>
        </section>

        <section class="settings-section" id="account-settings-section">
          <h3>Account</h3>
          <p class="hero-sub" id="account-signed-in-copy">Signed in as —</p>
          <form id="change-password-form" class="settings-form">
            <h4>Change Password</h4>
            <label>Current Password
              <input type="password" id="settings-current-password" placeholder="Enter current password" autocomplete="current-password" required />
            </label>
            <label>New Password
              <input type="password" id="settings-new-password" placeholder="At least 8 characters" autocomplete="new-password" minlength="8" required />
            </label>
            <label>Confirm New Password
              <input type="password" id="settings-confirm-password" placeholder="Confirm new password" autocomplete="new-password" minlength="8" required />
            </label>
            <button class="btn secondary" type="submit" id="settings-save-password">Save Password</button>
            <p class="hero-sub" id="settings-password-status"></p>
          </form>
        </section>

        <section class="settings-section">
          <h3>About</h3>
          <div class="settings-about">
            <p><strong>Version</strong> <span id="settings-app-version">${APP_VERSION}</span></p>
            <p class="hero-sub">${APP_NAME} · Golf cart fleet maintenance.</p>
          </div>
        </section>

        <div class="settings-save-bar">
          <span class="settings-save-status" id="settings-save-status">Settings save automatically.</span>
        </div>
      </div>
    </div>

  `);
}

function userIsAdmin() {
  const user = window.__currentUser || db?.getCachedUser?.();
  return user?.role === 'admin';
}

function syncShopNameAccess() {
  const isAdmin = userIsAdmin();
  const input = document.getElementById('settings-shop-name');
  const note = document.getElementById('settings-shop-name-note');
  if (!input) return;
  input.disabled = !isAdmin;
  input.classList.toggle('readonly-field', !isAdmin);
  if (note) note.classList.toggle('hidden', isAdmin);
}

function populateDefaultEventOptions(selected = '') {
  const select = document.getElementById('settings-default-location');
  if (!select || !window.MaintainSMIPEvents) return;
  const options = window.MaintainSMIPEvents.getSmiEventOptions();
  const current = selected || getSettings().defaultLocation || '';
  select.innerHTML = `
    <option value="">None</option>
    ${options.map((event) => `<option value="${event.value.replace(/"/g, '&quot;')}">${event.label}</option>`).join('')}
  `;
  if (current && !options.some((event) => event.value === current)) {
    const legacy = document.createElement('option');
    legacy.value = current;
    legacy.textContent = `${current} (saved)`;
    select.appendChild(legacy);
  }
  select.value = current;
}

function syncSettingsForm(settings = getSettings()) {
  const setValue = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.value = value ?? '';
  };
  const setChecked = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.checked = Boolean(value);
  };

  setValue('settings-shop-name', settings.shopName);
  populateDefaultEventOptions(settings.defaultLocation);
  syncShopNameAccess();
  setValue('settings-default-mechanic', settings.defaultMechanic);
  setValue('settings-default-template', settings.defaultWoTemplateId);
  setValue('settings-default-priority', settings.defaultPriority);
  setValue('settings-default-service-type', settings.defaultServiceType);
  setValue('settings-pm-window', String(settings.pmDueWindowDays));
  setValue('settings-fleet-location', settings.defaultFleetLocation || 'all');
  setValue('settings-landing-page', settings.defaultLandingPage);
  setValue('settings-date-format', settings.dateFormat);
  setValue('settings-session-timeout', String(settings.sessionTimeoutMinutes));
  setChecked('settings-notify-overdue-wo', settings.notifyOverdueWo);
  setChecked('settings-notify-pm-due', settings.notifyPmDue);
  setChecked('settings-notify-accidents', settings.notifyAccidents);
  syncCustomThemeForm(settings);
}

async function populateSettingsDynamicOptions() {
  populateDefaultEventOptions();
  const fleetSelect = document.getElementById('settings-fleet-location');
  const templateSelect = document.getElementById('settings-default-template');

  let locations = [];
  const carts = window.cartData || (typeof cartData !== 'undefined' ? cartData : []);
  if (Array.isArray(carts) && carts.length) {
    locations = Array.from(new Set(carts.map((cart) => cart.location).filter(Boolean))).sort();
  } else if (typeof db !== 'undefined') {
    try {
      const loaded = await db.getCarts();
      locations = Array.from(new Set(loaded.map((cart) => cart.location).filter(Boolean))).sort();
    } catch (err) {
      /* settings can open before fleet loads */
    }
  }

  if (fleetSelect) {
    const current = getSettings().defaultFleetLocation || 'all';
    fleetSelect.innerHTML = `
      <option value="all">All locations</option>
      ${locations.map((loc) => `<option value="${loc}">${loc}</option>`).join('')}
    `;
    fleetSelect.value = current;
  }

  if (templateSelect && typeof db !== 'undefined') {
    try {
      const templates = await db.getWoTemplates();
      const current = getSettings().defaultWoTemplateId || '';
      templateSelect.innerHTML = `
        <option value="">Use system default</option>
        ${templates.map((template) => `<option value="${template.id}">${template.name}</option>`).join('')}
      `;
      templateSelect.value = current;
    } catch (err) {
      /* templates load when API is ready */
    }
  }
}

function collectSettingsFromForm() {
  const current = getSettings();
  return {
    shopName: userIsAdmin()
      ? (document.getElementById('settings-shop-name')?.value.trim() || DEFAULT_SETTINGS.shopName)
      : current.shopName,
    defaultLocation: document.getElementById('settings-default-location')?.value.trim() || '',
    defaultMechanic: document.getElementById('settings-default-mechanic')?.value || '',
    defaultWoTemplateId: document.getElementById('settings-default-template')?.value || '',
    defaultPriority: document.getElementById('settings-default-priority')?.value || DEFAULT_SETTINGS.defaultPriority,
    defaultServiceType: document.getElementById('settings-default-service-type')?.value || DEFAULT_SETTINGS.defaultServiceType,
    pmDueWindowDays: Number(document.getElementById('settings-pm-window')?.value || DEFAULT_SETTINGS.pmDueWindowDays),
    defaultFleetLocation: document.getElementById('settings-fleet-location')?.value || 'all',
    defaultLandingPage: document.getElementById('settings-landing-page')?.value || DEFAULT_SETTINGS.defaultLandingPage,
    dateFormat: document.getElementById('settings-date-format')?.value || DEFAULT_SETTINGS.dateFormat,
    sessionTimeoutMinutes: Number(document.getElementById('settings-session-timeout')?.value ?? DEFAULT_SETTINGS.sessionTimeoutMinutes),
    notifyOverdueWo: Boolean(document.getElementById('settings-notify-overdue-wo')?.checked),
    notifyPmDue: Boolean(document.getElementById('settings-notify-pm-due')?.checked),
    notifyAccidents: Boolean(document.getElementById('settings-notify-accidents')?.checked),
  };
}

function flashSettingsSaved() {
  const status = document.getElementById('settings-save-status');
  if (!status) return;
  status.textContent = 'Saved.';
  window.clearTimeout(flashSettingsSaved._timer);
  flashSettingsSaved._timer = window.setTimeout(() => {
    status.textContent = 'Settings save automatically.';
  }, 1600);
}

async function syncNotificationPrefsToServer() {
  if (typeof db === 'undefined') return;
  const prefs = collectSettingsFromForm();
  try {
    await db.syncNotificationPrefs(prefs);
  } catch (err) {
    /* server sync is best-effort while offline */
  }
}

async function refreshPushStatusUi() {
  const statusCopy = document.getElementById('push-status-copy');
  const enableBtn = document.getElementById('enable-push-btn');
  const disableBtn = document.getElementById('disable-push-btn');
  const testBtn = document.getElementById('test-push-btn');
  if (!statusCopy || typeof db === 'undefined') return;

  if (!db.isPushSupported()) {
    statusCopy.textContent = 'Push requires HTTPS in Chrome, Edge, or Firefox. On iPhone, add the app to your Home Screen first.';
    enableBtn?.classList.add('hidden');
    disableBtn?.classList.add('hidden');
    testBtn?.classList.add('hidden');
    return;
  }

  const status = await db.getPushStatus();
  if (status.subscribed) {
    statusCopy.textContent = 'Push notifications are on for this device. You will receive alerts based on the options below.';
    enableBtn?.classList.add('hidden');
    disableBtn?.classList.remove('hidden');
    testBtn?.classList.remove('hidden');
  } else {
    statusCopy.textContent = 'Turn on push to get overdue work order, PM, and accident alerts on this device.';
    enableBtn?.classList.remove('hidden');
    disableBtn?.classList.add('hidden');
    testBtn?.classList.add('hidden');
  }
}

function wirePushNotifications() {
  document.getElementById('enable-push-btn')?.addEventListener('click', async () => {
    const statusEl = document.getElementById('push-action-status');
    if (typeof db === 'undefined') return;
    statusEl.textContent = 'Enabling push…';
    await syncNotificationPrefsToServer();
    const result = await db.subscribePush();
    if (result?.error) {
      statusEl.textContent = result.error;
      return;
    }
    statusEl.textContent = 'Push notifications enabled on this device.';
    await refreshPushStatusUi();
  });

  document.getElementById('disable-push-btn')?.addEventListener('click', async () => {
    const statusEl = document.getElementById('push-action-status');
    if (typeof db === 'undefined') return;
    await db.unsubscribePush();
    statusEl.textContent = 'Push notifications turned off for this device.';
    await refreshPushStatusUi();
  });

  document.getElementById('test-push-btn')?.addEventListener('click', async () => {
    const statusEl = document.getElementById('push-action-status');
    if (typeof db === 'undefined') return;
    statusEl.textContent = 'Sending test alert…';
    const result = await db.sendTestPush();
    statusEl.textContent = result?.error || 'Test alert sent — check your device notifications.';
  });
}

function wireSettingsForm() {
  const persistFromForm = () => {
    saveSettings(collectSettingsFromForm());
    syncNotificationPrefsToServer();
    flashSettingsSaved();
    wireSessionTimeout();
  };

  document.querySelectorAll('#shop-settings-form input, #shop-settings-form select, #wo-settings-form select, #fleet-settings-form select, #behavior-settings-form select')
    .forEach((el) => el.addEventListener('change', persistFromForm));

  document.querySelectorAll('.settings-check-row input').forEach((el) => {
    el.addEventListener('change', persistFromForm);
  });

  refreshThemeGrid();

  document.getElementById('custom-theme-save-btn')?.addEventListener('click', () => {
    saveCustomTheme({ apply: true });
  });

  document.getElementById('custom-theme-preview-btn')?.addEventListener('click', () => {
    const customTheme = collectCustomThemeFromForm();
    applyDocumentTheme({
      theme: CUSTOM_THEME_ID,
      layout: getSettings().layout,
      customTheme,
    });
    document.querySelectorAll('[data-theme-option]').forEach((button) => {
      button.classList.toggle('active', button.dataset.themeOption === CUSTOM_THEME_ID);
    });
  });

  document.querySelectorAll('#custom-theme-form input').forEach((input) => {
    input.addEventListener('input', () => {
      if (resolveThemeId(getSettings().theme, getSettings().customTheme) !== CUSTOM_THEME_ID) return;
      applyDocumentTheme({
        theme: CUSTOM_THEME_ID,
        layout: getSettings().layout,
        customTheme: collectCustomThemeFromForm(),
      });
      refreshThemeGrid();
    });
  });

  document.querySelectorAll('[data-layout-option]').forEach((button) => {
    button.addEventListener('click', () => applyLayout(button.dataset.layoutOption));
  });
}

function createSettingsButton({ floating = false } = {}) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = floating ? 'nav-settings-btn nav-settings-btn--floating' : 'nav-settings-btn';
  button.id = 'open-settings-btn';
  button.setAttribute('aria-label', 'Open settings');
  button.innerHTML = `<img src="img.icons8.png" alt="" class="nav-settings-icon" width="22" height="22" />`;
  return button;
}

async function injectUserBadge() {
  if (document.getElementById('nav-user') || typeof db === 'undefined') return;

  const user = await db.getCurrentUser();
  if (!user) return;

  window.__currentUser = user;

  const nav = document.querySelector('.nav');
  if (!nav) return;

  const navActions = nav.querySelector('.nav-actions') || nav;
  const badge = document.createElement('div');
  badge.className = 'nav-user';
  badge.id = 'nav-user';
  badge.innerHTML = `
    <span class="nav-user-name">${user.display_name}</span>
    <span class="nav-user-role">${user.role.replace('_', ' ')}</span>
    <button type="button" class="btn ghost nav-logout-btn" id="nav-logout-btn">Sign out</button>
  `;
  navActions.appendChild(badge);

  document.getElementById('nav-logout-btn')?.addEventListener('click', async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
    } catch (err) {
      /* still redirect */
    }
    window.location.href = '/login.html';
  });

  const accountCopy = document.getElementById('account-signed-in-copy');
  if (accountCopy) {
    accountCopy.textContent = `Signed in as ${user.display_name} (${user.role.replace('_', ' ')}).`;
  }

  if (user.role === 'admin') {
    injectAdminNavLink();
  }

  syncShopNameAccess();
  await maybeForcePasswordChange(user);
}

function wireChangePasswordForm() {
  const form = document.getElementById('change-password-form');
  if (!form || form._wired) return;
  form._wired = true;

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const status = document.getElementById('settings-password-status');
    const currentPassword = document.getElementById('settings-current-password').value;
    const newPassword = document.getElementById('settings-new-password').value;
    const confirmPassword = document.getElementById('settings-confirm-password').value;
    const button = document.getElementById('settings-save-password');

    if (newPassword !== confirmPassword) {
      status.textContent = 'New passwords do not match.';
      return;
    }

    button.disabled = true;
    status.textContent = 'Saving…';

    const result = await db.changePassword(currentPassword, newPassword);
    button.disabled = false;

    if (result?.error) {
      status.textContent = result.error;
      return;
    }

    form.reset();
    status.textContent = 'Password updated. Use your new password next time you sign in.';

    const modal = document.getElementById('settings-modal');
    if (modal?.dataset.forcePassword === 'true') {
      if (window.__currentUser) window.__currentUser.password_changed = true;
      exitForcedPasswordMode();
      status.textContent = `Password set. You can continue using ${APP_NAME}.`;
    }
  });
}

function injectAdminNavLink() {
  const navLinks = document.querySelector('.nav-links');
  if (!navLinks || navLinks.querySelector('[data-nav-admin]')) return;

  const link = document.createElement('a');
  link.href = 'admin.html';
  link.dataset.navAdmin = 'true';
  link.textContent = 'Admin';
  if (window.location.pathname.endsWith('admin.html')) {
    link.classList.add('active');
  }

  navLinks.appendChild(link);
}

function injectActivityNavLink() {
  const navLinks = document.querySelector('.nav-links');
  if (!navLinks || navLinks.querySelector('[data-nav-activity]')) return;

  const link = document.createElement('a');
  link.href = 'activity.html';
  link.dataset.navActivity = 'true';
  link.textContent = 'Activity';
  if (window.location.pathname.endsWith('activity.html')) {
    link.classList.add('active');
  }

  const accidentLink = [...navLinks.querySelectorAll('a')].find((anchor) => (
    anchor.getAttribute('href')?.includes('accidents')
  ));
  if (accidentLink) {
    accidentLink.insertAdjacentElement('afterend', link);
  } else {
    navLinks.appendChild(link);
  }
}

function injectReportsNavLink() {
  const navLinks = document.querySelector('.nav-links');
  if (!navLinks || navLinks.querySelector('[data-nav-reports]')) return;

  const link = document.createElement('a');
  link.href = 'reports.html';
  link.dataset.navReports = 'true';
  link.textContent = 'Reports';
  if (window.location.pathname.endsWith('reports.html')) {
    link.classList.add('active');
  }

  const activityLink = navLinks.querySelector('[data-nav-activity]')
    || [...navLinks.querySelectorAll('a')].find((anchor) => anchor.getAttribute('href')?.includes('activity'));
  if (activityLink) {
    activityLink.insertAdjacentElement('afterend', link);
  } else {
    navLinks.appendChild(link);
  }
}

function injectPartsNavLink() {
  const navLinks = document.querySelector('.nav-links');
  if (!navLinks || navLinks.querySelector('[data-nav-parts]')) return;

  const link = document.createElement('a');
  link.href = 'parts.html';
  link.dataset.navParts = 'true';
  link.textContent = 'Parts';
  if (window.location.pathname.endsWith('parts.html')) {
    link.classList.add('active');
  }

  const reportsLink = navLinks.querySelector('[data-nav-reports]')
    || [...navLinks.querySelectorAll('a')].find((anchor) => anchor.getAttribute('href')?.includes('reports'));
  if (reportsLink) {
    reportsLink.insertAdjacentElement('afterend', link);
  } else {
    navLinks.appendChild(link);
  }
}

function injectLeasingNavLink() {
  const navLinks = document.querySelector('.nav-links');
  if (!navLinks || navLinks.querySelector('[data-nav-leasing]')) return;

  const link = document.createElement('a');
  link.href = 'leasing.html';
  link.dataset.navLeasing = 'true';
  link.textContent = 'Leasing';
  if (window.location.pathname.endsWith('leasing.html')) {
    link.classList.add('active');
  }

  const partsLink = navLinks.querySelector('[data-nav-parts]')
    || [...navLinks.querySelectorAll('a')].find((anchor) => anchor.getAttribute('href')?.includes('parts'));
  if (partsLink) {
    partsLink.insertAdjacentElement('afterend', link);
  } else {
    navLinks.appendChild(link);
  }
}

function injectStoreNavLink() {
  const navLinks = document.querySelector('.nav-links');
  if (!navLinks || navLinks.querySelector('[data-nav-store]')) return;

  const link = document.createElement('a');
  link.href = 'store.html';
  link.dataset.navStore = 'true';
  link.textContent = 'Store';
  if (window.location.pathname.endsWith('store.html')) {
    link.classList.add('active');
  }

  const leasingLink = navLinks.querySelector('[data-nav-leasing]')
    || [...navLinks.querySelectorAll('a')].find((anchor) => anchor.getAttribute('href')?.includes('leasing'));
  if (leasingLink) {
    leasingLink.insertAdjacentElement('afterend', link);
  } else {
    const partsLink = navLinks.querySelector('[data-nav-parts]');
    if (partsLink) partsLink.insertAdjacentElement('afterend', link);
    else navLinks.appendChild(link);
  }
}

function injectSettingsButton() {
  if (document.getElementById('open-settings-btn')) return;

  const nav = document.querySelector('.nav');
  if (nav) {
    const navLinks = nav.querySelector('.nav-links');
    let navActions = nav.querySelector('.nav-actions');

    if (!navActions) {
      navActions = document.createElement('div');
      navActions.className = 'nav-actions';
      if (navLinks) {
        nav.insertBefore(navActions, navLinks);
        navActions.appendChild(navLinks);
      } else {
        nav.appendChild(navActions);
      }
    }

    navActions.appendChild(createSettingsButton());
    return;
  }

  document.body.appendChild(createSettingsButton({ floating: true }));
}

async function openSettings() {
  const modal = document.getElementById('settings-modal');
  if (!modal) return;
  await loadTeamAssignees();
  const mechanicSelect = document.getElementById('settings-default-mechanic');
  if (mechanicSelect) {
    const current = mechanicSelect.value;
    mechanicSelect.innerHTML = `
      <option value="">None</option>
      ${getTeamAssigneeNames().map((name) => `<option value="${name}">${name}</option>`).join('')}
    `;
    mechanicSelect.value = current;
  }
  await populateSettingsDynamicOptions();
  syncSettingsForm();
  refreshThemeGrid();
  wirePasswordVisibilityToggles(modal);
  refreshPushStatusUi();
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function closeSettings() {
  const modal = document.getElementById('settings-modal');
  if (!modal) return;
  if (modal.dataset.forcePassword === 'true') return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
  applySettings();
  syncCustomThemeForm();
  refreshThemeGrid();
}

function enterForcedPasswordMode(user) {
  const modal = document.getElementById('settings-modal');
  if (!modal) return;

  modal.dataset.forcePassword = 'true';
  modal.classList.add('settings-modal--forced');

  const closeBtn = document.getElementById('settings-close');
  if (closeBtn) closeBtn.classList.add('hidden');

  const headerTitle = modal.querySelector('.modal-header h2');
  if (headerTitle) headerTitle.textContent = 'Set Your Password';

  const headerEyebrow = modal.querySelector('.modal-header .eyebrow');
  if (headerEyebrow) headerEyebrow.textContent = 'Required';

  modal.querySelectorAll('.settings-section').forEach((section) => {
    section.classList.toggle('hidden', section.id !== 'account-settings-section');
  });

  const accountCopy = document.getElementById('account-signed-in-copy');
  if (accountCopy) {
    accountCopy.textContent = `${user.display_name}, choose a personal password before continuing. Use your current sign-in password once, then pick a new one (8+ characters).`;
  }

  const formHeading = modal.querySelector('#change-password-form h4');
  if (formHeading) formHeading.textContent = 'Choose a New Password';

  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
  wirePasswordVisibilityToggles(modal);
  document.getElementById('settings-current-password')?.focus();
}

function exitForcedPasswordMode() {
  const modal = document.getElementById('settings-modal');
  if (!modal) return;

  delete modal.dataset.forcePassword;
  modal.classList.remove('settings-modal--forced');

  const closeBtn = document.getElementById('settings-close');
  if (closeBtn) closeBtn.classList.remove('hidden');

  const headerTitle = modal.querySelector('.modal-header h2');
  if (headerTitle) headerTitle.textContent = `Customize ${APP_NAME}`;

  const headerEyebrow = modal.querySelector('.modal-header .eyebrow');
  if (headerEyebrow) headerEyebrow.textContent = 'Settings';

  modal.querySelectorAll('.settings-section').forEach((section) => {
    section.classList.remove('hidden');
  });

  const formHeading = modal.querySelector('#change-password-form h4');
  if (formHeading) formHeading.textContent = 'Change Password';

  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

async function maybeForcePasswordChange(user) {
  if (!user || user.password_changed) return;
  if ((window.location.pathname.split('/').pop() || '') === 'login.html') return;
  enterForcedPasswordMode(user);
}

let sessionTimeoutTimer = null;

async function logoutForTimeout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } catch (err) {
    /* still redirect */
  }
  window.location.href = '/login.html';
}

function wireSessionTimeout() {
  if (sessionTimeoutTimer) {
    window.clearTimeout(sessionTimeoutTimer);
    sessionTimeoutTimer = null;
  }

  const minutes = Number(getSettings().sessionTimeoutMinutes);
  if (!minutes) return;

  const resetTimer = () => {
    window.clearTimeout(sessionTimeoutTimer);
    sessionTimeoutTimer = window.setTimeout(logoutForTimeout, minutes * 60 * 1000);
  };

  if (!wireSessionTimeout._wired) {
    ['click', 'keydown', 'scroll', 'touchstart'].forEach((eventName) => {
      document.addEventListener(eventName, resetTimer, { passive: true });
    });
    wireSessionTimeout._wired = true;
  }

  resetTimer();
}

function maybeRedirectLandingPage() {
  const path = window.location.pathname.split('/').pop() || 'index.html';
  if (path !== 'index.html') return;

  const params = new URLSearchParams(window.location.search);
  if (params.has('id') || params.has('status') || params.has('due') || params.has('next')) return;

  const landing = getSettings().defaultLandingPage;
  if (landing && landing !== 'index.html') {
    window.location.replace(landing);
  }
}

function applyStoredSettingsEarly() {
  applySettings(readStoredSettings());
}

window.MaintainSMIPSettings = {
  APP_NAME,
  APP_VERSION,
  get: getSettings,
  save: saveSettings,
  apply: applySettings,
  formatDate: formatAppDate,
  getPmDueWindowDays,
  isPmDueSoon,
  getPmDueLabel,
  getCurrentUser: () => window.__currentUser || db?.getCachedUser?.() || null,
  getDefaultMechanic: () => {
    const settingsMechanic = getSettings().defaultMechanic || '';
    if (settingsMechanic) return settingsMechanic;
    return window.__currentUser?.display_name || db?.getCachedUser?.()?.display_name || '';
  },
  getDefaultLocation: () => getSettings().defaultLocation || '',
  getDefaultPriority: () => getSettings().defaultPriority || DEFAULT_SETTINGS.defaultPriority,
  getDefaultServiceType: () => getSettings().defaultServiceType || DEFAULT_SETTINGS.defaultServiceType,
  getDefaultWoTemplateId: () => getSettings().defaultWoTemplateId || '',
  getDefaultFleetLocation: () => getSettings().defaultFleetLocation || 'all',
  getShopName: () => getSettings().shopName || DEFAULT_SETTINGS.shopName,
  detectDeviceType,
  resolveLayout,
  loadTeamAssignees,
  populateAssigneeSelect,
  getTeamAssigneeNames,
  wirePasswordVisibilityToggles,
};

async function initPushBackground() {
  if (typeof db === 'undefined' || !db.isPushSupported()) return;
  try {
    await db.ensureServiceWorker();
    const serverPrefs = await db.getNotificationPrefs();
    if (serverPrefs) {
      saveSettings({
        notifyOverdueWo: serverPrefs.notify_overdue_wo,
        notifyPmDue: serverPrefs.notify_pm_due,
        notifyAccidents: serverPrefs.notify_accidents,
      });
    }
  } catch (err) {
    /* push warms up when user opens settings */
  }
}

async function initSettings() {
  buildSettingsModal();
  wirePasswordVisibilityToggles();
  injectActivityNavLink();
  injectReportsNavLink();
  injectPartsNavLink();
  injectLeasingNavLink();
  injectStoreNavLink();
  injectSettingsButton();
  await loadTeamAssignees();
  syncSettingsForm();
  wireChangePasswordForm();
  wirePushNotifications();
  applySettings();
  syncSettingsForm();
  wireSettingsForm();
  wireSessionTimeout();
  maybeRedirectLandingPage();
  injectUserBadge();
  window.addEventListener('load', () => {
    if (typeof db !== 'undefined') initPushBackground();
  });

  document.getElementById('open-settings-btn')?.addEventListener('click', openSettings);
  document.getElementById('settings-close')?.addEventListener('click', closeSettings);
  document.getElementById('settings-modal')?.addEventListener('click', (event) => {
    if (event.target.id === 'settings-modal') closeSettings();
  });

  let layoutResizeTimer;
  window.addEventListener('resize', () => {
    if ((getSettings().layoutMode || 'auto') !== 'auto') return;
    clearTimeout(layoutResizeTimer);
    layoutResizeTimer = setTimeout(() => applySettings(), 150);
  });
}

applyStoredSettingsEarly();

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSettings);
} else {
  initSettings();
}