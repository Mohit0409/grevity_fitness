(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null, view: 'dashboard', searchTimer: null };
  const setup = $('setup');
  const login = $('login');
  const app = $('app');
  const authError = $('authError');
  const flash = $('flash');

  function csrfToken() {
    const parts = document.cookie.split(';').map((part) => part.trim());
    const found = parts.find((part) =>
      part.startsWith('gravity_admin_csrf=') || part.startsWith('__Host-gravity_admin_csrf=')
    );
    return found ? decodeURIComponent(found.slice(found.indexOf('=') + 1)) : '';
  }

  function flashMessage(message, kind = 'ok') {
    flash.textContent = message;
    flash.className = `flash ${kind}`;
    flash.hidden = false;
    window.clearTimeout(flash._timer);
    flash._timer = window.setTimeout(() => { flash.hidden = true; }, 4500);
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
      error.data = data;
      throw error;
    }
    return data;
  }

  function hasPermission(permission) {
    const permissions = state.admin?.permissions || [];
    return permissions.includes('*') || permissions.includes(permission);
  }

  function setAuthScreen(name) {
    setup.hidden = name !== 'setup';
    login.hidden = name !== 'login';
    app.hidden = name !== 'app';
  }

  function formatTime(value) {
    if (!value) return 'â€”';
    const ms = Number(value) < 10_000_000_000 ? Number(value) * 1000 : Number(value);
    const date = new Date(ms);
    return Number.isNaN(date.getTime()) ? 'â€”' : date.toLocaleString();
  }

  function badge(status) {
    const span = document.createElement('span');
    span.className = `badge ${status === 'active' ? 'active' : 'disabled'}`;
    span.textContent = status || 'unknown';
    return span;
  }

  function emptyCell(message, colspan = 4) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = colspan;
    cell.className = 'empty';
    cell.textContent = message;
    row.appendChild(cell);
    return row;
  }

  async function renderDashboard() {
    const data = await api('/api/admin/dashboard');
    const stats = $('stats');
    stats.replaceChildren();
    const cards = [
      ['Total members', data.customers?.total ?? 0],
      ['Active members', data.customers?.active ?? 0],
      ['Disabled members', data.customers?.disabled ?? 0],
      ['Admin accounts', Object.values(data.admins || {}).reduce((a, b) => a + Number(b || 0), 0)],
    ];
    for (const [label, value] of cards) {
      const card = document.createElement('article');
      card.className = 'stat';
      const small = document.createElement('small');
      small.textContent = label;
      const strong = document.createElement('strong');
      strong.textContent = String(value);
      card.append(small, strong);
      stats.appendChild(card);
    }
    const recent = $('recentAudit');
    recent.replaceChildren();
    for (const item of data.recentAudit || []) {
      const row = document.createElement('div');
      row.className = 'audit-item';
      const label = document.createElement('span');
      label.textContent = item.action || 'activity';
      const time = document.createElement('small');
      time.textContent = `${item.result || ''} Â· ${formatTime(item.createdAt)}`;
      row.append(label, time);
      recent.appendChild(row);
    }
    if (!recent.children.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = 'No recent activity yet.';
      recent.appendChild(empty);
    }
  }

  async function renderMembers(query = '') {
    const data = await api(`/api/admin/members?q=${encodeURIComponent(query)}`);
    const body = $('membersBody');
    body.replaceChildren();
    for (const member of data.members || []) {
      const row = document.createElement('tr');
      const name = document.createElement('td');
      name.textContent = member.displayName || member.id;
      const contact = document.createElement('td');
      contact.textContent = member.email || member.phone || 'â€”';
      const status = document.createElement('td');
      status.appendChild(badge(member.status));
      const actions = document.createElement('td');
      actions.className = 'row-actions';
      if (hasPermission('members.manage')) {
        const button = document.createElement('button');
        const next = member.status === 'active' ? 'disabled' : 'active';
        button.textContent = next === 'active' ? 'Enable' : 'Disable';
        button.className = next === 'active' ? '' : 'ghost';
        button.addEventListener('click', async () => {
          try {
            await api(`/api/admin/members/${encodeURIComponent(member.id)}`, {
              method: 'PATCH', body: { status: next },
            });
            flashMessage(`Member ${next}.`);
            await renderMembers($('memberSearch').value);
          } catch (error) { flashMessage(error.message, 'error'); }
        });
        actions.appendChild(button);
      } else actions.textContent = 'Read only';
      if (window.GravityMembershipAdmin && hasPermission('members.read')) {
        const membershipButton = document.createElement('button');
        membershipButton.textContent = 'Membership';
        membershipButton.className = 'ghost';
        membershipButton.addEventListener('click', () => window.GravityMembershipAdmin.openMember(member));
        actions.appendChild(membershipButton);
      }
      row.append(name, contact, status, actions);
      body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyCell('No members found.'));
  }

  async function renderAdmins() {
    const data = await api('/api/admin/admins');
    const body = $('adminsBody');
    body.replaceChildren();
    for (const admin of data.admins || []) {
      const row = document.createElement('tr');
      const user = document.createElement('td'); user.textContent = admin.username;
      const role = document.createElement('td'); role.textContent = admin.role;
      const status = document.createElement('td'); status.appendChild(badge(admin.status));
      const action = document.createElement('td'); action.className = 'row-actions';
      if (admin.id === state.admin?.id) action.textContent = 'Current session';
      else {
        const button = document.createElement('button');
        const next = admin.status === 'active' ? 'disabled' : 'active';
        button.textContent = next === 'active' ? 'Enable' : 'Disable';
        button.className = next === 'active' ? '' : 'ghost';
        button.addEventListener('click', async () => {
          try {
            await api(`/api/admin/admins/${encodeURIComponent(admin.id)}`, {
              method: 'PATCH', body: { status: next },
            });
            flashMessage(`Administrator ${next}.`);
            await renderAdmins();
          } catch (error) { flashMessage(error.message, 'error'); }
        });
        action.appendChild(button);
      }
      row.append(user, role, status, action);
      body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyCell('No administrators found.'));
  }

  async function renderAudit() {
    const data = await api('/api/admin/audit?limit=100');
    const body = $('auditBody');
    body.replaceChildren();
    for (const item of data.audit || []) {
      const row = document.createElement('tr');
      for (const value of [formatTime(item.createdAt), item.username || 'system', item.action || 'â€”', item.result || 'â€”']) {
        const cell = document.createElement('td');
        cell.textContent = value;
        row.appendChild(cell);
      }
      body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyCell('No audit events yet.'));
  }

  async function showView(view) {
    const allowed = new Set(['dashboard', 'members', 'memberships', 'admins', 'audit']);
    state.view = allowed.has(view) ? view : 'dashboard';
    const titles = { dashboard: 'Overview', members: 'Members', memberships: 'Memberships', admins: 'Team access', audit: 'Audit trail' };
    document.querySelectorAll('.view').forEach((node) => { node.hidden = node.id !== `${state.view}View`; });
    document.querySelectorAll('nav [data-view]').forEach((node) => {
      node.classList.toggle('active', node.dataset.view === state.view);
    });
    $('viewTitle').textContent = titles[state.view];
    if (state.view === 'dashboard') await renderDashboard();
    if (state.view === 'members') await renderMembers($('memberSearch').value);
    if (state.view === 'admins') await renderAdmins();
    if (state.view === 'audit') await renderAudit();
  }

  async function enterApp(admin) {
    state.admin = admin;
    $('adminIdentity').textContent = `${admin.username} Â· ${admin.role}`;
    $('adminsNav').hidden = admin.role !== 'owner';
    $('newAdmin').hidden = admin.role !== 'owner';
    $('auditNav').hidden = !hasPermission('audit.read');
    setAuthScreen('app');
    await showView('dashboard');
  }

  async function loadSession() {
    try {
      const data = await api('/api/admin/session');
      if (!data.configured || data.bootstrapRequired) { setAuthScreen('setup'); return; }
      if (data.authenticated && data.admin) { await enterApp(data.admin); return; }
      setAuthScreen('login');
    } catch (_) {
      setAuthScreen('login');
      authError.textContent = 'Admin service is temporarily unavailable.';
    }
  }

  $('loginForm').addEventListener('submit', async (event) => {
    event.preventDefault(); authError.textContent = '';
    try {
      await api('/api/admin/login', {
        method: 'POST', body: { username: $('username').value, password: $('password').value },
      });
      $('password').value = '';
      $('loginForm').hidden = true;
      $('factorForm').hidden = false;
      $('factor').focus();
    } catch (_) { authError.textContent = 'Invalid administrator credentials or too many attempts.'; }
  });

  $('factorForm').addEventListener('submit', async (event) => {
    event.preventDefault(); authError.textContent = '';
    try {
      const data = await api('/api/admin/verify', { method: 'POST', body: { code: $('factor').value } });
      $('factor').value = '';
      await enterApp(data.admin);
    } catch (_) { authError.textContent = 'Invalid or expired verification code.'; }
  });

  $('backLogin').addEventListener('click', () => {
    $('factorForm').hidden = true; $('loginForm').hidden = false;
    authError.textContent = ''; $('username').focus();
  });

  $('logout').addEventListener('click', async () => {
    try { await api('/api/admin/logout', { method: 'POST' }); } catch (_) {}
    state.admin = null;
    $('factorForm').hidden = true; $('loginForm').hidden = false;
    setAuthScreen('login');
  });

  document.querySelectorAll('nav [data-view]').forEach((button) => {
    button.addEventListener('click', async () => {
      try { await showView(button.dataset.view); }
      catch (error) {
        if (error.status === 401) await loadSession();
        else flashMessage(error.message, 'error');
      }
    });
  });

  $('memberSearch').addEventListener('input', () => {
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => {
      renderMembers($('memberSearch').value).catch((error) => flashMessage(error.message, 'error'));
    }, 250);
  });

  $('newAdmin').addEventListener('click', () => {
    $('adminCreate').hidden = !$('adminCreate').hidden;
    $('adminSecret').hidden = true;
    $('adminSecret').textContent = '';
  });

  $('adminForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const data = await api('/api/admin/admins', {
        method: 'POST',
        body: {
          username: $('newUsername').value,
          password: $('newPassword').value,
          role: $('newRole').value,
        },
      });
      $('newUsername').value = ''; $('newPassword').value = '';
      const secret = [
        `TOTP secret: ${data.totpSecret}`,
        `TOTP URI: ${data.otpauthUri}`,
        'Recovery codes:', ...(data.recoveryCodes || []),
      ].join('\n');
      $('adminSecret').textContent = secret;
      $('adminSecret').hidden = false;
      flashMessage('Administrator created. Save the enrollment data now.');
      await renderAdmins();
    } catch (error) { flashMessage(error.message, 'error'); }
  });

  loadSession();
})();
