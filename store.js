let partsCache = [];
let salesCache = [];
let cart = []; // { part_id, part_number, description, qty, unit_price, on_hand }
let canWrite = true;

function money(value) {
  return (Number(value) || 0).toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}

function escapeHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatDate(value) {
  if (!value) return '—';
  if (window.MaintainSMIPSettings?.formatDate) {
    return window.MaintainSMIPSettings.formatDate(value);
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('en-US', {
    month: 'short',
    day: '2-digit',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function setTab(tab) {
  document.querySelectorAll('[data-store-tab]').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.storeTab === tab);
  });
  document.getElementById('sell-view').classList.toggle('hidden', tab !== 'sell');
  document.getElementById('history-view').classList.toggle('hidden', tab !== 'history');
}

function retailPrice(part) {
  const price = Number(part.unit_price) || 0;
  if (price > 0) return price;
  return Number(part.unit_cost) || 0;
}

async function refreshStats() {
  const stats = await db.getSalesStats();
  document.getElementById('stat-today').textContent = stats.today_sales ?? 0;
  document.getElementById('stat-today-rev').textContent = money(stats.today_revenue);
  document.getElementById('stat-sales').textContent = stats.completed_sales ?? 0;
  document.getElementById('stat-revenue').textContent = money(stats.revenue);
}

async function loadCatalog() {
  const search = document.getElementById('part-search').value.trim();
  const params = { active: '1' };
  if (search) params.search = search;
  partsCache = await db.getParts(params);
  const sellable = partsCache.filter((p) => Number(p.on_hand) > 0);
  const tbody = document.getElementById('catalog-tbody');
  const empty = document.getElementById('catalog-empty');
  if (!sellable.length) {
    tbody.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  tbody.innerHTML = sellable.map((p) => `
    <tr>
      <td>
        <strong>${escapeHtml(p.part_number || '—')}</strong>
        <div class="hero-sub">${escapeHtml(p.description)}</div>
      </td>
      <td>${escapeHtml(String(p.on_hand))}</td>
      <td>${money(retailPrice(p))}</td>
      <td>
        ${canWrite
          ? `<button class="btn secondary" type="button" data-add-part="${p.id}">Add</button>`
          : ''}
      </td>
    </tr>
  `).join('');
}

function cartTotal() {
  return cart.reduce((sum, line) => sum + line.qty * line.unit_price, 0);
}

function renderCart() {
  const wrap = document.getElementById('cart-lines');
  const empty = document.getElementById('cart-empty');
  document.getElementById('cart-total').textContent = money(cartTotal());
  if (!cart.length) {
    wrap.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  wrap.innerHTML = cart.map((line, index) => `
    <div class="cart-line">
      <div>
        <strong>${escapeHtml(line.part_number || line.description)}</strong>
        <div class="muted">${escapeHtml(line.description)} · ${money(line.unit_price)} each</div>
      </div>
      <div class="cart-line-controls">
        <input type="number" min="1" max="${line.on_hand}" step="1" value="${line.qty}" data-cart-qty="${index}" />
        <button class="btn secondary" type="button" data-cart-remove="${index}">✕</button>
      </div>
    </div>
  `).join('');
}

function addToCart(part) {
  const existing = cart.find((line) => line.part_id === part.id);
  const price = retailPrice(part);
  if (existing) {
    if (existing.qty + 1 > Number(part.on_hand)) {
      alert(`Only ${part.on_hand} on hand.`);
      return;
    }
    existing.qty += 1;
  } else {
    cart.push({
      part_id: part.id,
      part_number: part.part_number || '',
      description: part.description || '',
      qty: 1,
      unit_price: price,
      on_hand: Number(part.on_hand) || 0,
    });
  }
  renderCart();
}

async function loadSales() {
  const status = document.getElementById('sale-filter-status').value;
  const search = document.getElementById('sale-filter-search').value.trim();
  const params = { limit: 100 };
  if (status && status !== 'all') params.status = status;
  if (search) params.search = search;
  salesCache = await db.getSales(params);
  const tbody = document.getElementById('sales-tbody');
  const empty = document.getElementById('sales-empty');
  if (!salesCache.length) {
    tbody.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  tbody.innerHTML = salesCache.map((s) => {
    const itemCount = (s.lines || []).reduce((n, line) => n + Number(line.qty || 0), 0);
    return `
      <tr>
        <td><strong>${escapeHtml(s.sale_number || `SALE-${s.id}`)}</strong></td>
        <td>${escapeHtml(s.customer_name || '—')}</td>
        <td>${itemCount}</td>
        <td>${money(s.total)}</td>
        <td>${escapeHtml(s.payment_method || '—')}</td>
        <td>${escapeHtml(s.sold_by || '—')}</td>
        <td>${formatDate(s.created_at)}</td>
        <td><span class="badge badge-${s.status || 'completed'}">${escapeHtml(s.status || 'completed')}</span></td>
        <td class="row-actions">
          ${canWrite && s.status === 'completed'
            ? `<button class="btn secondary" type="button" data-void-sale="${s.id}">Void</button>`
            : ''}
        </td>
      </tr>
    `;
  }).join('');
}

async function init() {
  const user = await db.getCurrentUser();
  canWrite = !user || user.role !== 'readonly';
  if (!canWrite) {
    document.getElementById('complete-sale-btn')?.classList.add('hidden');
  }

  document.querySelectorAll('[data-store-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      setTab(btn.dataset.storeTab);
      if (btn.dataset.storeTab === 'history') loadSales();
    });
  });

  document.getElementById('part-search')?.addEventListener('input', () => {
    clearTimeout(window.__storeSearchTimer);
    window.__storeSearchTimer = setTimeout(loadCatalog, 250);
  });

  document.getElementById('sale-filter-status')?.addEventListener('change', loadSales);
  document.getElementById('sale-filter-search')?.addEventListener('input', () => {
    clearTimeout(window.__saleSearchTimer);
    window.__saleSearchTimer = setTimeout(loadSales, 250);
  });

  document.getElementById('catalog-tbody')?.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-add-part]');
    if (!btn) return;
    const part = partsCache.find((p) => String(p.id) === String(btn.dataset.addPart));
    if (part) addToCart(part);
  });

  document.getElementById('cart-lines')?.addEventListener('input', (event) => {
    const input = event.target.closest('[data-cart-qty]');
    if (!input) return;
    const index = Number(input.dataset.cartQty);
    const line = cart[index];
    if (!line) return;
    let qty = Number(input.value) || 1;
    if (qty < 1) qty = 1;
    if (qty > line.on_hand) {
      qty = line.on_hand;
      input.value = qty;
      alert(`Only ${line.on_hand} on hand.`);
    }
    line.qty = qty;
    document.getElementById('cart-total').textContent = money(cartTotal());
  });

  document.getElementById('cart-lines')?.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-cart-remove]');
    if (!btn) return;
    cart.splice(Number(btn.dataset.cartRemove), 1);
    renderCart();
  });

  document.getElementById('complete-sale-btn')?.addEventListener('click', async () => {
    if (!cart.length) {
      alert('Add parts to the cart first.');
      return;
    }
    const payload = {
      customer_name: document.getElementById('sale-customer').value.trim(),
      customer_phone: document.getElementById('sale-phone').value.trim(),
      payment_method: document.getElementById('sale-payment').value,
      notes: document.getElementById('sale-notes').value.trim(),
      lines: cart.map((line) => ({
        part_id: line.part_id,
        part_number: line.part_number,
        description: line.description,
        qty: line.qty,
        unit_price: line.unit_price,
      })),
    };
    const result = await db.createSale(payload);
    if (result?.error) {
      alert(result.error);
      return;
    }
    cart = [];
    renderCart();
    document.getElementById('sale-customer').value = '';
    document.getElementById('sale-phone').value = '';
    document.getElementById('sale-notes').value = '';
    await Promise.all([refreshStats(), loadCatalog()]);
    alert(`Sale ${result.sale_number} complete · ${money(result.total)}`);
  });

  document.getElementById('sales-tbody')?.addEventListener('click', async (event) => {
    const btn = event.target.closest('[data-void-sale]');
    if (!btn) return;
    if (!confirm('Void this sale and restore stock?')) return;
    const result = await db.voidSale(btn.dataset.voidSale);
    if (result?.error) {
      alert(result.error);
      return;
    }
    await Promise.all([refreshStats(), loadSales(), loadCatalog()]);
  });

  renderCart();
  await Promise.all([refreshStats(), loadCatalog()]);
}

init().catch((err) => console.error(err));
