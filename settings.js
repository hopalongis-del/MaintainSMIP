const APP_VERSION = '1.3.0';
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
  'Chelsie',
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
          <div class="settings-subblock hidden" id="admin-users-panel">
            <h4>Team Accounts</h4>
            <p class="hero-sub">Admins can add users, reset passwords, and deactivate accounts. You cannot delete yourself or the last active admin.</p>
            <div id="admin-users-list" class="admin-users-list"></div>
            <form class="settings-form" id="admin-create-user-form">
              <label>New Username
                <input type="text" id="admin-new-username" placeholder="firstname.lastname" required />
              </label>
              <label>Display Name
                <input type="text" id="admin-new-display-name" placeholder="Full name" required />
              </label>
              <label>Role
                <select id="admin-new-role">
                  <option value="technician">Technician</option>
                  <option value="manager">Manager</option>
                  <option value="readonly">Read-only</option>
                  <option value="admin">Admin</option>
                </select>
              </label>
              <label>Password
                <input type="password" id="admin-new-password" minlength="8" required />
              </label>
              <button class="btn secondary" type="submit">Add User</button>
            </form>
            <p class="hero-sub" id="admin-users-status"></p>
          </div>
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

    <div class="modal hidden" id="admin-reset-password-modal" aria-hidden="true">
      <div class="modal-panel card settings-panel" style="max-width: 420px;">
        <div class="modal-header">
          <div>
            <span class="eyebrow">Team Accounts</span>
            <h2 id="admin-reset-password-title">Reset Password</h2>
          </div>
          <button class="btn ghost" type="button" id="admin-reset-password-close" aria-label="Close">Close</button>
        </div>
        <form class="settings-form" id="admin-reset-password-form">
          <p class="hero-sub" id="admin-reset-password-copy">Set a new password for this user.</p>
          <label>New Password
            <input type="password" id="admin-reset-password-input" minlength="8" required autocomplete="new-password" />
          </label>
          <label>Confirm Password
            <input type="password" id="admin-reset-password-confirm" minlength="8" required autocomplete="new-password" />
          </label>
          <button class="btn secondary" type="submit">Save New Password</button>
          <p class="hero-sub" id="admin-reset-password-status"></p>
        </form>
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
    document.getElementById('admin-users-panel')?.classList.remove('hidden');
    await refreshAdminUsersList();
  }
}

let adminResetPasswordUserId = null;

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function refreshAdminUsersList() {
  const listEl = document.getElementById('admin-users-list');
  if (!listEl || typeof db === 'undefined') return;
  const users = await db.getUsers();
  if (!Array.isArray(users)) {
    listEl.innerHTML = '<p class="hero-sub">Could not load users.</p>';
    return;
  }
  const currentUser = window.__currentUser || db.getCachedUser?.() || null;
  listEl.innerHTML = users.map((user) => {
    const isSelf = currentUser && user.id === currentUser.id;
    return `
      <div class="admin-user-row" data-user-id="${user.id}">
        <div>
          <strong>${escapeHtml(user.display_name)}</strong>
          <span class="hero-sub">${escapeHtml(user.username)} · ${escapeHtml(user.role)}${isSelf ? ' · you' : ''}</span>
        </div>
        <div class="admin-user-actions">
          <button type="button" class="btn ghost" data-admin-reset-password="${user.id}" data-admin-display-name="${escapeHtml(user.display_name)}">Reset Password</button>
          ${isSelf ? '' : `<button type="button" class="btn ghost danger" data-admin-delete-user="${user.id}" data-admin-username="${escapeHtml(user.username)}">Delete</button>`}
        </div>
      </div>
    `;
  }).join('');
}

function openAdminResetPasswordModal(userId, displayName) {
  adminResetPasswordUserId = userId;
  const modal = document.getElementById('admin-reset-password-modal');
  const title = document.getElementById('admin-reset-password-title');
  const copy = document.getElementById('admin-reset-password-copy');
  const status = document.getElementById('admin-reset-password-status');
  const form = document.getElementById('admin-reset-password-form');
  if (!modal) return;
  if (title) title.textContent = `Reset Password`;
  if (copy) copy.textContent = `Set a new password for ${displayName}. They will sign in with this password on their next visit.`;
  if (status) status.textContent = '';
  form?.reset();
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
  document.getElementById('admin-reset-password-input')?.focus();
}

function closeAdminResetPasswordModal() {
  adminResetPasswordUserId = null;
  const modal = document.getElementById('admin-reset-password-modal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

function wireAdminUserActions() {
  const listEl = document.getElementById('admin-users-list');
  if (!listEl || listEl._wired) return;
  listEl._wired = true;

  listEl.addEventListener('click', async (event) => {
    const resetBtn = event.target.closest('[data-admin-reset-password]');
    if (resetBtn) {
      openAdminResetPasswordModal(
        Number(resetBtn.dataset.adminResetPassword),
        resetBtn.dataset.adminDisplayName || 'this user',
      );
      return;
    }

    const deleteBtn = event.target.closest('[data-admin-delete-user]');
    if (!deleteBtn || typeof db === 'undefined') return;

    const userId = Number(deleteBtn.dataset.adminDeleteUser);
    const username = deleteBtn.dataset.adminUsername || 'this user';
    const status = document.getElementById('admin-users-status');
    if (!window.confirm(`Deactivate ${username}? They will no longer be able to sign in.`)) return;

    const result = await db.deleteUser(userId);
    if (result?.error) {
      if (status) status.textContent = result.error;
      return;
    }
    if (status) status.textContent = `Deactivated ${username}.`;
    await refreshAdminUsersList();
  });

  const resetForm = document.getElementById('admin-reset-password-form');
  if (resetForm && !resetForm._wired) {
    resetForm._wired = true;
    resetForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const status = document.getElementById('admin-reset-password-status');
      const password = document.getElementById('admin-reset-password-input')?.value || '';
      const confirm = document.getElementById('admin-reset-password-confirm')?.value || '';
      if (!adminResetPasswordUserId) return;
      if (password.length < 8) {
        if (status) status.textContent = 'Password must be at least 8 characters.';
        return;
      }
      if (password !== confirm) {
        if (status) status.textContent = 'Passwords do not match.';
        return;
      }

      const result = await db.updateUser(adminResetPasswordUserId, { password });
      if (result?.error) {
        if (status) status.textContent = result.error;
        return;
      }

      const listStatus = document.getElementById('admin-users-status');
      if (listStatus) listStatus.textContent = `Password updated for ${result.display_name}.`;
      closeAdminResetPasswordModal();
    });
  }

  document.getElementById('admin-reset-password-close')?.addEventListener('click', closeAdminResetPasswordModal);
  document.getElementById('admin-reset-password-modal')?.addEventListener('click', (event) => {
    if (event.target.id === 'admin-reset-password-modal') closeAdminResetPasswordModal();
  });
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
  });
}

function wireAdminUserForm() {
  const form = document.getElementById('admin-create-user-form');
  if (!form || form._wired) return;
  form._wired = true;
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const status = document.getElementById('admin-users-status');
    const payload = {
      username: document.getElementById('admin-new-username').value.trim(),
      display_name: document.getElementById('admin-new-display-name').value.trim(),
      role: document.getElementById('admin-new-role').value,
      password: document.getElementById('admin-new-password').value,
    };
    const result = await db.createUser(payload);
    if (result?.error) {
      status.textContent = result.error;
      return;
    }
    form.reset();
    status.textContent = `Added ${result.display_name}.`;
    await refreshAdminUsersList();
  });
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
  refreshPushStatusUi();
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

function initSettings() {
  buildSettingsModal();
  injectActivityNavLink();
  injectReportsNavLink();
  injectSettingsButton();
  wireAdminUserForm();
  wireAdminUserActions();
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
}

applyStoredSettingsEarly();

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSettings);
} else {
  initSettings();
}