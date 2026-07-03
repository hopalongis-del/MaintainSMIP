(function applyStoredThemeEarly() {
  const saved = localStorage.getItem('maintainsmip-theme');
  if (saved) document.documentElement.setAttribute('data-theme', saved);
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
    subtitle: 'Classic Red',
    swatches: ['#0a0e1a', '#1a1f35', '#e11d29', '#e2e8f0'],
  },
];

const THEME_STORAGE_KEY = 'maintainsmip-theme';

function getActiveThemeId() {
  return localStorage.getItem(THEME_STORAGE_KEY) || 'smi-racing';
}

function applyTheme(themeId) {
  document.documentElement.setAttribute('data-theme', themeId);
  localStorage.setItem(THEME_STORAGE_KEY, themeId);
  document.querySelectorAll('[data-theme-option]').forEach((button) => {
    button.classList.toggle('active', button.dataset.themeOption === themeId);
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

function createSettingsGearButton({ floating = false } = {}) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = floating ? 'nav-gear-btn nav-gear-btn--floating' : 'nav-gear-btn';
  button.id = 'open-settings-btn';
  button.setAttribute('aria-label', 'Open settings');
  button.innerHTML = `
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path fill="currentColor" d="M12 15.5A3.5 3.5 0 1 0 12 8.5a3.5 3.5 0 0 0 0 7Zm8.94-2.34-.7-.41a6.8 6.8 0 0 0 .05-.78 6.8 6.8 0 0 0-.05-.78l.7-.41a1 1 0 0 0 .37-1.36l-.67-1.16a1 1 0 0 0-1.27-.44l-.83.34a7.2 7.2 0 0 0-1.35-.78l-.13-.88A1 1 0 0 0 14 4h-1.33a1 1 0 0 0-.99.84l-.13.88c-.48.2-.93.46-1.35.78l-.83-.34a1 1 0 0 0-1.27.44L6.43 7.8a1 1 0 0 0 .37 1.36l.7.41c-.03.26-.05.52-.05.78s.02.52.05.78l-.7.41a1 1 0 0 0-.37 1.36l.67 1.16a1 1 0 0 0 1.27.44l.83-.34c.42.32.87.58 1.35.78l.13.88A1 1 0 0 0 12.67 20H14a1 1 0 0 0 .99-.84l.13-.88c.48-.2.93-.46 1.35-.78l.83.34a1 1 0 0 0 1.27-.44l.67-1.16a1 1 0 0 0-.37-1.36Z"/>
    </svg>
  `;
  return button;
}

function injectSettingsGear() {
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

    navActions.appendChild(createSettingsGearButton());
    return;
  }

  document.body.appendChild(createSettingsGearButton({ floating: true }));
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
  injectSettingsGear();
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