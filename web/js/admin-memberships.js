(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null, plans: [] };
  const core = () => window.GravityAdminCore;

  function hasPermission(permission) { return core()?.hasPermission(permission) || false; }
  function formatDate(value) { if (!value) return '--'; const date = new Date(Number(value) * 1000); return Number.isNaN(date.getTime()) ? '--' : date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }); }
  function money(plan) { try { return new Intl.NumberFormat('en-IN', { style: 'currency', currency: plan.currency || 'INR', maximumFractionDigits: 0 }).format(Number(plan.pricePaise || 0) / 100); } catch (_) { return `${plan.currency || 'INR'} ${Number(plan.pricePaise || 0) / 100}`; } }
  function badge(status) { const span = document.createElement('span'); span.className = `badge badge--${String(status || 'unknown')}`; span.textContent = String(status || 'unknown').replaceAll('_', ' '); return span; }
  function emptyRow(message, colspan) { const row = document.createElement('tr'); const cell = document.createElement('td'); cell.colSpan = colspan; cell.className = 'empty'; cell.textContent = message; row.appendChild(cell); return row; }

  async function loadPlans() {
    const payload = await core().api('/api/admin/membership/plans');
    state.plans = Array.isArray(payload.plans) ? payload.plans : [];
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

  async function renderExpiring() {
    const body = $('expiringBody'); body.replaceChildren();
    if (!hasPermission('memberships.manage')) { body.appendChild(emptyRow('You do not have permission to view membership operations.', 6)); return; }
    const days = Number($('expiryDays').value || 7); const payload = await core().api(`/api/admin/memberships/expiring?days=${days}`); const memberships = Array.isArray(payload.memberships) ? payload.memberships : [];
    for (const item of memberships) {
      const row = document.createElement('tr');
      for (const value of [item.customer?.displayName || 'Customer', item.planName || '--', item.membershipNumber || '--', formatDate(item.endsAt), `${Number(item.daysRemaining ?? 0)} day${Number(item.daysRemaining ?? 0) === 1 ? '' : 's'}`]) { const cell = document.createElement('td'); cell.textContent = value; row.appendChild(cell); }
      const action = document.createElement('td'); const open = document.createElement('button'); open.type = 'button'; open.className = 'table-action'; open.textContent = 'Open customer'; open.addEventListener('click', () => window.GravityCustomerAdmin?.openCustomer({ id: item.customerId, displayName: item.customer?.displayName, email: item.customer?.email, phone: item.customer?.phone, status: 'active' })); action.appendChild(open); row.appendChild(action); body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow(`No memberships expire within ${days} days.`, 6));
  }

  async function renderWorkspace() { $('newPlan').hidden = !hasPermission('membership_plans.manage'); if (!hasPermission('membership_plans.manage')) $('planEditor').hidden = true; await Promise.all([renderPlans(), renderExpiring()]); }

  $('newPlan').addEventListener('click', () => editPlan()); $('cancelPlanEdit').addEventListener('click', () => { $('planEditor').hidden = true; });
  $('expiryDays').addEventListener('change', () => renderExpiring().catch(() => core().flash('Expiring memberships could not be loaded.', 'error')));
  $('planForm').addEventListener('submit', async (event) => { event.preventDefault(); if (!hasPermission('membership_plans.manage')) return; const id = $('planId').value; try { await core().api(id ? `/api/admin/membership/plans/${encodeURIComponent(id)}` : '/api/admin/membership/plans', { method: id ? 'PATCH' : 'POST', body: planPayload() }); $('planEditor').hidden = true; core().flash(id ? 'Membership plan updated.' : 'Membership plan created.'); await renderPlans(); } catch (_) { core().flash('Membership plan could not be saved.', 'error'); } });

  window.GravityMembershipAdmin = { setAdmin(admin) { state.admin = admin; }, renderWorkspace, refresh() { return renderWorkspace(); } };
})();
