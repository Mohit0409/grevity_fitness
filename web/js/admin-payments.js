(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null, timer: null, requestId: 0 };
  const core = () => window.GravityAdminCore;

  function hasPermission(permission) { return core()?.hasPermission(permission) || false; }
  function formatDate(value) { if (!value) return '--'; const date = new Date(Number(value) * 1000); return Number.isNaN(date.getTime()) ? '--' : date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }); }
  function moneyPaise(value, currency = 'INR') { try { return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(value || 0) / 100); } catch (_) { return `${currency} ${Number(value || 0) / 100}`; } }
  function emptyRow(message, colspan) { const row = document.createElement('tr'); const cell = document.createElement('td'); cell.colSpan = colspan; cell.className = 'empty'; cell.textContent = message; row.appendChild(cell); return row; }

  async function renderWorkspace() {
    const requestId = ++state.requestId;
    const body = $('feesBody'); const panel = $('feesPanel'); panel?.setAttribute('aria-busy', 'true'); body.replaceChildren(emptyRow('Loading fee balances...', 8));
    if (!hasPermission('payments.read')) { body.replaceChildren(emptyRow('You do not have permission to view fee balances.', 8)); $('feesPendingTotal').textContent = '--'; panel?.setAttribute('aria-busy', 'false'); return; }
    const query = $('feeSearch').value.trim(); const mode = $('feeBalanceFilter').value;
    const params = new URLSearchParams(); if (query) params.set('q', query); if (mode === 'pending') params.set('pendingOnly', '1');
    let result;
    try { result = await core().api(`/api/admin/fees?${params.toString()}`); }
    catch (error) { if (requestId !== state.requestId) return; body.replaceChildren(emptyRow('Fee balances are temporarily unavailable. Retry or change the filters.', 8)); $('feesPendingTotal').textContent = '--'; throw error; }
    finally { if (requestId === state.requestId) panel?.setAttribute('aria-busy', 'false'); }
    if (requestId !== state.requestId) return;
    body.replaceChildren();
    $('feesPendingTotal').textContent = moneyPaise(result.pendingFeesTotalPaise);
    let rows = Array.isArray(result.rows) ? result.rows : [];
    if (mode === 'paid') rows = rows.filter((item) => Number(item.membership?.payment?.pendingPaise || 0) === 0);
    for (const item of rows) {
      const membership = item.membership || {}; const payment = membership.payment || {};
      const row = document.createElement('tr');
      const customer = document.createElement('td');
      const openCustomer = document.createElement('button'); openCustomer.type = 'button'; openCustomer.className = 'lead-link'; openCustomer.textContent = item.customerName || 'Customer'; openCustomer.addEventListener('click', () => window.GravityCustomerAdmin?.openCustomerById(item.customerId)); customer.appendChild(openCustomer);
      const number = document.createElement('td'); number.textContent = membership.membershipNumber || '--';
      const plan = document.createElement('td'); plan.textContent = membership.planName || '--';
      const total = document.createElement('td'); total.textContent = moneyPaise(payment.totalPaise, membership.currency);
      const paid = document.createElement('td'); paid.textContent = moneyPaise(payment.paidPaise, membership.currency);
      const pending = document.createElement('td'); pending.textContent = moneyPaise(payment.pendingPaise, membership.currency); if (Number(payment.pendingPaise || 0) > 0) pending.className = 'amount-pending';
      const expiry = document.createElement('td'); expiry.textContent = formatDate(membership.endsAt);
      const action = document.createElement('td');
      if (Number(payment.pendingPaise || 0) > 0 && hasPermission('payments.record')) {
        const button = document.createElement('button'); button.type = 'button'; button.className = 'table-action'; button.textContent = 'Record Payment'; button.addEventListener('click', () => window.GravityCustomerAdmin?.openPaymentFor(membership, { id: item.customerId, displayName: item.customerName, phone: item.phone })); action.appendChild(button);
      } else { const settled = document.createElement('span'); settled.className = 'data-unavailable'; settled.textContent = Number(payment.pendingPaise || 0) === 0 ? 'Fully paid' : 'Read only'; action.appendChild(settled); }
      row.append(customer, number, plan, total, paid, pending, expiry, action); body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow(mode === 'paid' ? 'No fully paid memberships match this search.' : 'No fee records match this filter.', 8));
  }

  function scheduleRender() {
    window.clearTimeout(state.timer);
    state.timer = window.setTimeout(() => renderWorkspace().catch(() => core().flash('Fee balances are temporarily unavailable.', 'error')), 220);
  }

  function renderNow() {
    window.clearTimeout(state.timer);
    state.timer = null;
    return renderWorkspace().catch(() => core().flash('Fee balances are temporarily unavailable.', 'error'));
  }

  $('feeSearch').addEventListener('input', scheduleRender);
  $('feeBalanceFilter').addEventListener('change', renderNow);
  $('refreshFees').addEventListener('click', renderNow);

  window.GravityPaymentAdmin = { setAdmin(admin) { state.admin = admin; }, renderWorkspace };
})();
