(function applyStoredThemeEarly() {
  const saved = localStorage.getItem('maintainsmip-theme') || 'smi-racing';
  document.documentElement.setAttribute('data-theme', saved);
})();

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

const THEME_STORAGE_KEY = 'maintainsmip-theme';

function getActiveThemeId() {
  return localStorage.getItem(THEME_STORAGE_KEY) || 'smi-racing';
}

function applyTheme(themeId) {
  const valid = RACING_THEMES.some((theme) => theme.id === themeId);
  const nextTheme = valid ? themeId : 'smi-racing';
  document.documentElement.setAttribute('data-theme', nextTheme);
  localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
  document.querySelectorAll('[data-theme-option]').forEach((button) => {
    button.classList.toggle('active', button.dataset.themeOption === nextTheme);
  });
}

function buildSettingsModal() {
  if (document.getElementById('settings-modal')) return;

  const themeOptions = RACING_THEMES.map((theme) => `
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
          <h3>Racing Theme</h3>
          <p class="hero-sub">Pick a look for your shop. Your choice is saved on this device.</p>
          <div class="theme-grid" id="theme-grid">${themeOptions}</div>
        </section>

        <section class="settings-section">
          <h3>Change Password</h3>
          <p class="hero-sub">Password updates are coming soon. Use the placeholder fields below for now.</p>
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
      </div>
    </div>
  `);
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
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function closeSettings() {
  const modal = document.getElementById('settings-modal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

function initSettings() {
  buildSettingsModal();
  injectSettingsButton();
  applyTheme(getActiveThemeId());

  document.getElementById('open-settings-btn')?.addEventListener('click', openSettings);
  document.getElementById('settings-close')?.addEventListener('click', closeSettings);
  document.getElementById('settings-modal')?.addEventListener('click', (event) => {
    if (event.target.id === 'settings-modal') closeSettings();
  });

  document.querySelectorAll('[data-theme-option]').forEach((button) => {
    button.addEventListener('click', () => applyTheme(button.dataset.themeOption));
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSettings);
} else {
  initSettings();
}