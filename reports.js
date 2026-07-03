const OPEN_WO_STATUSES = new Set(['open', 'in_progress', 'on_hold']);
const CLOSED_WO_STATUSES = new Set(['completed', 'closed']);
const CLOSED_PM_STATUSES = new Set(['completed', 'skipped']);

let locationOptions = ['all'];
let currentReportId = null;
let currentReportState = {
  title: '',
  subtitle: '',
  columns: [],
  rows: [],
  generatedAt: null,
};

function formatReportDate(value) {
  if (window.MaintainSMIPSettings?.formatDate) {
    return window.MaintainSMIPSettings.formatDate(value);
  }
  if (!value) return '';
  return new Date(value).toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
}

function formatReportDateTime(value) {
  if (!value) return '';
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: '2-digit',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function startOfToday() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

function isOverdueDate(value) {
  if (!value) return false;
  return new Date(value) < startOfToday();
}

function isPmDueSoon(dateValue) {
  if (window.MaintainSMIPSettings?.isPmDueSoon) {
    return window.MaintainSMIPSettings.isPmDueSoon(dateValue);
  }
  if (!dateValue) return false;
  const days = window.MaintainSMIPSettings?.getPmDueWindowDays?.() || 7;
  const scheduled = new Date(dateValue);
  const today = startOfToday();
  const diffDays = Math.floor((scheduled - today) / 86400000);
  return diffDays >= 0 && diffDays <= days;
}

function getFilterValues() {
  const values = {};
  document.querySelectorAll('[data-report-filter]').forEach((el) => {
    if (el.type === 'checkbox') {
      values[el.dataset.reportFilter] = el.checked;
    } else {
      values[el.dataset.reportFilter] = el.value;
    }
  });
  return values;
}

function matchesLocation(recordLocation, filterLocation) {
  if (!filterLocation || filterLocation === 'all') return true;
  return (recordLocation || '') === filterLocation;
}

const REPORTS = [
  {
    id: 'open-work-orders',
    title: 'Open Work Orders',
    description: 'All work orders still open, in progress, or on hold.',
    filters: [
      { id: 'location', label: 'Location', type: 'select', optionsKey: 'locations', defaultValue: 'all' },
    ],
    async load(filters) {
      const rows = (await db.getWorkOrders())
        .filter((wo) => OPEN_WO_STATUSES.has(wo.status))
        .filter((wo) => matchesLocation(wo.location, filters.location))
        .sort((a, b) => String(a.due_date || '').localeCompare(String(b.due_date || '')));
      return {
        subtitle: filters.location === 'all' ? 'All locations' : `Location: ${filters.location}`,
        rows,
      };
    },
    columns: [
      { label: 'WO #', value: (r) => r.id },
      { label: 'Cart', value: (r) => r.cart_id },
      { label: 'Title', value: (r) => r.title },
      { label: 'Priority', value: (r) => r.priority },
      { label: 'Status', value: (r) => r.status },
      { label: 'Location', value: (r) => r.location },
      { label: 'Assigned To', value: (r) => r.assigned_to },
      { label: 'Due Date', value: (r) => formatReportDate(r.due_date) },
      { label: 'Created', value: (r) => formatReportDate(r.created_date) },
    ],
  },
  {
    id: 'overdue-work-orders',
    title: 'Overdue Work Orders',
    description: 'Open jobs with a due date in the past.',
    filters: [
      { id: 'location', label: 'Location', type: 'select', optionsKey: 'locations', defaultValue: 'all' },
    ],
    async load(filters) {
      const rows = (await db.getWorkOrders())
        .filter((wo) => !CLOSED_WO_STATUSES.has(wo.status))
        .filter((wo) => isOverdueDate(wo.due_date))
        .filter((wo) => matchesLocation(wo.location, filters.location))
        .sort((a, b) => String(a.due_date || '').localeCompare(String(b.due_date || '')));
      return {
        subtitle: filters.location === 'all' ? 'All locations' : `Location: ${filters.location}`,
        rows,
      };
    },
    columns: [
      { label: 'WO #', value: (r) => r.id },
      { label: 'Cart', value: (r) => r.cart_id },
      { label: 'Title', value: (r) => r.title },
      { label: 'Priority', value: (r) => r.priority },
      { label: 'Status', value: (r) => r.status },
      { label: 'Location', value: (r) => r.location },
      { label: 'Assigned To', value: (r) => r.assigned_to },
      { label: 'Due Date', value: (r) => formatReportDate(r.due_date) },
      { label: 'Days Overdue', value: (r) => {
        if (!r.due_date) return '';
        const days = Math.floor((startOfToday() - new Date(r.due_date)) / 86400000);
        return Math.max(days, 0);
      }},
    ],
  },
  {
    id: 'pm-schedule',
    title: 'PM Due & Overdue',
    description: 'Scheduled preventive maintenance due soon or already overdue.',
    filters: [
      { id: 'location', label: 'Location', type: 'select', optionsKey: 'locations', defaultValue: 'all' },
      { id: 'scope', label: 'Show', type: 'select', options: [
        { value: 'all', label: 'Due soon + overdue' },
        { value: 'due', label: 'Due soon only' },
        { value: 'overdue', label: 'Overdue only' },
      ], defaultValue: 'all' },
    ],
    async load(filters) {
      const rows = (await db.getPmRecords())
        .filter((rec) => rec.status === 'scheduled')
        .filter((rec) => matchesLocation(rec.location, filters.location))
        .filter((rec) => {
          const overdue = isOverdueDate(rec.scheduled_date);
          const dueSoon = isPmDueSoon(rec.scheduled_date);
          if (filters.scope === 'overdue') return overdue;
          if (filters.scope === 'due') return dueSoon && !overdue;
          return overdue || dueSoon;
        })
        .map((rec) => ({
          ...rec,
          pm_state: isOverdueDate(rec.scheduled_date) ? 'overdue' : 'due soon',
        }))
        .sort((a, b) => String(a.scheduled_date || '').localeCompare(String(b.scheduled_date || '')));
      const pmLabel = window.MaintainSMIPSettings?.getPmDueLabel?.() || 'due soon';
      return {
        subtitle: `${filters.scope === 'all' ? 'Due soon + overdue' : filters.scope} · ${pmLabel}`,
        rows,
      };
    },
    columns: [
      { label: 'PM #', value: (r) => r.id },
      { label: 'Template', value: (r) => r.template_name },
      { label: 'Cart', value: (r) => r.cart_id },
      { label: 'Location', value: (r) => r.location },
      { label: 'Scheduled', value: (r) => formatReportDate(r.scheduled_date) },
      { label: 'State', value: (r) => r.pm_state },
      { label: 'Tech', value: (r) => r.tech_name },
    ],
  },
  {
    id: 'open-accidents',
    title: 'Open Accident Reports',
    description: 'Damage reports that are not yet resolved.',
    filters: [
      { id: 'location', label: 'Location', type: 'select', optionsKey: 'locations', defaultValue: 'all' },
      { id: 'severity', label: 'Severity', type: 'select', options: [
        { value: 'all', label: 'All severities' },
        { value: 'minor', label: 'Minor' },
        { value: 'moderate', label: 'Moderate' },
        { value: 'major', label: 'Major' },
        { value: 'critical', label: 'Critical' },
      ], defaultValue: 'all' },
    ],
    async load(filters) {
      const rows = (await db.getAccidents())
        .filter((acc) => acc.status !== 'resolved')
        .filter((acc) => matchesLocation(acc.location, filters.location))
        .filter((acc) => filters.severity === 'all' || acc.severity === filters.severity)
        .sort((a, b) => String(b.incident_date || '').localeCompare(String(a.incident_date || '')));
      return {
        subtitle: filters.severity === 'all' ? 'All open severities' : `Severity: ${filters.severity}`,
        rows,
      };
    },
    columns: [
      { label: 'ACC #', value: (r) => r.id },
      { label: 'Cart', value: (r) => r.cart_id },
      { label: 'Location', value: (r) => r.location },
      { label: 'Incident Date', value: (r) => formatReportDate(r.incident_date) },
      { label: 'Severity', value: (r) => r.severity },
      { label: 'Status', value: (r) => r.status },
      { label: 'Reported By', value: (r) => r.reported_by },
      { label: 'Description', value: (r) => r.description },
    ],
  },
  {
    id: 'fleet-inventory',
    title: 'Fleet Inventory',
    description: 'Complete cart roster for inventory audits and venue planning.',
    filters: [
      { id: 'location', label: 'Location', type: 'select', optionsKey: 'locations', defaultValue: 'all' },
      { id: 'hideRetired', label: 'Hide retired carts', type: 'checkbox', defaultValue: true },
    ],
    async load(filters) {
      const rows = (await db.getCarts())
        .filter((cart) => matchesLocation(cart.location, filters.location))
        .filter((cart) => !filters.hideRetired || String(cart.status || '').toLowerCase() !== 'retired')
        .sort((a, b) => String(a.location || '').localeCompare(String(b.location || ''))
          || String(a.id).localeCompare(String(b.id), undefined, { numeric: true }));
      return {
        subtitle: filters.hideRetired ? 'Active fleet (retired hidden)' : 'Including retired carts',
        rows,
      };
    },
    columns: [
      { label: 'Cart ID', value: (r) => r.id },
      { label: 'Serial', value: (r) => r.serial },
      { label: 'Model', value: (r) => r.model },
      { label: 'Year', value: (r) => r.year },
      { label: 'Location', value: (r) => r.location },
      { label: 'Status', value: (r) => r.status },
      { label: 'Notes', value: (r) => r.notes },
    ],
  },
  {
    id: 'completed-work',
    title: 'Completed Work Summary',
    description: 'Finished work orders in a selected period — useful for labor and throughput review.',
    filters: [
      { id: 'days', label: 'Period', type: 'select', options: [
        { value: '7', label: 'Last 7 days' },
        { value: '30', label: 'Last 30 days' },
        { value: '90', label: 'Last 90 days' },
        { value: '365', label: 'Last year' },
      ], defaultValue: '30' },
      { id: 'location', label: 'Location', type: 'select', optionsKey: 'locations', defaultValue: 'all' },
    ],
    async load(filters) {
      const cutoff = Date.now() - Number(filters.days || 30) * 86400000;
      const rows = (await db.getWorkOrders())
        .filter((wo) => CLOSED_WO_STATUSES.has(wo.status))
        .filter((wo) => matchesLocation(wo.location, filters.location))
        .filter((wo) => {
          const stamp = wo.completed_date || wo.created_date;
          return stamp && new Date(stamp).getTime() >= cutoff;
        })
        .sort((a, b) => String(b.completed_date || b.created_date || '')
          .localeCompare(String(a.completed_date || a.created_date || '')));
      return {
        subtitle: `Last ${filters.days} days`,
        rows,
      };
    },
    columns: [
      { label: 'WO #', value: (r) => r.id },
      { label: 'Cart', value: (r) => r.cart_id },
      { label: 'Title', value: (r) => r.title },
      { label: 'Type', value: (r) => r.type },
      { label: 'Location', value: (r) => r.location },
      { label: 'Assigned To', value: (r) => r.assigned_to },
      { label: 'Labor (min)', value: (r) => r.labor_minutes ?? 0 },
      { label: 'Completed', value: (r) => formatReportDate(r.completed_date || r.created_date) },
    ],
  },
  {
    id: 'activity-log',
    title: 'Activity Log',
    description: 'Tabular audit trail for compliance and manager review.',
    filters: [
      { id: 'days', label: 'Period', type: 'select', options: [
        { value: '7', label: 'Last 7 days' },
        { value: '30', label: 'Last 30 days' },
        { value: '90', label: 'Last 90 days' },
        { value: '365', label: 'Last year' },
      ], defaultValue: '30' },
      { id: 'entity_type', label: 'Record type', type: 'select', options: [
        { value: 'all', label: 'All types' },
        { value: 'work_order', label: 'Work orders' },
        { value: 'pm_record', label: 'PM' },
        { value: 'accident', label: 'Accidents' },
        { value: 'cart', label: 'Fleet' },
      ], defaultValue: 'all' },
    ],
    async load(filters) {
      const params = { limit: '200', days: filters.days };
      if (filters.entity_type !== 'all') params.entity_type = filters.entity_type;
      const rows = await db.getAuditLog(params);
      return {
        subtitle: `Last ${filters.days} days`,
        rows,
      };
    },
    columns: [
      { label: 'When', value: (r) => formatReportDateTime(r.created_at) },
      { label: 'User', value: (r) => r.display_name },
      { label: 'Action', value: (r) => db.actionLabel(r.action) },
      { label: 'Type', value: (r) => db.entityTypeLabel(r.entity_type) },
      { label: 'Record #', value: (r) => r.entity_id },
      { label: 'Summary', value: (r) => r.summary },
    ],
  },
];

function renderReportCatalog() {
  const catalog = document.getElementById('report-catalog');
  catalog.innerHTML = REPORTS.map((report) => `
    <button type="button" class="report-card ${report.id === currentReportId ? 'active' : ''}" data-report-id="${report.id}">
      <strong>${report.title}</strong>
      <span>${report.description}</span>
    </button>
  `).join('');

  catalog.querySelectorAll('[data-report-id]').forEach((btn) => {
    btn.addEventListener('click', () => selectReport(btn.dataset.reportId));
  });
}

function renderReportFilters(report) {
  const container = document.getElementById('report-filters');
  if (!report?.filters?.length) {
    container.innerHTML = '';
    return;
  }

  container.innerHTML = report.filters.map((filter) => {
    if (filter.type === 'checkbox') {
      const checked = filter.defaultValue ? 'checked' : '';
      return `
        <div class="filter-group">
          <label>
            <input type="checkbox" data-report-filter="${filter.id}" ${checked} />
            ${filter.label}
          </label>
        </div>
      `;
    }

    let optionsHtml = '';
    if (filter.optionsKey === 'locations') {
      optionsHtml = locationOptions.map((loc) => {
        const label = loc === 'all' ? 'All locations' : loc;
        const selected = loc === filter.defaultValue ? 'selected' : '';
        return `<option value="${loc.replace(/"/g, '&quot;')}" ${selected}>${label}</option>`;
      }).join('');
    } else {
      optionsHtml = (filter.options || []).map((opt) => {
        const selected = opt.value === filter.defaultValue ? 'selected' : '';
        return `<option value="${opt.value}" ${selected}>${opt.label}</option>`;
      }).join('');
    }

    return `
      <div class="filter-group">
        <label for="report-filter-${filter.id}">${filter.label}</label>
        <select id="report-filter-${filter.id}" data-report-filter="${filter.id}">${optionsHtml}</select>
      </div>
    `;
  }).join('');
}

function renderReportTable(columns, rows) {
  if (!rows.length) {
    return '<div class="empty-state" style="padding: 24px;"><h3>No rows match this report</h3><p>Try different filters or check back after more data is recorded.</p></div>';
  }
  return `
    <table class="report-table">
      <thead>
        <tr>${columns.map((col) => `<th>${col.label}</th>`).join('')}</tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>${columns.map((col) => `<td>${String(col.value(row) ?? '').replace(/</g, '&lt;')}</td>`).join('')}</tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function updatePrintHeader() {
  const user = db.getCachedUser()?.display_name || 'User';
  const generated = currentReportState.generatedAt
    ? formatReportDateTime(currentReportState.generatedAt)
    : '';
  document.getElementById('report-print-header').innerHTML = `
    <h1>MaintainSMIP · ${window.MaintainSMIPSettings?.getShopName?.() || 'SMI Properties'}</h1>
    <h2>${currentReportState.title}</h2>
    <p>${currentReportState.subtitle}</p>
    <p>Generated ${generated} by ${user}</p>
    <p>${currentReportState.rows.length} ${currentReportState.rows.length === 1 ? 'row' : 'rows'}</p>
  `;
}

function setReportActionsEnabled(enabled) {
  document.getElementById('report-export-btn').disabled = !enabled;
  document.getElementById('report-print-btn').disabled = !enabled;
}

async function runCurrentReport() {
  const report = REPORTS.find((item) => item.id === currentReportId);
  if (!report) return;

  const preview = document.getElementById('report-preview');
  const meta = document.getElementById('report-meta');
  preview.innerHTML = '<div class="empty-state loading-pulse">Running report…</div>';
  setReportActionsEnabled(false);

  try {
    const filters = getFilterValues();
    const result = await report.load(filters);
    currentReportState = {
      title: report.title,
      subtitle: result.subtitle || '',
      columns: report.columns,
      rows: result.rows || [],
      generatedAt: new Date().toISOString(),
    };

    document.getElementById('report-preview-wrap').innerHTML = `<div id="report-preview">${renderReportTable(report.columns, currentReportState.rows)}</div>`;
    meta.textContent = `${currentReportState.rows.length} rows · ${currentReportState.subtitle}`;
    updatePrintHeader();
    setReportActionsEnabled(currentReportState.rows.length > 0);
  } catch (err) {
    const help = db.getOfflineHelp();
    preview.innerHTML = `<div class="empty-state"><h3>${help.title}</h3><p>${help.detail}</p></div>`;
    meta.textContent = '';
  }
}

function selectReport(reportId) {
  const report = REPORTS.find((item) => item.id === reportId);
  if (!report) return;

  currentReportId = reportId;
  const params = new URLSearchParams(window.location.search);
  params.set('report', reportId);
  window.history.replaceState({}, '', `${window.location.pathname}?${params}`);

  document.getElementById('report-eyebrow').textContent = 'Report';
  document.getElementById('report-title').textContent = report.title;
  document.getElementById('report-description').textContent = report.description;
  document.getElementById('report-meta').textContent = '';
  document.getElementById('report-preview-wrap').innerHTML = `
    <div class="empty-state" id="report-preview">
      <h3>Ready to run</h3>
      <p>Adjust filters if needed, then click <strong>Run Report</strong>.</p>
    </div>
  `;
  setReportActionsEnabled(false);
  renderReportCatalog();
  renderReportFilters(report);
}

function exportCurrentReport() {
  if (!currentReportState.rows.length) return;
  const slug = (currentReportId || 'report').replace(/-/g, '_');
  const date = new Date().toISOString().slice(0, 10);
  db.downloadCsv(`${slug}_${date}.csv`, currentReportState.columns, currentReportState.rows);
}

function printCurrentReport() {
  if (!currentReportState.rows.length) return;
  updatePrintHeader();
  window.print();
}

async function loadLocationOptions() {
  const carts = await db.getCarts();
  const locations = Array.from(new Set(carts.map((cart) => cart.location).filter(Boolean))).sort();
  locationOptions = ['all', ...locations];
}

function wireReportsPage() {
  document.getElementById('report-run-btn')?.addEventListener('click', runCurrentReport);
  document.getElementById('report-export-btn')?.addEventListener('click', exportCurrentReport);
  document.getElementById('report-print-btn')?.addEventListener('click', printCurrentReport);
}

async function initReportsPage() {
  wireReportsPage();
  renderReportCatalog();
  await loadLocationOptions();

  const defaultReport = db.readUrlParams().get('report') || REPORTS[0].id;
  if (REPORTS.some((report) => report.id === defaultReport)) {
    selectReport(defaultReport);
    await runCurrentReport();
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initReportsPage);
} else {
  initReportsPage();
}