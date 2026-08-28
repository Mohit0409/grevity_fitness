(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null, notifications: [], providerBlockers: {}, filter: 'all' };
  const channels = ['email', 'sms', 'whatsapp'];

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
      const error = new Error('notification_request_failed');
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function formatDateTime(value) {
    if (!value) return 'Not available';
    const numeric = Number(value);
    const date = new Date(numeric < 10_000_000_000 ? numeric * 1000 : numeric);
    if (Number.isNaN(date.getTime())) return 'Not available';
    return date.toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
    });
  }

  function triggerLabel(days) {
    const value = Number(days);
    if (value === 0) return 'Expired today';
    if (value === 1) return '1 day before expiry';
    if (Number.isFinite(value) && value > 1) return `${value} days before expiry`;
    return 'Reminder window unavailable';
  }

  function channelLabel(channel) {
    if (channel === 'sms') return 'SMS';
    if (channel === 'whatsapp') return 'WhatsApp';
    return 'Email';
  }

  function statusFor(delivery, reminderState) {
    if (!delivery) return { key: 'unknown', label: 'Status unavailable' };
    if (delivery.status === 'sent') return { key: 'sent', label: 'Sent' };
    if (reminderState === 'suppressed') return { key: 'suppressed', label: 'Suppressed after renewal' };
    if (delivery.status === 'queued') return { key: 'queued', label: 'Queued' };
    if (delivery.status === 'failed') {
      return delivery.nextAttemptAt
        ? { key: 'retrying', label: 'Retrying' }
        : { key: 'failed', label: 'Failed' };
    }
    if (delivery.status === 'blocked_external_config' || String(delivery.status || '').startsWith('blocked_')) {
      return { key: 'blocked', label: 'Blocked by configuration' };
    }
    if (delivery.status === 'missing_recipient') return { key: 'missing', label: 'Missing recipient' };
    return { key: 'unknown', label: 'Status unavailable' };
  }

  function createStatus(channel, delivery, reminderState) {
    const status = statusFor(delivery, reminderState);
    const row = document.createElement('div');
    row.className = 'notification-channel-row';
    const name = document.createElement('span');
    name.className = 'notification-channel-name';
    name.textContent = channelLabel(channel);
    const badge = document.createElement('span');
    badge.className = `notification-status notification-status--${status.key}`;
    badge.setAttribute('aria-label', `${channelLabel(channel)}: ${status.label}`);
    badge.textContent = status.label;
    row.append(name, badge);
    return row;
  }

  function providerLabel(value) {
    return value === 'READY'
      ? { key: 'ready', label: 'Ready' }
      : { key: 'blocked', label: 'Blocked by configuration' };
  }

  function renderProviderState() {
    const root = $('notificationBlockers');
    root.replaceChildren();
    root.setAttribute('role', 'list');
    for (const channel of channels) {
      const stateLabel = providerLabel(state.providerBlockers?.[channel]);
      const item = document.createElement('div');
      item.className = `notification-provider notification-provider--${stateLabel.key}`;
      item.setAttribute('role', 'listitem');
      item.setAttribute('aria-label', `${channelLabel(channel)} provider: ${stateLabel.label}`);
      const name = document.createElement('strong');
      name.textContent = channelLabel(channel);
      const copy = document.createElement('span');
      copy.textContent = stateLabel.label;
      item.append(name, copy);
      root.appendChild(item);
    }
  }

  function appendFact(list, term, value) {
    const dt = document.createElement('dt');
    dt.textContent = term;
    const dd = document.createElement('dd');
    dd.textContent = value;
    list.append(dt, dd);
  }

  function deliveryFor(item, audience, channel) {
    const deliveries = item.deliveries || [];
    const exact = deliveries.find((delivery) => delivery.recipientRole === audience && delivery.channel === channel);
    if (exact) return exact;
    if (audience === 'customer') {
      return deliveries.find((delivery) => !delivery.recipientRole && delivery.channel === channel) || null;
    }
    return null;
  }

  function renderAudience(title, item, audience) {
    const section = document.createElement('section');
    section.className = 'notification-audience';
    const heading = document.createElement('h5');
    heading.textContent = title;
    section.appendChild(heading);
    for (const channel of channels) {
      section.appendChild(createStatus(channel, deliveryFor(item, audience, channel), item.state));
    }
    return section;
  }

  function renderReminder(item) {
    const card = document.createElement('article');
    card.className = 'notification-admin-card';
    card.setAttribute('role', 'listitem');

    const head = document.createElement('div');
    head.className = 'notification-admin-head';
    const nameWrap = document.createElement('div');
    const name = document.createElement('h4');
    name.textContent = item.customer?.displayName || 'Customer';
    const membership = document.createElement('p');
    membership.textContent = item.payload?.membershipNumber
      ? `Membership ${item.payload.membershipNumber}` : 'Membership number unavailable';
    nameWrap.append(name, membership);
    const trigger = document.createElement('span');
    trigger.className = `notification-trigger${item.state === 'suppressed' ? ' notification-trigger--suppressed' : ''}`;
    trigger.textContent = item.state === 'suppressed' ? 'Suppressed after renewal' : triggerLabel(item.triggerDays);
    head.append(nameWrap, trigger);

    const facts = document.createElement('dl');
    facts.className = 'notification-admin-facts';
    appendFact(facts, 'Plan', item.payload?.planName || 'Not available');
    appendFact(facts, 'Expiry', formatDateTime(item.payload?.endsAt));
    appendFact(facts, 'Trigger window', triggerLabel(item.triggerDays));

    const audiences = document.createElement('div');
    audiences.className = 'notification-audience-grid';
    audiences.append(renderAudience('Customer notifications', item, 'customer'));
    audiences.append(renderAudience('Owner notifications', item, 'owner'));
    card.append(head, facts, audiences);
    return card;
  }

  function hasStatus(item, predicate) {
    return (item.deliveries || []).some(predicate);
  }

  function matchesFilter(item) {
    if (state.filter === 'expiring') return Number(item.triggerDays) > 0 && item.state !== 'suppressed';
    if (state.filter === 'expired') return Number(item.triggerDays) === 0 && item.state !== 'suppressed';
    if (state.filter === 'failed') return hasStatus(item, (delivery) => delivery.status === 'failed');
    if (state.filter === 'blocked') return hasStatus(item, (delivery) => String(delivery.status || '').startsWith('blocked_'));
    if (state.filter === 'suppressed') return item.state === 'suppressed';
    return true;
  }

  function renderList() {
    const list = $('notificationsList');
    list.replaceChildren();
    const visible = state.notifications.filter(matchesFilter);
    for (const item of visible) list.appendChild(renderReminder(item));
    if (!visible.length) {
      const empty = document.createElement('p');
      empty.className = 'notification-empty';
      empty.textContent = state.notifications.length ? 'No reminders match this filter.' : 'No membership expiry reminders yet.';
      list.appendChild(empty);
    }
    $('notificationFilterSummary').textContent = `${visible.length} of ${state.notifications.length} reminders shown`;
    list.setAttribute('aria-busy', 'false');
  }

  function renderUnavailable() {
    const list = $('notificationsList');
    list.replaceChildren();
    const error = document.createElement('p');
    error.className = 'notification-empty notification-error';
    error.setAttribute('role', 'alert');
    error.textContent = 'Notification data is temporarily unavailable. Try again later.';
    list.appendChild(error);
    list.setAttribute('aria-busy', 'false');
    $('notificationFilterSummary').textContent = 'Notification data unavailable';
    $('notificationBlockers').replaceChildren();
  }

  async function syncAdmin() {
    const session = await api('/api/admin/session');
    if (!session.authenticated || !session.admin) return null;
    state.admin = session.admin;
    $('notificationsNav').hidden = !hasPermission('notifications.manage');
    if (window.GravityMembershipAdmin) window.GravityMembershipAdmin.setAdmin(state.admin);
    return state.admin;
  }

  async function renderWorkspace() {
    if (!state.admin) await syncAdmin();
    if (!hasPermission('notifications.manage')) return;
    const list = $('notificationsList');
    list.setAttribute('aria-busy', 'true');
    try {
      const payload = await api('/api/admin/notifications?limit=100');
      state.notifications = (Array.isArray(payload.notifications) ? payload.notifications : [])
        .filter((item) => !item.eventType || item.eventType === 'membership_expiry');
      state.providerBlockers = payload.providerBlockers || {};
      renderProviderState();
      renderList();
    } catch (_) {
      renderUnavailable();
    }
  }

  async function scanNow() {
    if (!state.admin) await syncAdmin();
    if (!hasPermission('notifications.manage')) return;
    const daysBefore = Number($('notificationDays').value || 7);
    const button = $('scanNotifications');
    button.disabled = true;
    try {
      const payload = await api('/api/admin/notifications/scan', { method: 'POST', body: { daysBefore } });
      const result = payload.scan || {};
      flash(`Scan complete: ${result.created || 0} created, ${result.deduped || 0} already present, ${result.suppressedRenewed || 0} renewed.`);
      await renderWorkspace();
    } catch (_) {
      flash('Reminder scan could not be completed. Try again later.', 'error');
    } finally {
      button.disabled = false;
    }
  }

  $('scanNotifications').addEventListener('click', scanNow);
  $('notificationFilter').addEventListener('change', (event) => {
    state.filter = event.target.value;
    renderList();
  });

  window.GravityNotificationAdmin = {
    setAdmin(admin) { state.admin = admin; },
    renderWorkspace,
  };

  const app = $('app');
  const observer = new MutationObserver(() => {
    if (!app.hidden) syncAdmin().catch(() => {});
  });
  observer.observe(app, { attributes: true, attributeFilter: ['hidden'] });
  syncAdmin().catch(() => {});
})();
