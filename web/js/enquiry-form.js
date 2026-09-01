(() => {
  'use strict';
  const dialog = document.getElementById('request-dialog');
  const form = document.getElementById('enquiry-form');
  if (!dialog || !form) return;
  const type = document.getElementById('enquiry-type');
  const planWrap = document.getElementById('enquiry-plan-wrap');
  const plan = document.getElementById('enquiry-plan');
  const date = document.getElementById('enquiry-date');
  const time = document.getElementById('enquiry-time');
  const alert = document.getElementById('enquiry-alert');
  const success = document.getElementById('enquiry-success');
  const submit = form.querySelector('[type="submit"]');
  const reference = document.getElementById('enquiry-reference');
  const whatsapp = document.getElementById('enquiry-whatsapp');
  let csrfToken = '';
  let idempotencyKey = '';
  let opener = null;
  function isoDate(value) {
    const local = new Date(value.getTime() - value.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 10);
  }
  function setDateBounds() {
    const today = new Date();
    const maximum = new Date(today);
    maximum.setDate(maximum.getDate() + 90);
    date.min = isoDate(today);
    date.max = isoDate(maximum);
  }
  function clearErrors() {
    alert.hidden = true;
    alert.textContent = '';
    form.querySelectorAll('[aria-invalid="true"]').forEach((field) => field.removeAttribute('aria-invalid'));
    form.querySelectorAll('.field-error').forEach((node) => { node.textContent = ''; });
  }
  function showErrors(fields, message = 'Check the highlighted fields and try again.') {
    clearErrors();
    for (const [name, copy] of Object.entries(fields || {})) {
      const error = form.querySelector(`[data-error-for="${CSS.escape(name)}"]`);
      const field = form.elements.namedItem(name);
      if (error) error.textContent = String(copy);
      if (field instanceof HTMLElement) field.setAttribute('aria-invalid', 'true');
    }
    alert.textContent = message;
    alert.hidden = false;
    alert.focus();
  }
  function updateConditionalFields() {
    const membership = type.value === 'membership';
    const visit = type.value === 'trial_visit';
    planWrap.hidden = !membership;
    plan.required = membership;
    date.required = visit;
    time.required = visit;
  }
  function idempotency() {
    if (!idempotencyKey) idempotencyKey = typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID() : `${Date.now()}-${crypto.getRandomValues(new Uint32Array(2)).join('-')}`;
    return idempotencyKey;
  }
  async function loadToken() {
    const response = await fetch('/api/enquiries/token', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.csrfToken) throw new Error('request_service_unavailable');
    csrfToken = payload.csrfToken;
  }
  function populatePlans(plans) {
    const selected = plan.value;
    plan.replaceChildren(new Option('Choose a plan', ''));
    for (const item of plans) {
      const price = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(item.pricePaise) / 100);
      const duration = Number(item.durationMonths);
      plan.add(new Option(`${item.name} — ${price} / ${duration} month${duration === 1 ? '' : 's'}`, item.id));
    }
    if ([...plan.options].some((option) => option.value === selected)) plan.value = selected;
  }
  async function openDialog(kind = 'trial_visit', planId = '') {
    opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (document.getElementById('mobile-menu')?.open) document.getElementById('mobile-menu').close();
    form.hidden = false;
    success.hidden = true;
    clearErrors();
    type.value = ['trial_visit', 'membership', 'coaching', 'general'].includes(kind) ? kind : 'trial_visit';
    plan.value = planId;
    idempotencyKey = '';
    updateConditionalFields();
    setDateBounds();
    if (!dialog.open) dialog.showModal();
    document.body.classList.add('modal-open');
    document.documentElement.classList.add('modal-open');
    type.focus();
    try { await loadToken(); }
    catch (_) { showErrors({}, 'The request service is temporarily unavailable. You can still call Gravity on +91 79995 26112.'); }
  }
  function closeDialog() { if (dialog.open) dialog.close(); }
  async function submitForm(event) {
    event.preventDefault();
    clearErrors();
    if (!form.reportValidity()) return;
    if (!csrfToken) {
      try { await loadToken(); }
      catch (_) { showErrors({}, 'The request service is temporarily unavailable. Please try again or call Gravity.'); return; }
    }
    submit.disabled = true;
    submit.textContent = 'Sending request…';
    try {
      const response = await fetch('/api/enquiries', {
        method: 'POST', credentials: 'same-origin',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-Enquiry-CSRF-Token': csrfToken, 'Idempotency-Key': idempotency() },
        body: JSON.stringify(Object.fromEntries(new FormData(form).entries())),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 422) { showErrors(result.fields, 'Check the highlighted fields and try again.'); return; }
        if (response.status === 429) { showErrors({}, 'We have received several requests from this contact. Please wait before trying again.'); return; }
        if (response.status === 409) { showErrors({}, 'This form changed after a previous send attempt. Close it and start a new request.'); return; }
        if (response.status === 403) csrfToken = '';
        throw new Error(result.error || `HTTP ${response.status}`);
      }
      const enquiry = result.enquiry || {};
      reference.textContent = enquiry.reference || 'pending';
      whatsapp.href = `https://wa.me/917999526112?text=${encodeURIComponent(`Hello Gravity Fitness, I submitted website request ${enquiry.reference || ''} and would like to follow up.`)}`;
      form.hidden = true;
      success.hidden = false;
      success.focus();
    } catch (_) { showErrors({}, 'We could not confirm that the request was received. Please retry; the same request will not be duplicated.'); }
    finally { submit.disabled = false; submit.textContent = 'Send request'; }
  }
  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-request-kind]');
    if (!trigger) return;
    event.preventDefault();
    void openDialog(trigger.dataset.requestKind, trigger.dataset.planId || '');
  });
  type.addEventListener('change', updateConditionalFields);
  document.getElementById('request-close').addEventListener('click', closeDialog);
  document.getElementById('enquiry-done').addEventListener('click', closeDialog);
  dialog.addEventListener('close', () => { document.body.classList.remove('modal-open'); document.documentElement.classList.remove('modal-open'); opener?.focus(); });
  dialog.addEventListener('click', (event) => { if (event.target === dialog) closeDialog(); });
  form.addEventListener('submit', submitForm);
  window.addEventListener('gravity:plans-ready', (event) => populatePlans(event.detail?.plans || []));
  setDateBounds();
  updateConditionalFields();
  const requested = new URLSearchParams(window.location.search).get('request');
  if (['trial_visit', 'membership', 'coaching', 'general'].includes(requested)) {
    window.setTimeout(() => { void openDialog(requested); }, 0);
  }
})();
