(() => {
  const tip = document.querySelector('.tip');
  document.addEventListener('pointermove', (e) => {
    const el = e.target.closest && e.target.closest('[data-tip]');
    if (!el) { tip.hidden = true; return; }
    tip.textContent = el.dataset.tip;
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    const left = Math.max(8, Math.min(e.clientX + 12, innerWidth - r.width - 8));
    let top = e.clientY - r.height - 12;
    if (top < 8) top = e.clientY + 18;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  });
  document.addEventListener('pointerleave', () => { tip.hidden = true; });
  addEventListener('scroll', () => { tip.hidden = true; }, { passive: true });
  const links = new Map([...document.querySelectorAll('.side a')].map((a) => [a.hash.slice(1), a]));
  const mark = (id) => links.forEach((a, key) => key === id ? a.setAttribute('aria-current', 'true') : a.removeAttribute('aria-current'));
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) mark(e.target.id);
  }, { rootMargin: '-15% 0px -75% 0px' });
  document.querySelectorAll('main > section[id]').forEach((s) => io.observe(s));
})();
