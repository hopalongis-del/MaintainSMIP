const APP_VERSION = '1.5.2';
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
  'Gavin Weinmeister',
  'Kevin Stellman',
  'Cory Yeager',
  'Mike Casady',
  'Dusty Hixson',
  'Brian Lachance',
  'Chelsie',
  'Stephen Hering',
  'Mark Hixson',
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
  layoutMode: 'auto', // 'auto', 'phone', 'laptop'
  shopName: 'SMI Properties',
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
};

// Device detection utility
function detectDeviceType() {
  const userAgent = navigator.userAgent || navigator.vendor || window.opera;
  const screenWidth = window.innerWidth || document.documentElement.clientWidth;
  
  // Check if it's a mobile device based on user agent
  const isMobileUA = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/i.test(userAgent);
  
  // Check screen width (mobile if <= 768px)
  const isSmallScreen = screenWidth <= 768;
  
  // Check if touch device
  const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  
  // Determine if mobile
  if (isMobileUA || (isSmallScreen && isTouchDevice)) {
    return 'phone';
  }
  
  return 'laptop';
}

function resolveLayout(settings = getSettings()) {
  // If user manually set layout, use that
  if (settings.layoutMode !== 'auto') {
    return settings.layoutMode;
  }
  
  // Otherwise, auto-detect
  return detectDeviceType();
}

function readStoredSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
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

function applyLayout(layout) {
  saveSettings({ layoutMode: layout === 'phone' ? 'phone' : 'laptop' });
}

function applySettings(settings = getSettings()) {
  const theme = resolveThemeId(settings.theme, settings.customTheme);
  const resolvedLayout = resolveLayout(settings);
  const layout = resolvedLayout;

  applyDocumentTheme({ theme: settings.theme, layout, customTheme: settings.customTheme });

  document.querySelectorAll('[data-theme-option]').forEach((button) => {
    button.classList.toggle('active', button.dataset.themeOption === theme);
  });
  document.querySelectorAll('[data-layout-option]').forEach((button) => {
    button.classList.toggle('active', button.dataset.layoutOption === layout);
  });

  document.querySelectorAll('[data-settings-shop-name]').forEach((el) => {
    el.textContent = settings.shopName || DEFAULT_SETTINGS.shopName;
  });

  const footer = document.querySelector('[data-settings-footer]');
  if (footer) {
    const shop = settings.shopName || DEFAULT_SETTINGS.shopName;
    footer.textContent = `MaintainSMIP · ${shop} Fleet Maintenance`;
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
            <h2>Customize MaintainSMIP</h2>
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
            <p class="hero-sub">Pick four colors and we'll generate the full theme. Save it to add "My Custom Theme" to the list above.</p>
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
            <p class="hero-sub">Auto-detects your device, but you can override it here.</p>
            <div class="settings-toggle-group" id="layout-toggle">
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
              <input type="text" id="settings-shop-name" placeholder="SMI Properties" />
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
          <p class="hero-sub" id="push-status-copy">Checking push notification status...</p>
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
            <p><strong>Support</strong> <a href="mailto:support@smiproperties.com">support@smiproperties.com</a></p>
            <p class="hero-sub">MaintainSMIP · Fleet maintenance for SMI Properties.</p>
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
  
  // Sync layout toggle
  const resolvedLayout = resolveLayout(settings);
  document.querySelectorAll('[data-layout-option]').forEach((button) => {
    button.classList.toggle('active', button.dataset.layoutOption === resolvedLayout);
  });
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
      const dbCarts = await db.getCarts();
      locations = Array.from(new Set(dbCarts.map((c) => c.location).filter(Boolean))).sort();
    } catch (e) {
      /* ignore */
    }
  }

  if (fleetSelect) {
    fleetSelect.innerHTML = `
      <option value="all">All locations</option>
      ${locations.map((loc) => `<option value="${loc}">${loc}</option>`).join('')}
    `;
  }

  if (templateSelect && window.MaintainSMIPEvents) {
    const templates = window.MaintainSMIPEvents.getTemplates();
    templateSelect.innerHTML = `
      <option value="">Use system default</option>
      ${templates.map((t) => `<option value="${t.id}">${t.name}</option>`).join('')}
    `;
  }
}

function flashSettingsSaved() {
  const status = document.getElementById('settings-save-status');
  if (!status) return;
  status.textContent = 'Saved!';
  status.style.color = 'var(--success)';
  setTimeout(() => {
    status.textContent = 'Settings save automatically.';
    status.style.color = '';
  }, 1500);
}

function wireSettingsForm() {
  document.getElementById('settings-shop-name')?.addEventListener('change', (e) => {
    saveSettings({ shopName: e.target.value });
  });
  document.getElementById('settings-default-location')?.addEventListener('change', (e) => {
    saveSettings({ defaultLocation: e.target.value });
  });
  document.getElementById('settings-default-mechanic')?.addEventListener('change', (e) => {
    saveSettings({ defaultMechanic: e.target.value });
  });
  document.getElementById('settings-default-template')?.addEventListener('change', (e) => {
    saveSettings({ defaultWoTemplateId: e.target.value });
  });
  document.getElementById('settings-default-priority')?.addEventListener('change', (e) => {
    saveSettings({ defaultPriority: e.target.value });
  });
  document.getElementById('settings-default-service-type')?.addEventListener('change', (e) => {
    saveSettings({ defaultServiceType: e.target.value });
  });
  document.getElementById('settings-pm-window')?.addEventListener('change', (e) => {
    saveSettings({ pmDueWindowDays: Number(e.target.value) });
  });
  document.getElementById('settings-fleet-location')?.addEventListener('change', (e) => {
    saveSettings({ defaultFleetLocation: e.target.value });
  });
  document.getElementById('settings-landing-page')?.addEventListener('change', (e) => {
    saveSettings({ defaultLandingPage: e.target.value });
  });
  document.getElementById('settings-date-format')?.addEventListener('change', (e) => {
    saveSettings({ dateFormat: e.target.value });
  });
  document.getElementById('settings-session-timeout')?.addEventListener('change', (e) => {
    saveSettings({ sessionTimeoutMinutes: Number(e.target.value) });
  });
  document.getElementById('settings-notify-overdue-wo')?.addEventListener('change', (e) => {
    saveSettings({ notifyOverdueWo: e.target.checked });
  });
  document.getElementById('settings-notify-pm-due')?.addEventListener('change', (e) => {
    saveSettings({ notifyPmDue: e.target.checked });
  });
  document.getElementById('settings-notify-accidents')?.addEventListener('change', (e) => {
    saveSettings({ notifyAccidents: e.target.checked });
  });

  // Layout toggle
  document.querySelectorAll('[data-layout-option]').forEach((button) => {
    button.addEventListener('click', () => applyLayout(button.dataset.layoutOption));
  });
}

function wireSettingsModal() {
  const modal = document.getElementById('settings-modal');
  if (!modal) return;

  document.getElementById('settings-close')?.addEventListener('click', () => {
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  });

  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.classList.add('hidden');
      modal.setAttribute('aria-hidden', 'true');
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
      modal.classList.add('hidden');
      modal.setAttribute('aria-hidden', 'true');
    }
  });
}

function wirePasswordChangeForm() {
  const form = document.getElementById('change-password-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const currentPassword = document.getElementById('settings-current-password').value;
    const newPassword = document.getElementById('settings-new-password').value;
    const confirmPassword = document.getElementById('settings-confirm-password').value;
    const statusEl = document.getElementById('settings-password-status');

    if (newPassword !== confirmPassword) {
      statusEl.textContent = 'New passwords do not match.';
      statusEl.style.color = 'var(--danger, #dc2626)';
      return;
    }

    if (newPassword.length < 8) {
      statusEl.textContent = 'Password must be at least 8 characters.';
      statusEl.style.color = 'var(--danger, #dc2626)';
      return;
    }

    try {
      const result = await db.changePassword(currentPassword, newPassword);
      if (result?.error) {
        statusEl.textContent = result.error;
        statusEl.style.color = 'var(--danger, #dc2626)';
      } else {
        statusEl.textContent = 'Password updated successfully.';
        statusEl.style.color = 'var(--success)';
        form.reset();
      }
    } catch (err) {
      statusEl.textContent = 'Error updating password.';
      statusEl.style.color = 'var(--danger, #dc2626)';
    }
  });
}

async function initSettings() {
  const settings = getSettings();
  applySettings(settings);
  syncSettingsForm(settings);
  refreshThemeGrid();
  wireSettingsForm();
  wireSettingsModal();
  wirePasswordVisibilityToggles();
  wirePasswordChangeForm();
  await populateSettingsDynamicOptions();

  // Push notification setup
  const pushStatusCopy = document.getElementById('push-status-copy');
  const enableBtn = document.getElementById('enable-push-btn');
  const disableBtn = document.getElementById('disable-push-btn');
  const testBtn = document.getElementById('test-push-btn');
  const pushStatus = document.getElementById('push-action-status');

  if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
    if (pushStatusCopy) pushStatusCopy.textContent = 'Push notifications are enabled.';
    if (enableBtn) enableBtn.classList.add('hidden');
    if (disableBtn) disableBtn.classList.remove('hidden');
    if (testBtn) testBtn.classList.remove('hidden');
  } else if (typeof Notification !== 'undefined' && Notification.permission !== 'denied') {
    if (pushStatusCopy) pushStatusCopy.textContent = 'Push notifications are not enabled yet.';
  } else {
    if (pushStatusCopy) pushStatusCopy.textContent = 'Push notifications are blocked. Enable them in your browser settings.';
  }

  enableBtn?.addEventListener('click', async () => {
    try {
      const permission = await Notification.requestPermission();
      if (permission === 'granted') {
        if (pushStatusCopy) pushStatusCopy.textContent = 'Push notifications are enabled.';
        if (enableBtn) enableBtn.classList.add('hidden');
        if (disableBtn) disableBtn.classList.remove('hidden');
        if (testBtn) testBtn.classList.remove('hidden');
      } else {
        if (pushStatusCopy) pushStatusCopy.textContent = 'Push notifications were denied.';
      }
    } catch (err) {
      if (pushStatusCopy) pushStatusCopy.textContent = 'Error enabling push notifications.';
    }
  });

  disableBtn?.addEventListener('click', async () => {
    try {
      if ('serviceWorker' in navigator && 'getRegistration' in navigator.serviceWorker) {
        const reg = await navigator.serviceWorker.getRegistration();
        if (reg?.showNotification) {
          await reg.unregister();
        }
      }
      if (pushStatusCopy) pushStatusCopy.textContent = 'Push notifications turned off.';
      if (enableBtn) enableBtn.classList.remove('hidden');
      if (disableBtn) disableBtn.classList.add('hidden');
      if (testBtn) testBtn.classList.add('hidden');
    } catch (err) {
      if (pushStatusCopy) pushStatusCopy.textContent = 'Error turning off push notifications.';
    }
  });

  testBtn?.addEventListener('click', () => {
    if (pushStatus) pushStatus.textContent = 'Test alert sent!';
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
      new Notification('MaintainSMIP Test', { body: 'Push notifications are working!' });
    }
  });

  // Account section
  const accountCopy = document.getElementById('account-signed-in-copy');
  const currentUser = window.__currentUser || db?.getCachedUser?.();
  if (accountCopy && currentUser) {
    accountCopy.textContent = `Signed in as ${currentUser.display_name} (${currentUser.role})`;
  }
}

// Export for use in other files
window.MaintainSMIPSettings = {
  getSettings,
  saveSettings,
  applyTheme,
  applyLayout,
  applySettings,
  formatAppDate,
  getPmDueWindowDays,
  isPmDueSoon,
  getPmDueLabel,
  detectDeviceType,
  resolveLayout,
};

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSettings);
} else {
  initSettings();
}
