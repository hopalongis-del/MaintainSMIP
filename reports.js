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

const PERIOD_FILTER_OPTIONS = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '365', label: 'Last year' },
];

function periodCutoffMs(days) {
  return Date.now() - Number(days || 30) * 86400000;
}

function inPeriod(dateValue, cutoffMs) {
  if (!dateValue) return false;
  return new Date(dateValue).getTime() >= cutoffMs;
}

function pct(numerator, denominator) {
  if (!denominator) return '0%';
  return `${Math.round((numerator / denominator) * 100)}%`;
}

function extractPartsUsageRows(workOrders, filters) {
  const cutoff = periodCutoffMs(filters.days);
  const rows = [];

  workOrders.forEach((wo) => {
    if (!matchesLocation(wo.location, filters.location)) return;
    const stamp = wo.completed_date || wo.created_date;
    if (!inPeriod(stamp, cutoff)) return;

    const sheet = wo.maintenance_sheet || {};
    (sheet.parts_lines || []).forEach((line) => {
      if (!line?.qty && !line?.part_number && !line?.description) return;
      rows.push({
        wo_id: wo.id,
        cart_id: wo.cart_id,
        qty: line.qty || '',
        part_number: line.part_number || '',
        description: line.description || '',
        source: 'Maintenance sheet',
        assigned_to: wo.assigned_to || '',
        location: wo.location || '',
        used_date: stamp,
      });
    });

    (wo.parts_used || []).forEach((part) => {
      if (!part) return;
      if (typeof part === 'string') {
        rows.push({
          wo_id: wo.id,
          cart_id: wo.cart_id,
          qty: '1',
          part_number: '',
          description: part,
          source: 'Work order',
          assigned_to: wo.assigned_to || '',
          location: wo.location || '',
          used_date: stamp,
        });
        return;
      }
      rows.push({
        wo_id: wo.id,
        cart_id: wo.cart_id,
        qty: part.qty || part.quantity || '1',
        part_number: part.part_number || part.number || '',
        description: part.description || part.name || '',
        source: 'Work order',
        assigned_to: wo.assigned_to || '',
        location: wo.location || '',
        used_date: stamp,
      });
    });
  });

  return rows.sort((a, b) => String(b.used_date || '').localeCompare(String(a.used_date || '')));
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
      { id: 'days', label: 'Period', type: 'select', options: PERIOD_FILTER_OPTIONS, defaultValue: '30' },
      { id: 'location', label: 'Location', type: 'select', optionsKey: 'locations', defaultValue: 'all' },
    ],
    async load(filters) {
      const cutoff = periodCutoffMs(filters.days);
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
      { id: 'days', label: 'Period', type: 'select', options: PERIOD_FILTER_OPTIONS, defaultValue: '30' },
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
  {
    id: 'wo-by-technician',
    title: 'Work Orders by Technician',
    description: 'Open workload broken down by assigned technician.',
    filters: [
      { id: 'location', label: 'Location', type: 'select', optionsKey: 'locations', defaultValue: 'all' },
    ],
    async load(filters) {
      const buckets = new Map();
      (await db.getWorkOrders())
        .filter((wo) => OPEN_WO_STATUSES.has(wo.status))
        .filter((wo) => matchesLocation(wo.location, filters.location))
        .forEach((wo) => {
          const tech = wo.assigned_to?.trim() || 'Unassigned';
          if (!buckets.has(tech)) {
            buckets.set(tech, {
              technician: tech,
              open_count: 0,
              overdue_count: 0,
              high_priority: 0,
              critical_priority: 0,
            });
          }
          const row = buckets.get(tech);
          row.open_count += 1;
          if (isOverdueDate(wo.due_date)) row.overdue_count += 1;
          if (wo.priority === 'high') row.high_priority += 1;
          if (wo.priority === 'critical') row.critical_priority += 1;
        });

      const rows = [...buckets.values()].sort((a, b) => b.open_count - a.open_count);
      return {
        subtitle: filters.location === 'all' ? 'Open work orders by technician' : `Location: ${filters.location}`,
        rows,
      };
    },
    columns: [
      { label: 'Technician', value: (r) => r.technician },
      { label: 'Open WOs', value: (r) => r.open_count },
      { label: 'Overdue', value: (r) => r.overdue_count },
      { label: 'High Priority', value: (r) => r.high_priority },
      { label: 'Critical', value: (r) => r.critical_priority },
    ],
  },
  {
    id: 'wo-by-location',
    title: 'Work Orders by Location',
    description: 'Venue-level rollup of open and overdue maintenance work.',
    filters: [],
    async load() {
      const buckets = new Map();
      (await db.getWorkOrders())
        .filter((wo) => OPEN_WO_STATUSES.has(wo.status))
        .forEach((wo) => {
          const loc = wo.location?.trim() || 'Unknown';
          if (!buckets.has(loc)) {
            buckets.set(loc, {
              location: loc,
              open_count: 0,
              overdue_count: 0,
              high_priority: 0,
              in_progress: 0,
            });
          }
          const row = buckets.get(loc);
          row.open_count += 1;
          if (isOverdueDate(wo.due_date)) row.overdue_count += 1;
          if (wo.priority === 'high' || wo.priority === 'critical') row.high_priority += 1;
          if (wo.status === 'in_progress') row.in_progress += 1;
        });

      const rows = [...buckets.values()].sort((a, b) => b.open_count - a.open_count);
      return { subtitle: 'Open work orders grouped by venue', rows };
    },
    columns: [
      { label: 'Location', value: (r) => r.location },
      { label: 'Open WOs', value: (r) => r.open_count },
      { label: 'Overdue', value: (r) => r.overdue_count },
      { label: 'In Progress', value: (r) => r.in_progress },
      { label: 'High/Critical', value: (r) => r.high_priority },
    ],
  },
  {
    id: 'pm-completion-rate',
    title: 'PM Completion Rate',
    description: 'How preventive maintenance is completing by template over a selected period.',
    filters: [
      { id: 'days', label: 'Period', type: 'select', options: PERIOD_FILTER_OPTIONS, defaultValue: '30' },
      { id: 'location', label: 'Location', type: 'select', optionsKey: 'locations', defaultValue: 'all' },
    ],
    async load(filters) {
      const cutoff = periodCutoffMs(filters.days);
      const buckets = new Map();

      (await db.getPmRecords())
        .filter((rec) => matchesLocation(rec.location, filters.location))
        .forEach((rec) => {
          const name = rec.template_name || 'Unknown template';
          if (!buckets.has(name)) {
            buckets.set(name, {
              template: name,
              completed: 0,
              scheduled: 0,
              overdue: 0,
              skipped: 0,
            });
          }
          const row = buckets.get(name);

          if (rec.status === 'completed' && inPeriod(rec.completed_date || rec.scheduled_date, cutoff)) {
            row.completed += 1;
            return;
          }
          if (rec.status === 'skipped' && inPeriod(rec.scheduled_date, cutoff)) {
            row.skipped += 1;
            return;
          }
          if (rec.status === 'scheduled') {
            if (isOverdueDate(rec.scheduled_date)) row.overdue += 1;
            else if (inPeriod(rec.scheduled_date, cutoff) || isPmDueSoon(rec.scheduled_date)) row.scheduled += 1;
          }
        });

      const rows = [...buckets.values()]
        .map((row) => {
          const total = row.completed + row.scheduled + row.overdue + row.skipped;
          return { ...row, total, completion_rate: pct(row.completed, total) };
        })
        .filter((row) => row.total > 0)
        .sort((a, b) => b.total - a.total);

      return { subtitle: `Last ${filters.days} days`, rows };
    },
    columns: [
      { label: 'PM Template', value: (r) => r.template },
      { label: 'Completed', value: (r) => r.completed },
      { label: 'Scheduled', value: (r) => r.scheduled },
      { label: 'Overdue', value: (r) => r.overdue },
      { label: 'Skipped', value: (r) => r.skipped },
      { label: 'Total', value: (r) => r.total },
      { label: 'Completion Rate', value: (r) => r.completion_rate },
    ],
  },
  {
    id: 'accident-severity-summary',
    title: 'Accident Severity Summary',
    description: 'Damage report counts by venue and severity.',
    filters: [
      { id: 'openOnly', label: 'Open reports only', type: 'checkbox', defaultValue: false },
    ],
    async load(filters) {
      const buckets = new Map();
      (await db.getAccidents())
        .filter((acc) => !filters.openOnly || acc.status !== 'resolved')
        .forEach((acc) => {
          const location = acc.location?.trim() || 'Unknown';
          const severity = acc.severity || 'unknown';
          const key = `${location}||${severity}`;
          if (!buckets.has(key)) {
            buckets.set(key, {
              location,
              severity,
              count: 0,
              open_count: 0,
            });
          }
          const row = buckets.get(key);
          row.count += 1;
          if (acc.status !== 'resolved') row.open_count += 1;
        });

      const rows = [...buckets.values()].sort((a, b) => (
        a.location.localeCompare(b.location) || a.severity.localeCompare(b.severity)
      ));
      return {
        subtitle: filters.openOnly ? 'Open accidents only' : 'All accident reports',
        rows,
      };
    },
    columns: [
      { label: 'Location', value: (r) => r.location },
      { label: 'Severity', value: (r) => r.severity },
      { label: 'Total Reports', value: (r) => r.count },
      { label: 'Open', value: (r) => r.open_count },
    ],
  },
  {
    id: 'fleet-model-year',
    title: 'Fleet by Model & Year',
    description: 'Aging and composition analysis of the golf cart fleet.',
    filters: [
      { id: 'location', label: 'Location', type: 'select', optionsKey: 'locations', defaultValue: 'all' },
      { id: 'hideRetired', label: 'Hide retired carts', type: 'checkbox', defaultValue: true },
    ],
    async load(filters) {
      const buckets = new Map();
      (await db.getCarts())
        .filter((cart) => matchesLocation(cart.location, filters.location))
        .filter((cart) => !filters.hideRetired || String(cart.status || '').toLowerCase() !== 'retired')
        .forEach((cart) => {
          const model = cart.model?.trim() || 'Unknown model';
          const year = cart.year?.trim() || 'Unknown year';
          const key = `${model}||${year}`;
          if (!buckets.has(key)) {
            buckets.set(key, {
              model,
              year,
              count: 0,
              locations: new Set(),
            });
          }
          const row = buckets.get(key);
          row.count += 1;
          if (cart.location) row.locations.add(cart.location);
        });

      const rows = [...buckets.values()]
        .map((row) => ({
          model: row.model,
          year: row.year,
          count: row.count,
          locations: [...row.locations].sort().join(', '),
        }))
        .sort((a, b) => b.count - a.count || a.model.localeCompare(b.model));

      return {
        subtitle: filters.hideRetired ? 'Active fleet composition' : 'Including retired carts',
        rows,
      };
    },
    columns: [
      { label: 'Model', value: (r) => r.model },
      { label: 'Year', value: (r) => r.year },
      { label: 'Count', value: (r) => r.count },
      { label: 'Locations', value: (r) => r.locations },
    ],
  },
  {
    id: 'parts-usage',
    title: 'Parts Usage',
    description: 'Parts and service lines captured on work orders and maintenance sheets.',
    filters: [
      { id: 'days', label: 'Period', type: 'select', options: PERIOD_FILTER_OPTIONS, defaultValue: '30' },
      { id: 'location', label: 'Location', type: 'select', optionsKey: 'locations', defaultValue: 'all' },
    ],
    async load(filters) {
      const rows = extractPartsUsageRows(await db.getWorkOrders(), filters);
      return { subtitle: `Last ${filters.days} days`, rows };
    },
    columns: [
      { label: 'WO #', value: (r) => r.wo_id },
      { label: 'Cart', value: (r) => r.cart_id },
      { label: 'Qty', value: (r) => r.qty },
      { label: 'Part Number', value: (r) => r.part_number },
      { label: 'Description', value: (r) => r.description },
      { label: 'Source', value: (r) => r.source },
      { label: 'Technician', value: (r) => r.assigned_to },
      { label: 'Location', value: (r) => r.location },
      { label: 'Date', value: (r) => formatReportDate(r.used_date) },
    ],
  },
  {
    id: 'executive-summary',
    title: 'Executive Summary',
    description: 'One-page snapshot for management: fleet health, open work, PM, and accidents.',
    filters: [
      { id: 'days', label: 'Period', type: 'select', options: PERIOD_FILTER_OPTIONS, defaultValue: '30' },
    ],
    async load(filters) {
      const cutoff = periodCutoffMs(filters.days);
      const [stats, workOrders, pmRecords, accidents, carts] = await Promise.all([
        db.getStats(),
        db.getWorkOrders(),
        db.getPmRecords(),
        db.getAccidents(),
        db.getCarts(),
      ]);

      const completedWos = workOrders.filter(
        (wo) => CLOSED_WO_STATUSES.has(wo.status) && inPeriod(wo.completed_date || wo.created_date, cutoff),
      ).length;
      const pmCompleted = pmRecords.filter(
        (rec) => rec.status === 'completed' && inPeriod(rec.completed_date || rec.scheduled_date, cutoff),
      ).length;
      const pmDueSoon = pmRecords.filter(
        (rec) => rec.status === 'scheduled' && isPmDueSoon(rec.scheduled_date),
      ).length;
      const activeFleet = carts.filter((cart) => String(cart.status || '').toLowerCase() !== 'retired').length;
      const openAccidents = accidents.filter((acc) => acc.status !== 'resolved').length;
      const laborMinutes = workOrders
        .filter((wo) => CLOSED_WO_STATUSES.has(wo.status) && inPeriod(wo.completed_date || wo.created_date, cutoff))
        .reduce((sum, wo) => sum + Number(wo.labor_minutes || 0), 0);

      const rows = [
        { metric: 'Active Fleet Carts', value: activeFleet },
        { metric: 'Total Fleet Carts', value: carts.length },
        { metric: 'Open Work Orders', value: stats.open_work_orders ?? 0 },
        { metric: 'Overdue Work Orders', value: stats.overdue_work_orders ?? 0 },
        { metric: `Work Orders Completed (${filters.days}d)`, value: completedWos },
        { metric: 'PM Due Soon', value: pmDueSoon },
        { metric: 'PM Overdue', value: stats.pm_overdue ?? 0 },
        { metric: `PM Completed (${filters.days}d)`, value: pmCompleted },
        { metric: 'Open Accident Reports', value: openAccidents },
        { metric: `Labor Minutes Logged (${filters.days}d)`, value: laborMinutes },
      ];

      return {
        subtitle: `Management snapshot · last ${filters.days} days`,
        rows,
      };
    },
    columns: [
      { label: 'Metric', value: (r) => r.metric },
      { label: 'Value', value: (r) => r.value },
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
    <h1>${window.MaintainSMIPSettings?.APP_NAME || 'Fleet Maintain'} · ${window.MaintainSMIPSettings?.getShopName?.() || 'Fleet Shop'}</h1>
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