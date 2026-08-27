(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null };

  function hasPermission(permission) {
    const permissions = state.admin?.permissions || [];
    return permissions.includes('*') || permissions.includes(permission);
  }

  async function api(path) {
    const response = await fetch(path, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }

  function stat(label, value) {
    const card = document.createElement('div');
    card.className = 'stat';
    const small = document.createElement('small');
    small.textContent = label;
    const strong = document.createElement('strong');
    strong.textContent = value;
    card.append(small, strong);
    return card;
  }
  function row(area, check, ready, detail = '') {
    const tr = document.createElement('tr');
    const areaCell = document.createElement('td');
    areaCell.textContent = area;
    const checkCell = document.createElement('td');
    checkCell.textContent = check;
    const statusCell = document.createElement('td');
    const badge = document.createElement('span');
    badge.className = `badge${ready ? ' active' : ''}`;
    badge.textContent = detail || (ready ? 'ready' : 'blocked');
    statusCell.appendChild(badge);
    tr.append(areaCell, checkCell, statusCell);
    return tr;
  }

  async function syncAdmin() {
    const session = await api('/api/admin/session');
    if (!session.authenticated || !session.admin) return null;
    state.admin = session.admin;
    $('readinessNav').hidden = !hasPermission('system.readiness');
    return state.admin;
  }

  function addBooleanRows(body, area, object, labels) {
    for (const [key, label] of labels) {
      body.appendChild(row(area, label, Boolean(object?.[key])));
    }
  }
  function render(report) {
    const summary = $('readinessSummary');
    summary.replaceChildren(
      stat('Production ready', report.productionReady ? 'Yes' : 'No'),
      stat('Critical blockers', String(report.blockers?.length || 0)),
      stat('Business identity', report.business?.identityConfigured ? 'Ready' : 'Blocked'),
      stat('Tax invoice identity', report.business?.taxInvoiceIdentityConfigured ? 'Ready' : 'Blocked'),
    );
    $('readinessBlockers').textContent = report.blockers?.length
      ? `Critical blockers: ${report.blockers.join(' · ')}`
      : 'No critical configuration blockers remain.';

    const body = $('readinessBody');
    body.replaceChildren();
    addBooleanRows(body, 'Runtime', report.runtime, [
      ['productionMode', 'Production mode'], ['httpsBaseUrl', 'HTTPS base URL'], ['strongSecret', 'Strong application secret'],
    ]);
    addBooleanRows(body, 'Firebase', report.firebase, [
      ['clientConfigured', 'Browser authentication config'], ['backendConfigured', 'Admin verifier/service account'],
    ]);
    addBooleanRows(body, 'Razorpay', report.razorpay, [
      ['checkoutConfigured', 'Checkout credentials'], ['webhookConfigured', 'Webhook secret'],
    ]);
    addBooleanRows(body, 'Business', report.business, [
      ['identityConfigured', 'Verified business identity'], ['gstinConfigured', 'GSTIN configured'],
      ['gstinFormatValid', 'GSTIN format valid'], ['taxInvoiceEnabled', 'Tax invoice explicitly enabled'],
      ['taxInvoiceIdentityConfigured', 'Tax-invoice identity gate'],
    ]);
    for (const channel of ['email', 'sms', 'whatsapp']) {
      const item = report.notifications?.[channel] || {};
      body.appendChild(row('Notifications', channel, item.status === 'ready', String(item.status || 'blocked')));
    }
    addBooleanRows(body, 'Analytics', report.analytics, [
      ['googleConfigured', 'Google Analytics ID'], ['metaConfigured', 'Meta Pixel ID'],
      ['networkLoadingEnabled', 'Analytics network loading'],
    ]);
  }

  async function renderWorkspace() {
    if (!state.admin) await syncAdmin();
    if (!hasPermission('system.readiness')) return;
    const payload = await api('/api/admin/readiness');
    render(payload.readiness || {});
  }

  $('refreshReadiness').addEventListener('click', () => renderWorkspace().catch(() => {}));

  window.GravityReadinessAdmin = {
    setAdmin(admin) { state.admin = admin; },
    renderWorkspace,
  };

  const app = $('app');
  new MutationObserver(() => {
    if (!app.hidden) syncAdmin().catch(() => {});
  }).observe(app, { attributes: true, attributeFilter: ['hidden'] });
  syncAdmin().catch(() => {});
})();
