(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null, customers: [], selected: null, detail: null, plans: [], opener: null, accessOpener: null, paymentTarget: null, renewKey: null, paymentKey: null, listRequestId: 0 };
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

  function toPaise(value) {
    const amount = Number(value || 0);
    return Number.isFinite(amount) ? Math.max(0, Math.round(amount * 100)) : 0;
  }

  function newIdempotencyKey(prefix) {
    const uuid = globalThis.crypto?.randomUUID?.();
    if (uuid) return `${prefix}-${uuid}`;
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 14)}`;
  }

  function paymentMethodLabel(value) {
    const key = String(value || '').toLowerCase();
    return ({ cash: 'Cash', upi: 'UPI', card: 'Card', bank_transfer: 'Bank transfer', other: 'Other' })[key] || (key ? key.replaceAll('_', ' ') : '--');
  }

  function normalizePhoneInput(value) {
    const raw = String(value || '').trim();
    const digits = raw.replace(/\D/g, '');
    if (!raw.startsWith('+') && digits.length === 10) return `+91${digits}`;
    return raw;
  }

  function dateToUnix(value) {
    if (!value) return null;
    const date = new Date(`${value}T12:00:00`);
    return Number.isNaN(date.getTime()) ? null : Math.floor(date.getTime() / 1000);
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

  function setBusy(button, busy, busyLabel) {
    if (!button) return;
    if (busy) {
      button.dataset.idleLabel = button.textContent;
      button.textContent = busyLabel;
      button.disabled = true;
    } else {
      button.textContent = button.dataset.idleLabel || button.textContent;
      button.disabled = false;
    }
  }

  function errorText(error, context) {
    const fields = error?.data?.fields;
    if (fields && typeof fields === 'object') {
      const message = Object.values(fields).find((value) => typeof value === 'string' && value.trim());
      if (message) return message;
    }
    if (error?.status === 409) {
      if (context === 'add' || context === 'edit') return 'A customer with this mobile number already exists.';
      if (context === 'payment') return 'Payment is higher than the server-calculated pending balance.';
      return 'The requested change conflicts with the current membership state.';
    }
    if (error?.status === 403) return 'Your admin role does not have permission for this action.';
    if (error?.status === 404) return 'This customer or membership no longer exists.';
    return 'The operation could not be completed. Please retry.';
  }

  function currentMembership() { return state.detail?.membership?.current || null; }
  function allMemberships() { return Array.isArray(state.detail?.membership?.all) ? state.detail.membership.all : []; }

  function paymentTarget() {
    const current = currentMembership();
    if (current?.payment?.pendingPaise > 0) return current;
    return allMemberships().find((item) => item.status !== 'cancelled' && Number(item.payment?.pendingPaise || 0) > 0) || null;
  }

  async function loadPlans() {
    if (state.plans.length) return state.plans;
    const payload = await core().api('/api/admin/membership/plans');
    state.plans = Array.isArray(payload.plans) ? payload.plans : [];
    populatePlanFilters();
    return state.plans;
  }

  function populatePlanFilters() {
    const filter = $('customerPlanFilter');
    if (!filter) return;
    const current = filter.value;
    filter.replaceChildren(new Option('All plans', ''));
    for (const plan of state.plans) filter.appendChild(new Option(plan.name, plan.id));
    if (Array.from(filter.options).some((option) => option.value === current)) filter.value = current;
  }

  function renderCustomers() {
    const body = $('membersBody'); body.replaceChildren();
    const mobile = $('customersMobileList'); mobile.replaceChildren();
    for (const member of state.customers) {
      const membership = member.membership;
      const payment = membership?.payment || {};
      const row = document.createElement('tr');
      const name = document.createElement('td');
      const strong = document.createElement('strong'); strong.textContent = member.displayName || 'Customer';
      const created = document.createElement('small'); created.textContent = `Since ${formatDate(member.createdAt)}`;
      name.append(strong, document.createElement('br'), created);
      const phone = document.createElement('td'); phone.textContent = maskPhone(member.phone);
      const plan = document.createElement('td'); plan.textContent = membership?.planName || '--';
      const expiry = document.createElement('td'); expiry.textContent = membership ? formatDate(membership.endsAt) : '--';
      const pending = document.createElement('td'); pending.textContent = !hasPermission('payments.read') ? 'Restricted' : (membership ? moneyPaise(payment.pendingPaise, membership.currency) : '--');
      const status = document.createElement('td'); status.appendChild(statusBadge(member.status));
      const action = document.createElement('td');
      const open = document.createElement('button'); open.type = 'button'; open.className = 'table-action'; open.textContent = 'Open';
      open.addEventListener('click', () => openCustomerById(member.id, open)); action.appendChild(open);
      row.append(name, phone, plan, expiry, pending, status, action); body.appendChild(row);

      const card = document.createElement('article'); card.className = 'mobile-record'; card.setAttribute('role', 'listitem');
      const head = document.createElement('div'); head.className = 'mobile-record-head';
      const label = document.createElement('div'); const cname = document.createElement('strong'); cname.textContent = member.displayName || 'Customer'; const cphone = document.createElement('small'); cphone.textContent = maskPhone(member.phone); label.append(cname, cphone); head.append(label, statusBadge(member.status));
      const meta = document.createElement('dl'); meta.className = 'mobile-record-facts';
      const facts = [['Plan', membership?.planName || '--'], ['Expiry', membership ? formatDate(membership.endsAt) : '--']];
      if (hasPermission('payments.read')) facts.push(['Pending', membership ? moneyPaise(payment.pendingPaise, membership.currency) : '--']);
      facts.forEach(([key, value]) => { const div = document.createElement('div'); const dt = document.createElement('dt'); dt.textContent = key; const dd = document.createElement('dd'); dd.textContent = value; div.append(dt, dd); meta.appendChild(div); });
      const mobileOpen = document.createElement('button'); mobileOpen.type = 'button'; mobileOpen.className = 'table-action full-width'; mobileOpen.textContent = 'Open customer'; mobileOpen.addEventListener('click', () => openCustomerById(member.id, mobileOpen));
      card.append(head, meta, mobileOpen); mobile.appendChild(card);
    }
    if (!body.children.length) body.appendChild(emptyRow('No customers match these filters.', 7));
    if (!mobile.children.length) { const empty = document.createElement('p'); empty.className = 'software-empty'; empty.textContent = 'No customers match these filters.'; mobile.appendChild(empty); }
  }

  async function renderWorkspace() {
    await loadPlans();
    const requestId = ++state.listRequestId;
    const panel = $('customersPanel'); panel?.setAttribute('aria-busy', 'true');
    $('membersBody').replaceChildren(emptyRow('Loading customers...', 7));
    const params = new URLSearchParams();
    const query = $('memberSearch').value.trim();
    if (query) params.set('q', query);
    if ($('customerStatusFilter').value) params.set('status', $('customerStatusFilter').value);
    if ($('customerMembershipFilter').value) params.set('membershipStatus', $('customerMembershipFilter').value);
    if ($('customerPlanFilter').value) params.set('planId', $('customerPlanFilter').value);
    try {
      const payload = await core().api(`/api/admin/customers?${params.toString()}`);
      if (requestId !== state.listRequestId) return;
      state.customers = Array.isArray(payload.customers) ? payload.customers : [];
      renderCustomers();
    } catch (error) {
      if (requestId !== state.listRequestId) return;
      $('membersBody').replaceChildren(emptyRow('Customer list is temporarily unavailable. Retry or change the filters.', 7));
      throw error;
    } finally { if (requestId === state.listRequestId) panel?.setAttribute('aria-busy', 'false'); }
  }

  function renderMembershipHistory(root, memberships) {
    const section = document.createElement('section'); section.className = 'profile-section';
    const h = document.createElement('div'); h.className = 'profile-section-head'; h.innerHTML = '<h4>Membership history</h4>';
    const wrap = document.createElement('div'); wrap.className = 'tablewrap'; wrap.tabIndex = 0; wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', 'Membership history table');
    const table = document.createElement('table'); table.className = 'software-table compact-table';
    const canReadPayments = hasPermission('payments.read');
    table.innerHTML = canReadPayments ? '<thead><tr><th>Membership</th><th>Plan</th><th>Start</th><th>Expiry</th><th>Status</th><th>Paid / Pending</th></tr></thead>' : '<thead><tr><th>Membership</th><th>Plan</th><th>Start</th><th>Expiry</th><th>Status</th></tr></thead>';
    const body = document.createElement('tbody');
    for (const item of memberships) {
      const row = document.createElement('tr');
      for (const value of [item.membershipNumber || '--', item.planName || '--', formatDate(item.startsAt), formatDate(item.endsAt)]) { const td = document.createElement('td'); td.textContent = value; row.appendChild(td); }
      const status = document.createElement('td'); status.appendChild(statusBadge(item.status));
      row.appendChild(status);
      if (canReadPayments) { const payment = document.createElement('td'); payment.textContent = `${moneyPaise(item.payment?.paidPaise, item.currency)} / ${moneyPaise(item.payment?.pendingPaise, item.currency)}`; row.appendChild(payment); }
      body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow('No membership history yet.', canReadPayments ? 6 : 5));
    table.appendChild(body); wrap.appendChild(table); section.append(h, wrap); root.appendChild(section);
  }

  function renderPaymentHistory(root, payments) {
    const section = document.createElement('section'); section.className = 'profile-section';
    const h = document.createElement('div'); h.className = 'profile-section-head'; h.innerHTML = '<h4>Payment history</h4>';
    const wrap = document.createElement('div'); wrap.className = 'tablewrap'; wrap.tabIndex = 0; wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', 'Payment history table');
    const table = document.createElement('table'); table.className = 'software-table compact-table';
    table.innerHTML = '<thead><tr><th>Date</th><th>Membership</th><th>Amount</th><th>Method</th><th>Note</th></tr></thead>';
    const body = document.createElement('tbody');
    for (const item of payments) {
      const row = document.createElement('tr');
      [formatDate(item.paidAt), item.membershipNumber || '--', moneyPaise(item.amountPaise, item.currency), paymentMethodLabel(item.method), item.note || '--'].forEach((value) => { const td = document.createElement('td'); td.textContent = value; row.appendChild(td); });
      body.appendChild(row);
    }
    if (!body.children.length) body.appendChild(emptyRow('No manual payments recorded yet.', 5));
    table.appendChild(body); wrap.appendChild(table); section.append(h, wrap); root.appendChild(section);
  }

  function renderNotificationHistory(root, reminders) {
    const section = document.createElement('section'); section.className = 'profile-section';
    const h = document.createElement('div'); h.className = 'profile-section-head'; h.innerHTML = '<h4>Notification history</h4>';
    const list = document.createElement('div'); list.className = 'mini-history';
    for (const item of reminders.slice(0, 10)) {
      const row = document.createElement('div'); row.className = 'mini-history-row';
      const text = document.createElement('span');
      const title = document.createElement('strong'); title.textContent = item.triggerDays === 0 ? 'Expiry-day reminder' : `${item.triggerDays}-day expiry reminder`;
      const meta = document.createElement('small'); meta.textContent = formatDate(item.createdAt); text.append(title, meta);
      row.append(text, statusBadge(item.state === 'suppressed' ? 'suppressed' : item.state || 'pending')); list.appendChild(row);
    }
    if (!list.children.length) { const empty = document.createElement('p'); empty.className = 'software-empty'; empty.textContent = 'No membership reminders yet.'; list.appendChild(empty); }
    section.append(h, list); root.appendChild(section);
  }

  function renderCustomerProfile() {
    const detail = state.detail; if (!detail?.customer) return;
    const member = detail.customer;
    const current = detail.membership?.current || null;
    const upcoming = detail.membership?.upcoming || null;
    const body = $('customerDrawerBody'); body.replaceChildren();
    $('customerDrawerName').textContent = member.displayName || 'Customer';
    $('customerDrawerMeta').textContent = [member.phone || 'No mobile', `Customer since ${formatDate(member.createdAt)}`, String(member.status || 'unknown')].join(' | ');

    const top = document.createElement('div'); top.className = 'profile-summary-grid';
    const membership = document.createElement('section'); membership.className = 'profile-summary-card';
    const mh = document.createElement('h4'); mh.textContent = 'Current membership'; const facts = document.createElement('div'); facts.className = 'profile-facts';
    if (current) {
      appendFact(facts, 'Plan', current.planName || '--'); appendFact(facts, 'Membership', current.membershipNumber || '--'); appendFact(facts, 'Start', formatDate(current.startsAt)); appendFact(facts, 'Expiry', formatDate(current.endsAt)); appendFact(facts, 'Days remaining', String(current.daysRemaining ?? 0)); appendFact(facts, 'Status', String(current.status || '--'));
    } else if (upcoming) {
      appendFact(facts, 'Upcoming plan', upcoming.planName || '--'); appendFact(facts, 'Membership', upcoming.membershipNumber || '--'); appendFact(facts, 'Starts', formatDate(upcoming.startsAt)); appendFact(facts, 'Expiry', formatDate(upcoming.endsAt)); appendFact(facts, 'Status', 'scheduled');
    } else { const empty = document.createElement('p'); empty.className = 'software-empty'; empty.textContent = 'No active or scheduled membership.'; facts.appendChild(empty); }
    membership.append(mh, facts);

    const payMembership = current || upcoming;
    const payment = document.createElement('section'); payment.className = 'profile-summary-card';
    const ph = document.createElement('h4'); ph.textContent = 'Payment summary'; const pf = document.createElement('div'); pf.className = 'profile-facts';
    appendFact(pf, 'Total fee', payMembership ? moneyPaise(payMembership.payment?.totalPaise, payMembership.currency) : '--');
    appendFact(pf, 'Paid', payMembership ? moneyPaise(payMembership.payment?.paidPaise, payMembership.currency) : '--');
    appendFact(pf, 'Pending', payMembership ? moneyPaise(payMembership.payment?.pendingPaise, payMembership.currency) : '--');
    payment.append(ph, pf); top.appendChild(membership); if (hasPermission('payments.read')) top.appendChild(payment); body.appendChild(top);

    const actions = document.createElement('div'); actions.className = 'profile-actions';
    const latestExpired = allMemberships().filter((item) => item.status === 'expired').sort((a, b) => Number(b.endsAt || 0) - Number(a.endsAt || 0))[0] || null;
    const followupMembership = current && Number(current.daysRemaining ?? 999) <= 7 ? current : (!current && !upcoming ? latestExpired : null);
    if (followupMembership) { const whatsapp = document.createElement('button'); whatsapp.type = 'button'; whatsapp.className = 'whatsapp-action'; whatsapp.textContent = 'Send WhatsApp'; whatsapp.addEventListener('click', () => core()?.openWhatsAppReminder({ customerName: member.displayName, phone: member.phone, planName: followupMembership.planName, endsAt: followupMembership.endsAt, status: followupMembership.status, membershipNumber: followupMembership.membershipNumber })); actions.appendChild(whatsapp); }
    const pay = document.createElement('button'); pay.type = 'button'; pay.className = 'primary-action'; pay.textContent = 'Record Payment';
    const target = paymentTarget(); pay.disabled = !target || !hasPermission('payments.record'); pay.title = !target ? 'No pending membership balance' : '';
    pay.addEventListener('click', () => openRecordPayment(target, member));
    const renew = document.createElement('button'); renew.type = 'button'; renew.textContent = 'Renew Membership'; renew.disabled = !hasPermission('memberships.manage'); renew.addEventListener('click', openRenew);
    const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'ghost'; edit.textContent = 'Edit Customer'; edit.disabled = !hasPermission('members.manage'); edit.addEventListener('click', openEdit);
    const toggle = document.createElement('button'); toggle.type = 'button'; toggle.id = 'customerAccessToggle'; toggle.className = 'ghost'; toggle.textContent = member.status === 'active' ? 'Disable account' : 'Enable account'; toggle.disabled = !hasPermission('members.manage'); toggle.addEventListener('click', () => toggleStatus(toggle));
    if (hasPermission('payments.record')) actions.appendChild(pay);
    actions.append(renew, edit, toggle); body.appendChild(actions);

    renderMembershipHistory(body, allMemberships());
    if (hasPermission('payments.read')) renderPaymentHistory(body, Array.isArray(detail.payments) ? detail.payments : []);
    if (hasPermission('notifications.manage')) renderNotificationHistory(body, Array.isArray(detail.notifications) ? detail.notifications : []);
  }

  async function refreshSelected() {
    if (!state.selected?.id) return;
    state.detail = await core().api(`/api/admin/customers/${encodeURIComponent(state.selected.id)}`);
    state.selected = state.detail.customer;
    renderCustomerProfile();
  }

  async function openCustomerById(customerId, opener = document.activeElement) {
    if (!customerId) return;
    state.selected = { id: customerId }; state.opener = opener;
    const dialog = $('customerDrawer');
    $('customerDrawerName').textContent = 'Customer';
    $('customerDrawerBody').innerHTML = '<div class="software-loading">Loading customer profile...</div>';
    if (!dialog.open) dialog.showModal();
    try { await refreshSelected(); }
    catch (_) { $('customerDrawerBody').innerHTML = '<div class="software-empty error-state">Customer details are temporarily unavailable. Close and retry.</div>'; }
  }

  function openCustomer(member) { return openCustomerById(member?.id, document.activeElement); }

  async function applyCustomerStatus(next, button, errorNode = null) {
    if (!state.selected) return false;
    if (errorNode) errorNode.textContent = '';
    setBusy(button, true, next === 'disabled' ? 'Disabling...' : 'Enabling...');
    try {
      await core().api(`/api/admin/customers/${encodeURIComponent(state.selected.id)}`, { method: 'PATCH', body: { status: next } });
      core().flash(next === 'disabled' ? 'Customer disabled. Active customer sessions were revoked by the server.' : 'Customer enabled.');
      await refreshSelected(); await refreshRelated();
      return true;
    } catch (error) {
      const message = errorText(error, 'edit');
      if (errorNode) errorNode.textContent = message; else core().flash(message, 'error');
      return false;
    } finally { setBusy(button, false); }
  }

  async function toggleStatus(button) {
    if (!state.selected) return;
    const next = state.selected.status === 'active' ? 'disabled' : 'active';
    if (next === 'disabled') {
      state.accessOpener = button || document.activeElement;
      $('customerAccessError').textContent = '';
      $('customerAccessName').textContent = `Disable ${state.selected.displayName || 'this customer'}?`;
      const dialog = $('customerAccessDialog');
      if (!dialog.open) dialog.showModal();
      $('confirmCustomerDisable').focus();
      return;
    }
    await applyCustomerStatus(next, button);
  }

  async function confirmCustomerDisable(event) {
    event.preventDefault();
    const button = $('confirmCustomerDisable');
    const changed = await applyCustomerStatus('disabled', button, $('customerAccessError'));
    if (changed) { $('customerAccessDialog').close(); $('customerAccessToggle')?.focus(); }
  }

  function previewExpiry(startValue, months) {
    const date = startValue ? new Date(`${startValue}T12:00:00`) : new Date();
    if (Number.isNaN(date.getTime())) return '--';
    date.setMonth(date.getMonth() + Number(months || 1));
    return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  function selectedPlan(selectId) { return state.plans.find((item) => item.id === $(selectId).value); }

  function updateAddPreview() {
    const plan = selectedPlan('newCustomerPlan'); const received = toPaise($('newCustomerReceived').value);
    $('newCustomerFee').value = plan ? moneyPaise(plan.pricePaise, plan.currency) : '--';
    $('newCustomerExpiry').textContent = plan ? previewExpiry($('newCustomerStart').value, plan.durationMonths) : '--';
    $('newCustomerPending').textContent = plan ? moneyPaise(Math.max(0, Number(plan.pricePaise || 0) - received), plan.currency) : '--';
  }

  async function openAddCustomer() {
    state.opener = document.activeElement; await loadPlans();
    const form = $('addCustomerForm'); form.reset(); $('addCustomerError').textContent = '';
    const select = $('newCustomerPlan'); select.replaceChildren();
    for (const plan of state.plans.filter((item) => item.status === 'active')) select.appendChild(new Option(`${plan.name} - ${moneyPaise(plan.pricePaise, plan.currency)}`, plan.id));
    $('newCustomerStart').value = new Date().toISOString().slice(0, 10); $('newCustomerReceived').value = '0'; updateAddPreview();
    const dialog = $('addCustomerDialog'); if (!dialog.open) dialog.showModal(); $('newCustomerName').focus();
  }

  async function addCustomer(event) {
    event.preventDefault();
    const submit = $('submitNewCustomer'); $('addCustomerError').textContent = ''; setBusy(submit, true, 'Adding...');
    const body = {
      displayName: $('newCustomerName').value.trim(), phone: normalizePhoneInput($('newCustomerMobile').value), planId: $('newCustomerPlan').value,
      amountPaidPaise: toPaise($('newCustomerReceived').value), paymentMethod: $('newCustomerPaymentMethod').value,
    };
    const startsAt = dateToUnix($('newCustomerStart').value); if (startsAt) body.startsAt = startsAt;
    if ($('newCustomerNote').value.trim()) body.note = $('newCustomerNote').value.trim();
    try {
      const result = await core().api('/api/admin/customers', { method: 'POST', body });
      $('addCustomerDialog').close(); core().flash('Customer added with server-calculated membership and balance.');
      await refreshRelated();
      if (result.customer?.id) await openCustomerById(result.customer.id, state.opener);
    } catch (error) { $('addCustomerError').textContent = errorText(error, 'add'); }
    finally { setBusy(submit, false); }
  }

  function updateEditAccessImpact() {
    if (!state.selected) return;
    const phoneChanged = normalizePhoneInput($('editCustomerMobile').value) !== normalizePhoneInput(state.selected.phone || '');
    const disabling = state.selected.status === 'active' && $('editCustomerStatus').value === 'disabled';
    const impacts = [];
    if (disabling) impacts.push('Disabling the account blocks customer login and revokes active customer sessions.');
    if (phoneChanged) impacts.push('Changing the mobile invalidates previous phone verification and active customer sessions; the new mobile must be verified again.');
    const warning = $('editCustomerAccessWarning');
    const acknowledge = $('editCustomerAccessAcknowledge');
    warning.hidden = impacts.length === 0;
    $('editCustomerAccessImpact').textContent = impacts.join(' ');
    acknowledge.required = impacts.length > 0;
    if (!impacts.length) acknowledge.checked = false;
  }

  function openEdit() {
    if (!state.selected) return;
    state.opener = document.activeElement; $('editCustomerError').textContent = '';
    $('editCustomerName').value = state.selected.displayName || ''; $('editCustomerMobile').value = state.selected.phone || ''; $('editCustomerStatus').value = state.selected.status || 'active';
    $('editCustomerAccessAcknowledge').checked = false; updateEditAccessImpact();
    const dialog = $('editCustomerDialog'); if (!dialog.open) dialog.showModal(); $('editCustomerName').focus();
  }

  async function editCustomer(event) {
    event.preventDefault(); if (!state.selected) return;
    const submit = $('submitEditCustomer'); $('editCustomerError').textContent = ''; setBusy(submit, true, 'Saving...');
    try {
      await core().api(`/api/admin/customers/${encodeURIComponent(state.selected.id)}`, { method: 'PATCH', body: { displayName: $('editCustomerName').value.trim(), phone: normalizePhoneInput($('editCustomerMobile').value), status: $('editCustomerStatus').value } });
      $('editCustomerDialog').close(); core().flash('Customer updated.'); await refreshSelected(); await refreshRelated();
    } catch (error) { $('editCustomerError').textContent = errorText(error, 'edit'); }
    finally { setBusy(submit, false); }
  }

  function updateRenewPreview() {
    const plan = selectedPlan('renewPlan'); const received = toPaise($('renewReceived').value);
    $('renewFeePreview').value = plan ? moneyPaise(plan.pricePaise, plan.currency) : '--';
    $('renewExpiryPreview').value = plan ? previewExpiry($('renewStart').value, plan.durationMonths) : '--';
    $('renewPendingPreview').textContent = plan ? moneyPaise(Math.max(0, Number(plan.pricePaise || 0) - received), plan.currency) : '--';
  }

  async function openRenew() {
    if (!state.selected) return;
    state.opener = document.activeElement; state.renewKey = newIdempotencyKey('admin-renew'); await loadPlans();
    const current = currentMembership(); $('renewError').textContent = '';
    $('renewCurrentExpiry').textContent = current ? `Current membership ${current.membershipNumber || ''} expires ${formatDate(current.endsAt)}. Leave start date blank to let the server queue renewal safely.` : 'No active membership. The server will determine the authoritative start and expiry.';
    const select = $('renewPlan'); select.replaceChildren();
    for (const plan of state.plans.filter((item) => item.status === 'active')) select.appendChild(new Option(`${plan.name} - ${moneyPaise(plan.pricePaise, plan.currency)}`, plan.id));
    $('renewStart').value = ''; $('renewReceived').value = '0'; $('renewNote').value = ''; updateRenewPreview();
    const dialog = $('renewMembershipDialog'); if (!dialog.open) dialog.showModal(); select.focus();
  }

  async function renewMembership(event) {
    event.preventDefault(); if (!state.selected) return;
    const submit = $('submitRenewMembership'); $('renewError').textContent = ''; setBusy(submit, true, 'Renewing...');
    const body = { planId: $('renewPlan').value, amountPaidPaise: toPaise($('renewReceived').value), paymentMethod: $('renewPaymentMethod').value };
    const startsAt = dateToUnix($('renewStart').value); if (startsAt) body.startsAt = startsAt;
    if ($('renewNote').value.trim()) body.note = $('renewNote').value.trim();
    try {
      await core().api(`/api/admin/customers/${encodeURIComponent(state.selected.id)}/renew`, { method: 'POST', headers: { 'Idempotency-Key': state.renewKey }, body });
      $('renewMembershipDialog').close(); core().flash('Membership renewed. Server dates and balance are authoritative.'); await refreshSelected(); await refreshRelated();
    } catch (error) { $('renewError').textContent = errorText(error, 'renew'); }
    finally { setBusy(submit, false); }
  }

  function openRecordPayment(membership, customer = state.selected) {
    if (!membership || !customer) return;
    state.opener = document.activeElement; state.paymentTarget = { membership, customer }; state.paymentKey = newIdempotencyKey('admin-payment');
    $('paymentError').textContent = ''; $('paymentCustomer').textContent = customer.displayName || customer.customerName || 'Customer';
    $('paymentMembership').textContent = membership.membershipNumber || '--'; $('paymentPending').textContent = moneyPaise(membership.payment?.pendingPaise, membership.currency);
    $('paymentAmount').value = (Number(membership.payment?.pendingPaise || 0) / 100).toFixed(2); $('paymentAmount').max = (Number(membership.payment?.pendingPaise || 0) / 100).toFixed(2);
    $('paymentMethod').value = 'cash'; $('paymentDate').value = new Date().toISOString().slice(0, 10); $('paymentNote').value = '';
    const dialog = $('recordPaymentDialog'); if (!dialog.open) dialog.showModal(); $('paymentAmount').focus();
  }

  async function recordPayment(event) {
    event.preventDefault(); const target = state.paymentTarget; if (!target) return;
    const submit = $('submitPayment'); $('paymentError').textContent = ''; setBusy(submit, true, 'Recording...');
    const body = { amountPaise: toPaise($('paymentAmount').value), method: $('paymentMethod').value };
    const paidAt = dateToUnix($('paymentDate').value); if (paidAt) body.paidAt = paidAt;
    if ($('paymentNote').value.trim()) body.note = $('paymentNote').value.trim();
    try {
      await core().api(`/api/admin/memberships/${encodeURIComponent(target.membership.id)}/payments`, { method: 'POST', headers: { 'Idempotency-Key': state.paymentKey }, body });
      $('recordPaymentDialog').close(); core().flash('Payment recorded against the server ledger.');
      if (state.selected?.id === (target.customer.id || target.customer.customerId)) await refreshSelected();
      await refreshRelated();
    } catch (error) { $('paymentError').textContent = errorText(error, 'payment'); }
    finally { setBusy(submit, false); }
  }

  async function refreshRelated() {
    await Promise.allSettled([
      renderWorkspace(), window.GravityAdminDashboard?.renderWorkspace?.(), window.GravityMembershipAdmin?.renderWorkspace?.(), window.GravityPaymentAdmin?.renderWorkspace?.(),
    ]);
  }

  function installDialogA11y(dialog) {
    dialog.addEventListener('keydown', (event) => {
      if (event.key !== 'Tab') return;
      const focusable = Array.from(dialog.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])')).filter((node) => !node.hidden && node.getClientRects().length > 0);
      if (!focusable.length) return;
      const first = focusable[0]; const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
    });
    dialog.addEventListener('close', () => { const opener = dialog === $('customerAccessDialog') ? state.accessOpener : state.opener; if (opener && document.contains(opener)) opener.focus(); });
  }

  ['customerStatusFilter', 'customerMembershipFilter', 'customerPlanFilter'].forEach((id) => $(id).addEventListener('change', () => renderWorkspace().catch(() => core().flash('Customer list is temporarily unavailable.', 'error'))));
  ['newCustomerPlan', 'newCustomerStart', 'newCustomerReceived'].forEach((id) => $(id).addEventListener('input', updateAddPreview));
  ['renewPlan', 'renewStart', 'renewReceived'].forEach((id) => $(id).addEventListener('input', updateRenewPreview));
  $('editCustomerMobile').addEventListener('input', updateEditAccessImpact); $('editCustomerStatus').addEventListener('change', updateEditAccessImpact);
  $('addCustomerForm').addEventListener('submit', addCustomer); $('editCustomerForm').addEventListener('submit', editCustomer); $('customerAccessForm').addEventListener('submit', confirmCustomerDisable); $('renewMembershipForm').addEventListener('submit', renewMembership); $('recordPaymentForm').addEventListener('submit', recordPayment);
  document.querySelectorAll('[data-close-dialog]').forEach((button) => button.addEventListener('click', () => $(button.dataset.closeDialog).close()));
  [$('customerDrawer'), $('addCustomerDialog'), $('editCustomerDialog'), $('customerAccessDialog'), $('renewMembershipDialog'), $('recordPaymentDialog')].forEach(installDialogA11y);

  window.GravityCustomerAdmin = {
    setAdmin(admin) { state.admin = admin; }, renderWorkspace, openCustomer, openCustomerById, openAddCustomer,
    openPaymentFor(membership, customer) { openRecordPayment(membership, customer); }, refreshSelected,
  };
})();
