(() => {
  'use strict';
  const header = document.getElementById('site-header') || document.getElementById('header');
  const menu = document.getElementById('mobile-menu');
  const open = document.getElementById('menu-open');
  const close = document.getElementById('menu-close');
  const setScrolled = () => header?.classList.toggle('is-scrolled', window.scrollY > 12);
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
