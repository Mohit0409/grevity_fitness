(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null, plans: [] };
  const core = () => window.GravityAdminCore;

  function hasPermission(permission) { return core()?.hasPermission(permission) || false; }
  function formatDate(value) { if (!value) return '--'; const date = new Date(Number(value) * 1000); return Number.isNaN(date.getTime()) ? '--' : date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }); }
  function moneyPaise(value, currency = 'INR') { try { return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(value || 0) / 100); } catch (_) { return `${currency} ${Number(value || 0) / 100}`; } }
  function money(plan) { return moneyPaise(plan.pricePaise, plan.currency || 'INR'); }
  function badge(status) { const span = document.createElement('span'); span.className = `badge badge--${String(status || 'unknown')}`; span.textContent = String(status || 'unknown').replaceAll('_', ' '); return span; }
  function emptyRow(message, colspan) { const row = document.createElement('tr'); const cell = document.createElement('td'); cell.colSpan = colspan; cell.className = 'empty'; cell.textContent = message; row.appendChild(cell); return row; }

  async function loadPlans() {
    const payload = await core().api('/api/admin/membership/plans');
    state.plans = Array.isArray(payload.plans) ? payload.plans : [];
    const filter = $('membershipPlanFilter'); const current = filter.value; filter.replaceChildren(new Option('All plans', ''));
    for (const plan of state.plans) filter.appendChild(new Option(plan.name, plan.id));
    if (Array.from(filter.options).some((option) => option.value === current)) filter.value = current;
    return state.plans;
  }

  function editPlan(plan = null) {
    $('planId').value = plan?.id || ''; $('planName').value = plan?.name || ''; $('planCode').value = plan?.code || '';
    $('planPrice').value = plan ? (Number(plan.pricePaise) / 100).toFixed(2) : ''; $('planDuration').value = plan?.durationMonths || 1;
    $('planCurrency').value = plan?.currency || 'INR'; $('planStatus').value = plan?.status || 'inactive'; $('planSort').value = plan?.sortOrder || 0; $('planDescription').value = plan?.description || '';
    $('planEditor').hidden = false; $('planName').focus();
  }

  function planPayload() {
    return { name: $('planName').value.trim(), code: $('planCode').value.trim(), pricePaise: Math.round(Number($('planPrice').value) * 100), durationMonths: Number($('planDuration').value), currency: $('planCurrency').value.trim(), status: $('planStatus').value, sortOrder: Number($('planSort').value || 0), description: $('planDescription').value.trim() };
  }

  async function togglePlan(plan) {
    try { const next = plan.status === 'active' ? 'inactive' : 'active'; await core().api(`/api/admin/membership/plans/${encodeURIComponent(plan.id)}`, { method: 'PATCH', body: { status: next } }); core().flash(`Plan ${next}.`); await renderPlans(); }
    catch (_) { core().flash('Plan status could not be changed.', 'error'); }
  }

  async function renderPlans() {
    await loadPlans(); const body = $('plansBody'); body.replaceChildren();
    for (const plan of state.plans) {
      const row = document.createElement('tr'); const name = document.createElement('td'); const strong = document.createElement('strong'); strong.textContent = plan.name; const code = document.createElement('small'); code.textContent = plan.code; name.append(strong, document.createElement('br'), code);
      const price = document.createElement('td'); price.textContent = money(plan); const duration = document.createElement('td'); duration.textContent = `${plan.durationMonths} month${plan.durationMonths === 1 ? '' : 's'}`; const status = document.createElement('td'); status.appendChild(badge(plan.status));
      const actions = document.createElement('td'); actions.className = 'row-actions';
      if (hasPermission('membership_plans.manage')) { const edit = document.createElement('button'); edit.className = 'ghost table-action'; edit.textContent = 'Edit'; edit.addEventListener('click', () => editPlan(plan)); const toggle = document.createElement('button'); toggle.className = 'table-action'; toggle.textContent = plan.status === 'active' ? 'Deactivate' : 'Activate'; toggle.addEventListener('click', () => togglePlan(plan)); actions.append(edit, toggle); } else actions.textContent = 'Read only';
      row.append(name, price, duration, status, actions); body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow('No membership plans configured.', 5));
  }

  async function renderMemberships() {
    const panel = $('membershipsPanel'); panel?.setAttribute('aria-busy', 'true');
    const body = $('membershipsBody'); body.replaceChildren(emptyRow('Loading memberships...', 8));
    const statusFilter = $('membershipStatusFilter').value;
    const planId = $('membershipPlanFilter').value;
    $('expiryDays').disabled = statusFilter !== 'expiring';
    const params = new URLSearchParams();
    if (statusFilter && statusFilter !== 'expiring') params.set('status', statusFilter);
    if (statusFilter === 'expiring') params.set('status', 'active');
    if (planId) params.set('planId', planId);
    let payload;
    try { payload = await core().api(`/api/admin/memberships?${params.toString()}`); }
    catch (error) { body.replaceChildren(emptyRow('Memberships are temporarily unavailable. Retry or change the filters.', 8)); throw error; }
    finally { panel?.setAttribute('aria-busy', 'false'); }
    let rows = Array.isArray(payload.memberships) ? payload.memberships : [];
    if (statusFilter === 'expiring') {
      const days = Number($('expiryDays').value || 7);
      rows = rows.filter((item) => Number(item.membership?.daysRemaining ?? Number.POSITIVE_INFINITY) <= days);
    }
    body.replaceChildren();
    for (const item of rows) {
      const membership = item.membership || {}; const customer = item.customer || {}; const payment = membership.payment || {};
      const row = document.createElement('tr');
      const customerCell = document.createElement('td'); customerCell.textContent = customer.displayName || 'Customer';
      const number = document.createElement('td'); number.textContent = membership.membershipNumber || '--';
      const plan = document.createElement('td'); plan.textContent = membership.planName || '--';
      const start = document.createElement('td'); start.textContent = formatDate(membership.startsAt);
      const expiry = document.createElement('td'); expiry.textContent = formatDate(membership.endsAt);
      const status = document.createElement('td'); status.appendChild(badge(membership.status));
      const money = document.createElement('td'); money.textContent = hasPermission('payments.read') ? `${moneyPaise(payment.paidPaise, membership.currency)} / ${moneyPaise(payment.pendingPaise, membership.currency)}` : 'Restricted';
      const action = document.createElement('td'); action.className = 'row-actions';
      const open = document.createElement('button'); open.type = 'button'; open.className = 'table-action'; open.textContent = 'Open'; open.addEventListener('click', () => window.GravityCustomerAdmin?.openCustomerById(customer.id)); action.appendChild(open);
      if (Number(payment.pendingPaise || 0) > 0 && hasPermission('payments.record')) { const pay = document.createElement('button'); pay.type = 'button'; pay.className = 'ghost table-action'; pay.textContent = 'Pay'; pay.addEventListener('click', () => window.GravityCustomerAdmin?.openPaymentFor(membership, { id: customer.id, displayName: customer.displayName })); action.appendChild(pay); }
      row.append(customerCell, number, plan, start, expiry, status, money, action); body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow('No memberships match these filters.', 8));
  }

  async function renderWorkspace() {
    $('newPlan').hidden = !hasPermission('membership_plans.manage'); if (!hasPermission('membership_plans.manage')) $('planEditor').hidden = true;
    await loadPlans(); await renderMemberships();
  }

  $('newPlan').addEventListener('click', () => editPlan()); $('cancelPlanEdit').addEventListener('click', () => { $('planEditor').hidden = true; });
  ['membershipStatusFilter', 'membershipPlanFilter', 'expiryDays'].forEach((id) => $(id).addEventListener('change', () => renderMemberships().catch(() => core().flash('Memberships could not be loaded.', 'error'))));
  $('planForm').addEventListener('submit', async (event) => { event.preventDefault(); if (!hasPermission('membership_plans.manage')) return; const id = $('planId').value; try { await core().api(id ? `/api/admin/membership/plans/${encodeURIComponent(id)}` : '/api/admin/membership/plans', { method: id ? 'PATCH' : 'POST', body: planPayload() }); $('planEditor').hidden = true; core().flash(id ? 'Membership plan updated.' : 'Membership plan created.'); await renderPlans(); } catch (_) { core().flash('Membership plan could not be saved.', 'error'); } });

  window.GravityMembershipAdmin = { setAdmin(admin) { state.admin = admin; }, renderWorkspace, refresh() { return renderWorkspace(); } };
})();
