(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null, member: null, plans: [] };

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
    window.clearTimeout(node._membershipTimer);
    node._membershipTimer = window.setTimeout(() => { node.hidden = true; }, 4500);
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

  function formatDate(value) {
    if (!value) return '—';
    return new Date(Number(value) * 1000).toLocaleDateString();
  }

  function money(plan) {
    const amount = Number(plan.pricePaise || 0) / 100;
    try {
      return new Intl.NumberFormat('en-IN', {
        style: 'currency', currency: plan.currency || 'INR', maximumFractionDigits: 2,
      }).format(amount);
    } catch (_) {
      return `${plan.currency || 'INR'} ${amount.toFixed(2)}`;
    }
  }

  function statusBadge(status) {
    const span = document.createElement('span');
    span.className = `badge ${status === 'active' ? 'active' : 'disabled'}`;
    span.textContent = String(status || 'unknown').toUpperCase();
    return span;
  }

  function emptyRow(message, colspan) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = colspan;
    cell.className = 'empty';
    cell.textContent = message;
    row.appendChild(cell);
    return row;
  }

  async function loadPlans() {
    const payload = await api('/api/admin/membership/plans');
    state.plans = payload.plans || [];
    return state.plans;
  }

  function editPlan(plan = null) {
    $('planId').value = plan?.id || '';
    $('planName').value = plan?.name || '';
    $('planCode').value = plan?.code || '';
    $('planPrice').value = plan ? (Number(plan.pricePaise) / 100).toFixed(2) : '';
    $('planDuration').value = plan?.durationMonths || 1;
    $('planCurrency').value = plan?.currency || 'INR';
    $('planStatus').value = plan?.status || 'inactive';
    $('planSort').value = plan?.sortOrder || 0;
    $('planDescription').value = plan?.description || '';
    $('planEditor').hidden = false;
    $('planName').focus();
  }

  function planPayload() {
    return {
      name: $('planName').value.trim(), code: $('planCode').value.trim(),
      pricePaise: Math.round(Number($('planPrice').value) * 100),
      durationMonths: Number($('planDuration').value), currency: $('planCurrency').value.trim(),
      status: $('planStatus').value, sortOrder: Number($('planSort').value || 0),
      description: $('planDescription').value.trim(),
    };
  }

  async function renderPlans() {
    await loadPlans();
    const body = $('plansBody');
    body.replaceChildren();
    for (const plan of state.plans) {
      const row = document.createElement('tr');
      const name = document.createElement('td');
      const strong = document.createElement('strong');
      strong.textContent = plan.name;
      const code = document.createElement('small');
      code.textContent = plan.code;
      name.append(strong, document.createElement('br'), code);
      const price = document.createElement('td'); price.textContent = money(plan);
      const duration = document.createElement('td'); duration.textContent = `${plan.durationMonths} month${plan.durationMonths === 1 ? '' : 's'}`;
      const status = document.createElement('td'); status.appendChild(statusBadge(plan.status));
      const actions = document.createElement('td'); actions.className = 'row-actions';
      if (hasPermission('membership_plans.manage')) {
        const edit = document.createElement('button'); edit.className = 'ghost'; edit.textContent = 'Edit';
        edit.addEventListener('click', () => editPlan(plan));
        const toggle = document.createElement('button');
        toggle.textContent = plan.status === 'active' ? 'Deactivate' : 'Activate';
        toggle.addEventListener('click', () => togglePlan(plan));
        actions.append(edit, toggle);
      } else actions.textContent = 'Read only';
      row.append(name, price, duration, status, actions);
      body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow('No membership plans configured.', 5));
  }

  async function togglePlan(plan) {
    try {
      const next = plan.status === 'active' ? 'inactive' : 'active';
      await api(`/api/admin/membership/plans/${encodeURIComponent(plan.id)}`, {
        method: 'PATCH', body: { status: next },
      });
      flash(`Plan ${next === 'active' ? 'activated' : 'deactivated'}.`);
      await renderPlans();
    } catch (error) { flash(error.message, 'error'); }
  }

  async function renderExpiring() {
    const body = $('expiringBody');
    body.replaceChildren();
    if (!hasPermission('memberships.manage')) {
      body.appendChild(emptyRow('You do not have permission to view expiry operations.', 4));
      return;
    }
    const days = Number($('expiryDays').value || 7);
    const payload = await api(`/api/admin/memberships/expiring?days=${days}`);
    for (const item of payload.memberships || []) {
      const row = document.createElement('tr');
      for (const value of [
        item.customer?.displayName || item.customerId,
        item.planName || '—', formatDate(item.endsAt), String(item.daysRemaining ?? 0),
      ]) {
        const cell = document.createElement('td'); cell.textContent = value; row.appendChild(cell);
      }
      body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow(`No memberships expire within ${days} days.`, 4));
  }

  async function renderMemberMemberships() {
    if (!state.member) return;
    const payload = await api(`/api/admin/members/${encodeURIComponent(state.member.id)}/memberships`);
    const body = $('memberMembershipsBody');
    body.replaceChildren();
    for (const item of payload.memberships || []) {
      const row = document.createElement('tr');
      const plan = document.createElement('td'); plan.textContent = item.planName || '—';
      const status = document.createElement('td'); status.appendChild(statusBadge(item.status));
      const starts = document.createElement('td'); starts.textContent = formatDate(item.startsAt);
      const ends = document.createElement('td'); ends.textContent = formatDate(item.endsAt);
      const action = document.createElement('td'); action.className = 'row-actions';
      if (hasPermission('memberships.manage') && ['active', 'scheduled'].includes(item.status)) {
        const cancel = document.createElement('button'); cancel.className = 'ghost'; cancel.textContent = 'Cancel';
        cancel.addEventListener('click', () => cancelMembership(item));
        action.appendChild(cancel);
      } else action.textContent = '—';
      row.append(plan, status, starts, ends, action);
      body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow('No membership history for this member.', 5));
  }

  async function cancelMembership(item) {
    const reason = window.prompt('Cancellation reason (3–300 characters):', 'Member requested cancellation');
    if (!reason) return;
    try {
      await api(`/api/admin/memberships/${encodeURIComponent(item.id)}/cancel`, {
        method: 'PATCH', body: { reason },
      });
      flash('Membership cancelled.');
      await renderMemberMemberships();
      await renderExpiring();
    } catch (error) { flash(error.message, 'error'); }
  }

  async function openMember(member) {
    state.member = member;
    $('memberMembershipName').textContent = member.displayName || member.email || member.phone || member.id;
    $('memberMembershipPanel').hidden = false;
    $('memberMembershipForm').hidden = !hasPermission('memberships.manage');
    $('memberMembershipHint').textContent = hasPermission('memberships.manage')
      ? 'Renewals queue after the current live membership unless you choose a future start.'
      : 'Membership history is read-only for your role.';
    if (!state.plans.length) await loadPlans();
    const select = $('memberMembershipPlan');
    select.replaceChildren();
    for (const plan of state.plans.filter((item) => item.status === 'active')) {
      const option = document.createElement('option');
      option.value = plan.id;
      option.textContent = `${plan.name} · ${money(plan)} · ${plan.durationMonths} month${plan.durationMonths === 1 ? '' : 's'}`;
      select.appendChild(option);
    }
    $('assignMembership').disabled = !select.options.length;
    if (!select.options.length && hasPermission('memberships.manage')) {
      $('memberMembershipHint').textContent = 'No active plan is available. An Owner/Admin must verify and activate a plan first.';
    }
    await renderMemberMemberships();
    $('memberMembershipPanel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function renderWorkspace() {
    $('newPlan').hidden = !hasPermission('membership_plans.manage');
    if (!hasPermission('membership_plans.manage')) $('planEditor').hidden = true;
    await Promise.all([renderPlans(), renderExpiring()]);
  }

  $('newPlan').addEventListener('click', () => editPlan());
  $('cancelPlanEdit').addEventListener('click', () => { $('planEditor').hidden = true; });
  $('expiryDays').addEventListener('change', () => {
    renderExpiring().catch((error) => flash(error.message, 'error'));
  });
  $('closeMemberMembership').addEventListener('click', () => {
    state.member = null;
    $('memberMembershipPanel').hidden = true;
  });

  $('planForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!hasPermission('membership_plans.manage')) return;
    const planId = $('planId').value;
    try {
      await api(planId ? `/api/admin/membership/plans/${encodeURIComponent(planId)}` : '/api/admin/membership/plans', {
        method: planId ? 'PATCH' : 'POST', body: planPayload(),
      });
      $('planEditor').hidden = true;
      flash(planId ? 'Membership plan updated.' : 'Membership plan created.');
      await renderPlans();
    } catch (error) { flash(error.message, 'error'); }
  });

  $('memberMembershipForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!state.member || !hasPermission('memberships.manage')) return;
    const startInput = $('memberMembershipStart').value;
    const payload = { planId: $('memberMembershipPlan').value };
    if (startInput) payload.startsAt = Math.floor(new Date(startInput).getTime() / 1000);
    try {
      await api(`/api/admin/members/${encodeURIComponent(state.member.id)}/memberships`, {
        method: 'POST', body: payload,
      });
      $('memberMembershipStart').value = '';
      flash('Membership assigned. Renewal timing is server-controlled.');
      await renderMemberMemberships();
      await renderExpiring();
    } catch (error) { flash(error.message, 'error'); }
  });

  window.GravityMembershipAdmin = {
    setAdmin(admin) { state.admin = admin; },
    openMember(member) {
      openMember(member).catch((error) => flash(error.message, 'error'));
    },
    renderWorkspace() {
      return renderWorkspace().catch((error) => {
        flash(error.message, 'error');
        throw error;
      });
    },
  };
})();
