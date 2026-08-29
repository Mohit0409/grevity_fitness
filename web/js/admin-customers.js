(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null, members: [], selected: null, memberships: [], plans: [], notifications: [], opener: null };
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

  function maskPhone(value) {
    const phone = String(value || '');
    if (!phone) return '--';
    const digits = phone.replace(/\D/g, '');
    if (digits.length < 4) return phone;
    const prefix = phone.startsWith('+91') ? '+91 ' : '';
    return `${prefix}????? ${digits.slice(-4)}`;
  }

  function statusBadge(status) {
    const span = document.createElement('span');
    span.className = `badge badge--${String(status || 'unknown').toLowerCase()}`;
    span.textContent = String(status || 'unknown').replaceAll('_', ' ');
    return span;
  }

  function currentMembership(items) {
    return items.find((item) => item.status === 'active') || items.find((item) => item.status === 'scheduled') || null;
  }

  function appendFact(root, label, value) {
    const div = document.createElement('div'); div.className = 'profile-fact';
    const small = document.createElement('span'); small.textContent = label;
    const strong = document.createElement('strong'); strong.textContent = value;
    div.append(small, strong); root.appendChild(div);
  }

  function emptyRow(message, colspan) {
    const row = document.createElement('tr');
    const cell = document.createElement('td'); cell.colSpan = colspan; cell.className = 'empty'; cell.textContent = message;
    row.appendChild(cell); return row;
  }

  function filteredMembers() {
    const status = $('customerStatusFilter').value;
    return state.members.filter((member) => !status || member.status === status);
  }

  function rowAction(member) {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'table-action'; button.textContent = 'Open';
    button.addEventListener('click', () => openCustomer(member)); return button;
  }

  function renderMembers() {
    const members = filteredMembers();
    const body = $('membersBody'); body.replaceChildren();
    const mobile = $('customersMobileList'); mobile.replaceChildren();
    for (const member of members) {
      const row = document.createElement('tr');
      const name = document.createElement('td');
      const strong = document.createElement('strong'); strong.textContent = member.displayName || 'Customer';
      const created = document.createElement('small'); created.textContent = `Since ${formatDate(member.createdAt)}`;
      name.append(strong, document.createElement('br'), created);
      const phone = document.createElement('td'); phone.textContent = maskPhone(member.phone);
      const plan = document.createElement('td'); plan.innerHTML = '<span class="data-unavailable">Open profile</span>';
      const expiry = document.createElement('td'); expiry.innerHTML = '<span class="data-unavailable">Open profile</span>';
      const pending = document.createElement('td'); pending.innerHTML = '<span class="data-unavailable">Ledger API</span>';
      const status = document.createElement('td'); status.appendChild(statusBadge(member.status));
      const action = document.createElement('td'); action.appendChild(rowAction(member));
      row.append(name, phone, plan, expiry, pending, status, action); body.appendChild(row);

      const card = document.createElement('article'); card.className = 'mobile-record'; card.setAttribute('role', 'listitem');
      const head = document.createElement('div'); head.className = 'mobile-record-head';
      const label = document.createElement('div'); const cname = document.createElement('strong'); cname.textContent = member.displayName || 'Customer'; const cphone = document.createElement('small'); cphone.textContent = maskPhone(member.phone); label.append(cname, cphone); head.append(label, statusBadge(member.status));
      const meta = document.createElement('p'); meta.textContent = 'Membership and fee details open in the customer profile.';
      const open = rowAction(member); open.classList.add('full-width'); card.append(head, meta, open); mobile.appendChild(card);
    }
    if (!body.children.length) body.appendChild(emptyRow('No customers match these filters.', 7));
    if (!mobile.children.length) { const empty = document.createElement('p'); empty.className = 'software-empty'; empty.textContent = 'No customers match these filters.'; mobile.appendChild(empty); }
  }

  async function loadPlans() {
    if (state.plans.length) return state.plans;
    const payload = await core().api('/api/admin/membership/plans');
    state.plans = Array.isArray(payload.plans) ? payload.plans : [];
    return state.plans;
  }

  async function renderWorkspace() {
    const query = $('memberSearch').value.trim();
    const payload = await core().api(`/api/admin/members?q=${encodeURIComponent(query)}`);
    state.members = Array.isArray(payload.members) ? payload.members : [];
    renderMembers();
  }

  function renderMembershipHistory(root, memberships) {
    const section = document.createElement('section'); section.className = 'profile-section';
    const h = document.createElement('div'); h.className = 'profile-section-head'; h.innerHTML = '<h4>Membership history</h4>';
    const wrap = document.createElement('div'); wrap.className = 'tablewrap';
    const table = document.createElement('table'); table.className = 'software-table compact-table';
    table.innerHTML = '<thead><tr><th>Membership</th><th>Plan</th><th>Start</th><th>Expiry</th><th>Status</th></tr></thead>';
    const body = document.createElement('tbody');
    for (const item of memberships) {
      const row = document.createElement('tr');
      for (const value of [item.membershipNumber || '--', item.planName || '--', formatDate(item.startsAt), formatDate(item.endsAt)]) { const td = document.createElement('td'); td.textContent = value; row.appendChild(td); }
      const status = document.createElement('td'); status.appendChild(statusBadge(item.status)); row.appendChild(status); body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow('No membership history yet.', 5));
    table.appendChild(body); wrap.appendChild(table); section.append(h, wrap); root.appendChild(section);
  }

  function renderNotificationHistory(root, customerId) {
    const section = document.createElement('section'); section.className = 'profile-section';
    const h = document.createElement('div'); h.className = 'profile-section-head'; h.innerHTML = '<h4>Notification history</h4>';
    const list = document.createElement('div'); list.className = 'mini-history';
    const reminders = state.notifications.filter((item) => item.customerId === customerId).slice(0, 6);
    for (const item of reminders) {
      const row = document.createElement('div'); row.className = 'mini-history-row';
      const text = document.createElement('span'); const title = document.createElement('strong'); title.textContent = item.triggerDays === 0 ? 'Expiry day reminder' : `${item.triggerDays}-day expiry reminder`; const meta = document.createElement('small'); meta.textContent = formatDate(item.payload?.endsAt); text.append(title, meta);
      const status = statusBadge(item.state === 'suppressed' ? 'suppressed' : item.state || 'pending'); row.append(text, status); list.appendChild(row);
    }
    if (!list.children.length) { const empty = document.createElement('p'); empty.className = 'software-empty'; empty.textContent = 'No notification history in the latest admin reminder window.'; list.appendChild(empty); }
    section.append(h, list); root.appendChild(section);
  }

  function renderCustomerProfile() {
    const member = state.selected; if (!member) return;
    const body = $('customerDrawerBody'); body.replaceChildren();
    const current = currentMembership(state.memberships);
    $('customerDrawerName').textContent = member.displayName || 'Customer';
    $('customerDrawerMeta').textContent = [member.phone || 'No mobile', `Customer since ${formatDate(member.createdAt)}`, String(member.status || 'unknown')].join(' | ');

    const top = document.createElement('div'); top.className = 'profile-summary-grid';
    const membership = document.createElement('section'); membership.className = 'profile-summary-card'; const mh = document.createElement('h4'); mh.textContent = 'Current membership'; const facts = document.createElement('div'); facts.className = 'profile-facts';
    if (current) { appendFact(facts, 'Plan', current.planName || '--'); appendFact(facts, 'Start', formatDate(current.startsAt)); appendFact(facts, 'Expiry', formatDate(current.endsAt)); appendFact(facts, 'Days remaining', String(current.daysRemaining ?? 0)); appendFact(facts, 'Status', String(current.status || '--')); }
    else { const empty = document.createElement('p'); empty.className = 'software-empty'; empty.textContent = 'No active or scheduled membership.'; facts.appendChild(empty); }
    membership.append(mh, facts);

    const payment = document.createElement('section'); payment.className = 'profile-summary-card'; const ph = document.createElement('h4'); ph.textContent = 'Payment summary'; const pf = document.createElement('div'); pf.className = 'profile-facts';
    appendFact(pf, 'Total fee', current ? moneyPaise(current.pricePaise, current.currency) : '--'); appendFact(pf, 'Paid', '--'); appendFact(pf, 'Pending', '--');
    const note = document.createElement('p'); note.className = 'field-hint'; note.textContent = 'Paid and pending require the admin manual-payment ledger API.'; payment.append(ph, pf, note);
    top.append(membership, payment); body.appendChild(top);

    const actions = document.createElement('div'); actions.className = 'profile-actions';
    const pay = document.createElement('button'); pay.type = 'button'; pay.className = 'primary-action'; pay.textContent = 'Record Payment'; pay.addEventListener('click', openRecordPayment);
    const renew = document.createElement('button'); renew.type = 'button'; renew.textContent = 'Renew Membership'; renew.addEventListener('click', openRenew);
    const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'ghost'; edit.textContent = 'Edit Customer'; edit.addEventListener('click', () => core().flash('Customer editing requires a dedicated admin API.', 'error'));
    const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'ghost'; toggle.textContent = member.status === 'active' ? 'Disable account' : 'Enable account'; toggle.addEventListener('click', toggleStatus);
    actions.append(pay, renew, edit, toggle); body.appendChild(actions);

    renderMembershipHistory(body, state.memberships);
    const payments = document.createElement('section'); payments.className = 'profile-section'; payments.innerHTML = '<div class="profile-section-head"><h4>Payment history</h4></div><div class="software-notice neutral"><strong>Admin payment history API required</strong><span>Customer checkout records are not exposed through the admin API and manual payments do not yet have a ledger.</span></div>'; body.appendChild(payments);
    renderNotificationHistory(body, member.id);
  }

  async function refreshSelected() {
    if (!state.selected) return;
    const [membershipPayload, notificationPayload] = await Promise.all([
      core().api(`/api/admin/members/${encodeURIComponent(state.selected.id)}/memberships`),
      core().api('/api/admin/notifications?limit=100').catch(() => ({ notifications: [] })),
    ]);
    state.memberships = Array.isArray(membershipPayload.memberships) ? membershipPayload.memberships : [];
    state.notifications = Array.isArray(notificationPayload.notifications) ? notificationPayload.notifications : [];
    renderCustomerProfile();
  }

  async function openCustomer(member) {
    state.selected = member; state.opener = document.activeElement;
    const dialog = $('customerDrawer');
    $('customerDrawerName').textContent = member.displayName || 'Customer';
    $('customerDrawerBody').innerHTML = '<div class="software-loading">Loading customer profile...</div>';
    if (!dialog.open) dialog.showModal();
    try { await refreshSelected(); } catch (_) { $('customerDrawerBody').innerHTML = '<div class="software-empty error-state">Customer details are temporarily unavailable.</div>'; }
  }

  async function toggleStatus() {
    if (!state.selected) return;
    const next = state.selected.status === 'active' ? 'disabled' : 'active';
    try {
      await core().api(`/api/admin/members/${encodeURIComponent(state.selected.id)}`, { method: 'PATCH', body: { status: next } });
      state.selected.status = next; core().flash(`Customer ${next}.`); await renderWorkspace(); renderCustomerProfile();
    } catch (_) { core().flash('Customer status could not be updated.', 'error'); }
  }

  function previewExpiry(startValue, months) {
    const date = startValue ? new Date(`${startValue}T12:00:00`) : new Date();
    if (Number.isNaN(date.getTime())) return '--';
    date.setMonth(date.getMonth() + Number(months || 1));
    return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  function updateAddPreview() {
    const plan = state.plans.find((item) => item.id === $('newCustomerPlan').value);
    $('newCustomerFee').value = plan ? moneyPaise(plan.pricePaise, plan.currency) : '--';
    $('newCustomerExpiry').textContent = plan ? previewExpiry($('newCustomerStart').value, plan.durationMonths) : '--';
    $('newCustomerPending').textContent = '--';
  }

  async function openAddCustomer() {
    state.opener = document.activeElement;
    await loadPlans().catch(() => []);
    const select = $('newCustomerPlan'); select.replaceChildren();
    for (const plan of state.plans.filter((item) => item.status === 'active')) { const option = document.createElement('option'); option.value = plan.id; option.textContent = `${plan.name} - ${moneyPaise(plan.pricePaise, plan.currency)}`; select.appendChild(option); }
    $('newCustomerStart').value = new Date().toISOString().slice(0, 10); updateAddPreview();
    const dialog = $('addCustomerDialog'); if (!dialog.open) dialog.showModal(); $('newCustomerName').focus();
  }

  function updateRenewPreview() {
    const plan = state.plans.find((item) => item.id === $('renewPlan').value);
    $('renewFeePreview').value = plan ? moneyPaise(plan.pricePaise, plan.currency) : '--';
    $('renewExpiryPreview').value = plan ? previewExpiry($('renewStart').value, plan.durationMonths) : '--';
  }

  async function openRenew() {
    if (!state.selected) return;
    await loadPlans();
    const current = currentMembership(state.memberships);
    $('renewCurrentExpiry').textContent = current ? `Current expiry: ${formatDate(current.endsAt)}. Leave start date blank to let the server queue the renewal safely.` : 'No active membership. The server will determine the authoritative start and expiry.';
    const select = $('renewPlan'); select.replaceChildren();
    for (const plan of state.plans.filter((item) => item.status === 'active')) { const option = document.createElement('option'); option.value = plan.id; option.textContent = `${plan.name} - ${moneyPaise(plan.pricePaise, plan.currency)}`; select.appendChild(option); }
    $('renewStart').value = ''; updateRenewPreview();
    const dialog = $('renewMembershipDialog'); if (!dialog.open) dialog.showModal(); select.focus();
  }

  function openRecordPayment() { const dialog = $('recordPaymentDialog'); if (!dialog.open) dialog.showModal(); }

  async function renewMembership(event) {
    event.preventDefault(); if (!state.selected) return;
    const body = { planId: $('renewPlan').value };
    if ($('renewStart').value) body.startsAt = Math.floor(new Date(`${$('renewStart').value}T00:00:00`).getTime() / 1000);
    try {
      await core().api(`/api/admin/members/${encodeURIComponent(state.selected.id)}/memberships`, { method: 'POST', body });
      $('renewMembershipDialog').close(); core().flash('Membership renewed. Server dates are authoritative.');
      await refreshSelected(); window.GravityMembershipAdmin?.renderWorkspace(); window.GravityAdminDashboard?.renderWorkspace();
    } catch (_) { core().flash('Membership renewal could not be completed.', 'error'); }
  }

  function installDialogA11y(dialog) {
    dialog.addEventListener('keydown', (event) => {
      if (event.key !== 'Tab') return;
      const focusable = Array.from(dialog.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
      )).filter((node) => !node.hidden && node.getClientRects().length > 0);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    });
    dialog.addEventListener('close', () => {
      if (state.opener && document.contains(state.opener)) state.opener.focus();
    });
  }

  $('customerStatusFilter').addEventListener('change', renderMembers);
  $('newCustomerPlan').addEventListener('change', updateAddPreview); $('newCustomerStart').addEventListener('change', updateAddPreview);
  $('renewPlan').addEventListener('change', updateRenewPreview); $('renewStart').addEventListener('change', updateRenewPreview);
  $('renewMembershipForm').addEventListener('submit', renewMembership);
  document.querySelectorAll('[data-close-dialog]').forEach((button) => button.addEventListener('click', () => $(button.dataset.closeDialog).close()));
  [$('customerDrawer'), $('addCustomerDialog'), $('renewMembershipDialog'), $('recordPaymentDialog')].forEach(installDialogA11y);

  window.GravityCustomerAdmin = {
    setAdmin(admin) { state.admin = admin; }, renderWorkspace, openCustomer, openAddCustomer,
  };
})();
