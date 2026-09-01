(() => {
  'use strict';
  const container = document.getElementById('public-membership-plans');
  if (!container) return;
  container.setAttribute('aria-busy', 'true');
  container.classList.add('is-loading');
  const verified = new Map([
    ['one-month', { name: '1 Month', pricePaise: 120000, durationMonths: 1, order: 1 }],
    ['three-months', { name: '3 Months', pricePaise: 300000, durationMonths: 3, order: 2 }],
    ['one-year', { name: '1 Year', pricePaise: 1000000, durationMonths: 12, order: 3 }],
  ]);
  function element(tag, className, copy) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (copy !== undefined) node.textContent = copy;
    return node;
  }
  const formatPrice = (value) => new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR', maximumFractionDigits: 0,
  }).format(Number(value) / 100);
  function renderCard(plan, index) {
    const card = element('article', 'plan-card');
    card.appendChild(element('span', 'plan-card__number', `0${index + 1}`));
    card.appendChild(element('h3', '', plan.name));
    const price = element('div', 'plan-price');
    price.append(element('strong', '', formatPrice(plan.pricePaise)), element('span', '', plan.durationMonths === 1 ? 'for 1 month' : `for ${plan.durationMonths} months`));
    card.appendChild(price);
    card.appendChild(element('p', 'plan-card__copy', 'Gym membership fee. Ask Gravity to confirm the next step.'));
    const button = element('button', 'button', 'Enquire about this plan');
    button.type = 'button';
    button.dataset.requestKind = 'membership';
    button.dataset.planId = plan.id;
    button.dataset.planName = plan.name;
    card.appendChild(button);
    return card;
  }
  function renderUnavailable() {
    const card = element('article', 'plan-card');
    card.append(element('span', 'plan-card__number', 'MEMBERSHIP'), element('h3', '', 'Prices unavailable'));
    card.appendChild(element('p', 'plan-card__copy', 'Verified membership prices could not be loaded. Contact Gravity before relying on a price.'));
    const link = element('a', 'button', 'Call Gravity');
    link.href = 'tel:+917999526112';
    card.appendChild(link);
    container.replaceChildren(card);
  }
  async function load() {
    try {
      const response = await fetch('/api/membership/plans', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const plans = (Array.isArray(payload.plans) ? payload.plans : [])
        .filter((item) => {
          const expected = verified.get(item.code);
          return expected && item.name === expected.name && Number(item.pricePaise) === expected.pricePaise
            && Number(item.durationMonths) === expected.durationMonths && item.currency === 'INR' && item.status === 'active';
        })
        .sort((a, b) => verified.get(a.code).order - verified.get(b.code).order);
      if (plans.length !== verified.size) throw new Error('Verified plan set is incomplete');
      container.replaceChildren(...plans.map(renderCard));
      window.dispatchEvent(new CustomEvent('gravity:plans-ready', { detail: { plans } }));
    } catch (_) { renderUnavailable(); }
    finally { container.classList.remove('is-loading'); container.setAttribute('aria-busy', 'false'); }
  }
  load();
})();
