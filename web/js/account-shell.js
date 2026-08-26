(function () {
  'use strict';

  const links = Array.from(document.querySelectorAll('[data-account-link]'));
  if (!links.length) return;

  function render(label) {
    links.forEach((link) => {
      const target = link.querySelector('[data-account-label]') || link;
      target.textContent = label;
      link.removeAttribute('aria-busy');
    });
  }

  fetch('/api/auth/session', {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' }
  })
    .then((response) => response.ok ? response.json() : Promise.reject(new Error('session unavailable')))
    .then((session) => {
      if (!session.authenticated) return render('Member login');
      render(session.user && session.user.profileComplete ? 'Account' : 'Complete profile');
    })
    .catch(() => render('Member login'));
})();
