(() => {
  'use strict';

  const signedIn = document.getElementById('account-signed-in');
  if (!signedIn) return;

  const cookieValue = (name) => {
    const prefix = `${name}=`;
    const item = document.cookie.split(';').map((part) => part.trim()).find((part) => part.startsWith(prefix));
    return item ? decodeURIComponent(item.slice(prefix.length)) : '';
  };

  async function api(path, options = {}) {
    const request = { credentials: 'same-origin', ...options };
    request.headers = { Accept: 'application/json', ...(options.headers || {}) };
    if (options.body && typeof options.body !== 'string') {
      request.body = JSON.stringify(options.body);
      request.headers['Content-Type'] = 'application/json';
    }
    if (request.method && !['GET', 'HEAD'].includes(request.method)) {
      const csrf = cookieValue('gravity_csrf') || cookieValue('__Host-gravity_csrf');
      if (csrf) request.headers['X-CSRF-Token'] = csrf;
    }
    const response = await fetch(path, request);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || `HTTP ${response.status}`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  function money(amountPaise, currency = 'INR') {
    try {
      return new Intl.NumberFormat('en-IN', {
        style: 'currency', currency, maximumFractionDigits: 2,
      }).format(Number(amountPaise || 0) / 100);
    } catch (_) {
      return `${currency} ${(Number(amountPaise || 0) / 100).toFixed(2)}`;
    }
  }

  function createPanel() {
    let panel = document.getElementById('payment-panel');
    if (panel) return panel;
    panel = document.createElement('section');
    panel.id = 'payment-panel';
    panel.className = 'membership-card';
    panel.setAttribute('aria-labelledby', 'payment-heading');
    panel.innerHTML = `
      <div class="membership-card-head"><div><span class="membership-label">PAYMENTS</span>
      <h3 id="payment-heading">Secure membership payment</h3></div></div>
      <p id="payment-status" class="membership-muted">Checking secure payment availability…</p>
      <div id="payment-checkout" hidden></div>
      <details id="payment-history-wrap" class="membership-history" hidden>
        <summary>Payment history</summary><div id="payment-history"></div>
      </details>
      <details id="invoice-history-wrap" class="membership-history" hidden>
        <summary>Invoice & receipt records</summary><div id="invoice-history"></div>
      </details>`;
    const membership = signedIn.querySelector('.membership-card');
    membership?.insertAdjacentElement('afterend', panel);
    return panel;
  }

  function renderHistory(payments, invoices) {
    const paymentWrap = document.getElementById('payment-history-wrap');
    const paymentHistory = document.getElementById('payment-history');
    paymentHistory.replaceChildren();
    for (const item of payments || []) {
      const row = document.createElement('div');
      row.className = 'membership-history-item';
      const title = document.createElement('strong');
      title.textContent = `${item.planName || 'Membership'} · ${money(item.amountPaise, item.currency)}`;
      const detail = document.createElement('span');
      detail.textContent = `${String(item.status || '').toUpperCase()} · ${new Date(Number(item.createdAt) * 1000).toLocaleString()}`;
      row.append(title, detail);
      paymentHistory.appendChild(row);
    }
    paymentWrap.hidden = !paymentHistory.children.length;

    const invoiceWrap = document.getElementById('invoice-history-wrap');
    const invoiceHistory = document.getElementById('invoice-history');
    invoiceHistory.replaceChildren();
    for (const item of invoices || []) {
      const row = document.createElement('div');
      row.className = 'membership-history-item';
      const title = document.createElement('strong');
      title.textContent = `${item.documentNumber} · ${money(item.amountPaise, item.currency)}`;
      const detail = document.createElement('span');
      detail.textContent = item.status === 'issued'
        ? 'Server-issued receipt available.'
        : 'Receipt pending verified Gravity business/GST identity.';
      row.append(title, detail);
      invoiceHistory.appendChild(row);
    }
    invoiceWrap.hidden = !invoiceHistory.children.length;
  }

  function loadRazorpay() {
    if (window.Razorpay) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-gravity-razorpay]');
      if (existing) {
        existing.addEventListener('load', resolve, { once: true });
        existing.addEventListener('error', reject, { once: true });
        return;
      }
      const script = document.createElement('script');
      script.src = 'https://checkout.razorpay.com/v1/checkout.js';
      script.async = true;
      script.dataset.gravityRazorpay = '1';
      script.addEventListener('load', resolve, { once: true });
      script.addEventListener('error', () => reject(new Error('razorpay_checkout_unavailable')), { once: true });
      document.head.appendChild(script);
    });
  }

  async function verifyPayment(intent, response) {
    return api('/api/me/payments/verify', {
      method: 'POST',
      body: {
        intentId: intent.id,
        razorpayOrderId: response.razorpay_order_id,
        razorpayPaymentId: response.razorpay_payment_id,
        razorpaySignature: response.razorpay_signature,
      },
    });
  }

  async function startCheckout(planId) {
    const status = document.getElementById('payment-status');
    status.textContent = 'Creating a server-owned Razorpay order…';
    const payload = await api('/api/me/payments', { method: 'POST', body: { planId } });
    const intent = payload.payment;
    await loadRazorpay();
    const checkout = intent.checkout || {};
    const razorpay = new window.Razorpay({
      key: checkout.keyId,
      amount: checkout.amountPaise,
      currency: checkout.currency,
      name: 'Gravity Fitness',
      description: intent.planName || 'Gravity membership',
      order_id: checkout.orderId,
      handler: async (response) => {
        status.textContent = 'Verifying payment with Gravity…';
        try {
          await verifyPayment(intent, response);
          status.textContent = 'Payment verified. Your membership state is now server-confirmed.';
          await refresh();
          window.setTimeout(() => window.location.reload(), 900);
        } catch (_) {
          status.textContent = 'Payment could not be verified. No membership success was assumed.';
        }
      },
      modal: {
        ondismiss: () => {
          status.textContent = 'Checkout closed. No payment success was assumed.';
        },
      },
    });
    razorpay.on('payment.failed', () => {
      status.textContent = 'Razorpay reported a failed attempt. Your membership was not activated.';
    });
    razorpay.open();
  }

  function renderCheckout(config, plans) {
    const wrap = document.getElementById('payment-checkout');
    const status = document.getElementById('payment-status');
    wrap.replaceChildren();
    if (!config.enabled) {
      wrap.hidden = true;
      status.textContent = 'Online payment is not configured yet. No card/UPI details are collected by Gravity.';
      return;
    }
    if (!plans.length) {
      wrap.hidden = true;
      status.textContent = 'No verified active membership plan is available for online payment.';
      return;
    }
    status.textContent = 'Amounts below come from Gravity’s active server plan catalog.';
    const select = document.createElement('select');
    select.setAttribute('aria-label', 'Membership plan');
    for (const plan of plans) {
      const option = document.createElement('option');
      option.value = plan.id;
      option.textContent = `${plan.name} · ${money(plan.pricePaise, plan.currency)}`;
      select.appendChild(option);
    }
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-primary';
    button.textContent = 'Pay securely with Razorpay';
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        await startCheckout(select.value);
      } catch (_) {
        status.textContent = 'Secure checkout is temporarily unavailable. No payment success was assumed.';
      } finally {
        button.disabled = false;
      }
    });
    wrap.append(select, button);
    wrap.hidden = false;
  }

  async function refresh() {
    createPanel();
    const [config, plans, payments, invoices] = await Promise.all([
      api('/api/payment/config'),
      api('/api/membership/plans'),
      api('/api/me/payments?limit=25'),
      api('/api/me/invoices?limit=25'),
    ]);
    renderCheckout(config, plans.plans || []);
    renderHistory(payments.payments || [], invoices.invoices || []);
  }

  let active = false;
  async function sync() {
    const visible = !signedIn.hidden;
    if (!visible || active) return;
    active = true;
    try {
      await refresh();
    } catch (error) {
      if (error.status === 401) {
        active = false;
        return;
      }
      createPanel();
      document.getElementById('payment-status').textContent =
        'Payment history is temporarily unavailable. No payment state was changed.';
    }
  }

  const observer = new MutationObserver(() => { void sync(); });
  observer.observe(signedIn, { attributes: true, attributeFilter: ['hidden'] });
  void sync();
})();
