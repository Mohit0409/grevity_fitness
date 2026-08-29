(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null };
  const core = () => window.GravityAdminCore;

  function formatDate(value) {
    if (!value) return '--';
    const numeric = Number(value);
    const date = new Date(numeric < 10_000_000_000 ? numeric * 1000 : numeric);
    return Number.isNaN(date.getTime()) ? '--' : date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  function moneyPaise(value, currency = 'INR') {
    const amount = Number(value || 0) / 100;
    try { return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 0 }).format(amount); }
    catch (_) { return `${currency} ${amount.toFixed(0)}`; }
  }

  function stat(label, value, hint = '') {
    const item = document.createElement('article');
    item.className = 'software-stat';
    const small = document.createElement('span'); small.textContent = label;
    const strong = document.createElement('strong'); strong.textContent = value;
    item.append(small, strong);
    if (hint) { const note = document.createElement('small'); note.textContent = hint; item.appendChild(note); }
    return item;
  }

  function emptyRow(message, colspan) {
    const row = document.createElement('tr');
    const cell = document.createElement('td'); cell.colSpan = colspan; cell.className = 'empty'; cell.textContent = message;
    row.appendChild(cell); return row;
  }

  function renderStats(stats = {}) {
    const root = $('stats'); root.replaceChildren();
    root.append(
      stat('Total Customers', String(stats.totalCustomers ?? 0)),
      stat('Active Members', String(stats.activeMembers ?? 0)),
      stat('Expiring Soon', String(stats.expiringSoon ?? 0), 'Next 7 days'),
      stat('Expired Members', String(stats.expiredMembers ?? 0)),
      stat('Pending Fees', moneyPaise(stats.pendingFeesTotalPaise)),
      stat('New This Month', String(stats.newCustomersThisMonth ?? 0)),
      stat('Payments Today', moneyPaise(stats.paymentsReceivedTodayPaise)),
      stat('Payments This Month', moneyPaise(stats.paymentsReceivedThisMonthPaise)),
    );
  }

  function expiringRows(groups = {}) {
    return [
      ['Expired today', groups.today || []],
      ['Tomorrow', groups.tomorrow || []],
      ['Within 3 days', groups.threeDays || []],
      ['Within 7 days', groups.sevenDays || []],
    ].flatMap(([priority, rows]) => rows.map((row) => ({ ...row, priority })));
  }

  function renderExpiring(groups) {
    const body = $('dashboardExpiringBody'); body.replaceChildren();
    for (const item of expiringRows(groups).slice(0, 12)) {
      const row = document.createElement('tr');
      const customer = document.createElement('td'); customer.textContent = item.customerName || 'Customer';
      const plan = document.createElement('td'); plan.textContent = item.planName || '--';
      const expiry = document.createElement('td'); expiry.textContent = formatDate(item.endsAt);
      const priority = document.createElement('td'); priority.textContent = item.priority;
      const action = document.createElement('td');
      const button = document.createElement('button'); button.type = 'button'; button.className = 'table-action'; button.textContent = 'Open';
      button.addEventListener('click', () => window.GravityCustomerAdmin?.openCustomerById(item.customerId));
      action.appendChild(button); row.append(customer, plan, expiry, priority, action); body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow('No memberships need expiry attention.', 5));
  }

  function renderPendingFees(items = []) {
    const root = $('dashboardFeesState'); root.replaceChildren();
    for (const item of items.slice(0, 6)) {
      const row = document.createElement('button'); row.type = 'button'; row.className = 'activity-row';
      const text = document.createElement('span');
      const strong = document.createElement('strong'); strong.textContent = item.customerName || 'Customer';
      const small = document.createElement('small'); small.textContent = `${item.membershipNumber || '--'} ? ${item.planName || '--'}`;
      text.append(strong, small);
      const amount = document.createElement('strong'); amount.textContent = moneyPaise(item.pendingPaise);
      row.append(text, amount); row.addEventListener('click', () => core()?.openView('fees')); root.appendChild(row);
    }
    if (!root.children.length) { const empty = document.createElement('p'); empty.className = 'software-empty'; empty.textContent = 'No pending membership fees.'; root.appendChild(empty); }
  }

  function renderRecentCustomers(items = []) {
    const root = $('recentCustomers'); root.replaceChildren();
    for (const member of items.slice(0, 8)) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'activity-row';
      const text = document.createElement('span');
      const strong = document.createElement('strong'); strong.textContent = member.displayName || 'Customer';
      const small = document.createElement('small'); small.textContent = member.membership?.planName || 'No membership';
      text.append(strong, small);
      const time = document.createElement('small'); time.textContent = formatDate(member.createdAt);
      button.append(text, time); button.addEventListener('click', () => window.GravityCustomerAdmin?.openCustomerById(member.id)); root.appendChild(button);
    }
    if (!root.children.length) { const empty = document.createElement('p'); empty.className = 'software-empty'; empty.textContent = 'No customers yet.'; root.appendChild(empty); }
  }

  function renderRecentPayments(items = []) {
    const root = $('recentPayments'); root.replaceChildren();
    for (const item of items.slice(0, 8)) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'activity-row';
      const text = document.createElement('span');
      const strong = document.createElement('strong'); strong.textContent = item.customerName || 'Customer';
      const small = document.createElement('small'); small.textContent = `${String(item.method || 'payment').replaceAll('_', ' ')} ? ${formatDate(item.paidAt)}`;
      text.append(strong, small);
      const amount = document.createElement('strong'); amount.textContent = moneyPaise(item.amountPaise, item.currency || 'INR');
      button.append(text, amount); button.addEventListener('click', () => window.GravityCustomerAdmin?.openCustomerById(item.customerId)); root.appendChild(button);
    }
    if (!root.children.length) { const empty = document.createElement('p'); empty.className = 'software-empty'; empty.textContent = 'No recorded payments yet.'; root.appendChild(empty); }
  }

  async function renderWorkspace() {
    const api = core()?.api;
    if (!api) return;
    const dashboard = await api('/api/admin/dashboard');
    renderStats(dashboard.stats || {});
    renderExpiring(dashboard.expiring || {});
    renderPendingFees(Array.isArray(dashboard.pendingFees) ? dashboard.pendingFees : []);
    renderRecentPayments(Array.isArray(dashboard.recentPayments) ? dashboard.recentPayments : []);
    renderRecentCustomers(Array.isArray(dashboard.recentCustomers) ? dashboard.recentCustomers : []);
  }

  window.GravityAdminDashboard = { setAdmin(admin) { state.admin = admin; }, renderWorkspace };
})();
