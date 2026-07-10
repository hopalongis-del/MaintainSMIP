/**
 * Customizable dashboard widgets for MaintainSMIP.
 */
(function () {
  const STAT_WIDGET_DEFS = [
    {
      id: 'stat-open',
      type: 'stat',
      enabled: true,
      label: 'Open Work Orders',
      statKey: 'open_work_orders',
      href: 'workorders.html?status=open',
      alert: false,
      pmComputed: false,
    },
    {
      id: 'stat-overdue',
      type: 'stat',
      enabled: true,
      label: 'Overdue Work Orders',
      statKey: 'overdue_work_orders',
      href: 'workorders.html?overdue=1',
      alert: true,
      pmComputed: false,
    },
    {
      id: 'stat-pm-week',
      type: 'stat',
      enabled: true,
      label: 'PM Due This Week',
      statKey: 'pm_due_this_week',
      href: 'pm.html?due=week',
      alert: false,
      pmComputed: true,
    },
    {
      id: 'stat-pm-overdue',
      type: 'stat',
      enabled: true,
      label: 'PM Overdue',
      statKey: 'pm_overdue',
      href: 'pm.html?status=overdue',
      alert: true,
      pmComputed: false,
    },
    {
      id: 'stat-accidents',
      type: 'stat',
      enabled: true,
      label: 'Open Accident Reports',
      statKey: 'open_accidents',
      href: 'accidents.html?open=1',
      alert: true,
      pmComputed: false,
    },
  ];

  const ADDABLE_WIDGET_TYPES = [
    { type: 'analytics', label: 'Analytics Charts', description: 'Visual charts for fleet status and maintenance costs.' },
    { type: 'weather', label: 'Weather', description: 'Local forecast by city or device location.' },
    { type: 'nascar', label: 'NASCAR Cup Standings', description: 'Top 10 Cup Series drivers.' },
  ];

  let customizing = false;
  let latestStats = {};
  let latestPmDueCount = 0;

  function settingsApi() {
    return window.MaintainSMIPSettings || null;
  }

  function getWidgets() {
    const settings = settingsApi()?.get?.() || {};
    let saved = Array.isArray(settings.dashboardWidgets) ? settings.dashboardWidgets : [];
    if (saved.length === 0 && !settings.hasSeenDashboardWidgets) {
      saved = [
        { id: 'analytics-default', type: 'analytics', enabled: true, title: 'Fleet Analytics' },
        { id: 'weather-default', type: 'weather', enabled: true, title: 'Weather', location: 'Charlotte, NC', useDeviceLocation: false }
      ];
      settingsApi()?.save?.({ dashboardWidgets: saved, hasSeenDashboardWidgets: true });
    }
    return normalizeWidgets(saved);
  }

  function saveWidgets(widgets) {
    settingsApi()?.save?.({ dashboardWidgets: widgets });
  }

  function normalizeWidgets(saved) {
    const byId = new Map(saved.map((widget) => [widget.id, { ...widget }]));
    const merged = [];

    STAT_WIDGET_DEFS.forEach((def) => {
      const existing = byId.get(def.id);
      merged.push({ ...def, ...(existing || {}), type: 'stat', id: def.id });
      byId.delete(def.id);
    });

    byId.forEach((widget) => {
      if (widget.type === 'custom') return;
      const normalized = normalizeExtraWidget(widget);
      if (normalized) merged.push(normalized);
    });
    return merged.map((widget) => ({ ...widget, enabled: widget.enabled !== false }));
  }

  function normalizeExtraWidget(widget) {
    if (widget.type === 'analytics') {
      return {
        id: widget.id,
        type: 'analytics',
        enabled: widget.enabled !== false,
        title: widget.title || 'Fleet Analytics',
      };
    }
    if (widget.type === 'weather') {
      return {
        id: widget.id,
        type: 'weather',
        enabled: widget.enabled !== false,
        title: widget.title || 'Weather',
        location: widget.location || '',
        useDeviceLocation: widget.useDeviceLocation === true,
      };
    }
    if (widget.type === 'nascar') {
      return {
        id: widget.id,
        type: 'nascar',
        enabled: widget.enabled !== false,
        title: widget.title || 'NASCAR Cup Top 10',
      };
    }
    return null;
  }

  function enabledWidgets() {
    return getWidgets().filter((widget) => widget.enabled);
  }

  function statValue(widget) {
    if (widget.pmComputed) return latestPmDueCount;
    return latestStats[widget.statKey] ?? 0;
  }

  function statLabel(widget) {
    if (widget.id === 'stat-pm-week') {
      return settingsApi()?.getPmDueLabel?.() || widget.label;
    }
    return widget.label;
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function renderStatWidget(widget) {
    const alertClass = widget.alert ? ' alert' : '';
    const value = statValue(widget);
    const label = statLabel(widget);
    return `
      <a class="stat-card stat-card-link dashboard-widget-stat${alertClass}" href="${escapeHtml(widget.href)}" title="View ${escapeHtml(label)}">
        <strong class="stat-num">${escapeHtml(value)}</strong>
        <span class="stat-label">${escapeHtml(label)}</span>
      </a>
    `;
  }

  function widgetControls(widget, index, total) {
    return `
      <div class="dashboard-widget-controls" aria-hidden="${customizing ? 'false' : 'true'}">
        <button type="button" class="dashboard-widget-control" data-widget-move="up" data-widget-id="${escapeHtml(widget.id)}" ${index === 0 ? 'disabled' : ''} aria-label="Move up">↑</button>
        <button type="button" class="dashboard-widget-control" data-widget-move="down" data-widget-id="${escapeHtml(widget.id)}" ${index >= total - 1 ? 'disabled' : ''} aria-label="Move down">↓</button>
        <button type="button" class="dashboard-widget-control" data-widget-remove="${escapeHtml(widget.id)}" aria-label="Remove widget">×</button>
      </div>
    `;
  }

  async function fetchWeather(widget) {
    let query = '';
    if (widget.useDeviceLocation && navigator.geolocation) {
      const position = await new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: false,
          timeout: 10000,
          maximumAge: 300000,
        });
      });
      const { latitude, longitude } = position.coords;
      query = `lat=${encodeURIComponent(latitude)}&lon=${encodeURIComponent(longitude)}`;
    } else {
      const location = widget.location
        || settingsApi()?.getDefaultLocation?.()
        || settingsApi()?.get?.()?.defaultLocation
        || 'Charlotte, NC';
      query = `location=${encodeURIComponent(location)}`;
    }
    const response = await fetch(`/api/widgets/weather?${query}`, { credentials: 'include' });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Weather unavailable (${response.status})`);
    }
    return response.json();
  }

  function renderWeatherBody(widget, data) {
    return `
      <div class="dashboard-widget-weather-main">
        <span class="dashboard-widget-weather-temp">${Math.round(data.temperature_f)}°</span>
        <span>${escapeHtml(data.condition)}</span>
      </div>
      <div class="dashboard-widget-weather-details">
        <span>${escapeHtml(data.location)}</span>
        <span>Wind ${Math.round(data.wind_mph || 0)} mph</span>
        <span>Humidity ${Math.round(data.humidity || 0)}%</span>
      </div>
    `;
  }

  async function fetchNascar() {
    const response = await fetch('/api/widgets/nascar-standings', { credentials: 'include' });
    if (!response.ok) throw new Error(`NASCAR standings unavailable (${response.status})`);
    return response.json();
  }

  function renderNascarBody(data) {
    const drivers = (data.drivers || []).slice(0, 10);
    if (!drivers.length) {
      return '<p class="dashboard-widget-empty">Standings unavailable right now.</p>';
    }
    return `
      <ol class="dashboard-widget-list">
        ${drivers.map((driver) => `
          <li>
            <span class="dashboard-widget-rank">${escapeHtml(driver.position)}</span>
            <div>
              <div class="dashboard-widget-driver">${escapeHtml(driver.driver)}</div>
              <div class="dashboard-widget-meta">${escapeHtml(driver.team || '')}</div>
            </div>
            <span class="dashboard-widget-points">${escapeHtml(driver.points)}</span>
          </li>
        `).join('')}
      </ol>
    `;
  }

  async function hydratePanelWidget(container, widget) {
    const body = container.querySelector('[data-widget-body]');
    if (!body) return;

    try {
      if (widget.type === 'analytics') {
      return {
        id: widget.id,
        type: 'analytics',
        enabled: widget.enabled !== false,
        title: widget.title || 'Fleet Analytics',
      };
    }
    if (widget.type === 'weather') {
        const data = await fetchWeather(widget);
        body.innerHTML = renderWeatherBody(widget, data);
      } else if (widget.type === 'nascar') {
        const data = await fetchNascar();
        body.innerHTML = renderNascarBody(data);
      } else if (widget.type === 'analytics') {
        body.innerHTML = renderAnalyticsBody();
        renderAnalyticsCharts(container);
        const badge = container.querySelector('[data-widget-badge]');
        if (badge) {
          badge.textContent = data.source === 'live' ? 'Live' : 'Snapshot';
        }
        const link = container.querySelector('[data-widget-link]');
        if (link && data.live_url) link.href = data.live_url;
      }
    } catch (err) {
      body.innerHTML = `<p class="dashboard-widget-empty">${escapeHtml(err.message || 'Widget failed to load.')}</p>`;
    }
  }

  function renderPanelShell(widget, index, total) {
    const isWeather = widget.type === 'weather';
    const isNascar = widget.type === 'nascar';
    const isAnalytics = widget.type === 'analytics';
    const subtitle = isWeather
      ? (widget.useDeviceLocation ? 'Using your device location' : (widget.location || 'Default event location'))
      : (isNascar ? 'Cup Series top 10' : 'Fleet status and compliance charts');

    return `
      <article class="dashboard-widget is-panel ${isAnalytics ? 'is-analytics-panel' : ''}" data-widget-id="${escapeHtml(widget.id)}">
        ${customizing ? widgetControls(widget, index, total) : ''}
        <div class="dashboard-widget-panel">
          <div class="dashboard-widget-panel-header">
            <div>
              <h3>${escapeHtml(widget.title)}</h3>
              <p>${escapeHtml(subtitle)}</p>
            </div>
            ${isNascar ? '<div><span class="dashboard-widget-badge" data-widget-badge>Loading</span><br><a data-widget-link href="https://www.nascar.com/standings/cup-series/" target="_blank" rel="noopener noreferrer">View on NASCAR.com</a></div>' : ''}
          </div>
          <div data-widget-body>${isAnalytics ? renderAnalyticsBody() : '<p class="dashboard-widget-empty">Loading…</p>'}</div>
        </div>
      </article>
    `;
  }

  function renderWidget(widget, index, total) {
    if (widget.type === 'stat') {
      return `
        <div class="dashboard-widget" data-widget-id="${escapeHtml(widget.id)}">
          ${customizing ? widgetControls(widget, index, total) : ''}
          ${renderStatWidget(widget)}
        </div>
      `;
    }
    return renderPanelShell(widget, index, total);
  }

  function moveWidget(widgetId, direction) {
    const widgets = getWidgets();
    const index = widgets.findIndex((widget) => widget.id === widgetId);
    const target = direction === 'up' ? index - 1 : index + 1;
    if (index < 0 || target < 0 || target >= widgets.length) return;
    const copy = widgets.slice();
    const [item] = copy.splice(index, 1);
    copy.splice(target, 0, item);
    saveWidgets(copy);
    render();
  }

  function removeWidget(widgetId) {
    const widgets = getWidgets().map((widget) => (
      widget.id === widgetId ? { ...widget, enabled: false } : widget
    ));
    saveWidgets(widgets);
    render();
  }

  function addWidget(type) {
    const widgets = getWidgets().slice();
    const id = `${type}-${Date.now()}`;
    if (type === 'weather') {
      widgets.push({
        id,
        type: 'weather',
        enabled: true,
        title: 'Weather',
        location: settingsApi()?.get?.()?.defaultLocation || 'Charlotte, NC',
        useDeviceLocation: false,
      });
    } else if (type === 'nascar') {
      widgets.push({
        id,
        type: 'nascar',
        enabled: true,
        title: 'NASCAR Cup Top 10',
      });
    } else if (type === 'analytics') {
      widgets.push({
        id,
        type: 'analytics',
        enabled: true,
        title: 'Fleet Analytics',
      });
    }
    saveWidgets(widgets);
    render();
    renderCustomizePanel();
  }

  function toggleWidget(widgetId, enabled) {
    const widgets = getWidgets().map((widget) => (
      widget.id === widgetId ? { ...widget, enabled } : widget
    ));
    saveWidgets(widgets);
    render();
    renderCustomizePanel();
  }

  function updateWidgetField(widgetId, field, value) {
    const widgets = getWidgets().map((widget) => (
      widget.id === widgetId ? { ...widget, [field]: value } : widget
    ));
    saveWidgets(widgets);
  }

  function renderCustomizePanel() {
    const panel = document.getElementById('dashboard-widget-customize');
    if (!panel) return;

    const widgets = getWidgets();
    panel.innerHTML = `
      <h3>Dashboard widgets</h3>
      <p class="hero-sub">Show, hide, and reorder widgets. Add weather or NASCAR Cup standings.</p>
      <div class="dashboard-widget-picker">
        ${ADDABLE_WIDGET_TYPES.map((item) => `
          <button type="button" class="btn secondary" data-add-widget="${item.type}">+ ${escapeHtml(item.label)}</button>
        `).join('')}
      </div>
      <div class="dashboard-widget-catalog">
        ${widgets.map((widget, index) => `
          <div class="dashboard-widget-catalog-row">
            <label>
              <input type="checkbox" data-widget-toggle="${escapeHtml(widget.id)}" ${widget.enabled ? 'checked' : ''} />
              <span>${escapeHtml(widget.title || widget.label || widget.type)}</span>
            </label>
            <span class="dashboard-widget-meta">${escapeHtml(widget.type)}</span>
            <button type="button" class="btn ghost" data-widget-move="up" data-widget-id="${escapeHtml(widget.id)}" ${index === 0 ? 'disabled' : ''}>Up</button>
            <button type="button" class="btn ghost" data-widget-move="down" data-widget-id="${escapeHtml(widget.id)}" ${index >= widgets.length - 1 ? 'disabled' : ''}>Down</button>
            ${widget.type === 'weather' ? `
              <input type="text" data-widget-field="location" data-widget-id="${escapeHtml(widget.id)}" value="${escapeHtml(widget.location || '')}" placeholder="City, ST" />
            ` : ''}
            ${widget.type === 'weather' ? `
              <label><input type="checkbox" data-widget-field="useDeviceLocation" data-widget-id="${escapeHtml(widget.id)}" ${widget.useDeviceLocation ? 'checked' : ''} /> Use my location</label>
            ` : ''}
          </div>
        `).join('')}
      </div>
    `;
  }

  function wireCustomizePanel() {
    const panel = document.getElementById('dashboard-widget-customize');
    if (!panel || panel.dataset.wired === 'true') return;
    panel.dataset.wired = 'true';

    panel.addEventListener('click', (event) => {
      const addBtn = event.target.closest('[data-add-widget]');
      if (addBtn) {
        addWidget(addBtn.dataset.addWidget);
        return;
      }
      const moveBtn = event.target.closest('[data-widget-move]');
      if (moveBtn) {
        moveWidget(moveBtn.dataset.widgetId, moveBtn.dataset.widgetMove);
        renderCustomizePanel();
      }
    });

    panel.addEventListener('change', (event) => {
      const toggle = event.target.closest('[data-widget-toggle]');
      if (toggle) {
        toggleWidget(toggle.dataset.widgetToggle, toggle.checked);
        return;
      }
      const field = event.target.closest('[data-widget-field]');
      if (!field) return;
      const widgetId = field.dataset.widgetId;
      const key = field.dataset.widgetField;
      const value = field.type === 'checkbox' ? field.checked : field.value;
      updateWidgetField(widgetId, key, value);
      if (key === 'location' || key === 'useDeviceLocation') render();
    });
  }

  function wireGrid() {
    const grid = document.getElementById('dashboard-widget-grid');
    if (!grid || grid.dataset.wired === 'true') return;
    grid.dataset.wired = 'true';

    grid.addEventListener('click', (event) => {
      if (!customizing) return;
      const moveBtn = event.target.closest('[data-widget-move]');
      if (moveBtn) {
        event.preventDefault();
        moveWidget(moveBtn.dataset.widgetId, moveBtn.dataset.widgetMove);
        return;
      }
      const removeBtn = event.target.closest('[data-widget-remove]');
      if (removeBtn) {
        event.preventDefault();
        removeWidget(removeBtn.dataset.widgetRemove);
      }
    });
  }

  function render() {
    const grid = document.getElementById('dashboard-widget-grid');
    if (!grid) return;

    const widgets = enabledWidgets();
    grid.classList.toggle('is-customizing', customizing);
    grid.innerHTML = widgets.length
      ? widgets.map((widget, index) => renderWidget(widget, index, widgets.length)).join('')
      : '<p class="dashboard-widget-empty">No widgets enabled. Click Customize Widgets to add some.</p>';

    widgets.forEach((widget) => {
      if (widget.type === 'weather' || widget.type === 'nascar' || widget.type === 'analytics') {
        const container = grid.querySelector(`[data-widget-id="${widget.id}"]`);
        if (container) hydratePanelWidget(container, widget);
      }
    });
  }

  function setCustomizeMode(next) {
    customizing = next;
    const panel = document.getElementById('dashboard-widget-customize');
    const button = document.getElementById('dashboard-customize-btn');
    if (panel) panel.classList.toggle('hidden', !customizing);
    if (button) button.textContent = customizing ? 'Done Customizing' : 'Customize Widgets';
    render();
    if (customizing) renderCustomizePanel();
  }

  function init({ stats = {}, pmDueCount = 0 } = {}) {
    latestStats = stats;
    latestPmDueCount = pmDueCount;
    wireGrid();
    wireCustomizePanel();
    renderCustomizePanel();

    const button = document.getElementById('dashboard-customize-btn');
    if (button && button.dataset.wired !== 'true') {
      button.dataset.wired = 'true';
      button.addEventListener('click', () => setCustomizeMode(!customizing));
    }

    window.addEventListener('maintainsmip-settings-changed', () => {
      renderCustomizePanel();
      if (customizing) render();
    });

    render();
  }

  function updateStats(stats = {}, pmDueCount = 0) {
    latestStats = stats;
    latestPmDueCount = pmDueCount;
    const grid = document.getElementById('dashboard-widget-grid');
    const hasWidgets = grid?.querySelector('[data-widget-id]');
    if (!hasWidgets) {
      render();
      return;
    }
    enabledWidgets()
      .filter((widget) => widget.type === 'stat')
      .forEach((widget) => {
        const valueEl = grid.querySelector(`[data-widget-id="${widget.id}"] .stat-num`);
        if (valueEl) valueEl.textContent = statValue(widget);
      });
  }


  function renderAnalyticsBody() {
    return `
      <div class="analytics-widgets-container" style="display: flex; gap: 20px; flex-wrap: wrap; justify-content: space-around; width: 100%; padding: 10px 0;">
        <div class="chart-container" style="position: relative; height: 160px; width: 160px; display: flex; flex-direction: column; align-items: center;">
          <div style="position: relative; height: 130px; width: 130px;"><canvas id="chart-fleet-status"></canvas></div>
          <div style="text-align: center; font-size: 0.75rem; margin-top: 5px; font-weight: 600; color: var(--text);">Fleet Status</div>
        </div>
        <div class="chart-container" style="position: relative; height: 160px; width: 220px; display: flex; flex-direction: column; align-items: center;">
          <div style="position: relative; height: 130px; width: 220px;"><canvas id="chart-wo-status"></canvas></div>
          <div style="text-align: center; font-size: 0.75rem; margin-top: 5px; font-weight: 600; color: var(--text);">Maintenance Tasks</div>
        </div>
      </div>
    `;
  }

  function renderAnalyticsCharts(container) {
    const carts = window.cartData || [];
    const statusCounts = {
      'active': 0,
      'retired': 0,
      'maintenance': 0,
      'out_of_service': 0
    };
    
    carts.forEach(cart => {
      const status = (cart.status || '').toLowerCase();
      if (status.includes('active')) statusCounts['active'] += 1;
      else if (status.includes('retired')) statusCounts['retired'] += 1;
      else if (status.includes('maintenance')) statusCounts['maintenance'] += 1;
      else statusCounts['out_of_service'] += 1;
    });

    const fleetCanvas = container.querySelector('#chart-fleet-status');
    if (fleetCanvas) {
      if (typeof Chart === 'undefined') {
        fleetCanvas.parentElement.innerHTML = '<p class="dashboard-widget-empty" style="font-size:0.8rem;">Loading Chart.js...</p>';
      } else {
        new Chart(fleetCanvas, {
          type: 'doughnut',
          data: {
            labels: ['Active', 'Maintenance', 'Retired', 'Out of Service'],
            datasets: [{
              data: [
                statusCounts['active'],
                statusCounts['maintenance'],
                statusCounts['retired'],
                statusCounts['out_of_service']
              ],
              backgroundColor: ['#10b981', '#fbbf24', '#6b7280', '#ef4444'],
              borderWidth: 0
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false }
            },
            cutout: '65%'
          }
        });
      }
    }

    const woCanvas = container.querySelector('#chart-wo-status');
    if (woCanvas) {
      if (typeof Chart !== 'undefined') {
        new Chart(woCanvas, {
          type: 'bar',
          data: {
            labels: ['Open WO', 'Overdue', 'PM Due', 'PM Overdue', 'Accidents'],
            datasets: [{
              label: 'Count',
              data: [
                latestStats['open_work_orders'] || 0,
                latestStats['overdue_work_orders'] || 0,
                latestPmDueCount || 0,
                latestStats['pm_overdue'] || 0,
                latestStats['open_accidents'] || 0
              ],
              backgroundColor: ['#2563eb', '#dc2626', '#10b981', '#f59e0b', '#7c3aed'],
              borderWidth: 0,
              borderRadius: 4
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false }
            },
            scales: {
              y: {
                beginAtZero: true,
                ticks: { stepSize: 1, color: '#9ca3af', font: { size: 8 } },
                grid: { color: 'rgba(255,255,255,0.06)' }
              },
              x: {
                ticks: { color: '#9ca3af', font: { size: 8 } },
                grid: { display: false }
              }
            }
          }
        });
      }
    }
  }

  window.MaintainSMIPDashboard = {
    init,
    updateStats,
    getWidgets,
    saveWidgets,
  };
})();