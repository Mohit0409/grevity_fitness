(() => {
  'use strict';

  const container = document.getElementById('public-membership-plans');
  if (!container) return;

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text != null) element.textContent = text;
    return element;
  }

  function formatMoney(plan) {
    const amount = Number(plan.pricePaise || 0) / 100;
    try {
      return new Intl.NumberFormat('en-IN', {
        style: 'currency', currency: plan.currency || 'INR', maximumFractionDigits: 2,
      }).format(amount);
    } catch (_) {
      return `${plan.currency || 'INR'} ${amount.toFixed(2)}`;
    }
  }

  function emptyCard(message) {
    const card = node('div', 'price-card reveal');
    card.append(node('div', 'price-name', 'Membership enquiries'));
    card.append(node('div', 'price-duration', message));
    const link = node('a', 'plan-book-btn outline', 'Contact Gravity →');
    link.href = '#contact';
    card.append(link);
    return card;
  }
  function renderPlan(plan) {
    const card = node('div', 'price-card reveal');
    card.append(node('div', 'price-name', plan.name || 'Membership'));
    card.append(node('div', 'price-amount', formatMoney(plan)));
    const months = Number(plan.durationMonths || 1);
    card.append(node('div', 'price-duration', `${months} month${months === 1 ? '' : 's'} · verified active plan`));
    if (plan.description) card.append(node('p', 'price-description', plan.description));

    const button = node('button', 'plan-book-btn outline', 'Enquire →');
    button.type = 'button';
    button.addEventListener('click', () => {
      if (typeof window.openBooking !== 'function') return;
      window.openBooking('plan', plan.name || 'Membership', Number(plan.pricePaise || 0) / 100, months);
    });
    card.append(button);
    return card;
  }

  async function load() {
    try {
      const response = await fetch('/api/membership/plans', {
        credentials: 'same-origin', headers: { Accept: 'application/json' },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const plans = Array.isArray(payload.plans) ? payload.plans : [];
      container.replaceChildren();
      if (!plans.length) {
        container.append(emptyCard('No membership price is currently published. Contact Gravity for current options.'));
        return;
      }
      for (const plan of plans) container.append(renderPlan(plan));
    } catch (_) {
      container.replaceChildren(emptyCard('Verified membership options are temporarily unavailable. Please contact Gravity.'));
    }
  }

  load();
})();
