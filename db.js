// Same origin in production (Render); works locally at http://localhost:8000 too.
const API = '';

const db = {
  async getWorkOrders(filters = {}) {
    const p = new URLSearchParams(filters);
    const r = await fetch(`${API}/api/workorders?${p}`);
    return r.ok ? r.json() : [];
  },
  async saveWorkOrder(wo) {
    const r = await fetch(`${API}/api/workorders`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(wo)
    });
    return r.ok ? r.json() : null;
  },
  async updateWorkOrder(id, fields) {
    const r = await fetch(`${API}/api/workorders/${id}`, {
      method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(fields)
    });
    return r.ok ? r.json() : null;
  },
  async getPmTemplates() {
    const r = await fetch(`${API}/api/pm/templates`);
    return r.ok ? r.json() : [];
  },
  async savePmTemplate(t) {
    const r = await fetch(`${API}/api/pm/templates`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(t)
    });
    return r.ok ? r.json() : null;
  },
  async updatePmTemplate(id, fields) {
    const r = await fetch(`${API}/api/pm/templates/${id}`, {
      method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(fields)
    });
    return r.ok ? r.json() : null;
  },
  async getPmRecords(filters = {}) {
    const p = new URLSearchParams(filters);
    const r = await fetch(`${API}/api/pm/records?${p}`);
    return r.ok ? r.json() : [];
  },
  async savePmRecord(rec) {
    const r = await fetch(`${API}/api/pm/records`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(rec)
    });
    return r.ok ? r.json() : null;
  },
  async updatePmRecord(id, fields) {
    const r = await fetch(`${API}/api/pm/records/${id}`, {
      method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(fields)
    });
    return r.ok ? r.json() : null;
  },
  async deleteWorkOrder(id) {
    const r = await fetch(`${API}/api/workorders/${id}`, { method: 'DELETE' });
    return r.ok;
  },
  async deletePmRecord(id) {
    const r = await fetch(`${API}/api/pm/records/${id}`, { method: 'DELETE' });
    return r.ok;
  },
  async getStats() {
    const r = await fetch(`${API}/api/stats`);
    return r.ok ? r.json() : {};
  }
};