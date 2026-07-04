function parseArrayInput(value) {
  return value
    .split(',')
    .map(item => item.trim())
    .filter(Boolean);
}

async function getLinkedWorkOrders(ids) {
  if (!Array.isArray(ids) || ids.length === 0) return [];
  const workOrders = await db.getWorkOrders();
  return workOrders.filter(wo => ids.includes(wo.id));
}

function getFleetCarts() {
  return window.cartData || (typeof cartData !== 'undefined' ? cartData : []) || [];
}

function getLocations() {
  const carts = getFleetCarts();
  const set = new Set(carts.map(cart => cart.location).filter(Boolean));
  return Array.from(set).sort();
}

function formatPmDate(value) {
  if (window.MaintainSMIPSettings?.formatDate) {
    return window.MaintainSMIPSettings.formatDate(value);
  }
  if (!value) return 'N/A';
  return new Date(value).toLocaleDateString('en-US', {
    month: 'short',
    day: '2-digit',
    year: 'numeric'
  });
}

function isDueThisWeek(dateValue) {
  if (window.MaintainSMIPSettings?.isPmDueSoon) {
    return window.MaintainSMIPSettings.isPmDueSoon(dateValue);
  }
  const date = new Date(dateValue);
  const now = new Date();
  const diffDays = Math.ceil((date - now) / (1000 * 60 * 60 * 24));
  return diffDays >= 0 && diffDays <= 7;
}

function updatePmPageLabels() {
  const label = window.MaintainSMIPSettings?.getPmDueLabel?.() || 'Due This Week';
  const dueLabel = document.getElementById('pm-due-window-label');
  if (dueLabel) dueLabel.textContent = label;
}

function isOverdue(record) {
  if (!record.scheduled_date) return false;
  const now = new Date();
  return new Date(record.scheduled_date) < now && record.status !== 'completed' && record.status !== 'skipped';
}

function isCompletedThisMonth(record) {
  if (record.status !== 'completed' || !record.completed_date) return false;
  const date = new Date(record.completed_date);
  const now = new Date();
  return date.getMonth() === now.getMonth() && date.getFullYear() === now.getFullYear();
}

function applyPmUrlState() {
  const params = db.readUrlParams();
  window.__pmDueWeekFilter = false;
  window.__pmCompletedMonthFilter = false;

  if (params.get('status')) {
    document.getElementById('pm-filter-status').value = params.get('status');
  }
  if (params.get('due') === 'week') {
    window.__pmDueWeekFilter = true;
    document.getElementById('pm-filter-status').value = 'all';
    setScheduleTab();
  }
  if (params.get('completed') === 'month') {
    window.__pmCompletedMonthFilter = true;
    document.getElementById('pm-filter-status').value = 'all';
    setScheduleTab();
  }
  if (params.get('location')) {
    document.getElementById('pm-filter-location').value = params.get('location');
  }
  return db.parseDeepLinkId(params.get('id'));
}

function applyPmStatFilter(filter) {
  window.__pmDueWeekFilter = filter.due === 'week';
  window.__pmCompletedMonthFilter = filter.completed === 'month';
  document.getElementById('pm-filter-status').value = filter.status || 'all';
  setScheduleTab();
  renderPmSchedule();
  document.getElementById('pm-list')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function wirePmStatCards() {
  document.querySelectorAll('#pm-dashboard-strip [data-pm-filter]').forEach(card => {
    const activate = () => applyPmStatFilter(JSON.parse(card.dataset.pmFilter));
    card.addEventListener('click', activate);
    card.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        activate();
      }
    });
  });
}

function getRecordStatusLabel(record) {
  if (isOverdue(record)) return 'overdue';
  return record.status;
}

function getRecordClass(record) {
  const status = getRecordStatusLabel(record);
  if (status === 'overdue') return 'status-on_hold';
  if (status === 'scheduled') return 'status-open';
  if (status === 'in_progress') return 'status-in_progress';
  if (status === 'completed') return 'status-completed';
  if (status === 'skipped') return 'status-on_hold';
  return 'status-open';
}

function renderPmRecord(record) {
  const card = document.createElement('button');
  card.type = 'button';
  card.className = 'pm-record';
  card.innerHTML = `
    <div class="record-meta">
      <span><strong>${record.id}</strong></span>
      <span>${record.template_name}</span>
      <span>Cart #${record.cart_id}</span>
      <span>${formatPmDate(record.scheduled_date)}</span>
      <span class="badge ${getRecordClass(record)}">${getRecordStatusLabel(record).replace('_', ' ')}</span>
    </div>
    <p>${record.description}</p>
  `;
  card.addEventListener('click', () => openPmDetail(record.id));
  return card;
}

function updatePmFilters() {
  const select = document.getElementById('pm-filter-location');
  select.innerHTML = '<option value="all">All</option>';
  getLocations().forEach(location => {
    const option = document.createElement('option');
    option.value = location;
    option.textContent = location;
    select.appendChild(option);
  });
}

async function renderPmSchedule() {
  const list = document.getElementById('pm-list');
  const statusFilter = document.getElementById('pm-filter-status').value;
  const locationFilter = document.getElementById('pm-filter-location').value;
  const searchTerm = document.getElementById('pm-filter-search').value.trim().toLowerCase();

  const records = (await db.getPmRecords()).sort((a, b) => new Date(a.scheduled_date) - new Date(b.scheduled_date));
  const filtered = records.filter(record => {
    if (window.__pmDueWeekFilter) {
      if (record.status !== 'scheduled' || !isDueThisWeek(record.scheduled_date)) return false;
    }
    if (window.__pmCompletedMonthFilter && !isCompletedThisMonth(record)) return false;
    if (statusFilter !== 'all' && getRecordStatusLabel(record) !== statusFilter) return false;
    if (locationFilter !== 'all' && record.location !== locationFilter) return false;
    if (searchTerm) {
      return (`${record.id} ${record.template_name} ${record.cart_id}`.toLowerCase()).includes(searchTerm);
    }
    return true;
  });

  list.innerHTML = '';
  if (filtered.length === 0) {
    list.innerHTML = `<div class="empty-state"><h3>No PM records yet</h3><p>Use a template to create scheduled maintenance for fleet carts.</p></div>`;
    return;
  }

  filtered.forEach(record => list.appendChild(renderPmRecord(record)));
}

async function renderPmDetail(record) {
  const panel = document.getElementById('pm-detail-panel');
  const linkedWos = await getLinkedWorkOrders(record.linked_wo_ids || []);

  panel.classList.remove('hidden');
  panel.innerHTML = `
    <div class="detail-card">
      <h3>${record.id}</h3>
      <p><strong>${record.template_name}</strong></p>
      <p>${record.description}</p>
      <div class="record-meta">
        <span>Cart #${record.cart_id}</span>
        <span>${record.location}</span>
        <span>${formatPmDate(record.scheduled_date)}</span>
        ${record.completed_date ? `<span>Completed ${formatPmDate(record.completed_date)}</span>` : ''}
        ${record.tech_name ? `<span>Tech: ${record.tech_name}</span>` : ''}
      </div>
    </div>
    <div class="detail-card" id="pm-linked-wos">
      <h3>Linked Work Orders</h3>
      ${linkedWos.length === 0
        ? '<p>No linked work orders.</p>'
        : linkedWos.map(wo => `<p><a class="section-title-link" href="workorders.html?id=${wo.id}"><strong>WO-${wo.id}</strong> — ${wo.title}</a> <span class="badge status-${wo.status}">${wo.status.replace('_', ' ')}</span></p>`).join('')}
    </div>
    <div class="detail-card">
      <h3>Checklist</h3>
      <form id="pm-checklist-form">
        <div style="margin-bottom:12px;">
          <label>Technician
            <select id="pm-tech-select" style="margin-top:6px;">
              <option value="">— Select tech —</option>
              ${['Gavin Weinmeister','Kevin Stellman','Cory Yeager','Mike Casady','Dusty Hixson','Brian Lachance','Chelsie','Stephen Hering','Mark Hixson'].map(t => `<option${(record.tech_name||'')===t?' selected':''}>${t}</option>`).join('')}
            </select>
          </label>
        </div>
        <div class="checklist" id="pm-detail-checklist"></div>
        <div class="modal-actions">
          <button class="btn ghost" type="button" id="pm-delete-record" style="color:#f87171;">Delete</button>
          <button class="btn secondary" type="button" id="pm-fail-wos">Create WO for failed items</button>
          <button class="btn secondary" type="button" id="pm-skip-record">Skip PM</button>
          <button class="btn primary" type="submit">Save Checklist</button>
        </div>
      </form>
    </div>
  `;

  const checklistContainer = document.getElementById('pm-detail-checklist');
  (record.checklist_results || []).forEach(result => {
    const row = document.createElement('div');
    row.className = 'checklist-item';
    row.innerHTML = `
      <label><input type="checkbox" data-task-id="${result.task_id}" ${result.passed ? 'checked' : ''}/> ${result.task}</label>
      <input type="text" data-task-note="${result.task_id}" placeholder="Note" value="${result.note || ''}" />
    `;
    checklistContainer.appendChild(row);
  });

  document.getElementById('pm-checklist-form').addEventListener('submit', event => {
    event.preventDefault();
    savePmChecklist(record.id);
  });

  document.getElementById('pm-delete-record').addEventListener('click', () => deletePmRecord(record.id));
  document.getElementById('pm-fail-wos').addEventListener('click', () => createWoFromPm(record.id));
  document.getElementById('pm-skip-record').addEventListener('click', () => skipPmRecord(record.id));

  const auditEntries = await db.getAuditLog({ entity_type: 'pm_record', entity_id: record.id, limit: 20 });
  panel.insertAdjacentHTML('beforeend', `
    <div class="detail-card">
      <h3>Activity</h3>
      ${db.renderAuditActivityHtml(auditEntries)}
    </div>
  `);
}

async function savePmChecklist(recordId) {
  const records = await db.getPmRecords();
  const record = records.find(r => String(r.id) === String(recordId));
  if (!record) return;

  const items = Array.from(document.querySelectorAll('#pm-detail-checklist .checklist-item')).map(el => {
    const taskId = Number(el.querySelector('input[type=checkbox]').dataset.taskId);
    const passed = el.querySelector('input[type=checkbox]').checked;
    const note = el.querySelector('input[type=text]').value.trim();
    const templateTask = record.checklist_results.find(item => item.task_id === taskId);
    return {
      task_id: taskId,
      task: templateTask.task,
      passed,
      note
    };
  });

  const status = items.every(item => item.passed) ? 'completed' : 'in_progress';
  const completed_date = status === 'completed' ? new Date().toISOString() : null;
  const tech_name = document.getElementById('pm-tech-select')?.value || '';

  await db.updatePmRecord(recordId, {
    checklist_results: items,
    status,
    completed_date,
    tech_name
  });

  await renderPmSchedule();
  await updatePmDashboard();
  const updated = (await db.getPmRecords()).find(r => r.id === recordId);
  if (updated) await renderPmDetail(updated);
}

async function skipPmRecord(recordId) {
  await db.updatePmRecord(recordId, { status: 'skipped', completed_date: null });
  await renderPmSchedule();
  await updatePmDashboard();
  const record = (await db.getPmRecords()).find(r => r.id === recordId);
  if (record) await renderPmDetail(record);
}

async function createWoFromPm(recordId) {
  const records = await db.getPmRecords();
  const record = records.find(r => String(r.id) === String(recordId));
  if (!record) return;

  const failed = (record.checklist_results || []).filter(item => !item.passed);
  if (failed.length === 0) {
    alert('No failed checklist items to create a work order for.');
    return;
  }

  const description = failed.map(item => `${item.task}: ${item.note || 'Needs attention'}`).join('\n');
  const newWo = await db.saveWorkOrder({
    cart_id: record.cart_id,
    title: `PM follow-up for ${record.template_name}`,
    description,
    priority: 'high',
    status: 'open',
    type: 'repair',
    assigned_to: '',
    location: record.location,
    due_date: new Date().toISOString(),
    labor_minutes: 0,
    parts_used: [],
    comments: []
  });

  if (!newWo) {
    alert('Failed to create work order.');
    return;
  }

  const linkedIds = [...(record.linked_wo_ids || []), newWo.id];
  await db.updatePmRecord(recordId, { linked_wo_ids: linkedIds });

  alert(`Created work order ${newWo.id} and linked it to the PM record.`);
  await updatePmDashboard();
  const updated = (await db.getPmRecords()).find(r => r.id === recordId);
  if (updated) await renderPmDetail(updated);
}

async function deletePmRecord(id) {
  if (!confirm('Delete this PM record? This cannot be undone.')) return;
  await db.deletePmRecord(id);
  document.getElementById('pm-detail-panel').classList.add('hidden');
  await renderPmSchedule();
  await updatePmDashboard();
}

async function openPmDetail(recordId) {
  const records = await db.getPmRecords();
  const record = records.find(r => String(r.id) === String(recordId));
  if (!record) return;
  await renderPmDetail(record);
}

function getTemplateMatches(template, cart) {
  const appliesTo = typeof template.applies_to === 'string'
    ? JSON.parse(template.applies_to)
    : template.applies_to;
  const matchesModel = appliesTo.all || appliesTo.models.length === 0 || appliesTo.models.includes(cart.model);
  const matchesLocation = appliesTo.all || appliesTo.locations.length === 0 || appliesTo.locations.includes(cart.location);
  return matchesModel && matchesLocation;
}

function calculateNextScheduledDate(template) {
  const now = new Date();
  const days = Number(template.interval_value) || 90;
  return new Date(now.valueOf() + days * 24 * 60 * 60 * 1000).toISOString();
}

async function applyTemplateToFleet(templateId) {
  const templates = await db.getPmTemplates();
  const template = templates.find(t => String(t.id) === String(templateId));
  if (!template) return;

  const checklist = typeof template.checklist === 'string'
    ? JSON.parse(template.checklist)
    : template.checklist;

  const carts = getFleetCarts().filter((cart) => getTemplateMatches(template, cart));
  let created = 0;

  for (const cart of carts) {
    const rec = await db.savePmRecord({
      template_id: template.id,
      template_name: template.name,
      description: template.description,
      cart_id: cart.id,
      location: cart.location,
      scheduled_date: calculateNextScheduledDate(template),
      completed_date: null,
      status: 'scheduled',
      checklist_results: checklist.map(item => ({
        task_id: item.id,
        task: item.task,
        passed: false,
        note: ''
      })),
      tech_name: '',
      labor_minutes: 0,
      linked_wo_ids: []
    });
    if (rec) created += 1;
  }

  await renderPmSchedule();
  await updatePmDashboard();
  alert(`Created ${created} PM records from template ${template.name}.`);
}

function renderTemplateCard(template) {
  const card = document.createElement('div');
  card.className = 'template-card';
  card.innerHTML = `
    <div class="template-meta">
      <span><strong>${template.name}</strong></span>
      <span>${template.description}</span>
      <span>${template.trigger_type.replace('_', ' ')}: ${template.interval_value} days</span>
      <span>${template.active ? 'Active' : 'Inactive'}</span>
    </div>
    <div class="template-actions-row">
      <button class="btn secondary" type="button" data-edit="${template.id}">Edit</button>
      <button class="btn primary" type="button" data-apply="${template.id}">Apply to Fleet</button>
    </div>
  `;
  card.querySelector('[data-edit]').addEventListener('click', () => openTemplateModal(template.id));
  card.querySelector('[data-apply]').addEventListener('click', () => applyTemplateToFleet(template.id));
  return card;
}

async function renderTemplateList() {
  const list = document.getElementById('template-list');
  const templates = await db.getPmTemplates();
  list.innerHTML = '';
  if (templates.length === 0) {
    list.innerHTML = `<div class="empty-state"><h3>No PM templates</h3><p>Create a template to begin scheduling work.</p></div>`;
    return;
  }
  templates.forEach(template => list.appendChild(renderTemplateCard(template)));
}

async function openTemplateModal(templateId) {
  const modal = document.getElementById('pm-modal');
  const title = document.getElementById('pm-modal-title');
  const form = document.getElementById('pm-form');
  document.getElementById('pm-checklist').innerHTML = '';

  if (templateId) {
    const templates = await db.getPmTemplates();
    const template = templates.find(t => String(t.id) === String(templateId));
    const appliesTo = typeof template.applies_to === 'string'
      ? JSON.parse(template.applies_to)
      : template.applies_to;
    const checklist = typeof template.checklist === 'string'
      ? JSON.parse(template.checklist)
      : template.checklist;

    title.textContent = 'Edit Template';
    document.getElementById('pm-name').value = template.name;
    document.getElementById('pm-description').value = template.description;
    document.getElementById('pm-trigger').value = template.trigger_type;
    document.getElementById('pm-interval').value = template.interval_value;
    document.getElementById('pm-applies-all').checked = appliesTo.all;
    document.getElementById('pm-models').value = appliesTo.models.join(', ');
    document.getElementById('pm-locations').value = appliesTo.locations.join(', ');
    checklist.forEach(item => addCheckItem(item.task));
    form.dataset.editing = template.id;
  } else {
    title.textContent = 'Create Template';
    form.reset();
    document.getElementById('pm-applies-all').checked = true;
    addCheckItem('New task');
    delete form.dataset.editing;
  }

  modal.classList.remove('hidden');
}

function addCheckItem(value = '') {
  const checklist = document.getElementById('pm-checklist');
  const itemId = checklist.children.length + 1;
  const row = document.createElement('div');
  row.className = 'checklist-item';
  row.innerHTML = `
    <input type="text" data-task-id="${itemId}" value="${value}" />
    <button class="btn ghost" type="button" data-remove-task>Remove</button>
  `;
  row.querySelector('[data-remove-task]').addEventListener('click', () => row.remove());
  checklist.appendChild(row);
}

function closePmModal() {
  document.getElementById('pm-modal').classList.add('hidden');
}

function serializeTemplateForm() {
  const form = document.getElementById('pm-form');
  const checklist = Array.from(document.querySelectorAll('#pm-checklist .checklist-item input[type=text]')).map((input, index) => ({
    id: index + 1,
    task: input.value.trim() || `Task ${index + 1}`,
    required: true
  }));

  return {
    name: document.getElementById('pm-name').value.trim(),
    description: document.getElementById('pm-description').value.trim(),
    applies_to: {
      models: parseArrayInput(document.getElementById('pm-models').value),
      locations: parseArrayInput(document.getElementById('pm-locations').value),
      all: document.getElementById('pm-applies-all').checked
    },
    trigger_type: document.getElementById('pm-trigger').value,
    interval_value: Number(document.getElementById('pm-interval').value) || 90,
    checklist,
    estimated_labor_minutes: 0,
    active: true
  };
}

async function handleTemplateSave(event) {
  event.preventDefault();
  const form = document.getElementById('pm-form');
  const template = serializeTemplateForm();
  const editingId = form.dataset.editing;

  if (editingId) {
    await db.updatePmTemplate(editingId, template);
  } else {
    await db.savePmTemplate(template);
  }

  await renderTemplateList();
  await updatePmDashboard();
  closePmModal();
}

async function updatePmDashboard() {
  const records = await db.getPmRecords();
  document.getElementById('count-scheduled').textContent = records.filter(r => r.status === 'scheduled').length;
  document.getElementById('count-due-week').textContent = records.filter(r => isDueThisWeek(r.scheduled_date)).length;
  document.getElementById('count-overdue').textContent = records.filter(isOverdue).length;
  const now = new Date();
  document.getElementById('count-completed-month').textContent = records.filter(r => {
    if (r.status !== 'completed' || !r.completed_date) return false;
    const date = new Date(r.completed_date);
    return date.getMonth() === now.getMonth() && date.getFullYear() === now.getFullYear();
  }).length;
}

let automationWizardStep = 1;

function setActivePmTab(tab) {
  const views = {
    schedule: document.getElementById('schedule-view'),
    templates: document.getElementById('templates-view'),
    automation: document.getElementById('automation-view'),
  };
  const tabs = {
    schedule: document.getElementById('tab-schedule'),
    templates: document.getElementById('tab-templates'),
    automation: document.getElementById('tab-automation'),
  };
  Object.entries(views).forEach(([key, el]) => el?.classList.toggle('hidden', key !== tab));
  Object.entries(tabs).forEach(([key, el]) => el?.classList.toggle('active', key === tab));
}

function setScheduleTab() {
  setActivePmTab('schedule');
}

function setTemplatesTab() {
  setActivePmTab('templates');
}

function setAutomationTab() {
  setActivePmTab('automation');
  renderAutomationRules();
}

function formatAutomationScope(rule) {
  if (rule.scope_type === 'all') return 'Entire fleet';
  const values = (rule.scope_values || []).join(', ');
  if (rule.scope_type === 'location') return `Locations: ${values || '—'}`;
  if (rule.scope_type === 'model') return `Models: ${values || '—'}`;
  return rule.scope_type;
}

async function renderAutomationRules() {
  const list = document.getElementById('automation-rules-list');
  if (!list) return;
  const rules = await db.getPmAutomationRules();
  if (!Array.isArray(rules) || rules.length === 0) {
    list.innerHTML = '<div class="empty-state"><h3>No automation rules yet</h3><p>Use the wizard to create your first rule.</p></div>';
    return;
  }
  list.innerHTML = rules.map((rule) => `
    <div class="automation-rule-card" data-rule-id="${rule.id}">
      <div>
        <strong>${rule.name}</strong>
        <p class="hero-sub">${rule.template_id} · ${formatAutomationScope(rule)} · lead ${rule.lead_days} days</p>
        <p class="hero-sub">${rule.enabled ? 'Enabled' : 'Disabled'}${rule.last_run_at ? ` · last run ${formatPmDate(rule.last_run_at)}` : ''}</p>
      </div>
      <div class="template-actions-row">
        <button type="button" class="btn ghost" data-toggle-rule="${rule.id}">${rule.enabled ? 'Disable' : 'Enable'}</button>
        <button type="button" class="btn ghost danger" data-delete-rule="${rule.id}">Delete</button>
      </div>
    </div>
  `).join('');

  list.querySelectorAll('[data-toggle-rule]').forEach((button) => {
    button.addEventListener('click', async () => {
      const rule = rules.find((item) => item.id === Number(button.dataset.toggleRule));
      if (!rule) return;
      await db.updatePmAutomationRule(rule.id, { enabled: !rule.enabled });
      await renderAutomationRules();
    });
  });

  list.querySelectorAll('[data-delete-rule]').forEach((button) => {
    button.addEventListener('click', async () => {
      if (!window.confirm('Delete this automation rule?')) return;
      await db.deletePmAutomationRule(Number(button.dataset.deleteRule));
      await renderAutomationRules();
    });
  });
}

function updateAutomationScopeLabel() {
  const scopeType = document.getElementById('auto-rule-scope-type')?.value || 'all';
  const wrap = document.getElementById('auto-rule-scope-values-wrap');
  const input = document.getElementById('auto-rule-scope-values');
  if (!wrap || !input) return;
  if (scopeType === 'all') {
    wrap.classList.add('hidden');
    input.value = '';
    return;
  }
  wrap.classList.remove('hidden');
  const label = document.getElementById('auto-rule-scope-values-label');
  if (label) {
    label.textContent = scopeType === 'location'
      ? 'Locations (comma-separated)'
      : 'Models (comma-separated)';
  }
}

function showAutomationWizardStep(step) {
  automationWizardStep = step;
  [1, 2, 3, 4].forEach((num) => {
    document.getElementById(`automation-wizard-step-${num}`)?.classList.toggle('hidden', num !== step);
    document.querySelector(`[data-step-label="${num}"]`)?.classList.toggle('active', num === step);
  });
  document.getElementById('automation-wizard-back')?.classList.toggle('hidden', step === 1);
  document.getElementById('automation-wizard-next')?.classList.toggle('hidden', step === 4);
  document.getElementById('automation-wizard-save')?.classList.toggle('hidden', step !== 4);
}

async function openAutomationWizard() {
  const templates = await db.getPmTemplates();
  const select = document.getElementById('auto-rule-template');
  if (select) {
    select.innerHTML = templates.map((template) => `
      <option value="${template.id}">${template.name}</option>
    `).join('');
  }
  document.getElementById('auto-rule-name').value = '';
  document.getElementById('auto-rule-lead-days').value = '14';
  document.getElementById('auto-rule-scope-type').value = 'all';
  updateAutomationScopeLabel();
  document.getElementById('automation-wizard-status').textContent = '';
  showAutomationWizardStep(1);
  document.getElementById('automation-wizard-modal')?.classList.remove('hidden');
}

function closeAutomationWizard() {
  document.getElementById('automation-wizard-modal')?.classList.add('hidden');
}

function parseAutomationScopeValues() {
  const scopeType = document.getElementById('auto-rule-scope-type').value;
  const raw = document.getElementById('auto-rule-scope-values').value;
  if (scopeType === 'all') return [];
  return raw.split(',').map((item) => item.trim()).filter(Boolean);
}

function buildAutomationReviewHtml() {
  const templateId = document.getElementById('auto-rule-template').value;
  const templateName = document.getElementById('auto-rule-template').selectedOptions[0]?.textContent || templateId;
  const scopeType = document.getElementById('auto-rule-scope-type').value;
  const scopeValues = parseAutomationScopeValues();
  const leadDays = document.getElementById('auto-rule-lead-days').value;
  return `
    <p><strong>${document.getElementById('auto-rule-name').value.trim()}</strong></p>
    <p>Template: ${templateName}</p>
    <p>Scope: ${scopeType === 'all' ? 'Entire fleet' : `${scopeType} → ${scopeValues.join(', ')}`}</p>
    <p>Lead time: ${leadDays} days before due date</p>
    <p>Runs automatically once per day. Existing open PM records are not duplicated.</p>
  `;
}

async function saveAutomationRuleFromWizard() {
  const status = document.getElementById('automation-wizard-status');
  const payload = {
    name: document.getElementById('auto-rule-name').value.trim(),
    template_id: document.getElementById('auto-rule-template').value,
    scope_type: document.getElementById('auto-rule-scope-type').value,
    scope_values: parseAutomationScopeValues(),
    lead_days: Number(document.getElementById('auto-rule-lead-days').value || 14),
    enabled: true,
  };
  if (!payload.name) {
    status.textContent = 'Rule name is required.';
    return;
  }
  if (payload.scope_type !== 'all' && payload.scope_values.length === 0) {
    status.textContent = 'Enter at least one scope value or choose entire fleet.';
    return;
  }
  const result = await db.createPmAutomationRule(payload);
  if (result?.error) {
    status.textContent = result.error;
    return;
  }
  closeAutomationWizard();
  setAutomationTab();
  await renderAutomationRules();
}

function showPmApiError(message) {
  document.getElementById('pm-list').innerHTML = `
    <div class="empty-state">
      <h3>Could not load data</h3>
      <p>${message}</p>
    </div>
  `;
}

async function initPmModule() {
  updatePmPageLabels();
  window.addEventListener('maintainsmip-settings-changed', async () => {
    updatePmPageLabels();
    await renderPmSchedule();
    await updatePmDashboard();
  });

  try {
    await db.loadCartData();
    updatePmFilters();
    wirePmStatCards();
    const deepLinkId = applyPmUrlState();
    await renderPmSchedule();
    await renderTemplateList();
    await updatePmDashboard();
    if (deepLinkId) await openPmDetail(deepLinkId);
  } catch (err) {
    const help = db.getOfflineHelp();
    showPmApiError(`<strong>${help.title}</strong><br>${help.detail}`);
    return;
  }

  document.getElementById('tab-schedule').addEventListener('click', setScheduleTab);
  document.getElementById('tab-templates').addEventListener('click', setTemplatesTab);
  document.getElementById('tab-automation')?.addEventListener('click', setAutomationTab);
  document.getElementById('open-automation-wizard')?.addEventListener('click', openAutomationWizard);
  document.getElementById('automation-wizard-close')?.addEventListener('click', closeAutomationWizard);
  document.getElementById('automation-wizard-back')?.addEventListener('click', () => {
    if (automationWizardStep > 1) showAutomationWizardStep(automationWizardStep - 1);
  });
  document.getElementById('automation-wizard-next')?.addEventListener('click', () => {
    const status = document.getElementById('automation-wizard-status');
    if (automationWizardStep === 1 && !document.getElementById('auto-rule-name').value.trim()) {
      status.textContent = 'Enter a rule name.';
      return;
    }
    if (automationWizardStep === 2) {
      const scopeType = document.getElementById('auto-rule-scope-type').value;
      if (scopeType !== 'all' && parseAutomationScopeValues().length === 0) {
        status.textContent = 'Enter at least one scope value.';
        return;
      }
    }
    status.textContent = '';
    if (automationWizardStep === 3) {
      document.getElementById('automation-review-copy').innerHTML = buildAutomationReviewHtml();
    }
    if (automationWizardStep < 4) showAutomationWizardStep(automationWizardStep + 1);
  });
  document.getElementById('automation-wizard-save')?.addEventListener('click', saveAutomationRuleFromWizard);
  document.getElementById('auto-rule-scope-type')?.addEventListener('change', updateAutomationScopeLabel);
  document.getElementById('run-automation-now')?.addEventListener('click', async () => {
    const status = document.getElementById('automation-status');
    status.textContent = 'Running automation…';
    const result = await db.runPmAutomationNow();
    if (result?.error) {
      status.textContent = result.error;
      return;
    }
    status.textContent = `Automation run complete: ${result.created} PM record(s) created, ${result.skipped} skipped.`;
    await renderPmSchedule();
    await updatePmDashboard();
    await renderAutomationRules();
  });
  document.getElementById('pm-filter-status').addEventListener('change', () => {
    window.__pmDueWeekFilter = false;
    window.__pmCompletedMonthFilter = false;
    renderPmSchedule();
  });
  document.getElementById('pm-filter-location').addEventListener('change', () => renderPmSchedule());
  document.getElementById('pm-filter-search').addEventListener('input', () => renderPmSchedule());
  document.getElementById('new-template-btn').addEventListener('click', () => openTemplateModal());
  document.getElementById('add-check-item').addEventListener('click', () => addCheckItem('New task'));
  document.getElementById('pm-modal-close').addEventListener('click', closePmModal);
  document.getElementById('pm-modal-cancel').addEventListener('click', closePmModal);
  document.getElementById('pm-form').addEventListener('submit', handleTemplateSave);
}

initPmModule();