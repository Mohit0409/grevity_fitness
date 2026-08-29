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

  function renderStats(dashboard, expiring) {
    const root = $('stats'); root.replaceChildren();
    root.append(
      stat('Total Customers', String(dashboard.customers?.total ?? 0)),
      stat('Active Members', '--', 'Dashboard metric API required'),
      stat('Expiring Soon', String(expiring.length), 'Next 7 days'),
      stat('Expired', '--', 'Dashboard metric API required'),
      stat('Pending Fees', '--', 'Fee ledger API required'),
    );
  }

  function renderExpiring(items) {
    const body = $('dashboardExpiringBody'); body.replaceChildren();
    for (const item of items.slice(0, 8)) {
      const row = document.createElement('tr');
      const customer = document.createElement('td'); customer.textContent = item.customer?.displayName || 'Customer';
      const plan = document.createElement('td'); plan.textContent = item.planName || '--';
      const expiry = document.createElement('td'); expiry.textContent = formatDate(item.endsAt);
      const left = document.createElement('td'); left.textContent = `${Number(item.daysRemaining ?? 0)} day${Number(item.daysRemaining ?? 0) === 1 ? '' : 's'}`;
      const action = document.createElement('td');
      const button = document.createElement('button'); button.type = 'button'; button.className = 'table-action'; button.textContent = 'Open';
      button.addEventListener('click', () => window.GravityCustomerAdmin?.openCustomer({
        id: item.customerId,
        displayName: item.customer?.displayName,
        email: item.customer?.email,
        phone: item.customer?.phone,
        status: 'active',
      }));
      action.appendChild(button); row.append(customer, plan, expiry, left, action); body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow('No memberships expire in the next 7 days.', 5));
  }

  function renderRecentCustomers(members) {
    const root = $('recentCustomers'); root.replaceChildren();
    for (const member of members.slice(0, 6)) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'activity-row';
      const text = document.createElement('span'); text.innerHTML = `<strong></strong><small></small>`;
      text.querySelector('strong').textContent = member.displayName || 'Customer';
      text.querySelector('small').textContent = member.phone || member.email || 'No verified contact';
      const time = document.createElement('small'); time.textContent = formatDate(member.createdAt);
      button.append(text, time); button.addEventListener('click', () => window.GravityCustomerAdmin?.openCustomer(member)); root.appendChild(button);
    }
    if (!root.children.length) { const empty = document.createElement('p'); empty.className = 'software-empty'; empty.textContent = 'No customers yet.'; root.appendChild(empty); }
  }

  function renderAudit(items) {
    const root = $('recentAudit'); root.replaceChildren();
    for (const item of items || []) {
      const row = document.createElement('div'); row.className = 'activity-row static';
      const text = document.createElement('span');
      const strong = document.createElement('strong'); strong.textContent = item.action || 'Admin activity';
      const small = document.createElement('small'); small.textContent = item.result || '';
      text.append(strong, small);
      const time = document.createElement('small'); time.textContent = formatDate(item.createdAt);
      row.append(text, time); root.appendChild(row);
    }
    if (!root.children.length) { const empty = document.createElement('p'); empty.className = 'software-empty'; empty.textContent = 'No recent admin activity.'; root.appendChild(empty); }
  }

  function backendRequired(root, title, copy) {
    root.replaceChildren();
    const box = document.createElement('div'); box.className = 'software-notice neutral';
    const strong = document.createElement('strong'); strong.textContent = title;
    const span = document.createElement('span'); span.textContent = copy;
    box.append(strong, span); root.appendChild(box);
  }

  async function renderWorkspace() {
    const api = core()?.api;
    if (!api) return;
    const [dashboard, members, expiring] = await Promise.all([
      api('/api/admin/dashboard'), api('/api/admin/members?q='), api('/api/admin/memberships/expiring?days=7'),
    ]);
    const expiringItems = Array.isArray(expiring.memberships) ? expiring.memberships : [];
    renderStats(dashboard, expiringItems);
    renderExpiring(expiringItems);
    renderRecentCustomers(Array.isArray(members.members) ? members.members : []);
    renderAudit(dashboard.recentAudit || []);
    backendRequired($('dashboardFeesState'), 'Pending fee total unavailable', 'Chat 1 needs to expose the manual fee ledger summary.');
    backendRequired($('recentPayments'), 'Recent admin payments unavailable', 'Verified customer checkout history is not an admin manual-payment ledger.');
  }

  window.GravityAdminDashboard = { setAdmin(admin) { state.admin = admin; }, renderWorkspace };
})();
