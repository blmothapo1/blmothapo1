/*
 * Lux Layer – SEI additive lighting utilities
 * Non-destructive: only enhances when classes/attributes are present
 */

(() => {
  // Non-destructive: only enhance when classes/attr are present
  const root = document.documentElement;

  // Cursor spotlight (enabled where .lux-spotlight exists)
  let hasSpotlight = !!document.querySelector('.lux-spotlight');
  if (hasSpotlight) {
    const setPos = (x, y) => {
      root.style.setProperty('--lux-x', `${x}px`);
      root.style.setProperty('--lux-y', `${y}px`);
    };
    window.addEventListener('pointermove', (e) => setPos(e.clientX, e.clientY), { passive: true });
    // center on load
    setPos(window.innerWidth * 0.5, window.innerHeight * 0.4);
  }

  // Light sweep trigger: add .is-in when visible
  const sweeps = document.querySelectorAll('.lux-sweep');
  if (sweeps.length) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) en.target.classList.add('is-in');
      });
    }, { threshold: 0.25 });
    sweeps.forEach(el => io.observe(el));
  }
})();
