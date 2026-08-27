(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null };

  function hasPermission(permission) {
    const permissions = state.admin?.permissions || [];
    return permissions.includes('*') || permissions.includes(permission);
  }

  function csrfToken() {
    const part = document.cookie.split(';').map((item) => item.trim()).find((item) =>
      item.startsWith('gravity_admin_csrf=') || item.startsWith('__Host-gravity_admin_csrf=')
    );
    return part ? decodeURIComponent(part.slice(part.indexOf('=') + 1)) : '';
  }

  function flash(message, kind = 'ok') {
    const node = $('flash');
    node.textContent = message;
    node.className = `flash ${kind}`;
    node.hidden = false;
    window.clearTimeout(node._notificationTimer);
    node._notificationTimer = window.setTimeout(() => { node.hidden = true; }, 4500);
  }

  async function api(path, options = {}) {
    const request = { credentials: 'same-origin', ...options };
    request.headers = { Accept: 'application/json', ...(options.headers || {}) };
    if (options.body && typeof options.body !== 'string') {
      request.body = JSON.stringify(options.body);
      request.headers['Content-Type'] = 'application/json';
    }
    if (request.method && !['GET', 'HEAD'].includes(request.method)) {
      const csrf = csrfToken();
      if (csrf) request.headers['X-CSRF-Token'] = csrf;
    }
    const response = await fetch(path, request);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function formatDate(value) {
    if (!value) return '—';
    const date = new Date(Number(value) * 1000);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString();
  }

  function emptyRow(message) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 5;
    cell.className = 'empty';
    cell.textContent = message;
    row.appendChild(cell);
    return row;
  }

  function deliverySummary(deliveries) {
    if (!deliveries?.length) return 'No delivery records';
    return deliveries
      .map((item) => `${item.channel}: ${String(item.status || '').replaceAll('_', ' ')}`)
      .join(' · ');
  }

  async function syncAdmin() {
    const session = await api('/api/admin/session');
    if (!session.authenticated || !session.admin) return null;
    state.admin = session.admin;
    $('notificationsNav').hidden = !hasPermission('notifications.manage');
    $('adminIdentity').textContent = `${state.admin.username} · ${state.admin.role}`;
    if (window.GravityMembershipAdmin) window.GravityMembershipAdmin.setAdmin(state.admin);
    return state.admin;
  }

  async function renderWorkspace() {
    if (!state.admin) await syncAdmin();
    if (!hasPermission('notifications.manage')) return;
    const payload = await api('/api/admin/notifications?limit=100');
    const blockers = payload.providerBlockers || {};
    $('notificationBlockers').textContent = `Providers: ${Object.entries(blockers)
      .map(([key, value]) => `${key} ${value}`).join(' · ')}`;
    const body = $('notificationsBody');
    body.replaceChildren();

    for (const item of payload.notifications || []) {
      const row = document.createElement('tr');
      const member = document.createElement('td');
      member.textContent = item.customer?.displayName || item.customerId || 'Member';
      const membership = document.createElement('td');
      membership.textContent = item.payload?.membershipNumber || item.membershipId || '—';
      const windowCell = document.createElement('td');
      const ends = item.payload?.endsAt ? ` · ends ${formatDate(item.payload.endsAt)}` : '';
      windowCell.textContent = `${item.triggerDays} days${ends}`;
      const reminderState = document.createElement('td');
      reminderState.textContent = String(item.state || 'unknown').replaceAll('_', ' ');
      const delivery = document.createElement('td');
      delivery.textContent = deliverySummary(item.deliveries || []);
      row.append(member, membership, windowCell, reminderState, delivery);
      body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow('No expiry reminders have been generated yet.'));
  }

  async function scanNow() {
    if (!state.admin) await syncAdmin();
    if (!hasPermission('notifications.manage')) return;
    const daysBefore = Number($('notificationDays').value || 7);
    try {
      const payload = await api('/api/admin/notifications/scan', {
        method: 'POST', body: { daysBefore },
      });
      const result = payload.scan || {};
      flash(`Scan complete: ${result.created || 0} created, ${result.deduped || 0} deduped, ${result.suppressedRenewed || 0} suppressed.`);
      await renderWorkspace();
    } catch (error) { flash(error.message, 'error'); }
  }

  $('scanNotifications').addEventListener('click', scanNow);
  $('notificationDays').addEventListener('change', () => {
    renderWorkspace().catch((error) => flash(error.message, 'error'));
  });

  window.GravityNotificationAdmin = {
    setAdmin(admin) { state.admin = admin; },
    renderWorkspace() {
      return renderWorkspace().catch((error) => {
        flash(error.message, 'error');
        throw error;
      });
    },
  };

  const app = $('app');
  const observer = new MutationObserver(() => {
    if (!app.hidden) syncAdmin().catch(() => {});
  });
  observer.observe(app, { attributes: true, attributeFilter: ['hidden'] });
  syncAdmin().catch(() => {});
})();
