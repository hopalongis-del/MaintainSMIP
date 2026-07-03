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
  if (!value) return 'N/A';
  const date = new Date(value);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: '2-digit',
    year: 'numeric'
  });
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
  const card = document.createElement('button');
  card.type = 'button';
  card.className = 'wo-item';
  card.innerHTML = `
    <div class="wo-item-title">
      <div>
        <h3>${wo.id} — ${wo.title}</h3>
      </div>
      <span class="badge ${getPriorityClass(wo.priority)}">${wo.priority.replace('_', ' ')}</span>
    </div>
    <div class="wo-item-meta">
      <span>Cart #${wo.cart_id}</span>
      <span>${wo.assigned_to || 'Unassigned'}</span>
      <span>${formatDate(wo.due_date)}</span>
      <span>${getDaysAge(wo.created_date)} days old</span>
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

async function openWoDetail(id) {
  const workOrders = await db.getWorkOrders();
  const wo = workOrders.find(item => String(item.id) === String(id));
  if (!wo) return;

  const panel = document.getElementById('wo-detail-panel');
  panel.classList.add('slide-in');
  panel.innerHTML = `
    <div class="detail-row">
      <div>
        <span class="eyebrow">${wo.status.replace('_', ' ')}</span>
        <h2>${wo.id}</h2>
        <p>${wo.title}</p>
      </div>
      <div style="text-align:right; display:grid; gap:10px; justify-items:end;">
        <span class="badge ${getPriorityClass(wo.priority)}">${wo.priority.replace('_', ' ')}</span>
        <button class="btn primary" type="button" id="btn-edit">Edit Work Order</button>
      </div>
    </div>
    <div class="detail-card">
      <h3>Cart Details</h3>
      <p>Cart #${wo.cart_id} · ${wo.cart_serial}</p>
      <p>${wo.location}</p>
      <label style="margin-top:10px;">Assigned To
        <select id="wo-reassign" style="margin-top:6px;">
          <option value="">— Unassigned —</option>
          ${TECHNICIANS.map(t => `<option${wo.assigned_to === t ? ' selected' : ''}>${t}</option>`).join('')}
        </select>
      </label>
      <button class="btn secondary" type="button" id="btn-reassign" style="margin-top:8px;">Save Assignment</button>
    </div>
    <div class="detail-card">
      <h3>Description</h3>
      <p>${wo.description}</p>
    </div>
    <div class="detail-row">
      <div class="detail-card">
        <h3>Dates</h3>
        <p>Created: ${formatDate(wo.created_date)}</p>
        <p>Due: ${formatDate(wo.due_date)}</p>
        <p>Completed: ${wo.completed_date ? formatDate(wo.completed_date) : 'N/A'}</p>
      </div>
      <div class="detail-card">
        <h3>Work log</h3>
        <p>Labor: ${wo.labor_minutes} minutes</p>
        <p>Parts used: ${(wo.parts_used || []).length}</p>
        <p>Comments: ${(wo.comments || []).length}</p>
      </div>
    </div>
    <div class="detail-card">
      <h3>Comments</h3>
      ${(wo.comments || []).length === 0 ? '<p>No comments yet.</p>' : wo.comments.map(c => `<p><strong>${c.author}</strong>: ${c.text}</p>`).join('')}
      <div style="margin-top:12px; display:grid; gap:8px;">
        <textarea id="wo-new-comment" rows="3" placeholder="Add a comment..."></textarea>
        <button class="btn secondary" type="button" id="btn-add-comment">Add Comment</button>
      </div>
    </div>
    <div class="detail-card">
      <h3>Actions</h3>
      <div style="display:grid; gap:10px;">
        <button class="btn secondary" type="button" id="btn-start">Start Work</button>
        <button class="btn secondary" type="button" id="btn-hold">Put On Hold</button>
        <button class="btn secondary" type="button" id="btn-complete">Complete</button>
        <button class="btn secondary" type="button" id="btn-close">Close</button>
        <button class="btn ghost" type="button" id="btn-delete" style="color:#f87171;">Delete</button>
      </div>
    </div>
  `;

  document.getElementById('btn-edit').addEventListener('click', () => openEditModal(wo));
  document.getElementById('btn-start').addEventListener('click', () => updateWoStatus(wo.id, 'in_progress'));
  document.getElementById('btn-hold').addEventListener('click', () => updateWoStatus(wo.id, 'on_hold'));
  document.getElementById('btn-complete').addEventListener('click', () => updateWoStatus(wo.id, 'completed'));
  document.getElementById('btn-close').addEventListener('click', () => updateWoStatus(wo.id, 'closed'));
  document.getElementById('btn-reassign').addEventListener('click', async () => {
    const tech = document.getElementById('wo-reassign').value;
    await db.updateWorkOrder(wo.id, { assigned_to: tech });
    await renderWoList();
    await openWoDetail(wo.id);
  });
  document.getElementById('btn-delete').addEventListener('click', () => deleteWo(wo.id));
  document.getElementById('btn-add-comment').addEventListener('click', () => addWoComment(wo.id, wo.comments || []));
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

  await db.saveWorkOrder(serializeForm(false));
  closeModal();
  await renderWoList();
  await updateDashboard();
}

let selectedWoCart = null;
let editingWoId = null;

function showDetailPlaceholder() {
  const panel = document.getElementById('wo-detail-panel');
  panel.innerHTML = `
    <div class="empty-state">
      <h3>Select a work order</h3>
      <p>Choose one from the list to view details, then click <strong>Edit Work Order</strong> to change title, priority, due date, and more.</p>
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