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

function formatDate(value) {
  if (window.MaintainSMIPSettings?.formatDate) {
    return window.MaintainSMIPSettings.formatDate(value);
  }
  if (!value) return 'N/A';
  const date = new Date(value);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: '2-digit',
    year: 'numeric'
  });
}

function applyUserSettingsToWoForm() {
  const settingsApi = window.MaintainSMIPSettings;
  if (!settingsApi) return;

  const mechanic = settingsApi.getDefaultMechanic?.();
  const location = settingsApi.getDefaultLocation?.();
  const priority = settingsApi.getDefaultPriority?.();

  if (mechanic) {
    document.getElementById('wo-assigned-to').value = mechanic;
  }
  if (location) {
    document.getElementById('wo-location').value = location;
  }
  if (priority) {
    document.getElementById('wo-priority').value = priority;
  }
}

function getDaysAge(dateValue) {
  const date = new Date(dateValue);
  const now = new Date();
  const diff = now - date;
  return Math.max(0, Math.floor(diff / (1000 * 60 * 60 * 24)));
}

function getLocations() {
  const carts = cartData || [];
  const set = new Set(carts.map(cart => cart.location).filter(Boolean));
  return Array.from(set).sort();
}

function getSelectedCart() {
  return selectedWoCart || null;
}

function getPriorityClass(priority) {
  return `priority-${priority}`;
}

function getStatusClass(status) {
  return `status-${status}`;
}

function isWoOverdue(wo) {
  if (!wo.due_date) return false;
  return new Date(wo.due_date) < new Date() && !['completed', 'closed'].includes(wo.status);
}

function applyWoUrlState() {
  const params = db.readUrlParams();
  if (params.get('status')) {
    document.getElementById('filter-status').value = params.get('status');
  }
  if (params.get('overdue') === '1') {
    window.__woOverdueFilter = true;
    document.getElementById('filter-status').value = 'all';
  }
  if (params.get('location')) {
    document.getElementById('filter-location').value = params.get('location');
  }
  if (params.get('search')) {
    document.getElementById('filter-search').value = params.get('search');
  }
  return db.parseDeepLinkId(params.get('id'));
}

function applyWoStatFilter(filter) {
  window.__woOverdueFilter = filter.overdue === '1';
  document.getElementById('filter-status').value = filter.status || 'all';
  renderWoList();
  document.getElementById('wo-list')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function wireWoStatCards() {
  document.querySelectorAll('#wo-dashboard-strip [data-wo-filter]').forEach(card => {
    const activate = () => applyWoStatFilter(JSON.parse(card.dataset.woFilter));
    card.addEventListener('click', activate);
    card.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        activate();
      }
    });
  });
}

function buildWoCard(wo) {
  const progress = countCheckedItems(wo.maintenance_sheet || {});
  const card = document.createElement('button');
  card.type = 'button';
  card.className = 'wo-item';
  card.innerHTML = `
    <div class="wo-item-title">
      <div>
        <h3>WO-${wo.id} — ${wo.title}</h3>
      </div>
      <span class="badge ${getPriorityClass(wo.priority)}">${wo.priority.replace('_', ' ')}</span>
    </div>
    <div class="wo-item-meta">
      <span>Cart #${wo.cart_id}</span>
      <span>${wo.assigned_to || 'Unassigned'}</span>
      <span>Sheet ${progress.done}/${progress.total}</span>
      <span>${formatDate(wo.due_date)}</span>
      <span class="badge ${getStatusClass(wo.status)}">${wo.status.replace('_', ' ')}</span>
    </div>
  `;
  card.addEventListener('click', () => openWoDetail(wo.id));
  return card;
}

async function renderWoList() {
  const listEl = document.getElementById('wo-list');
  const statusFilter = document.getElementById('filter-status').value;
  const priorityFilter = document.getElementById('filter-priority').value;
  const locationFilter = document.getElementById('filter-location').value;
  const typeFilter = document.getElementById('filter-type').value;
  const searchTerm = document.getElementById('filter-search').value.trim().toLowerCase();

  const workOrders = await db.getWorkOrders();
  const filtered = workOrders.filter(wo => {
    if (window.__woOverdueFilter && !isWoOverdue(wo)) return false;
    if (statusFilter !== 'all' && wo.status !== statusFilter) return false;
    if (priorityFilter !== 'all' && wo.priority !== priorityFilter) return false;
    if (typeFilter !== 'all' && wo.type !== typeFilter) return false;
    if (locationFilter !== 'all' && wo.location !== locationFilter) return false;
    if (searchTerm) {
      const searchTarget = `${wo.id} ${wo.cart_id} ${wo.cart_serial}`.toLowerCase();
      return searchTarget.includes(searchTerm);
    }
    return true;
  });

  listEl.innerHTML = '';
  if (filtered.length === 0) {
    listEl.innerHTML = `
      <div class="empty-state">
        <h3>No work orders found</h3>
        <p>Use the button above to create your first work order or adjust filters.</p>
      </div>
    `;
    return;
  }

  filtered.forEach(wo => listEl.appendChild(buildWoCard(wo)));
}

async function updateDashboard() {
  const stats = await db.getStats();
  document.getElementById('count-open').textContent = stats.open_work_orders ?? 0;
  document.getElementById('count-overdue').textContent = stats.overdue_work_orders ?? 0;

  const workOrders = await db.getWorkOrders();
  document.getElementById('count-in-progress').textContent =
    workOrders.filter(wo => wo.status === 'in_progress').length;
  document.getElementById('count-on-hold').textContent =
    workOrders.filter(wo => wo.status === 'on_hold').length;
}

function setLocationFilterOptions() {
  const select = document.getElementById('filter-location');
  select.innerHTML = '<option value="all">All</option>';
  getLocations().forEach(location => {
    const option = document.createElement('option');
    option.value = location;
    option.textContent = location;
    select.appendChild(option);
  });
}

function getCartDisplay(cart) {
  return `Cart #${cart.id} · ${cart.model} · ${cart.location} · ${cart.status}`;
}

function renderCartSelection(filter = '') {
  const list = document.getElementById('wo-cart-list');
  const query = filter.trim().toLowerCase();
  list.innerHTML = '';
  const matches = cartData
    .map((cart, index) => ({ cart, index, label: getCartDisplay(cart) }))
    .filter(item => !query || item.label.toLowerCase().includes(query));

  if (matches.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'cart-card';
    empty.textContent = 'No matching cart found.';
    empty.style.cursor = 'default';
    list.appendChild(empty);
    return;
  }

  matches.slice(0, 40).forEach(item => {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'cart-card';
    card.innerHTML = `
      <div><strong>${item.label}</strong></div>
      <small>Serial: ${item.cart.serial || 'N/A'} · Year: ${item.cart.year || 'unknown'}</small>
    `;
    card.addEventListener('click', () => {
      selectedWoCart = item.cart;
      document.querySelectorAll('.cart-card').forEach(el => el.classList.remove('selected'));
      card.classList.add('selected');
      document.getElementById('wo-location').value = item.cart.location || '';
      document.getElementById('wo-selected-cart').textContent = `Selected cart #${item.cart.id} · ${item.cart.model} · ${item.cart.location}`;
    });
    list.appendChild(card);
  });
}

function toDateInputValue(value) {
  if (!value) return '';
  return String(value).slice(0, 10);
}

function setModalMode(mode) {
  const isEdit = mode === 'edit';
  document.getElementById('wo-modal-eyebrow').textContent = isEdit ? 'Edit Work Order' : 'New Work Order';
  document.getElementById('wo-modal-heading').textContent = isEdit ? 'Update Work Order' : 'Create Work Order';
  document.getElementById('wo-save-btn').textContent = isEdit ? 'Save Changes' : 'Save Work Order';
}

function openModal() {
  editingWoId = null;
  setModalMode('create');
  selectedWoCart = null;
  document.getElementById('wo-form').reset();
  document.getElementById('wo-labor-minutes').value = '0';
  document.getElementById('wo-cart-list').innerHTML = '';
  renderCartSelection();
  document.getElementById('wo-selected-cart').textContent = 'Select a cart to populate work order fields.';
  document.getElementById('wo-location').value = '';
  populateWoTemplateSelect(activeWoTemplate?.id);
  applyTemplateDefaultsToForm(getActiveWoTemplate());
  applyUserSettingsToWoForm();
  document.getElementById('wo-modal').classList.remove('hidden');
}

function openEditModal(wo) {
  editingWoId = wo.id;
  setModalMode('edit');
  selectedWoCart = cartData.find(cart => cart.id === wo.cart_id) || null;

  document.getElementById('wo-title').value = wo.title || '';
  document.getElementById('wo-description').value = wo.description || '';
  document.getElementById('wo-type').value = wo.type || 'repair';
  document.getElementById('wo-priority').value = wo.priority || 'medium';
  document.getElementById('wo-status').value = wo.status || 'open';
  document.getElementById('wo-assigned-to').value = wo.assigned_to || '';
  document.getElementById('wo-location').value = wo.location || '';
  document.getElementById('wo-due-date').value = toDateInputValue(wo.due_date);
  document.getElementById('wo-labor-minutes').value = String(wo.labor_minutes ?? 0);

  renderCartSelection();
  if (selectedWoCart) {
    document.getElementById('wo-selected-cart').textContent =
      `Selected cart #${selectedWoCart.id} · ${selectedWoCart.model} · ${selectedWoCart.location}`;
  } else {
    document.getElementById('wo-selected-cart').textContent =
      `Cart #${wo.cart_id} · ${wo.cart_serial || 'serial unknown'}`;
  }

  document.getElementById('wo-modal').classList.remove('hidden');
}

function closeModal() {
  editingWoId = null;
  document.getElementById('wo-modal').classList.add('hidden');
}

function wireMaintenanceSheetPanel(wo) {
  document.getElementById('sheet-add-part-row')?.addEventListener('click', () => {
    const body = document.getElementById('sheet-parts-body');
    const row = document.createElement('tr');
    row.innerHTML = `
      <td><input type="text" data-part-field="qty" /></td>
      <td><input type="text" data-part-field="part_number" /></td>
      <td><input type="text" data-part-field="description" /></td>
    `;
    body.appendChild(row);
  });

  wireGlobalCheckAll();

  document.getElementById('sheet-save-btn')?.addEventListener('click', async () => {
    const sheet = collectMaintenanceSheetFromDom(wo.maintenance_sheet);
    const mechanic = document.getElementById('sheet-mechanic')?.value?.trim() || '';
    const laborHours = Number(sheet.total_labor_hours || 0);
    const completionDate = document.getElementById('sheet-completion-date')?.value;
    const fields = {
      maintenance_sheet: sheet,
      assigned_to: mechanic,
      labor_minutes: Math.round(laborHours * 60),
      type: sheet.service_type === 'full' ? 'inspection' : 'repair',
    };
    if (sheet.sheet_comments?.trim()) {
      fields.description = sheet.sheet_comments.trim();
    }
    if (sheet.start_date) {
      fields.maintenance_sheet.start_date = sheet.start_date;
    }
    if (completionDate) {
      fields.completed_date = `${completionDate}T12:00:00`;
      fields.status = 'completed';
    } else if (wo.status === 'open' && sheet.checklist.some((item) => item.checked)) {
      fields.status = 'in_progress';
    }
    await db.updateWorkOrder(wo.id, fields);
    await renderWoList();
    await updateDashboard();
    await openWoDetail(wo.id);
  });
}

async function openWoDetail(id) {
  const workOrders = await db.getWorkOrders();
  const wo = workOrders.find(item => String(item.id) === String(id));
  if (!wo) return;

  const panel = document.getElementById('wo-detail-panel');
  panel.classList.add('slide-in');
  panel.innerHTML = `
    <div class="detail-row wo-detail-toolbar">
      <div>
        <span class="eyebrow">${wo.status.replace('_', ' ')}</span>
        <h2>${escapeHtml(wo.title)}</h2>
        <p class="hero-sub">${escapeHtml(wo.description)}</p>
      </div>
      <div class="wo-detail-actions">
        <span class="badge ${getPriorityClass(wo.priority)}">${wo.priority.replace('_', ' ')}</span>
        <button class="btn secondary" type="button" id="btn-edit">Edit Header</button>
        <button class="btn secondary" type="button" id="btn-start">Start</button>
        <button class="btn secondary" type="button" id="btn-complete">Complete</button>
        <button class="btn ghost" type="button" id="btn-delete" style="color:#f87171;">Delete</button>
      </div>
    </div>
    <div class="detail-card">
      ${renderMaintenanceSheetHtml(wo, wo.maintenance_sheet || applyWoTemplate(getActiveWoTemplate()))}
    </div>
  `;

  wireMaintenanceSheetPanel(wo);
  document.getElementById('btn-edit').addEventListener('click', () => openEditModal(wo));
  document.getElementById('btn-start').addEventListener('click', () => updateWoStatus(wo.id, 'in_progress'));
  document.getElementById('btn-complete').addEventListener('click', () => updateWoStatus(wo.id, 'completed'));
  document.getElementById('btn-delete').addEventListener('click', () => deleteWo(wo.id));
}

async function addWoComment(id, existingComments) {
  const text = document.getElementById('wo-new-comment').value.trim();
  if (!text) return;

  const updatedComments = [
    ...existingComments,
    { author: 'Technician', text, date: new Date().toISOString() }
  ];
  await db.updateWorkOrder(id, { comments: updatedComments });
  await openWoDetail(id);
  await updateDashboard();
}

async function deleteWo(id) {
  if (!confirm('Delete this work order? This cannot be undone.')) return;
  await db.deleteWorkOrder(id);
  showDetailPlaceholder();
  await renderWoList();
  await updateDashboard();
}

async function updateWoStatus(id, status) {
  const fields = { status };
  if (status === 'completed') {
    fields.completed_date = new Date().toISOString();
  }
  await db.updateWorkOrder(id, fields);
  await renderWoList();
  await openWoDetail(id);
  await updateDashboard();
}

function serializeForm(forEdit = false) {
  const cart = getSelectedCart();
  const dueDate = document.getElementById('wo-due-date').value;
  const payload = {
    title: document.getElementById('wo-title').value.trim(),
    description: document.getElementById('wo-description').value.trim(),
    priority: document.getElementById('wo-priority').value,
    status: document.getElementById('wo-status').value,
    type: document.getElementById('wo-type').value,
    assigned_to: document.getElementById('wo-assigned-to').value.trim(),
    location: document.getElementById('wo-location').value.trim(),
    due_date: dueDate ? `${dueDate}T00:00:00` : null,
    labor_minutes: Number(document.getElementById('wo-labor-minutes').value || 0),
  };

  if (cart) {
    payload.cart_id = cart.id;
  }

  if (!forEdit) {
    payload.parts_used = [];
    payload.comments = [];
    const template = getActiveWoTemplate();
    payload.maintenance_sheet = applyWoTemplate(template);
    if (!payload.title && template?.default_title) {
      payload.title = template.default_title;
    }
    if (template?.default_type) payload.type = template.default_type;
    if (template?.default_priority) payload.priority = template.default_priority;
  }

  return payload;
}

async function handleWoSave(event) {
  event.preventDefault();
  const cart = getSelectedCart();

  if (editingWoId) {
    if (!cart) {
      alert('Please select the cart for this work order.');
      return;
    }
    const saved = await db.updateWorkOrder(editingWoId, serializeForm(true));
    if (!saved) {
      alert('Failed to save changes.');
      return;
    }
    closeModal();
    await renderWoList();
    await updateDashboard();
    await openWoDetail(editingWoId);
    return;
  }

  if (!cart) {
    alert('Please select a cart for the work order.');
    return;
  }

  const created = await db.saveWorkOrder(serializeForm(false));
  closeModal();
  await renderWoList();
  await updateDashboard();
  if (created?.id) await openWoDetail(created.id);
}

let selectedWoCart = null;
let editingWoId = null;
let woTemplates = [];
let activeWoTemplate = null;

function getActiveWoTemplate() {
  return activeWoTemplate || woTemplates[0] || null;
}

function renderWoTemplateBar() {
  const template = getActiveWoTemplate();
  const nameEl = document.getElementById('wo-template-name');
  const descEl = document.getElementById('wo-template-desc');
  if (!template) {
    nameEl.textContent = 'SMI Maintenance Sheet';
    descEl.textContent = 'Default checklist template used for all new work orders.';
    return;
  }
  nameEl.textContent = template.name;
  descEl.textContent = template.description || 'Used for all new work orders.';
}

function populateWoTemplateSelect(selectedId) {
  const select = document.getElementById('wo-template-select');
  if (!select) return;
  select.innerHTML = woTemplates.map((template) => `
    <option value="${template.id}" ${template.id === selectedId ? 'selected' : ''}>${template.name}</option>
  `).join('');
}

function applyTemplateDefaultsToForm(template = getActiveWoTemplate()) {
  if (!template || editingWoId) return;
  const settingsApi = window.MaintainSMIPSettings;
  const defaultPriority = settingsApi?.getDefaultPriority?.() || template.default_priority || 'medium';
  document.getElementById('wo-title').value = template.default_title || 'Maintenance Service';
  document.getElementById('wo-type').value = template.default_type || 'repair';
  document.getElementById('wo-priority').value = defaultPriority;
  document.getElementById('wo-description').value = template.description || '';
}

async function loadWoTemplates() {
  woTemplates = await db.getWoTemplates();
  const preferredId = window.MaintainSMIPSettings?.getDefaultWoTemplateId?.() || '';
  activeWoTemplate = woTemplates.find((template) => template.id === preferredId) || woTemplates[0] || null;
  renderWoTemplateBar();
  populateWoTemplateSelect(activeWoTemplate?.id);
}

function showDetailPlaceholder() {
  const panel = document.getElementById('wo-detail-panel');
  panel.innerHTML = `
    <div class="empty-state">
      <h3>Select a work order</h3>
      <p>Choose one from the list to view the maintenance sheet, check off items, and save.</p>
    </div>
  `;
}

function showApiError(listId, message) {
  document.getElementById(listId).innerHTML = `
    <div class="empty-state">
      <h3>Could not load data</h3>
      <p>${message}</p>
    </div>
  `;
}

async function initWorkOrders() {
  document.getElementById('wo-template-select')?.addEventListener('change', (event) => {
    activeWoTemplate = woTemplates.find((t) => t.id === event.target.value) || woTemplates[0];
    renderWoTemplateBar();
    applyTemplateDefaultsToForm(activeWoTemplate);
  });

  document.getElementById('new-wo-btn').addEventListener('click', openModal);
  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.getElementById('modal-cancel').addEventListener('click', closeModal);
  document.getElementById('wo-form').addEventListener('submit', handleWoSave);
  document.getElementById('wo-cart-search').addEventListener('input', event => renderCartSelection(event.target.value));
  document.getElementById('filter-priority').addEventListener('change', () => renderWoList());
  document.getElementById('filter-location').addEventListener('change', () => renderWoList());
  document.getElementById('filter-type').addEventListener('change', () => renderWoList());
  document.getElementById('filter-search').addEventListener('input', () => renderWoList());

  document.getElementById('filter-status').addEventListener('change', () => {
    window.__woOverdueFilter = false;
    renderWoList();
  });

  try {
    await loadWoTemplates();
    showDetailPlaceholder();
    setLocationFilterOptions();
    wireWoStatCards();
    const deepLinkId = applyWoUrlState();
    await renderWoList();
    await updateDashboard();
    if (deepLinkId) await openWoDetail(deepLinkId);
  } catch (err) {
    const help = db.getOfflineHelp();
    showApiError('wo-list', `<strong>${help.title}</strong><br>${help.detail}`);
  }
}

initWorkOrders();