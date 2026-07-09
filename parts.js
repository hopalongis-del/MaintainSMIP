let partsCache = [];
let vendorsCache = [];
let posCache = [];
let canWrite = true;

function money(value) {
  const n = Number(value) || 0;
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}

function formatDate(value) {
  if (!value) return '—';
  if (window.MaintainSMIPSettings?.formatDate) {
    return window.MaintainSMIPSettings.formatDate(value);
  }
  return new Date(value).toLocaleDateString('en-US', {
    month: 'short',
    day: '2-digit',
    year: 'numeric',
  });
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
  document.querySelectorAll('[data-parts-tab]').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.partsTab === tab);
  });
  document.getElementById('inventory-view').classList.toggle('hidden', tab !== 'inventory');
  document.getElementById('vendors-view').classList.toggle('hidden', tab !== 'vendors');
  document.getElementById('pos-view').classList.toggle('hidden', tab !== 'pos');
}

function poStatusBadge(status) {
  const s = (status || 'draft').replace('_', ' ');
  return `<span class="badge badge-po-${status || 'draft'}">${s}</span>`;
}

async function refreshStats() {
  try {
    const stats = await db.getPartsStats();
    document.getElementById('count-parts').textContent = stats.active_parts ?? 0;
    document.getElementById('count-low-stock').textContent = stats.low_stock ?? 0;
    document.getElementById('count-vendors').textContent = stats.active_vendors ?? 0;
    document.getElementById('count-draft-pos').textContent = stats.draft_pos ?? 0;
    document.getElementById('count-inv-value').textContent = money(stats.inventory_value);
  } catch (err) {
    console.error(err);
  }
}

function fillVendorSelect(selectEl, selected = '') {
  if (!selectEl) return;
  const options = vendorsCache
    .filter((v) => v.active !== false)
    .map((v) => `<option value="${v.id}">${escapeHtml(v.name)}</option>`)
    .join('');
  selectEl.innerHTML = `<option value="">— None —</option>${options}`;
  if (selected !== '' && selected != null) selectEl.value = String(selected);
}

function escapeHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function loadVendors() {
  vendorsCache = await db.getVendors({ active: '1' });
  const filter = document.getElementById('part-filter-vendor');
  const current = filter.value;
  filter.innerHTML = '<option value="all">All</option>' +
    vendorsCache.map((v) => `<option value="${v.id}">${escapeHtml(v.name)}</option>`).join('');
  if (current) filter.value = current;
  fillVendorSelect(document.getElementById('part-vendor'));
}

async function loadParts() {
  const search = document.getElementById('part-filter-search').value.trim();
  const stock = document.getElementById('part-filter-stock').value;
  const vendor = document.getElementById('part-filter-vendor').value;
  const params = { active: '1' };
  if (search) params.search = search;
  if (stock === 'low') params.low_stock = '1';
  if (vendor && vendor !== 'all') params.vendor_id = vendor;
  partsCache = await db.getParts(params);
  renderPartsTable();
}

function renderPartsTable() {
  const tbody = document.getElementById('parts-tbody');
  const empty = document.getElementById('parts-empty');
  tbody.innerHTML = '';
  if (!partsCache.length) {
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  partsCache.forEach((part) => {
    const tr = document.createElement('tr');
    const low = part.needs_reorder;
    tr.innerHTML = `
      <td data-label="Part #">${escapeHtml(part.part_number || '—')}</td>
      <td data-label="Description">${escapeHtml(part.description)}</td>
      <td data-label="Vendor">${escapeHtml(part.vendor_name || '—')}</td>
      <td data-label="On Hand" class="${low ? 'stock-low' : 'stock-ok'}">${part.on_hand}${low ? ' ⚠' : ''}</td>
      <td data-label="Reorder">${part.reorder_point} / ${part.reorder_qty}</td>
      <td data-label="Cost / Sell">${money(part.unit_cost)} / ${money(part.unit_price || part.unit_cost)}</td>
      <td data-label="Location">${escapeHtml(part.location || '—')}</td>
      <td class="row-actions" data-label="">
        ${canWrite ? `
          <button class="btn secondary" type="button" data-edit-part="${part.id}">Edit</button>
          <button class="btn secondary" type="button" data-adjust-part="${part.id}">Adjust</button>
        ` : ''}
      </td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll('[data-edit-part]').forEach((btn) => {
    btn.addEventListener('click', () => openPartEditor(Number(btn.dataset.editPart)));
  });
  tbody.querySelectorAll('[data-adjust-part]').forEach((btn) => {
    btn.addEventListener('click', () => openAdjust(Number(btn.dataset.adjustPart)));
  });
}

function openPartEditor(partId = null) {
  const part = partId ? partsCache.find((p) => p.id === partId) : null;
  document.getElementById('part-modal-title').textContent = part ? 'Edit Part' : 'Add Part';
  document.getElementById('part-id').value = part ? part.id : '';
  document.getElementById('part-number').value = part?.part_number || '';
  document.getElementById('part-description').value = part?.description || '';
  document.getElementById('part-category').value = part?.category || '';
  fillVendorSelect(document.getElementById('part-vendor'), part?.vendor_id ?? '');
  document.getElementById('part-vendor-pn').value = part?.vendor_part_number || '';
  document.getElementById('part-uom').value = part?.unit_of_measure || 'each';
  document.getElementById('part-cost').value = part?.unit_cost ?? 0;
  document.getElementById('part-price').value = part?.unit_price ?? part?.unit_cost ?? 0;
  document.getElementById('part-on-hand').value = part?.on_hand ?? 0;
  document.getElementById('part-reorder-point').value = part?.reorder_point ?? 0;
  document.getElementById('part-reorder-qty').value = part?.reorder_qty ?? 0;
  document.getElementById('part-location').value = part?.location || '';
  document.getElementById('part-active').checked = part ? !!part.active : true;
  document.getElementById('part-notes').value = part?.notes || '';
  openModal('part-modal');
}

function openAdjust(partId) {
  const part = partsCache.find((p) => p.id === partId);
  if (!part) return;
  document.getElementById('adjust-part-id').value = partId;
  document.getElementById('adjust-part-label').textContent =
    `${part.part_number || part.description} — on hand: ${part.on_hand}`;
  document.getElementById('adjust-delta').value = '';
  document.getElementById('adjust-note').value = '';
  openModal('adjust-modal');
}

async function savePart(event) {
  event.preventDefault();
  const id = document.getElementById('part-id').value;
  const vendorVal = document.getElementById('part-vendor').value;
  const payload = {
    part_number: document.getElementById('part-number').value.trim(),
    description: document.getElementById('part-description').value.trim(),
    category: document.getElementById('part-category').value.trim(),
    vendor_id: vendorVal ? Number(vendorVal) : null,
    vendor_part_number: document.getElementById('part-vendor-pn').value.trim(),
    unit_of_measure: document.getElementById('part-uom').value.trim() || 'each',
    unit_cost: Number(document.getElementById('part-cost').value) || 0,
    unit_price: Number(document.getElementById('part-price').value) || 0,
    on_hand: Number(document.getElementById('part-on-hand').value) || 0,
    reorder_point: Number(document.getElementById('part-reorder-point').value) || 0,
    reorder_qty: Number(document.getElementById('part-reorder-qty').value) || 0,
    location: document.getElementById('part-location').value.trim(),
    active: document.getElementById('part-active').checked,
    notes: document.getElementById('part-notes').value.trim(),
  };
  if (!payload.description) {
    alert('Description is required.');
    return;
  }
  const result = id
    ? await db.updatePart(Number(id), payload)
    : await db.createPart(payload);
  if (result?.error) {
    alert(result.error);
    return;
  }
  closeModal('part-modal');
  await refreshAll();
}

async function saveAdjust(event) {
  event.preventDefault();
  const id = Number(document.getElementById('adjust-part-id').value);
  const delta = Number(document.getElementById('adjust-delta').value);
  const note = document.getElementById('adjust-note').value.trim();
  if (!delta) {
    alert('Enter a non-zero quantity change.');
    return;
  }
  const result = await db.adjustPartStock(id, { delta, note });
  if (result?.error) {
    alert(result.error);
    return;
  }
  closeModal('adjust-modal');
  await refreshAll();
}

async function loadVendorsTable() {
  const search = document.getElementById('vendor-filter-search').value.trim();
  const params = { active: '1' };
  if (search) params.search = search;
  const vendors = await db.getVendors(params);
  const tbody = document.getElementById('vendors-tbody');
  const empty = document.getElementById('vendors-empty');
  tbody.innerHTML = '';
  if (!vendors.length) {
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  vendors.forEach((v) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td data-label="Name">${escapeHtml(v.name)}</td>
      <td data-label="Contact">${escapeHtml(v.contact_name || '—')}</td>
      <td data-label="Email">${escapeHtml(v.email || '—')}</td>
      <td data-label="Phone">${escapeHtml(v.phone || '—')}</td>
      <td data-label="Account #">${escapeHtml(v.account_number || '—')}</td>
      <td data-label="Terms">${escapeHtml(v.default_terms || '—')}</td>
      <td class="row-actions" data-label="">
        ${canWrite ? `<button class="btn secondary" type="button" data-edit-vendor="${v.id}">Edit</button>` : ''}
      </td>
    `;
    tbody.appendChild(tr);
  });
  tbody.querySelectorAll('[data-edit-vendor]').forEach((btn) => {
    btn.addEventListener('click', () => openVendorEditor(Number(btn.dataset.editVendor), vendors));
  });
}

function openVendorEditor(vendorId = null, list = vendorsCache) {
  const vendor = vendorId ? list.find((v) => v.id === vendorId) : null;
  document.getElementById('vendor-modal-title').textContent = vendor ? 'Edit Vendor' : 'Add Vendor';
  document.getElementById('vendor-id').value = vendor ? vendor.id : '';
  document.getElementById('vendor-name').value = vendor?.name || '';
  document.getElementById('vendor-contact').value = vendor?.contact_name || '';
  document.getElementById('vendor-email').value = vendor?.email || '';
  document.getElementById('vendor-phone').value = vendor?.phone || '';
  document.getElementById('vendor-account').value = vendor?.account_number || '';
  document.getElementById('vendor-terms').value = vendor?.default_terms || '';
  document.getElementById('vendor-active').checked = vendor ? !!vendor.active : true;
  document.getElementById('vendor-notes').value = vendor?.notes || '';
  openModal('vendor-modal');
}

async function saveVendor(event) {
  event.preventDefault();
  const id = document.getElementById('vendor-id').value;
  const payload = {
    name: document.getElementById('vendor-name').value.trim(),
    contact_name: document.getElementById('vendor-contact').value.trim(),
    email: document.getElementById('vendor-email').value.trim(),
    phone: document.getElementById('vendor-phone').value.trim(),
    account_number: document.getElementById('vendor-account').value.trim(),
    default_terms: document.getElementById('vendor-terms').value.trim(),
    active: document.getElementById('vendor-active').checked,
    notes: document.getElementById('vendor-notes').value.trim(),
  };
  if (!payload.name) {
    alert('Vendor name is required.');
    return;
  }
  const result = id
    ? await db.updateVendor(Number(id), payload)
    : await db.createVendor(payload);
  if (result?.error) {
    alert(result.error);
    return;
  }
  closeModal('vendor-modal');
  await refreshAll();
}

async function loadPos() {
  const status = document.getElementById('po-filter-status').value;
  const params = {};
  if (status && status !== 'all') params.status = status;
  posCache = await db.getPurchaseOrders(params);
  renderPosTable();
}

function renderPosTable() {
  const tbody = document.getElementById('pos-tbody');
  const empty = document.getElementById('pos-empty');
  tbody.innerHTML = '';
  if (!posCache.length) {
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  posCache.forEach((po) => {
    const tr = document.createElement('tr');
    const lineCount = (po.lines || []).length;
    tr.innerHTML = `
      <td data-label="PO #">${escapeHtml(po.po_number || `PO-${po.id}`)}</td>
      <td data-label="Vendor">${escapeHtml(po.vendor_name || '—')}</td>
      <td data-label="Status">${poStatusBadge(po.status)}</td>
      <td data-label="Lines">${lineCount}</td>
      <td data-label="Total">${money(po.total)}</td>
      <td data-label="Requested By">${escapeHtml(po.requested_by || '—')}</td>
      <td data-label="Created">${formatDate(po.created_at)}</td>
      <td class="row-actions" data-label="">
        <button class="btn secondary" type="button" data-view-po="${po.id}">Open</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
  tbody.querySelectorAll('[data-view-po]').forEach((btn) => {
    btn.addEventListener('click', () => openPoDetail(Number(btn.dataset.viewPo)));
  });
}

async function openPoDetail(poId) {
  const po = await db.getPurchaseOrder(poId);
  if (po?.error) {
    alert(po.error);
    return;
  }
  document.getElementById('po-modal-title').textContent = po.po_number || `PO-${po.id}`;
  const lines = (po.lines || [])
    .map(
      (line) => `
      <tr>
        <td>${escapeHtml(line.part_number || '—')}</td>
        <td>${escapeHtml(line.description || '')}</td>
        <td>${line.qty}</td>
        <td>${money(line.unit_cost)}</td>
        <td>${money((Number(line.qty) || 0) * (Number(line.unit_cost) || 0))}</td>
      </tr>`
    )
    .join('');
  const body = document.getElementById('po-detail-body');
  body.innerHTML = `
    <div class="po-meta">
      <span>Vendor: <strong>${escapeHtml(po.vendor_name || '—')}</strong></span>
      <span>Status: ${poStatusBadge(po.status)}</span>
      <span>Total: <strong>${money(po.total)}</strong></span>
      <span>Requested: ${escapeHtml(po.requested_by || '—')}</span>
      ${po.approved_by ? `<span>Approved: ${escapeHtml(po.approved_by)}</span>` : ''}
    </div>
    ${po.notes ? `<p class="hero-sub">${escapeHtml(po.notes)}</p>` : ''}
    <table class="po-lines">
      <thead>
        <tr><th>Part #</th><th>Description</th><th>Qty</th><th>Unit</th><th>Ext</th></tr>
      </thead>
      <tbody>${lines || '<tr><td colspan="5">No lines</td></tr>'}</tbody>
    </table>
    <div class="modal-actions" id="po-actions"></div>
  `;
  const actions = document.getElementById('po-actions');
  if (canWrite && po.status === 'draft') {
    actions.innerHTML = `
      <button class="btn secondary" type="button" data-po-status="cancelled">Cancel</button>
      <button class="btn primary" type="button" data-po-status="approved">Approve</button>
    `;
  } else if (canWrite && po.status === 'approved') {
    actions.innerHTML = `
      <button class="btn secondary" type="button" data-po-status="cancelled">Cancel</button>
      <button class="btn primary" type="button" data-po-status="submitted">Mark Submitted</button>
    `;
  } else if (canWrite && po.status === 'submitted') {
    actions.innerHTML = `
      <button class="btn primary" type="button" data-po-status="received">Mark Received</button>
    `;
  }
  actions?.querySelectorAll('[data-po-status]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const status = btn.dataset.poStatus;
      if (status === 'cancelled' && !confirm('Cancel this purchase order?')) return;
      const result = await db.updatePurchaseOrder(po.id, { status });
      if (result?.error) {
        alert(result.error);
        return;
      }
      if (status === 'received') {
        // Bump on-hand for line parts when received
        for (const line of po.lines || []) {
          if (line.part_id && line.qty) {
            await db.adjustPartStock(line.part_id, {
              delta: Number(line.qty),
              note: `Received on ${po.po_number}`,
            });
          }
        }
      }
      closeModal('po-modal');
      await refreshAll();
    });
  });
  openModal('po-modal');
}

async function createEmptyPo() {
  if (!vendorsCache.length) {
    alert('Add a vendor first.');
    setTab('vendors');
    return;
  }
  const vendorId = vendorsCache[0].id;
  const result = await db.createPurchaseOrder({
    vendor_id: vendorId,
    status: 'draft',
    lines: [],
    notes: 'Manual draft',
  });
  if (result?.error) {
    alert(result.error);
    return;
  }
  setTab('pos');
  await loadPos();
  await openPoDetail(result.id);
}

async function draftFromReorder() {
  const result = await db.createPoFromReorder();
  if (result?.error) {
    alert(result.error);
    return;
  }
  setTab('pos');
  await refreshAll();
  await openPoDetail(result.id);
}

async function refreshAll() {
  await refreshStats();
  await loadVendors();
  await loadParts();
  await loadVendorsTable();
  await loadPos();
}

function wireUi() {
  document.querySelectorAll('[data-parts-tab]').forEach((btn) => {
    btn.addEventListener('click', () => setTab(btn.dataset.partsTab));
  });
  document.querySelectorAll('[data-close-modal]').forEach((btn) => {
    btn.addEventListener('click', () => closeModal(btn.dataset.closeModal));
  });
  document.getElementById('new-part-btn')?.addEventListener('click', () => openPartEditor());
  document.getElementById('new-vendor-btn')?.addEventListener('click', () => openVendorEditor());
  document.getElementById('new-po-btn')?.addEventListener('click', createEmptyPo);
  document.getElementById('draft-reorder-btn')?.addEventListener('click', draftFromReorder);
  document.getElementById('part-form')?.addEventListener('submit', savePart);
  document.getElementById('adjust-form')?.addEventListener('submit', saveAdjust);
  document.getElementById('vendor-form')?.addEventListener('submit', saveVendor);
  document.getElementById('part-filter-search')?.addEventListener('input', () => loadParts());
  document.getElementById('part-filter-stock')?.addEventListener('change', () => loadParts());
  document.getElementById('part-filter-vendor')?.addEventListener('change', () => loadParts());
  document.getElementById('vendor-filter-search')?.addEventListener('input', () => loadVendorsTable());
  document.getElementById('po-filter-status')?.addEventListener('change', () => loadPos());
  document.getElementById('stat-low-stock')?.addEventListener('click', () => {
    document.getElementById('part-filter-stock').value = 'low';
    setTab('inventory');
    loadParts();
  });
}

async function init() {
  wireUi();
  try {
    const me = await db.getCurrentUser();
    canWrite = !me || me.role !== 'readonly';
  } catch (err) {
    canWrite = true;
  }
  if (!canWrite) {
    ['new-part-btn', 'new-vendor-btn', 'new-po-btn', 'draft-reorder-btn'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.classList.add('hidden');
    });
  }
  await refreshAll();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
