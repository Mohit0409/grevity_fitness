(() => {
  'use strict';
  const header = document.getElementById('site-header') || document.getElementById('header');
  const menu = document.getElementById('mobile-menu');
  const open = document.getElementById('menu-open');
  const close = document.getElementById('menu-close');
  const focusableSelector = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  const menuFocusables = () => Array.from(menu?.querySelectorAll(focusableSelector) || [])
    .filter((node) => node.getClientRects().length > 0);  const setScrolled = () => header?.classList.toggle('is-scrolled', window.scrollY > 12);
  function closeMenu() {
    if (!menu?.open) return;
    menu.close();
    document.body.classList.remove('modal-open');
    document.documentElement.classList.remove('modal-open');
    open?.setAttribute('aria-expanded', 'false');
    open?.focus();
  }
  open?.addEventListener('click', () => {
    if (!menu || menu.open) return;
    menu.showModal();
    document.body.classList.add('modal-open');
    document.documentElement.classList.add('modal-open');
    open.setAttribute('aria-expanded', 'true');
    menu.querySelector('a')?.focus();
  });
  close?.addEventListener('click', closeMenu);
  menu?.addEventListener('cancel', (event) => {
    event.preventDefault();
    closeMenu();
  });
  menu?.addEventListener('keydown', (event) => {
    if (event.key !== 'Tab' || !menu.open) return;
    const focusable = menuFocusables();
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!menu.contains(document.activeElement)) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
  menu?.addEventListener('close', () => {
    document.body.classList.remove('modal-open');
    document.documentElement.classList.remove('modal-open');
    open?.setAttribute('aria-expanded', 'false');
  });
  menu?.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
    if (menu.open) menu.close();
  }));
  menu?.addEventListener('click', (event) => { if (event.target === menu) closeMenu(); });
  window.addEventListener('scroll', setScrolled, { passive: true });
  setScrolled();
})();
