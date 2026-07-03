const APP_VERSION = '1.2.0';
const LEGACY_THEME_KEY = 'maintainsmip-theme';
const SETTINGS_KEY = 'maintainsmip-settings';

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
];

const TECHNICIANS = [
  'Gavin Weinmeister',
  'Kevin Stellman',
  'Cory Yeager',
  'Mike Casady',
  'Dusty Hixson',
  'Brian Lachance',
  'Stephen Hering',
  'Mark Hixson',
];

const DEFAULT_SETTINGS = {
  theme: 'smi-racing',
  layout: 'laptop',
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
  const valid = RACING_THEMES.some((theme) => theme.id === themeId);
  saveSettings({ theme: valid ? themeId : DEFAULT_SETTINGS.theme });
}

function applyLayout(layout) {
  saveSettings({ layout: layout === 'phone' ? 'phone' : 'laptop' });
}

function applySettings(settings = getSettings()) {
  const theme = RACING_THEMES.some((item) => item.id === settings.theme)
    ? settings.theme
    : DEFAULT_SETTINGS.theme;
  const layout = settings.layout === 'phone' ? 'phone' : 'laptop';

  document.documentElement.setAttribute('data-theme', theme);
  document.documentElement.setAttribute('data-layout', layout);

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

function buildThemeOptions() {
  return RACING_THEMES.map((theme) => `
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
            <h4>Layout</h4>
            <div class="settings-toggle-group" id="layout-toggle">
              <button type="button" class="settings-toggle" data-layout-option="phone">Optimized for Phone</button>
              <button type="button" class="settings-toggle" data-layout-option="laptop">Optimized for Laptop</button>
            </div>
          </div>
        </section>

        <section class="settings-section">
          <h3>Shop</h3>
          <p class="hero-sub">Defaults for your track and crew.</p>
          <form class="settings-form" id="shop-settings-form">
            <label>Shop Name
              <input type="text" id="settings-shop-name" placeholder="SMI Properties" />
            </label>
            <label>Default Location
              <input type="text" id="settings-default-location" list="settings-location-options" placeholder="e.g. Charlotte Motor Speedway" />
            </label>
            <label>Default Mechanic
              <select id="settings-default-mechanic">
                <option value="">None</option>
                ${TECHNICIANS.map((name) => `<option value="${name}">${name}</option>`).join('')}
              </select>
            </label>
          </form>
          <datalist id="settings-location-options"></datalist>
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
          <p class="hero-sub">Alert preferences are saved now. Delivery is coming soon.</p>
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
        </section>

        <section class="settings-section">
          <h3>Account</h3>
          <p class="hero-sub">Password updates are coming soon.</p>
          <form id="change-password-form" class="settings-form">
            <label>Current Password
              <input type="password" id="settings-current-password" placeholder="Enter current password" autocomplete="current-password" disabled />
            </label>
            <label>New Password
              <input type="password" id="settings-new-password" placeholder="Enter new password" autocomplete="new-password" disabled />
            </label>
            <label>Confirm New Password
              <input type="password" id="settings-confirm-password" placeholder="Confirm new password" autocomplete="new-password" disabled />
            </label>
            <button class="btn secondary" type="button" id="settings-password-placeholder" disabled>Save Password (Coming Soon)</button>
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
  setValue('settings-default-location', settings.defaultLocation);
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
}

async function populateSettingsDynamicOptions() {
  const locationList = document.getElementById('settings-location-options');
  const fleetSelect = document.getElementById('settings-fleet-location');
  const templateSelect = document.getElementById('settings-default-template');

  let locations = [];
  if (typeof cartData !== 'undefined' && Array.isArray(cartData)) {
    locations = Array.from(new Set(cartData.map((cart) => cart.location).filter(Boolean))).sort();
  }

  if (locationList) {
    locationList.innerHTML = locations.map((loc) => `<option value="${loc}"></option>`).join('');
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
  return {
    shopName: document.getElementById('settings-shop-name')?.value.trim() || DEFAULT_SETTINGS.shopName,
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

function wireSettingsForm() {
  const persistFromForm = () => {
    saveSettings(collectSettingsFromForm());
    flashSettingsSaved();
    wireSessionTimeout();
  };

  document.querySelectorAll('#shop-settings-form input, #wo-settings-form select, #fleet-settings-form select, #behavior-settings-form select')
    .forEach((el) => el.addEventListener('change', persistFromForm));

  document.querySelectorAll('.settings-check-row input').forEach((el) => {
    el.addEventListener('change', persistFromForm);
  });

  document.querySelectorAll('[data-theme-option]').forEach((button) => {
    button.addEventListener('click', () => applyTheme(button.dataset.themeOption));
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

function openSettings() {
  const modal = document.getElementById('settings-modal');
  if (!modal) return;
  populateSettingsDynamicOptions().then(() => syncSettingsForm());
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function closeSettings() {
  const modal = document.getElementById('settings-modal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
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
  APP_VERSION,
  get: getSettings,
  save: saveSettings,
  apply: applySettings,
  formatDate: formatAppDate,
  getPmDueWindowDays,
  isPmDueSoon,
  getPmDueLabel,
  getDefaultMechanic: () => getSettings().defaultMechanic || '',
  getDefaultLocation: () => getSettings().defaultLocation || '',
  getDefaultPriority: () => getSettings().defaultPriority || DEFAULT_SETTINGS.defaultPriority,
  getDefaultServiceType: () => getSettings().defaultServiceType || DEFAULT_SETTINGS.defaultServiceType,
  getDefaultWoTemplateId: () => getSettings().defaultWoTemplateId || '',
  getDefaultFleetLocation: () => getSettings().defaultFleetLocation || 'all',
  getShopName: () => getSettings().shopName || DEFAULT_SETTINGS.shopName,
};

function initSettings() {
  buildSettingsModal();
  injectSettingsButton();
  applySettings();
  syncSettingsForm();
  wireSettingsForm();
  wireSessionTimeout();
  maybeRedirectLandingPage();

  document.getElementById('open-settings-btn')?.addEventListener('click', openSettings);
  document.getElementById('settings-close')?.addEventListener('click', closeSettings);
  document.getElementById('settings-modal')?.addEventListener('click', (event) => {
    if (event.target.id === 'settings-modal') closeSettings();
  });
}

applyStoredSettingsEarly();

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSettings);
} else {
  initSettings();
}