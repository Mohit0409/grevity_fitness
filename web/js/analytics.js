// Gravity Fitness public analytics adapter.
// Provider network loading is intentionally disabled until a verified production ID is configured.
(function () {
  'use strict';

  function gTrack(eventName, params = {}) {
    if (typeof window.gtag !== 'function') return;
    window.gtag('event', eventName, {
      ...params,
      page: window.location.pathname,
    });
  }

  function event(name, category, extras = {}) {
    gTrack(name, { event_category: category, ...extras });
  }

  window.gTrack = gTrack;
  window.trackBookingOpen = (type, plan) => event('booking_request_open', 'Booking', { booking_type: type, item_name: plan || type });
  window.trackBookingStep = (step, plan) => event('booking_request_step', 'Booking', { checkout_step: step, item_name: plan || '' });
  window.trackBookingComplete = (method, plan) => event('booking_request_submitted', 'Booking', { request_method: method, item_name: plan || '' });
  window.trackTrialVisitRequest = () => event('trial_visit_request', 'Lead');
  window.trackClassBooking = (name) => event('class_enquiry', 'Lead', { item_name: name || '' });
  window.trackBMICalculator = (bmi) => event('bmi_reference_calculated', 'Engagement', { bmi: Number(bmi) || 0 });
  window.trackWhatsAppClick = (source) => event('whatsapp_click', 'Contact', { source: source || 'unknown' });
  window.trackSectionView = (section) => event('section_view', 'Engagement', { section: section || '' });
  window.trackGoogleAdsConversion = () => {};
  window.trackMetaLead = () => {};
  window.trackMetaPurchase = () => {};

  window.calculateBMI = function calculateBMI() {
    const weight = Number(document.getElementById('bmi-weight')?.value);
    const heightCm = Number(document.getElementById('bmi-height')?.value);
    const result = document.getElementById('bmi-result');
    if (!result) return;

    result.replaceChildren();
    result.style.display = 'block';
    if (!Number.isFinite(weight) || !Number.isFinite(heightCm) || weight <= 0 || heightCm <= 0) {
      const message = document.createElement('p');
      message.textContent = 'Enter a valid weight and height.';
      result.appendChild(message);
      return;
    }

    const heightM = heightCm / 100;
    const bmi = weight / (heightM * heightM);
    if (!Number.isFinite(bmi) || bmi < 5 || bmi > 100) {
      const message = document.createElement('p');
      message.textContent = 'Those values do not produce a reasonable BMI estimate.';
      result.appendChild(message);
      return;
    }
    const value = document.createElement('div');
    value.style.fontSize = '2rem';
    value.style.fontWeight = '900';
    value.style.color = 'var(--lime)';
    value.textContent = bmi.toFixed(1);

    const label = document.createElement('p');
    label.textContent = 'BMI estimate';

    const note = document.createElement('p');
    note.style.color = 'var(--muted)';
    note.textContent = 'General reference only. BMI does not diagnose health, prescribe calories, or select a training or nutrition plan.';

    result.append(value, label, note);
    window.trackBMICalculator(bmi.toFixed(1));
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => gTrack('page_view', { page_title: document.title }), { once: true });
  } else {
    gTrack('page_view', { page_title: document.title });
  }
})();
