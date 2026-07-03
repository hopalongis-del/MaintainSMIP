// SMI Properties paper maintenance sheet — digitized from scanned work order form.
function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

const MAINTENANCE_SHEET_SECTIONS = [
  {
    title: 'Engine / Differential',
    items: [
      { id: 'air_filter', label: 'Air Filter' },
      { id: 'spark_plug', label: 'Spark Plug' },
      { id: 'fuel_filters', label: 'Fuel Filter(s)' },
      { id: 'oil', label: 'Oil' },
      { id: 'oil_filter', label: 'Oil Filter' },
      { id: 'drive_belt', label: 'Drive Belt' },
      { id: 'starter_generator_belt', label: 'Starter Generator Belt' },
      { id: 'adjust_valves', label: 'Adjust Valves' },
      { id: 'check_rpms', label: 'Check RPMs' },
      { id: 'rear_end_oil', label: 'Rear End Oil' },
    ],
  },
  {
    title: 'Electrical System',
    items: [
      { id: 'headlights', label: 'Headlights' },
      { id: 'taillights', label: 'Taillights' },
      { id: 'low_oil_fuel_light', label: 'Low Oil / Fuel Light' },
      { id: 'horn', label: 'Horn' },
      { id: 'reverse_buzzer', label: 'Reverse Buzzer' },
      { id: 'key_switch', label: 'Key Switch' },
      { id: 'fuel_gauge', label: 'Fuel Gauge' },
      { id: 'battery_cables', label: 'Battery Cables / Terminals' },
      { id: 'battery_water', label: 'Battery Water Level' },
      { id: 'battery_volts', label: 'Battery Volts' },
      { id: 'charge_batteries', label: 'Charge Batteries' },
    ],
  },
  {
    title: 'Exterior',
    items: [
      { id: 'front_bumper', label: 'Front Bumper(s)' },
      { id: 'front_cowl', label: 'Front Cowl' },
      { id: 'center_body', label: 'Center Body' },
      { id: 'side_panels', label: 'Side Panels' },
      { id: 'side_rocker_trim', label: 'Side Rocker Panels / Trim' },
      { id: 'rear_body', label: 'Rear Body' },
      { id: 'rear_fenders', label: 'Rear Fenders / Fender Flares' },
      { id: 'bed_latch_tailgate', label: 'Bed / Latch / Tailgate' },
      { id: 'windshield_top', label: 'Windshield / Top' },
      { id: 'seats', label: 'Seats' },
      { id: 'condition', label: 'Condition' },
      { id: 'tighten', label: 'Tighten' },
    ],
  },
  {
    title: 'Clutches',
    items: [
      { id: 'drive_clutch', label: 'Drive Clutch' },
      { id: 'driven_clutch', label: 'Driven Clutch' },
    ],
  },
  {
    title: 'Suspension',
    items: [
      { id: 'alignment', label: 'Alignment' },
      { id: 'lube_front_end', label: 'Lube Front End' },
      { id: 'wheel_bearings', label: 'Wheel Bearings' },
      { id: 'inspect_front_suspension', label: 'Inspect Front Suspension' },
      { id: 'inspect_rear_suspension', label: 'Inspect Rear Suspension' },
    ],
  },
  {
    title: 'Fuel System',
    items: [
      { id: 'carburetor', label: 'Carburetor' },
      { id: 'fuel_leaks', label: 'Check for Leaks' },
      { id: 'fuel_cap', label: 'Check Fuel Cap' },
    ],
  },
  {
    title: 'Brakes',
    items: [
      { id: 'brake_pedal_travel', label: 'Check Brake Pedal Free Travel' },
      { id: 'brake_cables', label: 'Inspect Brake Cables / Lines' },
      { id: 'brake_shoes_clean', label: 'Check / Clean Brake Shoes' },
      { id: 'adjust_brake_shoes', label: 'Adjust Brake Shoes' },
      { id: 'park_brake', label: 'Check Park Brake' },
      { id: 'brake_fluid', label: 'Check Brake Fluid' },
    ],
  },
  {
    title: 'Exhaust System',
    items: [
      { id: 'exhaust_leaks', label: 'Check for Leaks' },
    ],
  },
  {
    title: 'Tires & Wheels',
    items: [
      { id: 'tire_pressure', label: 'Tire Pressure' },
      { id: 'tire_tread', label: 'Tire Tread' },
    ],
  },
  {
    title: 'General',
    items: [
      { id: 'remove_glue', label: 'Remove Glue Residue' },
      { id: 'remove_items', label: 'Remove Unnecessary Items' },
      { id: 'perm_credential', label: 'Permanent Credential? Y/N' },
      { id: 'perm_cred_filled', label: 'Is Perm. Cred. Filled Out? Y/N' },
      { id: 'numbers_present', label: 'Are All Numbers Present? Y/N' },
      { id: 'numbers_match', label: 'Do All Numbers Match? Y/N' },
      { id: 'date_on_gas_tank', label: 'Write Date of Service on Gas Tank' },
    ],
  },
];

function applyWoTemplate(template) {
  const base = defaultMaintenanceSheet();
  if (!template) return base;
  const sheet = template.maintenance_sheet || {};
  return normalizeMaintenanceSheet({
    ...sheet,
    start_date: sheet.start_date || new Date().toISOString().slice(0, 10),
  });
}

function defaultMaintenanceSheet() {
  const checklist = [];
  MAINTENANCE_SHEET_SECTIONS.forEach((section) => {
    section.items.forEach((item) => {
      checklist.push({
        id: item.id,
        section: section.title,
        label: item.label,
        checked: false,
        note: '',
      });
    });
  });
  return {
    service_type: 'repair',
    start_date: new Date().toISOString().slice(0, 10),
    previous_service_date: '',
    total_labor_hours: 0,
    rpm_reading: '',
    brake_depths: { frt_l: '', frt_r: '', rear_l: '', rear_r: '' },
    checklist,
    parts_lines: [{ qty: '', part_number: '', description: '' }],
    sheet_comments: '',
  };
}

function normalizeMaintenanceSheet(raw) {
  const base = defaultMaintenanceSheet();
  if (!raw || typeof raw !== 'object') return base;

  const byId = new Map((raw.checklist || []).map((item) => [item.id, item]));
  base.checklist = base.checklist.map((item) => ({
    ...item,
    checked: Boolean(byId.get(item.id)?.checked),
    note: byId.get(item.id)?.note || '',
  }));

  return {
    ...base,
    service_type: raw.service_type || base.service_type,
    start_date: raw.start_date || '',
    previous_service_date: raw.previous_service_date || '',
    total_labor_hours: Number(raw.total_labor_hours || 0),
    rpm_reading: raw.rpm_reading || '',
    brake_depths: { ...base.brake_depths, ...(raw.brake_depths || {}) },
    parts_lines: (raw.parts_lines?.length ? raw.parts_lines : base.parts_lines).map((line) => ({
      qty: line.qty ?? '',
      part_number: line.part_number ?? '',
      description: line.description ?? '',
    })),
    sheet_comments: raw.sheet_comments || '',
  };
}

function countCheckedItems(sheet) {
  const normalized = normalizeMaintenanceSheet(sheet);
  const total = normalized.checklist.length;
  const done = normalized.checklist.filter((item) => item.checked).length;
  return { done, total };
}

function renderMaintenanceSheetHtml(wo, sheet, { editable = true } = {}) {
  const normalized = normalizeMaintenanceSheet(sheet);
  const cart = (typeof cartData !== 'undefined' ? cartData : []).find((c) => c.id === wo.cart_id);
  const progress = countCheckedItems(normalized);

  const sectionHtml = MAINTENANCE_SHEET_SECTIONS.map((section) => {
    const sectionId = section.title.toLowerCase().replace(/[^a-z0-9]+/g, '-');
    return `
    <div class="sheet-section" data-sheet-section="${sectionId}">
      <div class="sheet-section-head">
        <h4>${section.title}</h4>
        ${editable ? `<button type="button" class="btn ghost sheet-check-all" data-check-all-section="${sectionId}">Check All</button>` : ''}
      </div>
      <div class="sheet-checklist">
        ${section.items.map((item) => {
          const row = normalized.checklist.find((c) => c.id === item.id);
          return `
            <label class="sheet-check">
              <input type="checkbox" data-sheet-item="${item.id}" data-sheet-section="${sectionId}" ${row?.checked ? 'checked' : ''} ${editable ? '' : 'disabled'} />
              <span>${item.label}</span>
            </label>
          `;
        }).join('')}
      </div>
    </div>
  `;
  }).join('');

  const partsRows = normalized.parts_lines.map((line, index) => `
    <tr>
      <td><input type="text" data-part-field="qty" value="${escapeHtml(line.qty ?? '')}" ${editable ? '' : 'disabled'} /></td>
      <td><input type="text" data-part-field="part_number" value="${escapeHtml(line.part_number ?? '')}" ${editable ? '' : 'disabled'} /></td>
      <td><input type="text" data-part-field="description" value="${escapeHtml(line.description ?? '')}" ${editable ? '' : 'disabled'} /></td>
    </tr>
  `).join('');

  return `
    <div class="maintenance-sheet">
      <div class="sheet-header">
        <div>
          <span class="eyebrow">SMI Properties</span>
          <h3>Maintenance Sheet</h3>
        </div>
        <div class="sheet-service-no">Service No. <strong>WO-${wo.id}</strong></div>
      </div>

      <div class="sheet-meta-grid">
        <label>Mechanic
          <input type="text" id="sheet-mechanic" value="${escapeHtml(wo.assigned_to || '')}" ${editable ? '' : 'disabled'} />
        </label>
        <label>Start Date
          <input type="date" id="sheet-start-date" value="${(normalized.start_date || '').slice(0, 10)}" ${editable ? '' : 'disabled'} />
        </label>
        <label>Completion Date
          <input type="date" id="sheet-completion-date" value="${(wo.completed_date || '').slice(0, 10)}" ${editable ? '' : 'disabled'} />
        </label>
        <label>Previous Service Date
          <input type="date" id="sheet-prev-date" value="${(normalized.previous_service_date || '').slice(0, 10)}" ${editable ? '' : 'disabled'} />
        </label>
        <label>Total Labor Hours
          <input type="number" step="0.25" min="0" id="sheet-labor-hours" value="${normalized.total_labor_hours || 0}" ${editable ? '' : 'disabled'} />
        </label>
      </div>

      <div class="sheet-vehicle-grid">
        <label>Car Number<input type="text" value="${escapeHtml(wo.cart_id || '')}" disabled /></label>
        <label>Serial Number<input type="text" value="${escapeHtml(wo.cart_serial || cart?.serial || '')}" disabled /></label>
        <label>Car Type<input type="text" value="${escapeHtml(cart?.model || '')}" disabled /></label>
        <label>Car Model<input type="text" value="${escapeHtml(cart?.model || '')}" disabled /></label>
        <label>Location<input type="text" value="${escapeHtml(wo.location || cart?.location || '')}" disabled /></label>
        <label>Status<input type="text" value="${escapeHtml(wo.status.replace('_', ' '))}" disabled /></label>
      </div>

      <div class="sheet-progress">Checklist ${progress.done} / ${progress.total} complete</div>
      <div class="sheet-sections">${sectionHtml}</div>

      <div class="sheet-extra-fields">
        <label>RPM Reading
          <input type="text" id="sheet-rpm" value="${normalized.rpm_reading || ''}" ${editable ? '' : 'disabled'} />
        </label>
        <div class="sheet-brake-depths">
          <span>Brake Shoe Depth</span>
          <label>Frt L<input type="text" data-brake-depth="frt_l" value="${normalized.brake_depths.frt_l || ''}" ${editable ? '' : 'disabled'} /></label>
          <label>Frt R<input type="text" data-brake-depth="frt_r" value="${normalized.brake_depths.frt_r || ''}" ${editable ? '' : 'disabled'} /></label>
          <label>Rear L<input type="text" data-brake-depth="rear_l" value="${normalized.brake_depths.rear_l || ''}" ${editable ? '' : 'disabled'} /></label>
          <label>Rear R<input type="text" data-brake-depth="rear_r" value="${normalized.brake_depths.rear_r || ''}" ${editable ? '' : 'disabled'} /></label>
        </div>
      </div>

      <div class="sheet-parts">
        <h4>Parts or Service</h4>
        <table class="sheet-parts-table">
          <thead><tr><th>Qty</th><th>Part Number</th><th>Description of Parts or Service</th></tr></thead>
          <tbody id="sheet-parts-body">${partsRows}</tbody>
        </table>
        ${editable ? '<button type="button" class="btn secondary" id="sheet-add-part-row">Add Line</button>' : ''}
      </div>

      <div class="sheet-service-type">
        <span>Type of Service</span>
        <label><input type="radio" name="sheet-service-type" value="full" ${normalized.service_type === 'full' ? 'checked' : ''} ${editable ? '' : 'disabled'} /> Full</label>
        <label><input type="radio" name="sheet-service-type" value="partial" ${normalized.service_type === 'partial' ? 'checked' : ''} ${editable ? '' : 'disabled'} /> Partial</label>
        <label><input type="radio" name="sheet-service-type" value="repair" ${normalized.service_type === 'repair' ? 'checked' : ''} ${editable ? '' : 'disabled'} /> Repair</label>
      </div>

      <label class="sheet-comments-label">Comments
        <textarea id="sheet-comments" rows="4" ${editable ? '' : 'disabled'}>${escapeHtml(normalized.sheet_comments || '')}</textarea>
      </label>

      <p class="sheet-release-note">Must be completed before the car is released from service.</p>
      ${editable ? '<button type="button" class="btn primary" id="sheet-save-btn">Save Maintenance Sheet</button>' : ''}
    </div>
  `;
}

function collectMaintenanceSheetFromDom(existingSheet) {
  const normalized = normalizeMaintenanceSheet(existingSheet);
  normalized.checklist = normalized.checklist.map((item) => {
    const input = document.querySelector(`[data-sheet-item="${item.id}"]`);
    return { ...item, checked: Boolean(input?.checked) };
  });
  normalized.rpm_reading = document.getElementById('sheet-rpm')?.value || '';
  normalized.start_date = document.getElementById('sheet-start-date')?.value || '';
  normalized.previous_service_date = document.getElementById('sheet-prev-date')?.value || '';
  normalized.total_labor_hours = Number(document.getElementById('sheet-labor-hours')?.value || 0);
  normalized.sheet_comments = document.getElementById('sheet-comments')?.value || '';
  normalized.service_type = document.querySelector('input[name="sheet-service-type"]:checked')?.value || 'repair';
  normalized.brake_depths = {
    frt_l: document.querySelector('[data-brake-depth="frt_l"]')?.value || '',
    frt_r: document.querySelector('[data-brake-depth="frt_r"]')?.value || '',
    rear_l: document.querySelector('[data-brake-depth="rear_l"]')?.value || '',
    rear_r: document.querySelector('[data-brake-depth="rear_r"]')?.value || '',
  };

  const partsBody = document.getElementById('sheet-parts-body');
  if (partsBody) {
    const rows = Array.from(partsBody.querySelectorAll('tr'));
    normalized.parts_lines = rows.map((row) => ({
      qty: row.querySelector('[data-part-field="qty"]')?.value || '',
      part_number: row.querySelector('[data-part-field="part_number"]')?.value || '',
      description: row.querySelector('[data-part-field="description"]')?.value || '',
    })).filter((line) => line.qty || line.part_number || line.description);
    if (!normalized.parts_lines.length) {
      normalized.parts_lines = [{ qty: '', part_number: '', description: '' }];
    }
  }

  return normalized;
}

function updateSheetProgress() {
  const inputs = document.querySelectorAll('[data-sheet-item]');
  const done = Array.from(inputs).filter((input) => input.checked).length;
  const progressEl = document.querySelector('.sheet-progress');
  if (progressEl) {
    progressEl.textContent = `Checklist ${done} / ${inputs.length} complete`;
  }
}

function wireSectionCheckAll() {
  document.querySelectorAll('[data-check-all-section]').forEach((button) => {
    button.addEventListener('click', () => {
      const sectionId = button.dataset.checkAllSection;
      const boxes = document.querySelectorAll(`[data-sheet-section="${sectionId}"] [data-sheet-item]`);
      const allChecked = Array.from(boxes).every((box) => box.checked);
      boxes.forEach((box) => {
        box.checked = !allChecked;
      });
      button.textContent = allChecked ? 'Check All' : 'Uncheck All';
      updateSheetProgress();
    });
  });

  document.querySelectorAll('[data-sheet-item]').forEach((input) => {
    input.addEventListener('change', () => {
      updateSheetProgress();
      const sectionId = input.dataset.sheetSection;
      const sectionButton = document.querySelector(`[data-check-all-section="${sectionId}"]`);
      const sectionBoxes = document.querySelectorAll(`[data-sheet-section="${sectionId}"] [data-sheet-item]`);
      if (sectionButton) {
        const allChecked = Array.from(sectionBoxes).every((box) => box.checked);
        sectionButton.textContent = allChecked ? 'Uncheck All' : 'Check All';
      }
    });
  });

  document.querySelectorAll('[data-check-all-section]').forEach((button) => {
    const sectionId = button.dataset.checkAllSection;
    const sectionBoxes = document.querySelectorAll(`[data-sheet-section="${sectionId}"] [data-sheet-item]`);
    const allChecked = sectionBoxes.length > 0 && Array.from(sectionBoxes).every((box) => box.checked);
    button.textContent = allChecked ? 'Uncheck All' : 'Check All';
  });
}