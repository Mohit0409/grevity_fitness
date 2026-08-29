(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { events: [], loaded: false, requestId: 0 };
  const SENSITIVE_METADATA = /(password|secret|token|csrf|recovery|credential|authorization|cookie)/i;
  const ACTION_LABELS = {
    admin_login: 'Admin sign-in',
    admin_login_password: 'Password check',
    admin_second_factor: 'Second-factor check',
    admin_logout: 'Signed out',
    admin_logout_all: 'Signed out all sessions',
    admin_created: 'Staff account created',
  };

  function core() { return window.GravityAdminCore; }
  function humanize(value) {
    return String(value || '—').replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
  }
  function actionLabel(action) { return ACTION_LABELS[action] || humanize(action); }
  function targetLabel(event) {
    if (!event.targetType && !event.targetId) return '—';
    const type = humanize(event.targetType || 'record');
    return event.targetId ? `${type} · ${event.targetId}` : type;
  }

  function visibleMetadata(metadata) {
    return Object.entries(metadata || {}).filter(([key]) => !SENSITIVE_METADATA.test(key));
  }

  function searchableText(event) {
    const metadata = visibleMetadata(event.metadata).map(([key, value]) => `${key} ${formatMetadataValue(value)}`).join(' ');
    return [event.username, event.action, actionLabel(event.action), event.targetType, event.targetId, event.result, metadata]
      .filter(Boolean).join(' ').toLocaleLowerCase();
  }

  function filteredEvents() {
    const query = $('auditSearch').value.trim().toLocaleLowerCase();
    const result = $('auditResultFilter').value;
    const action = $('auditActionFilter').value;
    return state.events.filter((event) => {
      if (query && !searchableText(event).includes(query)) return false;
      if (result && String(event.result || '').toLocaleLowerCase() !== result) return false;
      if (action && event.action !== action) return false;
      return true;
    });
  }

  function resultBadge(result) {
    const span = document.createElement('span');
    const normalized = String(result || 'unknown').toLocaleLowerCase();
    span.className = `badge ${normalized === 'success' ? 'active' : normalized === 'failed' ? 'disabled' : ''}`;
    span.textContent = humanize(normalized);
    return span;
  }

  function renderActionOptions() {
    const select = $('auditActionFilter');
    const selected = select.value;
    const actions = Array.from(new Set(state.events.map((event) => event.action).filter(Boolean)))
      .sort((left, right) => actionLabel(left).localeCompare(actionLabel(right)));
    select.replaceChildren(new Option('All events', ''));
    for (const action of actions) select.appendChild(new Option(actionLabel(action), action));
    if (actions.includes(selected)) select.value = selected;
  }

  function setSummary(count, message = '') {
    $('auditSummary').textContent = message || `${count} of ${state.events.length} events shown · latest 200 server events`;
  }

  function renderEmpty(message) {
    const body = $('auditBody');
    body.replaceChildren();
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 6;
    cell.className = 'empty';
    cell.textContent = message;
    row.appendChild(cell);
    body.appendChild(row);
  }

  function renderRows() {
    const events = filteredEvents();
    const body = $('auditBody');
    body.replaceChildren();
    if (!events.length) {
      renderEmpty(state.events.length ? 'No audit events match these filters.' : 'No audit events yet.');
      setSummary(0);
      return;
    }
    for (const event of events) {
      const row = document.createElement('tr');
      const time = document.createElement('td');
      time.textContent = core().formatTime(event.createdAt);
      const actor = document.createElement('td');
      actor.textContent = event.username || 'System';
      const action = document.createElement('td');
      const actionName = document.createElement('strong');
      actionName.textContent = actionLabel(event.action);
      const actionCode = document.createElement('small');
      actionCode.textContent = event.action || '—';
      action.append(actionName, actionCode);
      const target = document.createElement('td');
      target.textContent = targetLabel(event);
      const result = document.createElement('td');
      result.appendChild(resultBadge(event.result));
      const detail = document.createElement('td');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'ghost compact-button';
      button.textContent = 'View details';
      button.addEventListener('click', () => openDetail(event));
      detail.appendChild(button);
      row.append(time, actor, action, target, result, detail);
      body.appendChild(row);
    }
    setSummary(events.length);
  }

  function addFact(list, label, value) {
    const dt = document.createElement('dt');
    dt.textContent = label;
    const dd = document.createElement('dd');
    dd.textContent = value || '—';
    list.append(dt, dd);
  }
  function openDetail(event) {
    $('auditDetailTitle').textContent = actionLabel(event.action);
    const facts = $('auditDetailFacts');
    facts.replaceChildren();
    addFact(facts, 'Time', core().formatTime(event.createdAt));
    addFact(facts, 'Staff', event.username || 'System');
    addFact(facts, 'Event code', event.action || '—');
    addFact(facts, 'Result', humanize(event.result));
    addFact(facts, 'Target', targetLabel(event));

    const metadata = $('auditDetailMetadata');
    metadata.replaceChildren();
    const entries = visibleMetadata(event.metadata);
    if (!entries.length) {
      const empty = document.createElement('p');
      empty.className = 'micro';
      empty.textContent = 'No additional non-sensitive event details.';
      metadata.appendChild(empty);
    } else {
      const list = document.createElement('dl');
      for (const [key, value] of entries) addFact(list, humanize(key), formatMetadataValue(value));
      metadata.appendChild(list);
    }
    $('auditDetailDialog').showModal();
  }

  function sanitizeMetadataValue(value, depth = 0) {
    if (depth > 3) return '[nested data]';
    if (Array.isArray(value)) return value.slice(0, 20).map((item) => sanitizeMetadataValue(item, depth + 1));
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value)
      .filter(([key]) => !SENSITIVE_METADATA.test(key))
      .map(([key, item]) => [key, sanitizeMetadataValue(item, depth + 1)]));
    return value;
  }
  function formatMetadataValue(value) {
    if (value === null || value === undefined || value === '') return '—';
    if (typeof value === 'object') {
      try { return JSON.stringify(sanitizeMetadataValue(value)).slice(0, 500); } catch (_) { return '[unavailable]'; }
    }
    return String(value).slice(0, 500);
  }
  function renderFailure() {
    const body = $('auditBody');
    body.replaceChildren();
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 6;
    const wrap = document.createElement('div');
    wrap.className = 'audit-error-state';
    const text = document.createElement('p');
    text.textContent = 'Audit trail is temporarily unavailable.';
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'ghost';
    retry.textContent = 'Retry audit trail';
    retry.addEventListener('click', refresh);
    wrap.append(text, retry);
    cell.appendChild(wrap);
    row.appendChild(cell);
    body.appendChild(row);
    setSummary(0, 'Audit events could not be loaded.');
  }

  async function refresh() {
    const requestId = ++state.requestId;
    $('auditPanel').setAttribute('aria-busy', 'true');
    renderEmpty('Loading audit events…');
    setSummary(0, 'Loading audit events…');
    try {
      const data = await core().api('/api/admin/audit?limit=200');
      if (requestId !== state.requestId) return;
      state.events = Array.isArray(data.audit) ? data.audit : [];
      state.loaded = true;
      renderActionOptions();
      renderRows();
    } catch (_) {
      if (requestId !== state.requestId) return;
      state.loaded = false;
      renderFailure();
    } finally {
      if (requestId === state.requestId) $('auditPanel').setAttribute('aria-busy', 'false');
    }
  }

  async function renderWorkspace() {
    if (!state.loaded) return refresh();
    renderRows();
  }

  $('auditSearch').addEventListener('input', renderRows);
  $('auditResultFilter').addEventListener('change', renderRows);
  $('auditActionFilter').addEventListener('change', renderRows);
  $('refreshAudit').addEventListener('click', refresh);

  window.GravityAuditAdmin = { renderWorkspace, refresh };
})();
