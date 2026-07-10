// Same origin in production (Render); works locally at http://localhost:8000 too.
window.cartData = window.cartData || [];
const API = '';
const LIVE_URL = 'https://maintainsmip.onrender.com';

(function redirectIfLocalFile() {
  if (window.location.protocol !== 'file:') return;
  const page = window.location.pathname.split(/[/\\]/).pop() || 'index.html';
  const path = page === 'index.html' ? '' : `/${page}`;
  const useLocal = new URLSearchParams(window.location.search).get('local') === '1';
  const target = useLocal ? `http://localhost:8000${path || '/'}` : `${LIVE_URL}${path}`;
  window.location.replace(target);
})();

function isLocalFile() {
  return window.location.protocol === 'file:';
}

function isLocalhost() {
  const h = window.location.hostname;
  return h === 'localhost' || h === '127.0.0.1';
}

function isRenderHost() {
  return window.location.hostname.includes('onrender.com');
}

function getOfflineHelp() {
  if (isLocalFile()) {
    return {
      title: 'Open through the web server',
      detail: `Double-click <strong>open-app.bat</strong> for local use, or open <a href="${LIVE_URL}">${LIVE_URL}</a> for the live demo.`,
      retryable: false,
    };
  }
  if (isLocalhost()) {
    return {
      title: 'Server offline',
      detail: 'Run <strong>start.bat</strong> in the project folder, then refresh this page.',
      retryable: true,
    };
  }
  if (isRenderHost()) {
    return {
      title: 'Server waking up',
      detail: 'The live app can take up to a minute to start after being idle. This page will retry automatically — or <a href="#" onclick="location.reload();return false;">refresh now</a>.',
      retryable: true,
    };
  }
  return {
    title: 'Could not reach the API',
    detail: 'Check your connection and refresh the page.',
    retryable: true,
  };
}

async function fetchApi(path, options = {}) {
  const retries = isRenderHost() || isLocalhost() ? 6 : 1;
  const delays = [0, 1500, 2500, 4000, 6000, 10000];
  let lastErr;
  for (let attempt = 0; attempt < retries; attempt++) {
    if (attempt > 0) {
      await new Promise((resolve) => setTimeout(resolve, delays[attempt] || 5000));
    }
    try {
      const response = await fetch(`${API}${path}`, {
        credentials: 'same-origin',
        ...options,
      });
      if (response.status === 401) {
        const next = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.href = `/login.html?next=${next}`;
        return response;
      }
      if (response.status < 500) {
        return response;
      }
      lastErr = new Error(`Server error ${response.status} on ${path}`);
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr;
}

let cartDataPromise = null;

function resetCartCache() {
  cartDataPromise = null;
  window.cartData = [];
}

async function loadCartData() {
  if (!cartDataPromise) {
    cartDataPromise = (async () => {
      try {
        const response = await fetchApi('/api/carts');
        if (response.ok) {
          const carts = await response.json();
          if (Array.isArray(carts)) {
            window.cartData = carts;
          }
        }
      } catch (err) {
        console.error('Could not load fleet carts from API', err);
      }
      window.cartData = window.cartData || [];
      return window.cartData;
    })();
  }
  return cartDataPromise;
}

function userCanWrite() {
  const role = currentUser?.role;
  return Boolean(role && role !== 'readonly');
}

function userIsAdmin() {
  return currentUser?.role === 'admin';
}

const API_FIELD_LABELS = {
  id: 'Cart ID',
  serial: 'Serial',
  model: 'Model',
  year: 'Year',
  location: 'Location',
  status: 'Status',
  title: 'Title',
  description: 'Description',
  cart_id: 'Cart',
};

function escapeCsvValue(value) {
  const text = String(value ?? '');
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function downloadCsv(filename, columns, rows) {
  const header = columns.map((col) => escapeCsvValue(col.label)).join(',');
  const lines = rows.map((row) => (
    columns.map((col) => escapeCsvValue(col.value(row))).join(',')
  ));
  const blob = new Blob([[header, ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

function formatApiError(detail, fallback = "Can't save. Please try again.") {
  if (!detail) return fallback;
  if (typeof detail === 'string') {
    if (/^can'?t save/i.test(detail)) return detail;
    if (/^missing required fields:/i.test(detail)) {
      return `Can't save — ${detail.charAt(0).toLowerCase()}${detail.slice(1)}`;
    }
    return detail;
  }
  if (Array.isArray(detail)) {
    const fields = [];
    for (const item of detail) {
      if (!item || typeof item !== 'object') continue;
      const loc = Array.isArray(item.loc) ? item.loc : [];
      const fieldKey = loc[loc.length - 1];
      const label = API_FIELD_LABELS[fieldKey]
        || (typeof fieldKey === 'string' ? fieldKey.replace(/_/g, ' ') : 'Field');
      if (!fields.includes(label)) fields.push(label);
    }
    if (fields.length) {
      return `Can't save — required field missing: ${fields.join(', ')}`;
    }
    const messages = detail.map((item) => item?.msg).filter(Boolean);
    if (messages.length) return `Can't save — ${messages.join('; ')}`;
  }
  if (typeof detail === 'object' && detail.msg) {
    return `Can't save — ${detail.msg}`;
  }
  return fallback;
}

function parseDeepLinkId(value) {
  if (!value) return null;
  return String(value).replace(/^(WO-|PM-|ACC-)/i, '');
}

function readUrlParams() {
  return new URLSearchParams(window.location.search);
}

let currentUser = null;
let currentUserPromise = null;

function formatAuditTimestamp(value) {
  if (!value) return '';
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: '2-digit',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function entityTypeLabel(type) {
  return {
    work_order: 'Work Order',
    pm_record: 'PM',
    accident: 'Accident',
    cart: 'Fleet',
  }[type] || type;
}

function actionLabel(action) {
  return {
    created: 'Created',
    updated: 'Updated',
    deleted: 'Deleted',
    photo_added: 'Photo added',
    photo_removed: 'Photo removed',
  }[action] || (action || '').replace(/_/g, ' ');
}

function entityRecordHref(entry) {
  const id = entry.entity_id;
  switch (entry.entity_type) {
    case 'work_order':
      return `workorders.html?id=${id}`;
    case 'pm_record':
      return `pm.html?id=${id}`;
    case 'accident':
      return `accidents.html?id=${id}`;
    case 'cart':
      return `index.html?fleet_search=${encodeURIComponent(id)}#fleet`;
    default:
      return null;
  }
}

function renderAuditActivityHtml(entries) {
  if (!entries?.length) {
    return '<p class="hero-sub">No activity recorded yet.</p>';
  }
  return `
    <ul class="audit-list">
      ${entries.map((entry) => `
        <li class="audit-item">
          <div class="audit-item-head">
            <strong>${entry.display_name || 'System'}</strong>
            <span class="audit-item-time">${formatAuditTimestamp(entry.created_at)}</span>
          </div>
          <p class="audit-item-summary">${entry.summary}</p>
        </li>
      `).join('')}
    </ul>
  `;
}

function renderGlobalActivityHtml(entries) {
  if (!entries?.length) {
    return '<div class="empty-state"><h3>No activity found</h3><p>Try widening your filters or make a change to a work order, PM record, accident, or cart.</p></div>';
  }
  return `
    <ul class="audit-list activity-feed">
      ${entries.map((entry) => {
        const href = entityRecordHref(entry);
        const typeLabel = entityTypeLabel(entry.entity_type);
        const recordLink = href
          ? `<a class="activity-entity-link" href="${href}">${typeLabel} #${entry.entity_id}</a>`
          : `<span class="activity-entity-link">${typeLabel} #${entry.entity_id}</span>`;
        return `
          <li class="audit-item activity-row">
            <div class="audit-item-head">
              <strong>${entry.display_name || 'System'}</strong>
              <span class="audit-item-time">${formatAuditTimestamp(entry.created_at)}</span>
            </div>
            <div class="activity-meta">
              <span class="badge activity-type-badge">${typeLabel}</span>
              <span class="badge activity-action-badge">${actionLabel(entry.action)}</span>
              ${recordLink}
            </div>
            <p class="audit-item-summary">${entry.summary}</p>
          </li>
        `;
      }).join('')}
    </ul>
  `;
}

async function loadCurrentUser() {
  if (!currentUserPromise) {
    currentUserPromise = (async () => {
      try {
        const response = await fetchApi('/api/auth/me');
        if (response.ok) {
          currentUser = await response.json();
        } else {
          currentUser = null;
        }
      } catch (err) {
        currentUser = null;
      }
      return currentUser;
    })();
  }
  return currentUserPromise;
}

const db = {
  getOfflineHelp,
  parseDeepLinkId,
  readUrlParams,
  loadCartData,
  resetCartCache,
  userCanWrite,
  userIsAdmin,
  loadCurrentUser,
  getCurrentUser: loadCurrentUser,
  getCachedUser() {
    return currentUser;
  },
  formatAuditTimestamp,
  formatApiError,
  downloadCsv,
  renderAuditActivityHtml,
  renderGlobalActivityHtml,
  entityTypeLabel,
  actionLabel,
  async getAuditLog(filters = {}) {
    const p = new URLSearchParams(filters);
    const r = await fetchApi(`/api/audit?${p}`);
    return r.ok ? r.json() : [];
  },
  async getCarts() {
    const r = await fetchApi('/api/carts');
    return r.ok ? r.json() : [];
  },
  async getCart(id) {
    const r = await fetchApi(`/api/carts/${encodeURIComponent(id)}`);
    return r.ok ? r.json() : null;
  },
  async saveCart(cart) {
    const r = await fetchApi('/api/carts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cart),
    });
    if (!r.ok) {
      let message = `Can't save cart (${r.status})`;
      try {
        const body = await r.json();
        message = formatApiError(body.detail, message);
      } catch (err) {
        /* ignore */
      }
      return { error: message };
    }
    resetCartCache();
    return r.json();
  },
  async updateCart(id, fields) {
    const r = await fetchApi(`/api/carts/${encodeURIComponent(id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(fields),
    });
    if (!r.ok) {
      let message = `Can't save cart (${r.status})`;
      try {
        const body = await r.json();
        message = formatApiError(body.detail, message);
      } catch (err) {
        /* ignore */
      }
      return { error: message };
    }
    resetCartCache();
    return r.json();
  },
  async getWoTemplates() {
    const r = await fetchApi('/api/wo/templates');
    if (!r.ok) {
      console.error('Work order templates request failed', r.status);
      return [];
    }
    return r.json();
  },
  async getWorkOrders(filters = {}) {
    const p = new URLSearchParams(filters);
    const r = await fetchApi(`/api/workorders?${p}`);
    return r.ok ? r.json() : [];
  },
  async saveWorkOrder(wo) {
    const r = await fetchApi('/api/workorders', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(wo)
    });
    if (!r.ok) {
      let detail = `Save failed (${r.status})`;
      try {
        const body = await r.json();
        detail = body.detail || detail;
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },
  async updateWorkOrder(id, fields) {
    const r = await fetchApi(`/api/workorders/${id}`, {
      method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(fields)
    });
    return r.ok ? r.json() : null;
  },
  async getPmTemplates() {
    const r = await fetchApi('/api/pm/templates');
    return r.ok ? r.json() : [];
  },
  async savePmTemplate(t) {
    const r = await fetchApi('/api/pm/templates', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(t)
    });
    return r.ok ? r.json() : null;
  },
  async updatePmTemplate(id, fields) {
    const r = await fetchApi(`/api/pm/templates/${id}`, {
      method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(fields)
    });
    return r.ok ? r.json() : null;
  },
  async getPmRecords(filters = {}) {
    const p = new URLSearchParams(filters);
    const r = await fetchApi(`/api/pm/records?${p}`);
    return r.ok ? r.json() : [];
  },
  async savePmRecord(rec) {
    const r = await fetchApi('/api/pm/records', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(rec)
    });
    return r.ok ? r.json() : null;
  },
  async updatePmRecord(id, fields) {
    const r = await fetchApi(`/api/pm/records/${id}`, {
      method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(fields)
    });
    return r.ok ? r.json() : null;
  },
  async deleteWorkOrder(id) {
    const r = await fetchApi(`/api/workorders/${id}`, { method: 'DELETE' });
    return r.ok;
  },
  async deletePmRecord(id) {
    const r = await fetchApi(`/api/pm/records/${id}`, { method: 'DELETE' });
    return r.ok;
  },
  async getStats() {
    const r = await fetchApi('/api/stats');
    return r.ok ? r.json() : {};
  },
  async getAccidents(filters = {}) {
    const p = new URLSearchParams(filters);
    const r = await fetchApi(`/api/accidents?${p}`);
    return r.ok ? r.json() : [];
  },
  async saveAccident(report) {
    const r = await fetchApi('/api/accidents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(report),
    });
    if (!r.ok) {
      let detail = `Save failed (${r.status})`;
      try {
        const body = await r.json();
        detail = body.detail || detail;
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },
  async updateAccident(id, fields) {
    const r = await fetchApi(`/api/accidents/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(fields),
    });
    return r.ok ? r.json() : null;
  },
  async deleteAccident(id) {
    const r = await fetchApi(`/api/accidents/${id}`, { method: 'DELETE' });
    return r.ok;
  },
  async uploadAccidentPhoto(id, file) {
    const form = new FormData();
    const filename = file.name || 'photo.jpg';
    form.append('file', file, filename);
    const r = await fetchApi(`/api/accidents/${id}/photos`, {
      method: 'POST',
      body: form,
    });
    if (!r.ok) {
      let detail = 'Upload failed';
      try {
        const body = await r.json();
        detail = body.detail || detail;
      } catch (err) {
        /* ignore */
      }
      console.error('Accident photo upload failed:', detail);
      return null;
    }
    return r.json();
  },
  async deleteAccidentPhoto(id, path) {
    const r = await fetchApi(
      `/api/accidents/${id}/photos?path=${encodeURIComponent(path)}`,
      { method: 'DELETE' },
    );
    return r.ok ? r.json() : null;
  },
  async getUsers() {
    const r = await fetchApi('/api/users');
    return r.ok ? r.json() : [];
  },
  async getTeamMembers() {
    const r = await fetchApi('/api/users/team-members');
    return r.ok ? r.json() : [];
  },
  async getAuditUsernames() {
    const r = await fetchApi('/api/audit/usernames');
    return r.ok ? r.json() : [];
  },
  async getPmAutomationRules() {
    const r = await fetchApi('/api/pm/automation-rules');
    return r.ok ? r.json() : [];
  },
  async createPmAutomationRule(payload) {
    const r = await fetchApi('/api/pm/automation-rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail = `Could not save automation rule (${r.status})`;
      try {
        const body = await r.json();
        detail = body.detail || detail;
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },
  async updatePmAutomationRule(ruleId, payload) {
    const r = await fetchApi(`/api/pm/automation-rules/${ruleId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail = `Could not update automation rule (${r.status})`;
      try {
        const body = await r.json();
        detail = body.detail || detail;
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },
  async deletePmAutomationRule(ruleId) {
    const r = await fetchApi(`/api/pm/automation-rules/${ruleId}`, { method: 'DELETE' });
    return r.ok ? r.json() : null;
  },
  async runPmAutomationNow() {
    const r = await fetchApi('/api/pm/automation-rules/run-now', { method: 'POST' });
    if (!r.ok) {
      let detail = `Automation run failed (${r.status})`;
      try {
        const body = await r.json();
        detail = body.detail || detail;
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },
  async importFleetCsv(file) {
    const formData = new FormData();
    formData.append('file', file);
    const r = await fetchApi('/api/admin/fleet-import', {
      method: 'POST',
      body: formData,
    });
    if (!r.ok) {
      let detail = `Fleet import failed (${r.status})`;
      try {
        const body = await r.json();
        detail = body.detail || detail;
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },
  async getBackupInfo() {
    const r = await fetchApi('/api/admin/backup/info');
    return r.ok ? r.json() : null;
  },
  async downloadDatabaseBackup() {
    const r = await fetchApi('/api/admin/backup');
    if (!r.ok) {
      let detail = `Backup failed (${r.status})`;
      try {
        const body = await r.json();
        detail = body.detail || detail;
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }

    const blob = await r.blob();
    const disposition = r.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^";]+)"?/i);
    const filename = match?.[1] || `maintainsmip-backup-${new Date().toISOString().slice(0, 10)}.db`;
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    return { ok: true, filename };
  },
  async restoreDatabaseBackup(file) {
    const formData = new FormData();
    formData.append('file', file);
    const r = await fetchApi('/api/admin/restore', {
      method: 'POST',
      body: formData,
    });
    if (!r.ok) {
      let detail = `Restore failed (${r.status})`;
      try {
        const body = await r.json();
        detail = body.detail || detail;
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },
  async changePassword(currentPassword, newPassword) {
    const r = await fetchApi('/api/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });
    if (!r.ok) {
      let detail = `Password change failed (${r.status})`;
      try {
        const body = await r.json();
        detail = body.detail || detail;
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },
  isPushSupported() {
    return 'serviceWorker' in navigator && 'PushManager' in window && window.isSecureContext;
  },
  urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    return Uint8Array.from([...rawData], (char) => char.charCodeAt(0));
  },
  async ensureServiceWorker() {
    if (!this.isPushSupported()) return null;
    return navigator.serviceWorker.register('/service-worker.js');
  },
  async getPushPublicKey() {
    const r = await fetchApi('/api/push/vapid-public-key');
    return r.ok ? r.json() : null;
  },
  async getPushStatus() {
    const r = await fetchApi('/api/push/status');
    return r.ok ? r.json() : { subscribed: false, subscription_count: 0 };
  },
  async getNotificationPrefs() {
    const r = await fetchApi('/api/notifications/preferences');
    return r.ok ? r.json() : null;
  },
  async syncNotificationPrefs(prefs) {
    const r = await fetchApi('/api/notifications/preferences', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        notify_overdue_wo: Boolean(prefs.notifyOverdueWo),
        notify_pm_due: Boolean(prefs.notifyPmDue),
        notify_accidents: Boolean(prefs.notifyAccidents),
      }),
    });
    return r.ok ? r.json() : null;
  },
  async subscribePush() {
    if (!this.isPushSupported()) {
      return { error: 'Push notifications require HTTPS and a supported browser.' };
    }
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      return { error: 'Notification permission was blocked. Enable it in browser settings.' };
    }
    const registration = await this.ensureServiceWorker();
    await navigator.serviceWorker.ready;
    const keyData = await this.getPushPublicKey();
    if (!keyData?.public_key) {
      return { error: 'Could not load push configuration from the server.' };
    }
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: this.urlBase64ToUint8Array(keyData.public_key),
      });
    }
    const body = subscription.toJSON();
    const r = await fetchApi('/api/push/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      let detail = 'Could not save push subscription.';
      try {
        const payload = await r.json();
        detail = payload.detail || detail;
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },
  async unsubscribePush() {
    if (!this.isPushSupported()) return { unsubscribed: true };
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (!subscription) return { unsubscribed: true };
    const endpoint = subscription.endpoint;
    await fetchApi('/api/push/subscribe', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint }),
    });
    await subscription.unsubscribe();
    return { unsubscribed: true };
  },
  async sendTestPush() {
    const r = await fetchApi('/api/push/test', { method: 'POST' });
    if (!r.ok) {
      let detail = 'Test push failed.';
      try {
        const payload = await r.json();
        detail = payload.detail || detail;
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },
  async createUser(user) {
    const r = await fetchApi('/api/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(user),
    });
    if (!r.ok) {
      let detail = `Create user failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },
  async updateUser(userId, fields) {
    const r = await fetchApi(`/api/users/${userId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(fields),
    });
    if (!r.ok) {
      let detail = `Update user failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },
  async deleteUser(userId) {
    const r = await fetchApi(`/api/users/${userId}`, { method: 'DELETE' });
    if (!r.ok) {
      let detail = `Delete user failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async getPartsStats() {
    const r = await fetchApi('/api/parts/stats');
    if (!r.ok) throw new Error(`Parts stats failed (${r.status})`);
    return r.json();
  },

  async getParts(params = {}) {
    const p = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') p.set(key, value);
    });
    const q = p.toString() ? `?${p}` : '';
    const r = await fetchApi(`/api/parts${q}`);
    if (!r.ok) throw new Error(`Parts list failed (${r.status})`);
    return r.json();
  },

  async getPart(id) {
    const r = await fetchApi(`/api/parts/${id}`);
    if (!r.ok) {
      let detail = `Get part failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async createPart(payload) {
    const r = await fetchApi('/api/parts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail = `Create part failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async updatePart(id, payload) {
    const r = await fetchApi(`/api/parts/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail = `Update part failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async adjustPartStock(id, payload) {
    const r = await fetchApi(`/api/parts/${id}/adjust`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail = `Stock adjust failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async deletePart(id) {
    const r = await fetchApi(`/api/parts/${id}`, { method: 'DELETE' });
    if (!r.ok) {
      let detail = `Delete part failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async getVendors(params = {}) {
    const p = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') p.set(key, value);
    });
    const q = p.toString() ? `?${p}` : '';
    const r = await fetchApi(`/api/vendors${q}`);
    if (!r.ok) throw new Error(`Vendors list failed (${r.status})`);
    return r.json();
  },

  async createVendor(payload) {
    const r = await fetchApi('/api/vendors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail = `Create vendor failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async updateVendor(id, payload) {
    const r = await fetchApi(`/api/vendors/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail = `Update vendor failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async getPurchaseOrders(params = {}) {
    const p = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') p.set(key, value);
    });
    const q = p.toString() ? `?${p}` : '';
    const r = await fetchApi(`/api/purchase-orders${q}`);
    if (!r.ok) throw new Error(`PO list failed (${r.status})`);
    return r.json();
  },

  async getPurchaseOrder(id) {
    const r = await fetchApi(`/api/purchase-orders/${id}`);
    if (!r.ok) {
      let detail = `Get PO failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async createPurchaseOrder(payload) {
    const r = await fetchApi('/api/purchase-orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail = `Create PO failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async updatePurchaseOrder(id, payload) {
    const r = await fetchApi(`/api/purchase-orders/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail = `Update PO failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async createPoFromReorder(vendorId = null) {
    const q = vendorId != null ? `?vendor_id=${encodeURIComponent(vendorId)}` : '';
    const r = await fetchApi(`/api/purchase-orders/from-reorder${q}`, { method: 'POST' });
    if (!r.ok) {
      let detail = `Reorder PO failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async getLeaseStats() {
    const r = await fetchApi('/api/lease/stats');
    if (!r.ok) throw new Error(`Lease stats failed (${r.status})`);
    return r.json();
  },

  async getLeaseUnits(params = {}) {
    const p = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') p.set(key, value);
    });
    const q = p.toString() ? `?${p}` : '';
    const r = await fetchApi(`/api/lease/units${q}`);
    if (!r.ok) throw new Error(`Lease units failed (${r.status})`);
    return r.json();
  },

  async createLeaseUnit(payload) {
    const r = await fetchApi('/api/lease/units', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail = `Create lease unit failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async updateLeaseUnit(id, payload) {
    const r = await fetchApi(`/api/lease/units/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail = `Update lease unit failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async getLeases(params = {}) {
    const p = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') p.set(key, value);
    });
    const q = p.toString() ? `?${p}` : '';
    const r = await fetchApi(`/api/leases${q}`);
    if (!r.ok) throw new Error(`Leases list failed (${r.status})`);
    return r.json();
  },

  async createLease(payload) {
    const r = await fetchApi('/api/leases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail = `Create lease failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async returnLease(id, payload = {}) {
    const r = await fetchApi(`/api/leases/${id}/return`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail = `Return lease failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async getSalesStats() {
    const r = await fetchApi('/api/sales/stats');
    if (!r.ok) throw new Error(`Sales stats failed (${r.status})`);
    return r.json();
  },

  async getSales(params = {}) {
    const p = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') p.set(key, value);
    });
    const q = p.toString() ? `?${p}` : '';
    const r = await fetchApi(`/api/sales${q}`);
    if (!r.ok) throw new Error(`Sales list failed (${r.status})`);
    return r.json();
  },

  async createSale(payload) {
    const r = await fetchApi('/api/sales', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail = `Sale failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async voidSale(id) {
    const r = await fetchApi(`/api/sales/${id}/void`, { method: 'POST' });
    if (!r.ok) {
      let detail = `Void sale failed (${r.status})`;
      try {
        const body = await r.json();
        detail = formatApiError(body.detail, detail);
      } catch (err) {
        /* ignore */
      }
      return { error: detail };
    }
    return r.json();
  },

  async getCartTimeline(cartId) {
    const r = await fetchApi(`/api/carts/${cartId}/timeline`);
    if (!r.ok) throw new Error(`Cart timeline failed (${r.status})`);
    return r.json();
  },
};