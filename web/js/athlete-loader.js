(function () {
  'use strict';
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (window.matchMedia('(max-width: 768px)').matches) return;

  const load = () => {
    if (document.querySelector('script[data-athlete-animation]')) return;
    const script = document.createElement('script');
    script.src = '/js/athlete-animation.js';
    script.defer = true;
    script.dataset.athleteAnimation = '1';
    document.body.appendChild(script);
  };

  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(load, { timeout: 4000 });
  } else {
    window.setTimeout(load, 2500);
  }
})();
