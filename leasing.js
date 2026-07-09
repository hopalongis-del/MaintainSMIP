let unitsCache = [];
let leasesCache = [];
let canWrite = true;

function money(value) {
  return (Number(value) || 0).toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}

function escapeHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatDate(value) {
  if (!value) return '—';
  if (window.MaintainSMIPSettings?.formatDate) {
    return window.MaintainSMIPSettings.formatDate(value);
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
}

function openModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('hidden');
  el.setAttribute('aria-hidden', 'false');
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.add('hidden');
  el.setAttribute('aria-hidden', 'true');
}

function setTab(tab) {
  document.querySelectorAll('[data-lease-tab]').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.leaseTab === tab);
  });
  document.getElementById('leases-view').classList.toggle('hidden', tab !== 'leases');
  document.getElementById('units-view').classList.toggle('hidden', tab !== 'units');
}

function statusBadge(status) {
  const s = status || 'available';
  return `<span class="badge badge-${s}">${escapeHtml(s)}</span>`;
}

async function refreshStats() {
  const stats = await db.getLeaseStats();
  document.getElementById('stat-units').textContent = stats.units ?? 0;
  document.getElementById('stat-available').textContent = stats.available ?? 0;
  document.getElementById('stat-leased').textContent = stats.leased ?? 0;
  document.getElementById('stat-active').textContent = stats.active_leases ?? 0;
}

async function loadUnits() {
  const status = document.getElementById('unit-filter-status').value;
  const search = document.getElementById('unit-filter-search').value.trim();
  const params = {};
  if (status && status !== 'all') params.status = status;
  if (search) params.search = search;
  unitsCache = await db.getLeaseUnits(params);
  const tbody = document.getElementById('units-tbody');
  const empty = document.getElementById('units-empty');
  if (!unitsCache.length) {
    tbody.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  tbody.innerHTML = unitsCache.map((u) => `
    <tr>
      <td><strong>${escapeHtml(u.unit_code)}</strong></td>
      <td>${escapeHtml(u.model || '—')}</td>
      <td>${escapeHtml(u.serial || '—')}</td>
      <td>${escapeHtml(u.condition || '—')}</td>
      <td>${escapeHtml(u.venue || '—')}</td>
      <td>${money(u.daily_rate)}</td>
      <td>${statusBadge(u.status)}</td>
      <td class="row-actions">
        ${canWrite ? `<button class="btn secondary" type="button" data-edit-unit="${u.id}">Edit</button>` : ''}
      </td>
    </tr>
  `).join('');
}

async function loadLeases() {
  const status = document.getElementById('lease-filter-status').value;
  const search = document.getElementById('lease-filter-search').value.trim();
  const params = {};
  if (status && status !== 'all') params.status = status;
  if (search) params.search = search;
  leasesCache = await db.getLeases(params);
  const tbody = document.getElementById('leases-tbody');
  const empty = document.getElementById('leases-empty');
  if (!leasesCache.length) {
    tbody.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  tbody.innerHTML = leasesCache.map((l) => `
    <tr>
      <td><strong>${escapeHtml(l.lease_number || `LS-${l.id}`)}</strong></td>
      <td>
        ${escapeHtml(l.customer_name)}
        ${l.customer_phone ? `<div class="hero-sub">${escapeHtml(l.customer_phone)}</div>` : ''}
      </td>
      <td>${escapeHtml(l.unit_code || '—')}<div class="hero-sub">${escapeHtml(l.unit_model || '')}</div></td>
      <td>${formatDate(l.start_date)}</td>
      <td>${formatDate(l.expected_return)}</td>
      <td>${money(l.daily_rate)}</td>
      <td>${statusBadge(l.status)}</td>
      <td class="row-actions">
        ${canWrite && l.status === 'active'
          ? `<button class="btn primary" type="button" data-return-lease="${l.id}">Return</button>`
          : ''}
      </td>
    </tr>
  `).join('');
}

function openUnitModal(unit = null) {
  document.getElementById('unit-modal-title').textContent = unit ? 'Edit Lease Unit' : 'Add Lease Unit';
  document.getElementById('unit-id').value = unit?.id || '';
  document.getElementById('unit-code').value = unit?.unit_code || '';
  document.getElementById('unit-model').value = unit?.model || '';
  document.getElementById('unit-serial').value = unit?.serial || '';
  document.getElementById('unit-year').value = unit?.year || '';
  document.getElementById('unit-condition').value = unit?.condition || 'good';
  document.getElementById('unit-status').value = unit?.status || 'available';
  document.getElementById('unit-venue').value = unit?.venue || '';
  document.getElementById('unit-rate').value = unit?.daily_rate ?? 75;
  document.getElementById('unit-fleet-id').value = unit?.fleet_cart_id || '';
  document.getElementById('unit-notes').value = unit?.notes || '';
  openModal('unit-modal');
}

async function openLeaseModal() {
  const available = await db.getLeaseUnits({ status: 'available' });
  const select = document.getElementById('lease-unit');
  select.innerHTML = available.length
    ? available.map((u) => (
      `<option value="${u.id}" data-rate="${u.daily_rate}">${escapeHtml(u.unit_code)} — ${escapeHtml(u.model || 'Cart')} (${money(u.daily_rate)}/day)</option>`
    )).join('')
    : '<option value="">No available units</option>';
  document.getElementById('lease-customer').value = '';
  document.getElementById('lease-phone').value = '';
  document.getElementById('lease-email').value = '';
  document.getElementById('lease-start').value = new Date().toISOString().slice(0, 10);
  document.getElementById('lease-expected').value = '';
  document.getElementById('lease-deposit').value = '0';
  document.getElementById('lease-notes').value = '';
  const first = available[0];
  document.getElementById('lease-rate').value = first?.daily_rate ?? 0;
  openModal('lease-modal');
}

function openReturnModal(lease) {
  document.getElementById('return-lease-id').value = lease.id;
  document.getElementById('return-summary').textContent =
    `${lease.lease_number || `LS-${lease.id}`} · ${lease.customer_name} · ${lease.unit_code || 'unit'}`;
  document.getElementById('return-date').value = new Date().toISOString().slice(0, 16);
  document.getElementById('return-total').value = lease.deposit || 0;
  document.getElementById('return-condition').value = '';
  document.getElementById('return-notes').value = '';
  openModal('return-modal');
}

async function init() {
  const user = await db.getCurrentUser();
  canWrite = !user || user.role !== 'readonly';
  if (!canWrite) {
    document.getElementById('new-lease-btn')?.classList.add('hidden');
    document.getElementById('new-unit-btn')?.classList.add('hidden');
  }

  document.querySelectorAll('[data-lease-tab]').forEach((btn) => {
    btn.addEventListener('click', () => setTab(btn.dataset.leaseTab));
  });
  document.querySelectorAll('[data-close-modal]').forEach((btn) => {
    btn.addEventListener('click', () => closeModal(btn.dataset.closeModal));
  });

  document.getElementById('new-unit-btn')?.addEventListener('click', () => openUnitModal());
  document.getElementById('new-lease-btn')?.addEventListener('click', () => openLeaseModal());

  document.getElementById('unit-filter-status')?.addEventListener('change', loadUnits);
  document.getElementById('unit-filter-search')?.addEventListener('input', () => {
    clearTimeout(window.__unitSearchTimer);
    window.__unitSearchTimer = setTimeout(loadUnits, 250);
  });
  document.getElementById('lease-filter-status')?.addEventListener('change', loadLeases);
  document.getElementById('lease-filter-search')?.addEventListener('input', () => {
    clearTimeout(window.__leaseSearchTimer);
    window.__leaseSearchTimer = setTimeout(loadLeases, 250);
  });

  document.getElementById('lease-unit')?.addEventListener('change', (event) => {
    const opt = event.target.selectedOptions[0];
    if (opt?.dataset.rate != null) {
      document.getElementById('lease-rate').value = opt.dataset.rate;
    }
  });

  document.getElementById('units-tbody')?.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-edit-unit]');
    if (!btn) return;
    const unit = unitsCache.find((u) => String(u.id) === String(btn.dataset.editUnit));
    if (unit) openUnitModal(unit);
  });

  document.getElementById('leases-tbody')?.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-return-lease]');
    if (!btn) return;
    const lease = leasesCache.find((l) => String(l.id) === String(btn.dataset.returnLease));
    if (lease) openReturnModal(lease);
  });

  document.getElementById('unit-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const id = document.getElementById('unit-id').value;
    const payload = {
      unit_code: document.getElementById('unit-code').value.trim(),
      model: document.getElementById('unit-model').value.trim(),
      serial: document.getElementById('unit-serial').value.trim(),
      year: document.getElementById('unit-year').value.trim(),
      condition: document.getElementById('unit-condition').value,
      status: document.getElementById('unit-status').value,
      venue: document.getElementById('unit-venue').value.trim(),
      daily_rate: Number(document.getElementById('unit-rate').value) || 0,
      fleet_cart_id: document.getElementById('unit-fleet-id').value.trim() || null,
      notes: document.getElementById('unit-notes').value.trim(),
    };
    const result = id
      ? await db.updateLeaseUnit(id, payload)
      : await db.createLeaseUnit(payload);
    if (result?.error) {
      alert(result.error);
      return;
    }
    closeModal('unit-modal');
    await Promise.all([refreshStats(), loadUnits(), loadLeases()]);
  });

  document.getElementById('lease-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const unitId = Number(document.getElementById('lease-unit').value);
    if (!unitId) {
      alert('Add an available lease unit first.');
      return;
    }
    const payload = {
      unit_id: unitId,
      customer_name: document.getElementById('lease-customer').value.trim(),
      customer_phone: document.getElementById('lease-phone').value.trim(),
      customer_email: document.getElementById('lease-email').value.trim(),
      start_date: document.getElementById('lease-start').value,
      expected_return: document.getElementById('lease-expected').value || '',
      daily_rate: Number(document.getElementById('lease-rate').value) || 0,
      deposit: Number(document.getElementById('lease-deposit').value) || 0,
      notes: document.getElementById('lease-notes').value.trim(),
    };
    const result = await db.createLease(payload);
    if (result?.error) {
      alert(result.error);
      return;
    }
    closeModal('lease-modal');
    setTab('leases');
    await Promise.all([refreshStats(), loadUnits(), loadLeases()]);
  });

  document.getElementById('return-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const id = document.getElementById('return-lease-id').value;
    const rawDate = document.getElementById('return-date').value;
    const payload = {
      actual_return: rawDate ? new Date(rawDate).toISOString() : undefined,
      total_charged: Number(document.getElementById('return-total').value) || 0,
      condition: document.getElementById('return-condition').value || null,
      notes: document.getElementById('return-notes').value.trim(),
    };
    const result = await db.returnLease(id, payload);
    if (result?.error) {
      alert(result.error);
      return;
    }
    closeModal('return-modal');
    await Promise.all([refreshStats(), loadUnits(), loadLeases()]);
  });

  await Promise.all([refreshStats(), loadUnits(), loadLeases()]);
}

init().catch((err) => console.error(err));
