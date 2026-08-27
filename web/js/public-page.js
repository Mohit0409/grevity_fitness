(function () {
  'use strict';
  const nav = document.getElementById('mobile-nav');
  const openButton = document.querySelector('.hamburger');
  const closeButton = document.querySelector('.mobile-nav-close');

  function setOpen(open) {
    if (!nav) return;
    nav.classList.toggle('open', open);
    openButton?.setAttribute('aria-expanded', String(open));
    document.body.style.overflow = open ? 'hidden' : '';
    if (open) closeButton?.focus();
  }

  openButton?.addEventListener('click', () => setOpen(true));
  closeButton?.addEventListener('click', () => setOpen(false));
  nav?.querySelectorAll('a').forEach(link => link.addEventListener('click', () => setOpen(false)));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && nav?.classList.contains('open')) {
      setOpen(false);
      openButton?.focus();
    }
  });

  const header = document.getElementById('header');
  window.addEventListener('scroll', () => header?.classList.toggle('scrolled', window.scrollY > 20), { passive: true });
})();
