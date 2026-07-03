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

async function loadCartData() {
  if (!cartDataPromise) {
    cartDataPromise = (async () => {
      try {
        const response = await fetchApi('/api/carts');
        if (response.ok) {
          const carts = await response.json();
          if (Array.isArray(carts) && carts.length) {
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

function parseDeepLinkId(value) {
  if (!value) return null;
  return String(value).replace(/^(WO-|PM-|ACC-)/i, '');
}

function readUrlParams() {
  return new URLSearchParams(window.location.search);
}

const db = {
  getOfflineHelp,
  parseDeepLinkId,
  readUrlParams,
  loadCartData,
  async getCarts() {
    const r = await fetchApi('/api/carts');
    return r.ok ? r.json() : [];
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
};