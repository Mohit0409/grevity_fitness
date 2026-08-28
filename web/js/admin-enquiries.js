(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null, current: null, timer: null };

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

  async function api(path, options = {}) {
    const request = { credentials: 'same-origin', ...options };
    request.headers = { Accept: 'application/json', ...(options.headers || {}) };
    if (options.body && typeof options.body !== 'string') {
      request.body = JSON.stringify(options.body);
      request.headers['Content-Type'] = 'application/json';
    }
    if (request.method && !['GET', 'HEAD'].includes(request.method)) {
      request.headers['X-CSRF-Token'] = csrfToken();
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

  function flash(message, kind = 'ok') {
    const node = $('flash');
    node.textContent = message;
    node.className = `flash ${kind}`;
    node.hidden = false;
    window.clearTimeout(node._enquiryTimer);
    node._enquiryTimer = window.setTimeout(() => { node.hidden = true; }, 4500);
  }

  function formatTime(value) {
    if (!value) return '—';
    const date = new Date(Number(value) * 1000);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
  }

  function typeLabel(value) {
    return ({ trial_visit: 'Trial visit', membership: 'Membership', coaching: 'Coaching', general: 'General' })[value] || value;
  }

  function statusBadge(status) {
    const badge = document.createElement('span');
    badge.className = `badge lead-status lead-status--${status}`;
    badge.textContent = status || 'unknown';
    return badge;
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

  function queryString() {
    const query = new URLSearchParams();
    const search = $('enquirySearch').value.trim();
    const status = $('enquiryStatusFilter').value;
    const type = $('enquiryTypeFilter').value;
    if (search) query.set('q', search);
    if (status) query.set('status', status);
    if (type) query.set('type', type);
    return query.toString();
  }

  async function renderList() {
    if (!hasPermission('enquiries.read')) return;
    const payload = await api(`/api/admin/enquiries?${queryString()}`);
    const body = $('enquiriesBody');
    body.replaceChildren();
    for (const enquiry of payload.enquiries || []) {
      const row = document.createElement('tr');
      const request = document.createElement('td');
      const open = document.createElement('button');
      open.type = 'button';
      open.className = 'lead-link';
      open.textContent = enquiry.reference;
      open.addEventListener('click', () => openDetail(enquiry.id));
      const name = document.createElement('small');
      name.textContent = enquiry.name;
      request.append(open, name);
      const contact = document.createElement('td');
      contact.textContent = enquiry.phone || enquiry.email || '—';
      const type = document.createElement('td');
      type.textContent = typeLabel(enquiry.type);
      const status = document.createElement('td');
      status.appendChild(statusBadge(enquiry.status));
      const received = document.createElement('td');
      received.textContent = formatTime(enquiry.createdAt);
      row.append(request, contact, type, status, received);
      body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow('No enquiries match these filters.'));
  }

  function fact(term, value) {
    const fragment = document.createDocumentFragment();
    const dt = document.createElement('dt');
    dt.textContent = term;
    const dd = document.createElement('dd');
    dd.textContent = value || '—';
    fragment.append(dt, dd);
    return fragment;
  }

  function renderDetail(enquiry) {
    state.current = enquiry;
    $('enquiryDetailReference').textContent = enquiry.reference;
    const facts = $('enquiryFacts');
    facts.replaceChildren(
      fact('Name', enquiry.name), fact('Phone', enquiry.phone), fact('Email', enquiry.email),
      fact('Type', typeLabel(enquiry.type)), fact('Plan', enquiry.planName),
      fact('Preferred date', enquiry.preferredDate), fact('Time preference', typeLabel(enquiry.preferredTime)),
      fact('Received', formatTime(enquiry.createdAt)), fact('Retain until', formatTime(enquiry.retentionExpiresAt)),
    );
    $('enquiryMessage').textContent = enquiry.message || '';
    $('enquiryMessage').hidden = !enquiry.message;
    $('enquiryDetailStatus').value = enquiry.status;
    $('saveEnquiryStatus').hidden = !hasPermission('enquiries.manage');
    $('enquiryNoteForm').hidden = !hasPermission('enquiries.manage');
    const notes = $('enquiryNotes');
    notes.replaceChildren();
    for (const item of enquiry.notes || []) {
      const article = document.createElement('article');
      const copy = document.createElement('p');
      copy.textContent = item.note;
      const meta = document.createElement('small');
      meta.textContent = `${item.username} · ${formatTime(item.createdAt)}`;
      article.append(copy, meta);
      notes.appendChild(article);
    }
    if (!notes.children.length) {
      const empty = document.createElement('p');
      empty.className = 'micro';
      empty.textContent = 'No private notes yet.';
      notes.appendChild(empty);
    }
    $('enquiryDetail').hidden = false;
  }

  async function openDetail(id) {
    try {
      const payload = await api(`/api/admin/enquiries/${encodeURIComponent(id)}`);
      renderDetail(payload.enquiry);
      $('enquiryDetail').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      flash(error.message, 'error');
    }
  }

  async function saveStatus() {
    if (!state.current || !hasPermission('enquiries.manage')) return;
    try {
      const payload = await api(`/api/admin/enquiries/${encodeURIComponent(state.current.id)}/status`, {
        method: 'PATCH', body: { status: $('enquiryDetailStatus').value },
      });
      renderDetail(payload.enquiry);
      await renderList();
      flash('Enquiry status updated.');
    } catch (error) {
      flash(error.message, 'error');
    }
  }

  async function addNote(event) {
    event.preventDefault();
    if (!state.current || !hasPermission('enquiries.manage')) return;
    try {
      const payload = await api(`/api/admin/enquiries/${encodeURIComponent(state.current.id)}/notes`, {
        method: 'POST', body: { note: $('enquiryNote').value },
      });
      $('enquiryNote').value = '';
      renderDetail(payload.enquiry);
      flash('Private note added.');
    } catch (error) {
      flash(error.message, 'error');
    }
  }

  function scheduleRender() {
    window.clearTimeout(state.timer);
    state.timer = window.setTimeout(() => renderList().catch((error) => flash(error.message, 'error')), 250);
  }

  $('refreshEnquiries').addEventListener('click', () => renderList().catch((error) => flash(error.message, 'error')));
  $('enquirySearch').addEventListener('input', scheduleRender);
  $('enquiryStatusFilter').addEventListener('change', scheduleRender);
  $('enquiryTypeFilter').addEventListener('change', scheduleRender);
  $('closeEnquiryDetail').addEventListener('click', () => { $('enquiryDetail').hidden = true; state.current = null; });
  $('saveEnquiryStatus').addEventListener('click', saveStatus);
  $('enquiryNoteForm').addEventListener('submit', addNote);

  window.GravityEnquiryAdmin = {
    setAdmin(admin) {
      state.admin = admin;
      $('enquiriesNav').hidden = !hasPermission('enquiries.read');
    },
    renderWorkspace() {
      return renderList().catch((error) => {
        flash(error.message, 'error');
        throw error;
      });
    },
  };
})();
