/**
 * Analytics Pro — API Client v2
 * Dados reais: NuvemShop + GA4 + Meta Ads
 */

const API = 'http://localhost:8000/api';

// ─── Utilitários ─────────────────────────────────────────
const $ = id => document.getElementById(id);

async function apiFetch(path) {
  try {
    const res = await fetch(API + path);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    console.warn('[API] Erro:', path, e.message);
    return null;
  }
}

function brl(n) {
  if (n == null || isNaN(n)) return '—';
  if (n >= 1000000) return 'R$ ' + (n/1000000).toFixed(2).replace('.',',') + 'M';
  if (n >= 1000)    return 'R$ ' + (n/1000).toFixed(1).replace('.',',') + 'k';
  return 'R$ ' + Number(n).toLocaleString('pt-BR', {minimumFractionDigits:2});
}

function num(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString('pt-BR');
}

function pct(n) {
  if (n == null || isNaN(n)) return '—';
  return Number(n).toFixed(2).replace('.',',') + '%';
}

function set(id, val) {
  const el = $(id);
  if (el) el.textContent = val;
}

// ─── Estado global ────────────────────────────────────────
let _days = 30;

// ─── Filtro de Datas ─────────────────────────────────────
function toggleCustomDate() {
  const bar = $('custom-date-bar');
  if (!bar) return;
  bar.style.display = bar.style.display === 'none' ? 'flex' : 'none';
}

function applyDatePreset(raw) {
  const today = new Date();
  const toStr = today.toISOString().split('T')[0];
  let fromStr, days;

  if (raw === '0') {
    // Hoje
    fromStr = toStr; days = 1;
  } else if (raw === '1') {
    // Ontem
    const y = new Date(today); y.setDate(y.getDate()-1);
    fromStr = y.toISOString().split('T')[0]; days = 1;
  } else if (raw === '7') {
    const f = new Date(today); f.setDate(f.getDate()-7);
    fromStr = f.toISOString().split('T')[0]; days = 7;
  } else if (raw === 'month') {
    fromStr = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0];
    days = today.getDate();
  } else {
    const d = parseInt(raw);
    const f = new Date(today); f.setDate(f.getDate()-d);
    fromStr = f.toISOString().split('T')[0]; days = d;
  }

  _days = days;
  if ($('date-from')) $('date-from').value = fromStr;
  if ($('date-to'))   $('date-to').value   = toStr;

  const bar = $('custom-date-bar');
  if (bar) bar.style.display = 'none';

  refreshAll();
}

function applyCustomDate() {
  const from = $('date-from')?.value;
  const to   = $('date-to')?.value;
  if (!from || !to) return;
  _days = Math.max(1, Math.round((new Date(to)-new Date(from))/(86400000))+1);
  document.querySelectorAll('.date-preset-btn').forEach(b => b.classList.remove('active'));
  $('btn-custom')?.classList.add('active');
  refreshAll();
}

document.querySelectorAll('.date-preset-btn[data-days]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.date-preset-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    applyDatePreset(btn.dataset.days);
  });
});

// ─── Dashboard ───────────────────────────────────────────
async function loadDashboard() {
  const data = await apiFetch(`/dashboard/summary?days=${_days}`);
  if (!data) return;

  const ns   = data.ecommerce   || {};
  const ga   = data.analytics   || {};
  const meta = data.paid_ads    || {};
  const cross= data.cross_metrics || {};

  // Ecommerce
  set('kpi-revenue',  brl(ns.total_revenue));
  set('kpi-orders',   num(ns.total_orders));
  set('kpi-ticket',   brl(ns.avg_ticket));

  // Analytics
  set('kpi-sessions',   num(ga.sessions));
  set('kpi-conversion', ga.sessions ? pct(ga.transactions/ga.sessions*100) : '—');

  // Meta
  set('kpi-spend', brl(meta.spend_brl));
  set('kpi-roas',  meta.roas != null ? meta.roas+'x' : '—');
  set('kpi-cac',   cross.cac != null ? brl(cross.cac) : '—');
}

// ─── Marketing (Meta overview) ────────────────────────────
async function loadMarketing() {
  const meta = await apiFetch(`/meta/overview?days=${_days}`);
  if (!meta) return;

  set('meta-spend',       brl(meta.spend_brl));
  set('meta-roas',        meta.roas != null ? meta.roas+'x' : '—');
  set('meta-purchases',   num(meta.purchases));
  set('meta-impressions', meta.impressions >= 1e6 ? (meta.impressions/1e6).toFixed(2)+'M' : num(meta.impressions));
  set('meta-ctr',         meta.ctr != null ? pct(meta.ctr) : '—');
  set('meta-usd-rate',    meta.usd_rate_used ? 'R$ '+meta.usd_rate_used.toFixed(4) : '—');

  // Cards por conta
  const brlAcc = meta.accounts?.brl;
  const usdAcc = meta.accounts?.usd;

  const brlCard = $('meta-brl-card');
  if (brlCard && brlAcc) {
    brlCard.querySelector('.kpi-value').textContent = brl(brlAcc.spend_brl);
    brlCard.querySelector('.kpi-sub').textContent   =
      `Gasto original: R$ ${Number(brlAcc.spend_original).toLocaleString('pt-BR',{minimumFractionDigits:2})} · ${num(brlAcc.purchases)} compras`;
  }

  const usdCard = $('meta-usd-card');
  if (usdCard && usdAcc) {
    usdCard.querySelector('.kpi-value').textContent = brl(usdAcc.spend_brl);
    usdCard.querySelector('.kpi-sub').textContent   =
      `Gasto original: US$ ${Number(usdAcc.spend_original).toLocaleString('en-US',{minimumFractionDigits:2})} · ${num(usdAcc.purchases)} compras`;
  }
}

// ─── Campanhas Meta ───────────────────────────────────────
async function loadCampaigns() {
  const tbody = $('campaigns-tbody');
  const label = $('camp-period-label');
  if (!tbody) return;

  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--text3)">⏳ Carregando campanhas…</td></tr>';
  if (label) label.textContent = `Últimos ${_days} dias`;

  const data = await apiFetch(`/meta/campaigns/summary?days=${_days}`);
  if (!data) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--danger)">❌ Erro ao carregar campanhas</td></tr>';
    return;
  }
  if (!data.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text3);padding:20px">Nenhuma campanha no período</td></tr>';
    return;
  }

  tbody.innerHTML = data.map(c => {
    const active = c.status === 'ACTIVE';
    const sc = active ? 'tag-success' : 'tag-warning';
    const sl = active ? '🟢 Ativa' : '⏸ Pausada';
    const ac = c.currency_original === 'USD' ? 'tag-info' : 'tag-default';
    const usdInfo = c.currency_original === 'USD' ? ` (US$ ${Number(c.spend_original).toLocaleString('en-US',{minimumFractionDigits:2})})` : '';
    return `<tr>
      <td class="td-bold" style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${c.name}">${c.name}</td>
      <td><span class="tag ${ac}" style="font-size:10px">${c.account.replace('Conta ','C')}</span></td>
      <td>${brl(c.spend_brl)}${usdInfo}</td>
      <td>${num(c.impressions)}</td>
      <td>${num(c.clicks)}</td>
      <td>${pct(c.ctr*100)}</td>
      <td>${c.purchases}</td>
      <td><span class="tag ${sc}">${sl}</span></td>
    </tr>`;
  }).join('');
}

// ─── Produtos NuvemShop ───────────────────────────────────
async function loadProducts() {
  const tbody = $('products-tbody');
  if (!tbody) return;

  tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--text3)">⏳ Carregando produtos…</td></tr>';

  const data = await apiFetch(`/nuvemshop/products/top?limit=20`);
  if (!data || !data.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--danger)">❌ Erro ao carregar produtos</td></tr>';
    return;
  }

  tbody.innerHTML = data.map((p, i) => `
    <tr>
      <td style="color:var(--text3);font-weight:600;width:30px">${i+1}</td>
      <td class="td-bold">${p.name}</td>
      <td style="text-align:center">${num(p.quantity)}</td>
      <td><strong>${brl(p.revenue)}</strong></td>
    </tr>
  `).join('');
}

// ─── Clientes ─────────────────────────────────────────────
async function loadClientes() {
  const data = await apiFetch(`/nuvemshop/customers/new?days=${_days}`);
  set('kpi-new-customers', data ? num(data.new_customers) : '—');
}

// ─── Gráficos ─────────────────────────────────────────────
async function loadRevenueChart() {
  const data = await apiFetch(`/nuvemshop/orders/by-day?days=${_days > 7 ? _days : 30}`);
  if (!data?.length) return;
  const chart = window.__charts?.revenue;
  if (!chart) return;
  chart.data.labels = data.map(d => d.date.slice(5));
  chart.data.datasets[0].data = data.map(d => d.revenue);
  chart.update();
}

async function loadMetaSpendChart() {
  const data = await apiFetch(`/meta/spend-by-day?days=${_days > 7 ? _days : 30}`);
  if (!data?.length) return;
  const chart = window.__charts?.metaSpend;
  if (!chart) return;
  chart.data.labels = data.map(d => d.date.slice(5));
  chart.data.datasets[0].data = data.map(d => d.spend);
  chart.update();
}

// ─── Configurações / Câmbio ───────────────────────────────
async function loadSettings() {
  const data = await apiFetch('/meta/settings');
  if (!data) return;
  const { spread, usd_rate_api: apiRate, usd_rate_manual, use_manual_rate } = data;
  set('rate-api',         apiRate ? 'R$ '+apiRate.toFixed(4) : 'Indisponível');
  set('rate-with-spread', apiRate ? 'R$ '+(apiRate*(1+spread/100)).toFixed(4) : '—');
  if ($('manual-rate-input') && usd_rate_manual) $('manual-rate-input').value = usd_rate_manual;
  if ($('use-manual-rate')) $('use-manual-rate').checked = !!use_manual_rate;
}

async function saveSettings() {
  const manual   = parseFloat($('manual-rate-input')?.value);
  const useManual = $('use-manual-rate')?.checked;
  const spread    = parseFloat($('spread-input')?.value || '5');
  const res = await fetch(API+'/meta/settings', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({usd_rate_manual: isNaN(manual)?null:manual, use_manual_rate:!!useManual, spread})
  });
  const msg = $('settings-msg');
  if (msg) { msg.textContent = res.ok ? '✅ Salvo!' : '❌ Erro'; setTimeout(()=>msg.textContent='',3000); }
  loadSettings();
}

// ─── Status de Integrações ────────────────────────────────
async function loadMetaStatus() {
  const data = await apiFetch('/meta/status');
  if (!data) return;
  ['brl','usd'].forEach(key => {
    const el = $(`meta-${key}-status`);
    if (!el) return;
    const ok = data[key]?.connected;
    el.innerHTML = `<div style="font-size:28px">${ok?'🟢':'🔴'}</div>
      <div><div class="kpi-value" style="font-size:16px">Meta Ads — ${data[key]?.label||key}</div>
      <div class="kpi-sub">${ok ? (data[key].account_name+' · Conectado') : ('Erro: '+data[key]?.message)}</div></div>`;
  });
}

// ─── Status de Conexões ───────────────────────────────────
async function loadConnectionStatus() {
  const data = await apiFetch('/dashboard/connections');
  if (!data) return;
  const sources = [
    { key: 'nuvemshop',       label: 'NuvemShop',        d: data.nuvemshop },
    { key: 'google_analytics',label: 'Google Analytics',  d: data.google_analytics },
    { key: 'meta_ads',        label: 'Meta Ads',          d: data.meta_ads },
  ];
  sources.forEach(({key, label, d}) => {
    const dot   = $(`dot-${key}`);
    const lbl   = $(`label-${key}`);
    if (dot) dot.style.background = d?.connected ? '#00d4aa' : '#ff6b6b';
    if (lbl) lbl.textContent = d?.connected ? label+' ✓' : label+' ✗';
  });
}

// ─── Refresh geral ────────────────────────────────────────
async function refreshAll() {
  const activePage = document.querySelector('.page.active')?.id?.replace('page-','') || 'dashboard';
  await loadDashboard();
  if (activePage === 'marketing') { await loadMarketing(); await loadCampaigns(); await loadMetaSpendChart(); }
  if (activePage === 'produtos')  { await loadProducts(); }
  if (activePage === 'clientes')  { await loadClientes(); }
  await loadRevenueChart();
}

// ─── Navegação ────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    const pg = item.dataset.page;
    if (pg === 'marketing')    { loadMarketing(); loadCampaigns(); loadMetaSpendChart(); }
    if (pg === 'produtos')     { loadProducts(); }
    if (pg === 'clientes')     { loadClientes(); }
    if (pg === 'configuracoes') loadSettings();
    if (pg === 'integracoes')  loadMetaStatus();
  });
});

// ─── Exportação ───────────────────────────────────────────
function exportData() { alert('Exportação em breve! Os dados serão gerados em CSV/Excel.'); }

// ─── Inicialização ────────────────────────────────────────
async function initAPI() {
  // Define período inicial como "Mês"
  applyDatePreset('month');
  document.querySelectorAll('.date-preset-btn[data-days="month"]').forEach(b => b.classList.add('active'));

  await loadConnectionStatus();
  await Promise.all([
    loadDashboard(),
    loadMarketing(),
    loadCampaigns(),
    loadProducts(),
    loadRevenueChart(),
    loadMetaSpendChart(),
  ]);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAPI);
} else {
  initAPI();
}
