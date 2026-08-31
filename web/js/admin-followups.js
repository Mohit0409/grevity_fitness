(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null, items: [], filter: 'all', requestId: 0 };
  const core = () => window.GravityAdminCore;

  function formatDate(value) {
    const numeric = Number(value || 0);
    if (!numeric) return '--';
    const date = new Date(numeric < 10_000_000_000 ? numeric * 1000 : numeric);
    return Number.isNaN(date.getTime()) ? '--' : date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  function flatten(groups = {}) {
    return [
      ['expired', 'Expired', groups.expired || []],
      ['today', 'Expires today', groups.today || []],
      ['tomorrow', 'Expires tomorrow', groups.tomorrow || []],
      ['threeDays', 'Expires within 3 days', groups.threeDays || []],
      ['sevenDays', 'Expires within 7 days', groups.sevenDays || []],
    ].flatMap(([bucket, label, rows]) => rows.map((row) => ({ ...row, bucket, label })));
  }

  function matches(item) {
    if (state.filter === 'all') return true;
    if (state.filter === 'expired') return item.bucket === 'expired';
    if (state.filter === 'today') return item.bucket === 'today';
    if (state.filter === 'tomorrow') return item.bucket === 'tomorrow';
    if (state.filter === 'next3') return ['today', 'tomorrow', 'threeDays'].includes(item.bucket);
    if (state.filter === 'next7') return item.bucket !== 'expired';
    return true;
  }

  function followupCard(item) {
    const card = document.createElement('article'); card.className = 'followup-card'; card.setAttribute('role', 'listitem');
    const head = document.createElement('div'); head.className = 'followup-card-head';
    const identity = document.createElement('div');
    const name = document.createElement('h4'); name.textContent = item.customerName || 'Customer';
    const phone = document.createElement('small'); phone.textContent = item.phone || 'Mobile number missing';
    identity.append(name, phone);
    const status = document.createElement('span'); status.className = `followup-status followup-status--${item.bucket === 'expired' ? 'expired' : 'due'}`; status.textContent = item.label;
    head.append(identity, status);

    const facts = document.createElement('div'); facts.className = 'followup-facts';
    const plan = document.createElement('span'); plan.innerHTML = `<small>Plan</small><strong></strong>`; plan.querySelector('strong').textContent = item.planName || '--';
    const expiry = document.createElement('span'); expiry.innerHTML = `<small>Expiry</small><strong></strong>`; expiry.querySelector('strong').textContent = formatDate(item.endsAt);
    const membership = document.createElement('span'); membership.innerHTML = `<small>Membership</small><strong></strong>`; membership.querySelector('strong').textContent = item.membershipNumber || '--';
    facts.append(plan, expiry, membership);

    const actions = document.createElement('div'); actions.className = 'followup-actions';
    const whatsapp = document.createElement('button'); whatsapp.type = 'button'; whatsapp.className = 'whatsapp-action'; whatsapp.textContent = item.phone ? 'Send WhatsApp' : 'Mobile missing'; whatsapp.disabled = !item.phone;
    whatsapp.addEventListener('click', () => core()?.openWhatsAppReminder(item));
    const open = document.createElement('button'); open.type = 'button'; open.className = 'ghost'; open.textContent = 'Open customer';
    open.addEventListener('click', () => window.GravityCustomerAdmin?.openCustomerById(item.customerId));
    actions.append(whatsapp, open); card.append(head, facts, actions); return card;
  }

  function render() {
    const list = $('followupsList');
    const visible = state.items.filter(matches);
    list.replaceChildren(...visible.map(followupCard));
    if (!visible.length) {
      const empty = document.createElement('p'); empty.className = 'followup-empty'; empty.setAttribute('role', 'listitem'); empty.textContent = 'No customers need a membership follow-up in this filter.'; list.appendChild(empty);
    }
    const expired = visible.filter((item) => item.bucket === 'expired').length;
    const expiring = visible.length - expired;
    $('followupSummary').textContent = `${visible.length} to contact · ${expired} expired · ${expiring} expiring soon`;
  }

  async function renderWorkspace() {
    const api = core()?.api;
    if (!api) return;
    const requestId = ++state.requestId;
    const panel = $('followupPanel'); panel.setAttribute('aria-busy', 'true');
    $('followupSummary').textContent = 'Loading follow-ups…';
    try {
      const dashboard = await api('/api/admin/dashboard');
      if (requestId !== state.requestId) return;
      state.items = flatten(dashboard.expiring || {});
      render();
    } catch (_) {
      if (requestId !== state.requestId) return;
      state.items = [];
      $('followupsList').replaceChildren();
      const error = document.createElement('p'); error.className = 'followup-empty error-state'; error.setAttribute('role', 'listitem'); error.textContent = 'Follow-ups are temporarily unavailable. Refresh to try again.'; $('followupsList').appendChild(error);
      $('followupSummary').textContent = 'Could not load follow-ups';
    } finally {
      if (requestId === state.requestId) panel.setAttribute('aria-busy', 'false');
    }
  }

  $('followupFilter').addEventListener('change', () => { state.filter = $('followupFilter').value; render(); });
  $('refreshFollowups').addEventListener('click', () => renderWorkspace().catch(() => {}));

  window.GravityFollowupAdmin = {
    setAdmin(admin) { state.admin = admin; },
    renderWorkspace,
    setFilter(filter) {
      const allowed = ['all', 'expired', 'next7', 'next3', 'tomorrow', 'today'];
      state.filter = allowed.includes(filter) ? filter : 'all';
      $('followupFilter').value = state.filter;
      render();
    },
  };
})();
