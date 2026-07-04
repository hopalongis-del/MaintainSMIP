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
  if (!listEl) return;
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
  if (title) title.textContent = 'Reset Password';
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
    if (!deleteBtn) return;

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

async function initAdminPage() {
  const user = await db.getCurrentUser();
  if (!user) return;
  window.__currentUser = user;

  if (user.role !== 'admin') {
    window.location.replace('index.html');
    return;
  }

  wireAdminUserForm();
  wireAdminUserActions();
  await refreshAdminUsersList();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAdminPage);
} else {
  initAdminPage();
}