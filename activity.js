let activityLimit = 50;

function readActivityFilters() {
  const type = document.getElementById('activity-filter-type').value;
  const action = document.getElementById('activity-filter-action').value;
  const username = document.getElementById('activity-filter-user').value;
  const days = document.getElementById('activity-filter-days').value;
  const filters = { limit: String(activityLimit) };
  if (type !== 'all') filters.entity_type = type;
  if (action !== 'all') filters.action = action;
  if (username !== 'all') filters.username = username;
  if (days !== 'all') filters.days = days;
  return filters;
}

async function populateActivityUsers() {
  const select = document.getElementById('activity-filter-user');
  const users = await db.getAuditUsernames();
  if (!Array.isArray(users)) return;
  const current = select.value;
  select.innerHTML = '<option value="all">All users</option>';
  users
    .sort((a, b) => a.display_name.localeCompare(b.display_name))
    .forEach((user) => {
      const opt = document.createElement('option');
      opt.value = user.username;
      opt.textContent = user.display_name;
      select.appendChild(opt);
    });
  if ([...select.options].some((opt) => opt.value === current)) {
    select.value = current;
  }
}

async function loadActivity({ append = false } = {}) {
  const list = document.getElementById('activity-list');
  const countEl = document.getElementById('activity-count');
  const sub = document.getElementById('activity-sub');
  const loadMoreBtn = document.getElementById('activity-load-more');

  if (!append) {
    list.innerHTML = '<div class="empty-state loading-pulse">Loading activity…</div>';
  }

  try {
    const entries = await db.getAuditLog(readActivityFilters());
    list.innerHTML = db.renderGlobalActivityHtml(entries);
    countEl.textContent = entries.length
      ? `Showing ${entries.length} recent ${entries.length === 1 ? 'entry' : 'entries'}`
      : 'No matching entries';
    sub.textContent = 'Track who changed what, when — click a record to open it.';
    loadMoreBtn.classList.toggle('hidden', entries.length < activityLimit);
  } catch (err) {
    const help = db.getOfflineHelp();
    list.innerHTML = `<div class="empty-state"><h3>${help.title}</h3><p>${help.detail}</p></div>`;
    countEl.textContent = '';
    sub.textContent = help.title;
    loadMoreBtn.classList.add('hidden');
  }
}

function wireActivityPage() {
  const filterIds = [
    'activity-filter-type',
    'activity-filter-action',
    'activity-filter-user',
    'activity-filter-days',
  ];
  filterIds.forEach((id) => {
    document.getElementById(id)?.addEventListener('change', () => {
      activityLimit = 50;
      loadActivity();
    });
  });

  document.getElementById('activity-refresh-btn')?.addEventListener('click', () => loadActivity());
  document.getElementById('activity-load-more')?.addEventListener('click', async () => {
    activityLimit = Math.min(activityLimit + 50, 200);
    await loadActivity();
  });
}

async function initActivityPage() {
  wireActivityPage();
  await populateActivityUsers();
  await loadActivity();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initActivityPage);
} else {
  initActivityPage();
}