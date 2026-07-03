const TECHNICIANS = [
  'Gavin Weinmeister', 'Kevin Stellman', 'Cory Yeager', 'Mike Casady',
  'Dusty Hixson', 'Brian Lachance', 'Stephen Hering', 'Mark Hixson',
];

let selectedAccidentCart = null;
let editingAccidentId = null;
let pendingReviewPhoto = null;
let approvedPendingPhotos = [];
let uploadOnApproveAccidentId = null;

function formatDate(value) {
  if (!value) return 'N/A';
  return new Date(value).toLocaleDateString('en-US', {
    month: 'short', day: '2-digit', year: 'numeric',
  });
}

function toDateInput(value) {
  if (!value) return '';
  return String(value).slice(0, 10);
}

function severityClass(severity) {
  return `severity-${severity}`;
}

function accidentStatusClass(status) {
  return `status-${status}`;
}

function parseDamageAreas(value) {
  return value.split(',').map(s => s.trim()).filter(Boolean);
}

function getLocations() {
  return Array.from(new Set((cartData || []).map(c => c.location).filter(Boolean))).sort();
}

function getCartLabel(cart) {
  return `Cart #${cart.id} · ${cart.model} · ${cart.location}`;
}

function renderCartPicker(filter = '') {
  const list = document.getElementById('acc-cart-list');
  const query = filter.trim().toLowerCase();
  list.innerHTML = '';
  const matches = (cartData || [])
    .map(cart => ({ cart, label: getCartLabel(cart) }))
    .filter(item => !query || item.label.toLowerCase().includes(query) || String(item.cart.id).includes(query));

  if (!matches.length) {
    list.innerHTML = '<div class="cart-card">No matching cart found.</div>';
    return;
  }

  matches.slice(0, 40).forEach(item => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'cart-card' + (selectedAccidentCart?.id === item.cart.id ? ' selected' : '');
    btn.innerHTML = `<div><strong>${item.label}</strong></div><small>Serial: ${item.cart.serial || 'N/A'}</small>`;
    btn.addEventListener('click', () => {
      selectedAccidentCart = item.cart;
      document.getElementById('acc-location').value = item.cart.location || '';
      document.getElementById('acc-selected-cart').textContent = `Selected ${item.label}`;
      renderCartPicker(document.getElementById('acc-cart-search').value);
    });
    list.appendChild(btn);
  });
}

function renderPendingPhotos() {
  const grid = document.getElementById('pending-photo-grid');
  if (!approvedPendingPhotos.length) {
    grid.innerHTML = '<p class="hero-sub">No photos attached yet.</p>';
    return;
  }
  grid.innerHTML = approvedPendingPhotos.map((item, index) => `
    <div class="photo-thumb">
      <img src="${item.previewUrl}" alt="Pending damage photo ${index + 1}" />
      <span class="photo-pending-label">Pending</span>
      <button type="button" data-remove-pending="${index}" title="Remove">✕</button>
    </div>
  `).join('');

  grid.querySelectorAll('[data-remove-pending]').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = Number(btn.dataset.removePending);
      URL.revokeObjectURL(approvedPendingPhotos[idx].previewUrl);
      approvedPendingPhotos.splice(idx, 1);
      renderPendingPhotos();
    });
  });
}

function showPhotoReview(file) {
  if (pendingReviewPhoto?.previewUrl) {
    URL.revokeObjectURL(pendingReviewPhoto.previewUrl);
  }
  pendingReviewPhoto = {
    file,
    previewUrl: URL.createObjectURL(file),
  };
  document.getElementById('photo-review-image').src = pendingReviewPhoto.previewUrl;
  document.getElementById('photo-review').classList.remove('hidden');
}

function hidePhotoReview() {
  document.getElementById('photo-review').classList.add('hidden');
  if (pendingReviewPhoto?.previewUrl) {
    URL.revokeObjectURL(pendingReviewPhoto.previewUrl);
  }
  pendingReviewPhoto = null;
}

function isImageFile(file) {
  if (!file) return false;
  if (file.type && file.type.startsWith('image/')) return true;
  const name = (file.name || '').toLowerCase();
  return /\.(jpe?g|png|webp|heic|heif|gif)$/i.test(name);
}

function onPhotoInput(event) {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!isImageFile(file)) {
    alert('Please choose a photo (JPEG, PNG, or HEIC).');
    return;
  }
  showPhotoReview(file);
}

async function approvePhoto() {
  if (!pendingReviewPhoto) return;

  if (uploadOnApproveAccidentId) {
    const accidentId = uploadOnApproveAccidentId;
    const file = pendingReviewPhoto.file;
    hidePhotoReview();
    uploadOnApproveAccidentId = null;
    const uploaded = await db.uploadAccidentPhoto(accidentId, file);
    if (!uploaded) {
      alert('Could not upload the photo. Try again or choose from gallery.');
      return;
    }
    await renderAccidentList();
    await openAccidentDetail(accidentId);
    return;
  }

  approvedPendingPhotos.push({ ...pendingReviewPhoto });
  pendingReviewPhoto = null;
  document.getElementById('photo-review').classList.add('hidden');
  renderPendingPhotos();
}

function denyPhoto() {
  uploadOnApproveAccidentId = null;
  hidePhotoReview();
}

async function uploadPendingPhotos(accidentId) {
  let failed = 0;
  for (const photo of approvedPendingPhotos) {
    const uploaded = await db.uploadAccidentPhoto(accidentId, photo.file);
    if (!uploaded) failed += 1;
    URL.revokeObjectURL(photo.previewUrl);
  }
  approvedPendingPhotos = [];
  renderPendingPhotos();
  if (failed) {
    alert(`${failed} photo(s) could not be uploaded. The report was saved — try adding photos again from the detail view.`);
  }
}

function buildAccidentCard(acc) {
  const card = document.createElement('button');
  card.type = 'button';
  card.className = 'accident-item';
  const photoCount = (acc.photos || []).length;
  card.innerHTML = `
    <div class="accident-item-title">
      <h3>ACC-${acc.id} — Cart #${acc.cart_id}</h3>
      <span class="badge ${severityClass(acc.severity)}">${acc.severity.replace('_', ' ')}</span>
    </div>
    <div class="accident-item-meta">
      <span>${acc.location || 'Unknown'}</span>
      <span>${formatDate(acc.incident_date)}</span>
      <span class="badge ${accidentStatusClass(acc.status)}">${acc.status.replace('_', ' ')}</span>
      <span>${photoCount} photo${photoCount === 1 ? '' : 's'}</span>
    </div>
    <p style="margin:10px 0 0; color: var(--muted); font-size:0.9rem;">${acc.description}</p>
  `;
  card.addEventListener('click', () => openAccidentDetail(acc.id));
  return card;
}

async function renderAccidentList() {
  const list = document.getElementById('accident-list');
  const status = document.getElementById('acc-filter-status').value;
  const severity = document.getElementById('acc-filter-severity').value;
  const location = document.getElementById('acc-filter-location').value;
  const search = document.getElementById('acc-filter-search').value.trim().toLowerCase();

  const accidents = await db.getAccidents();
  updateAccidentDashboardCounts(accidents);
  const filtered = accidents.filter(acc => {
    if (window.__accOpenOnly && acc.status === 'resolved') return false;
    if (status !== 'all' && acc.status !== status) return false;
    if (severity !== 'all' && acc.severity !== severity) return false;
    if (location !== 'all' && acc.location !== location) return false;
    if (search) {
      const target = `${acc.id} ${acc.cart_id} ${acc.description} ${acc.reported_by || ''}`.toLowerCase();
      if (!target.includes(search)) return false;
    }
    return true;
  });

  list.innerHTML = '';
  if (!filtered.length) {
    list.innerHTML = '<div class="empty-state"><h3>No accident reports</h3><p>Tap Report Damage to document cart damage with photos.</p></div>';
    return;
  }
  filtered.forEach(acc => list.appendChild(buildAccidentCard(acc)));
}

function renderDamageTags(areas) {
  if (!areas?.length) return '<p class="hero-sub">No specific areas listed.</p>';
  return `<div class="damage-tags">${areas.map(a => `<span class="damage-tag">${a}</span>`).join('')}</div>`;
}

function renderPhotoGrid(photos, accidentId, editable = false) {
  if (!photos?.length) return '<p class="hero-sub">No photos attached.</p>';
  return `<div class="photo-grid">${photos.map(path => `
    <div class="photo-thumb">
      <a href="/${path}" target="_blank" rel="noopener">
        <img src="/${path}" alt="Damage photo" />
      </a>
      ${editable ? `<button type="button" data-delete-photo="${path}" title="Delete photo">✕</button>` : ''}
    </div>
  `).join('')}</div>`;
}

async function openAccidentDetail(id) {
  const accidents = await db.getAccidents();
  const acc = accidents.find(a => String(a.id) === String(id));
  if (!acc) return;

  const panel = document.getElementById('accident-detail-panel');
  panel.innerHTML = `
    <div class="detail-row" style="display:flex; justify-content:space-between; gap:16px; margin-bottom:18px;">
      <div>
        <span class="eyebrow">${acc.status.replace('_', ' ')}</span>
        <h2>ACC-${acc.id}</h2>
        <p>Cart #${acc.cart_id} · ${acc.cart_serial || '—'} · ${acc.location}</p>
      </div>
      <div style="text-align:right; display:grid; gap:10px; justify-items:end;">
        <span class="badge ${severityClass(acc.severity)}">${acc.severity.replace('_', ' ')}</span>
        <button class="btn primary" type="button" id="btn-edit-accident">Edit Report</button>
      </div>
    </div>
    <div class="detail-card">
      <h3>Incident</h3>
      <p><strong>Date:</strong> ${formatDate(acc.incident_date)}</p>
      <p><strong>Reported by:</strong> ${acc.reported_by || 'Unassigned'}</p>
      <p>${acc.description}</p>
      ${renderDamageTags(acc.damage_areas)}
      ${acc.notes ? `<p style="margin-top:12px; color:var(--muted);">${acc.notes}</p>` : ''}
    </div>
    <div class="detail-card">
      <h3>Photos</h3>
      ${renderPhotoGrid(acc.photos, acc.id, true)}
      <div class="photo-actions">
        <button class="btn photo-btn camera" type="button" id="btn-detail-camera">📷 Add Photo</button>
      </div>
      <input type="file" id="detail-camera-input" accept="image/*" capture="environment" hidden />
    </div>
    <div class="detail-card">
      <h3>Actions</h3>
      <div style="display:grid; gap:10px;">
        <button class="btn secondary" type="button" data-set-status="under_review">Mark Under Review</button>
        <button class="btn secondary" type="button" data-set-status="repair_scheduled">Schedule Repair</button>
        <button class="btn secondary" type="button" data-set-status="resolved">Mark Resolved</button>
        <button class="btn ghost" type="button" id="btn-delete-accident" style="color:#f87171;">Delete Report</button>
      </div>
    </div>
  `;

  document.getElementById('btn-edit-accident').addEventListener('click', () => openEditModal(acc));
  document.getElementById('btn-delete-accident').addEventListener('click', () => deleteAccident(acc.id));
  panel.querySelectorAll('[data-set-status]').forEach(btn => {
    btn.addEventListener('click', async () => {
      await db.updateAccident(acc.id, { status: btn.dataset.setStatus });
      await renderAccidentList();
      await openAccidentDetail(acc.id);
    });
  });
  panel.querySelectorAll('[data-delete-photo]').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('Remove this photo?')) return;
      await db.deleteAccidentPhoto(acc.id, btn.dataset.deletePhoto);
      await renderAccidentList();
      await openAccidentDetail(acc.id);
    });
  });

  const detailInput = document.getElementById('detail-camera-input');
  document.getElementById('btn-detail-camera').addEventListener('click', () => detailInput.click());
  detailInput.addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    uploadOnApproveAccidentId = acc.id;
    showPhotoReview(file);
  });
}

function showDetailPlaceholder() {
  document.getElementById('accident-detail-panel').innerHTML = `
    <div class="empty-state">
      <h3>Select an accident report</h3>
      <p>Choose a report from the list, or tap <strong>Report Damage</strong> to document new damage with photos.</p>
    </div>
  `;
}

function openCreateModal() {
  editingAccidentId = null;
  selectedAccidentCart = null;
  approvedPendingPhotos.forEach(p => URL.revokeObjectURL(p.previewUrl));
  approvedPendingPhotos = [];
  document.getElementById('accident-form').reset();
  document.getElementById('acc-incident-date').value = new Date().toISOString().slice(0, 10);
  document.getElementById('acc-modal-eyebrow').textContent = 'Accident Report';
  document.getElementById('acc-modal-heading').textContent = 'Report Damage';
  document.getElementById('acc-save-btn').textContent = 'Save Report';
  document.getElementById('acc-selected-cart').textContent = 'Select the damaged cart.';
  renderCartPicker();
  renderPendingPhotos();
  document.getElementById('accident-modal').classList.remove('hidden');
}

function openEditModal(acc) {
  editingAccidentId = acc.id;
  selectedAccidentCart = cartData.find((c) => String(c.id) === String(acc.cart_id)) || null;
  approvedPendingPhotos = [];
  document.getElementById('acc-description').value = acc.description || '';
  document.getElementById('acc-notes').value = acc.notes || '';
  document.getElementById('acc-severity').value = acc.severity || 'moderate';
  document.getElementById('acc-status').value = acc.status || 'reported';
  document.getElementById('acc-reported-by').value = acc.reported_by || '';
  document.getElementById('acc-location').value = acc.location || '';
  document.getElementById('acc-incident-date').value = toDateInput(acc.incident_date);
  document.getElementById('acc-damage-areas').value = (acc.damage_areas || []).join(', ');
  document.getElementById('acc-modal-eyebrow').textContent = 'Edit Report';
  document.getElementById('acc-modal-heading').textContent = `Edit ACC-${acc.id}`;
  document.getElementById('acc-save-btn').textContent = 'Save Changes';
  document.getElementById('acc-selected-cart').textContent = selectedAccidentCart
    ? `Selected ${getCartLabel(selectedAccidentCart)}`
    : `Cart #${acc.cart_id}`;
  renderCartPicker();
  renderPendingPhotos();
  document.getElementById('accident-modal').classList.remove('hidden');
}

function closeAccidentModal() {
  hidePhotoReview();
  editingAccidentId = null;
  document.getElementById('accident-modal').classList.add('hidden');
}

function serializeAccidentForm() {
  const incidentDate = document.getElementById('acc-incident-date').value;
  return {
    cart_id: Number(selectedAccidentCart.id),
    location: document.getElementById('acc-location').value.trim(),
    reported_by: document.getElementById('acc-reported-by').value,
    incident_date: incidentDate ? `${incidentDate}T12:00:00` : null,
    description: document.getElementById('acc-description').value.trim(),
    severity: document.getElementById('acc-severity').value,
    status: document.getElementById('acc-status').value,
    damage_areas: parseDamageAreas(document.getElementById('acc-damage-areas').value),
    notes: document.getElementById('acc-notes').value.trim(),
    photos: [],
  };
}

async function handleAccidentSave(event) {
  event.preventDefault();
  if (!selectedAccidentCart) {
    alert('Please select the damaged cart.');
    return;
  }

  const payload = serializeAccidentForm();
  let saved;

  if (editingAccidentId) {
    saved = await db.updateAccident(editingAccidentId, payload);
    if (!saved) {
      alert('Failed to save changes.');
      return;
    }
    if (approvedPendingPhotos.length) {
      await uploadPendingPhotos(editingAccidentId);
    }
    closeAccidentModal();
    await renderAccidentList();
    await openAccidentDetail(editingAccidentId);
    return;
  }

  saved = await db.saveAccident(payload);
  if (!saved) {
    alert('Failed to save accident report.');
    return;
  }
  if (approvedPendingPhotos.length) {
    await uploadPendingPhotos(saved.id);
  }
  closeAccidentModal();
  await renderAccidentList();
  await openAccidentDetail(saved.id);
}

async function deleteAccident(id) {
  if (!confirm('Delete this accident report and all photos?')) return;
  await db.deleteAccident(id);
  showDetailPlaceholder();
  await renderAccidentList();
}

function applyAccUrlState() {
  const params = db.readUrlParams();
  window.__accOpenOnly = params.get('open') === '1';
  if (params.get('status')) {
    document.getElementById('acc-filter-status').value = params.get('status');
    window.__accOpenOnly = false;
  }
  if (params.get('location')) {
    document.getElementById('acc-filter-location').value = params.get('location');
  }
  return db.parseDeepLinkId(params.get('id'));
}

function applyAccStatFilter(filter) {
  window.__accOpenOnly = filter.open === '1';
  document.getElementById('acc-filter-status').value = filter.status || 'all';
  renderAccidentList();
  document.getElementById('accident-list')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function wireAccStatCards() {
  document.querySelectorAll('#acc-dashboard-strip [data-acc-filter]').forEach(card => {
    const activate = () => applyAccStatFilter(JSON.parse(card.dataset.accFilter));
    card.addEventListener('click', activate);
    card.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        activate();
      }
    });
  });
}

function updateAccidentDashboardCounts(accidents) {
  const openEl = document.getElementById('count-acc-open');
  if (!openEl) return;
  document.getElementById('count-acc-open').textContent =
    accidents.filter(acc => acc.status !== 'resolved').length;
  document.getElementById('count-acc-review').textContent =
    accidents.filter(acc => acc.status === 'under_review').length;
  document.getElementById('count-acc-repair').textContent =
    accidents.filter(acc => acc.status === 'repair_scheduled').length;
  document.getElementById('count-acc-resolved').textContent =
    accidents.filter(acc => acc.status === 'resolved').length;
}

function setupLocationFilter() {
  const select = document.getElementById('acc-filter-location');
  select.innerHTML = '<option value="all">All</option>';
  getLocations().forEach(loc => {
    const opt = document.createElement('option');
    opt.value = loc;
    opt.textContent = loc;
    select.appendChild(opt);
  });
}

async function initAccidents() {
  document.getElementById('new-accident-btn').addEventListener('click', openCreateModal);
  document.getElementById('acc-modal-close').addEventListener('click', closeAccidentModal);
  document.getElementById('acc-modal-cancel').addEventListener('click', closeAccidentModal);
  document.getElementById('accident-form').addEventListener('submit', handleAccidentSave);
  document.getElementById('acc-cart-search').addEventListener('input', e => renderCartPicker(e.target.value));
  document.getElementById('acc-filter-status').addEventListener('change', () => {
    window.__accOpenOnly = false;
    renderAccidentList();
  });
  document.getElementById('acc-filter-severity').addEventListener('change', renderAccidentList);
  document.getElementById('acc-filter-location').addEventListener('change', renderAccidentList);
  document.getElementById('acc-filter-search').addEventListener('input', renderAccidentList);

  document.getElementById('btn-take-photo').addEventListener('click', () => {
    document.getElementById('photo-camera-input').click();
  });
  document.getElementById('btn-choose-photo').addEventListener('click', () => {
    document.getElementById('photo-gallery-input').click();
  });
  document.getElementById('photo-camera-input').addEventListener('change', onPhotoInput);
  document.getElementById('photo-gallery-input').addEventListener('change', onPhotoInput);
  document.getElementById('photo-approve-btn').addEventListener('click', approvePhoto);
  document.getElementById('photo-deny-btn').addEventListener('click', denyPhoto);

  try {
    showDetailPlaceholder();
    setupLocationFilter();
    wireAccStatCards();
    const deepLinkId = applyAccUrlState();
    await renderAccidentList();
    if (deepLinkId) await openAccidentDetail(deepLinkId);
  } catch (err) {
    const help = db.getOfflineHelp();
    document.getElementById('accident-list').innerHTML =
      `<div class="empty-state"><h3>${help.title}</h3><p>${help.detail}</p></div>`;
  }
}

initAccidents();