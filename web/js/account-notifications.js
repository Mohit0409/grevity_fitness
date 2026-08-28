(() => {
  'use strict';

  const signedIn = document.getElementById('account-signed-in');
  const profileForm = document.getElementById('profile-form');
  if (!signedIn || !profileForm) return;

  const card = document.createElement('section');
  card.className = 'membership-card notification-history-card';
  card.id = 'notification-history-card';
  card.hidden = true;
  card.setAttribute('aria-labelledby', 'notification-history-heading');

  const head = document.createElement('div');
  head.className = 'membership-card-head';
  const titleWrap = document.createElement('div');
  const label = document.createElement('span');
  label.className = 'membership-label';
  label.textContent = 'REMINDERS';
  const title = document.createElement('h3');
  title.id = 'notification-history-heading';
  title.textContent = 'Membership expiry reminders';
  titleWrap.append(label, title);
  head.appendChild(titleWrap);

  const note = document.createElement('p');
  note.className = 'membership-muted notification-history-intro';
  note.textContent = 'A simple history of expiry reminders generated for your membership.';

  const list = document.createElement('div');
  list.id = 'notification-history-list';
  list.className = 'notification-reminders';
  list.setAttribute('role', 'list');
  list.setAttribute('aria-live', 'polite');
  list.setAttribute('aria-busy', 'false');
  card.append(head, note, list);
  signedIn.insertBefore(card, profileForm);

  function formatDateTime(value) {
    if (!value) return 'Not available';
    const numeric = Number(value);
    const date = new Date(numeric < 10_000_000_000 ? numeric * 1000 : numeric);
    if (Number.isNaN(date.getTime())) return 'Not available';
    return date.toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
    });
  }

  function reminderTiming(days) {
    const value = Number(days);
    if (value === 0) return 'Membership expired today';
    if (value === 1) return 'Membership expires tomorrow';
    if (value === 3) return 'Membership expires in 3 days';
    if (value === 7) return 'Membership expires in 7 days';
    if (Number.isFinite(value) && value > 1) return `Membership expires in ${value} days`;
    return 'Membership expiry reminder';
  }

  function reminderWindow(days) {
    const value = Number(days);
    if (value === 0) return 'Expiry day';
    if (value === 1) return '1 day before expiry';
    if (Number.isFinite(value) && value > 1) return `${value} days before expiry`;
    return 'Reminder timing unavailable';
  }

  function customerReminderStatus(item) {
    if (item.state === 'suppressed') return { key: 'suppressed', label: 'Suppressed after renewal' };
    const deliveries = Array.isArray(item.deliveries)
      ? item.deliveries.filter((delivery) => delivery.recipientRole !== 'owner') : [];
    if (deliveries.some((delivery) => delivery.status === 'sent')) return { key: 'sent', label: 'Sent' };
    if (item.state === 'pending' || deliveries.some((delivery) => ['queued', 'failed', 'blocked_external_config'].includes(delivery.status))) {
      return { key: 'pending', label: 'Pending' };
    }
    return { key: 'reminder', label: 'Reminder' };
  }

  function appendFact(listNode, term, value) {
    const dt = document.createElement('dt');
    dt.textContent = term;
    const dd = document.createElement('dd');
    dd.textContent = value;
    listNode.append(dt, dd);
  }

  function renderReminder(item) {
    const row = document.createElement('article');
    row.className = 'notification-reminder';
    row.setAttribute('role', 'listitem');

    const top = document.createElement('div');
    top.className = 'notification-reminder-head';
    const heading = document.createElement('strong');
    heading.textContent = reminderTiming(item.triggerDays);
    const reminderStatus = customerReminderStatus(item);
    const status = document.createElement('span');
    status.className = `notification-customer-status notification-customer-status--${reminderStatus.key}`;
    status.textContent = reminderStatus.label;
    status.setAttribute('aria-label', `Reminder status: ${reminderStatus.label}`);
    top.append(heading, status);

    const facts = document.createElement('dl');
    facts.className = 'notification-reminder-facts';
    appendFact(facts, 'Plan', item.payload?.planName || 'Plan not available');
    if (item.payload?.membershipNumber) appendFact(facts, 'Membership', item.payload.membershipNumber);
    appendFact(facts, 'Expiry', formatDateTime(item.payload?.endsAt));
    appendFact(facts, 'Reminder timing', reminderWindow(item.triggerDays));
    row.append(top, facts);

    if (item.state === 'suppressed') {
      const stopped = document.createElement('p');
      stopped.className = 'notification-suppressed';
      stopped.textContent = 'Renewal confirmed. This reminder was stopped.';
      row.appendChild(stopped);
    }
    return row;
  }

  function renderState(message, className = 'notification-history-state') {
    const state = document.createElement('p');
    state.className = className;
    state.textContent = message;
    list.appendChild(state);
  }

  function render(items) {
    list.replaceChildren();
    for (const item of items || []) {
      if (!item.eventType || item.eventType === 'membership_expiry') list.appendChild(renderReminder(item));
    }
    if (!list.children.length) renderState('No membership reminders yet.');
    list.setAttribute('aria-busy', 'false');
    card.hidden = false;
  }

  async function refresh() {
    if (signedIn.hidden) return;
    list.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch('/api/me/notifications', {
        credentials: 'same-origin', headers: { Accept: 'application/json' }
      });
      if (response.status === 401) { card.hidden = true; return; }
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error('notification_history_unavailable');
      render(payload.notifications || []);
    } catch (_) {
      list.replaceChildren();
      renderState('Reminder history is temporarily unavailable. Try again later.', 'notification-history-state notification-history-error');
      list.setAttribute('aria-busy', 'false');
      card.hidden = false;
    }
  }

  const observer = new MutationObserver(() => {
    if (!signedIn.hidden) refresh();
    else card.hidden = true;
  });
  observer.observe(signedIn, { attributes: true, attributeFilter: ['hidden'] });
  if (!signedIn.hidden) refresh();
})();
