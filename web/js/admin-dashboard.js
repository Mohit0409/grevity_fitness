(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null, requestId: 0 };
  const core = () => window.GravityAdminCore;
  function hasPermission(permission) { return core()?.hasPermission(permission) || false; }

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

  function stat(label, value, hint = '', action = null) {
    const item = document.createElement(action ? 'button' : 'article');
    if (action) { item.type = 'button'; item.addEventListener('click', action); item.setAttribute('aria-label', `${label}: ${value}`); }
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
    const items = [
      stat('Total Members', String(stats.totalCustomers ?? 0), '', () => openPeople('member')),
      stat('Staff', String(stats.totalStaff ?? 0), '', () => openPeople('staff')),
      stat('Active Members', String(stats.activeMembers ?? 0), '', () => openPeople('member', 'active')),
      stat('Expiring Today', String((state.dashboard?.expiring?.today || []).length), '', () => openFollowups('today')),
      stat('Expiring Soon', String(stats.expiringSoon ?? 0), 'Next 7 days', () => openFollowups('next7')),
      stat('Expired Members', String(stats.expiredMembers ?? 0), '', () => openFollowups('expired')),
      stat('New Members This Month', String(stats.newCustomersThisMonth ?? 0), '', () => openPeople('member')),
    ];
    if (hasPermission('payments.read')) items.push(
      stat('Pending Fees', moneyPaise(stats.pendingFeesTotalPaise), '', () => openFees('pending')),
      stat('Payments Today', moneyPaise(stats.paymentsReceivedTodayPaise), '', () => openFees('all')),
      stat('Payments This Month', moneyPaise(stats.paymentsReceivedThisMonthPaise), '', () => openFees('all')),
    );
    root.append(...items);
  }

  async function openPeople(personType, membershipStatus = '') {
    await core()?.openView('members');
    await window.GravityCustomerAdmin?.setDirectoryFilters?.({ personType, membershipStatus });
  }

  async function openFollowups(filter) {
    await core()?.openView('notifications');
    window.GravityFollowupAdmin?.setFilter?.(filter);
  }

  async function openFees(balance) {
    await core()?.openView('fees');
    await window.GravityPaymentAdmin?.setBalance?.(balance);
  }

  function expiringRows(groups = {}) {
    return [
      ['Expires today', groups.today || []],
      ['Expired', groups.expired || []],
      ['Expires tomorrow', groups.tomorrow || []],
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
      const action = document.createElement('td'); action.className = 'row-actions';
      const whatsapp = document.createElement('button'); whatsapp.type = 'button'; whatsapp.className = 'whatsapp-action table-action'; whatsapp.textContent = 'Send WhatsApp';
      whatsapp.addEventListener('click', () => core()?.openWhatsAppReminder(item));
      const open = document.createElement('button'); open.type = 'button'; open.className = 'ghost table-action'; open.textContent = 'Open';
      open.addEventListener('click', () => window.GravityCustomerAdmin?.openCustomerById(item.customerId));
      action.append(whatsapp, open); row.append(customer, plan, expiry, priority, action); body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow('No memberships need expiry attention.', 5));
  }

  function renderPendingFees(items = []) {
    const root = $('dashboardFeesState'); root.replaceChildren();
    for (const item of items.slice(0, 6)) {
      const row = document.createElement('button'); row.type = 'button'; row.className = 'activity-row';
      const text = document.createElement('span');
      const strong = document.createElement('strong'); strong.textContent = item.customerName || 'Customer';
      const small = document.createElement('small'); small.textContent = `${item.membershipNumber || '--'} | ${item.planName || '--'}`;
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
      const small = document.createElement('small'); small.textContent = `${String(item.method || 'payment').replaceAll('_', ' ')} | ${formatDate(item.paidAt)}`;
      text.append(strong, small);
      const amount = document.createElement('strong'); amount.textContent = moneyPaise(item.amountPaise, item.currency || 'INR');
      button.append(text, amount); button.addEventListener('click', () => window.GravityCustomerAdmin?.openCustomerById(item.customerId)); root.appendChild(button);
    }
    if (!root.children.length) { const empty = document.createElement('p'); empty.className = 'software-empty'; empty.textContent = 'No recorded payments yet.'; root.appendChild(empty); }
  }

  async function renderWorkspace() {
    const api = core()?.api;
    if (!api) return;
    const requestId = ++state.requestId;
    const canReadPayments = hasPermission('payments.read');
    $('dashboardFeesPanel').hidden = !canReadPayments;
    $('dashboardPaymentsPanel').hidden = !canReadPayments;
    $('stats').setAttribute('aria-busy', 'true');
    $('stats').replaceChildren(stat('Loading dashboard', '--'));
    $('dashboardExpiringBody').replaceChildren(emptyRow('Loading memberships...', 5));
    try {
      const dashboard = await api('/api/admin/dashboard');
      if (requestId !== state.requestId) return;
      state.dashboard = dashboard;
      renderStats(dashboard.stats || {});
      renderExpiring(dashboard.expiring || {});
      if (canReadPayments) {
        renderPendingFees(Array.isArray(dashboard.pendingFees) ? dashboard.pendingFees : []);
        renderRecentPayments(Array.isArray(dashboard.recentPayments) ? dashboard.recentPayments : []);
      }
      renderRecentCustomers(Array.isArray(dashboard.recentCustomers) ? dashboard.recentCustomers : []);
    } catch (error) {
      if (requestId !== state.requestId) return;
      const forbidden = error?.status === 403;
      $('stats').replaceChildren(stat(forbidden ? 'Dashboard access denied' : 'Dashboard unavailable', '--', forbidden ? 'Your current role cannot load this workspace' : 'Retry to refresh operational data'));
      $('dashboardExpiringBody').replaceChildren(emptyRow(forbidden ? 'Dashboard access denied.' : 'Dashboard data is temporarily unavailable.', 5));
      $('dashboardFeesState').replaceChildren();
      $('recentPayments').replaceChildren();
      if (forbidden) {
        const message = document.createElement('p'); message.className = 'software-empty'; message.textContent = 'Dashboard data is not available to this admin session.';
        $('recentCustomers').replaceChildren(message);
      } else {
        const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'ghost'; retry.textContent = 'Retry dashboard'; retry.addEventListener('click', () => renderWorkspace());
        $('recentCustomers').replaceChildren(retry);
      }
    } finally {
      if (requestId === state.requestId) $('stats').setAttribute('aria-busy', 'false');
    }
  }

  window.GravityAdminDashboard = { setAdmin(admin) { state.admin = admin; }, renderWorkspace };
})();
