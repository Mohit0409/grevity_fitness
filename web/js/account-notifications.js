(() => {
  'use strict';

  const signedIn = document.getElementById('account-signed-in');
  const profileForm = document.getElementById('profile-form');
  if (!signedIn || !profileForm) return;

  const card = document.createElement('section');
  card.className = 'membership-card';
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
  title.textContent = 'Membership expiry notifications';
  titleWrap.append(label, title);
  head.appendChild(titleWrap);

  const note = document.createElement('p');
  note.className = 'membership-muted';
  note.textContent = 'Reminder history is server-owned. Email, SMS and WhatsApp delivery remain blocked until verified provider configuration exists.';
  const list = document.createElement('div');
  list.id = 'notification-history-list';
  list.className = 'membership-history';
  card.append(head, note, list);
  signedIn.insertBefore(card, profileForm);

  function formatDate(value) {
    if (!value) return '—';
    const date = new Date(Number(value) * 1000);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric'
    });
  }

  function deliverySummary(deliveries) {
    if (!deliveries?.length) return 'No delivery records';
    return deliveries
      .map((item) => `${item.channel}: ${String(item.status || '').replaceAll('_', ' ')}`)
      .join(' · ');
  }

  function render(items) {
    list.replaceChildren();
    for (const item of items || []) {
      const row = document.createElement('div');
      row.className = 'membership-history-item';
      const strong = document.createElement('strong');
      strong.textContent = item.payload?.planName || item.payload?.membershipNumber || 'Gravity membership';
      const detail = document.createElement('span');
      const ends = item.payload?.endsAt ? ` · ends ${formatDate(item.payload.endsAt)}` : '';
      detail.textContent = `${item.triggerDays} day reminder · ${String(item.state || '').replaceAll('_', ' ')}${ends}`;
      const delivery = document.createElement('small');
      delivery.textContent = deliverySummary(item.deliveries || []);
      row.append(strong, detail, delivery);
      list.appendChild(row);
    }
    if (!list.children.length) {
      const empty = document.createElement('div');
      empty.className = 'membership-muted';
      empty.textContent = 'No membership expiry reminders have been generated for your account.';
      list.appendChild(empty);
    }
    card.hidden = false;
  }

  async function refresh() {
    if (signedIn.hidden) return;
    try {
      const response = await fetch('/api/me/notifications', {
        credentials: 'same-origin', headers: { Accept: 'application/json' }
      });
      if (response.status === 401) { card.hidden = true; return; }
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      render(payload.notifications || []);
    } catch (_) {
      list.replaceChildren();
      const error = document.createElement('div');
      error.className = 'membership-muted';
      error.textContent = 'Reminder history is temporarily unavailable. No account data was changed.';
      list.appendChild(error);
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
