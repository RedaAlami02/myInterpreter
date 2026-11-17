// Current display only: expiry clears values; refresh requests no trade operation.
(() => {
  document.querySelectorAll('.market-preview').forEach(panel => {
    const cards = [...panel.querySelectorAll('[data-market-card]')];
    let timer;
    function expire() {
      clearTimeout(timer);
      const now = Date.now();
      let next = Infinity;
      cards.forEach(card => {
        const expiry = Date.parse(card.dataset.marketExpiry);
        const capture = Date.parse(card.dataset.marketCaptured);
        if (!Number.isFinite(expiry) || !Number.isFinite(capture)) return;
        if (now < capture || now >= expiry) {
          card.classList.add('is-unavailable');
          card.querySelectorAll('[data-market-value]').forEach(node => { node.textContent = '—'; });
          card.querySelector('[data-market-state]').textContent = card.dataset.marketExpiredLabel;
        } else next = Math.min(next, expiry - now);
      });
      if (Number.isFinite(next)) timer = setTimeout(expire, Math.max(1, next));
    }
    const search = panel.querySelector('[data-market-search]');
    search?.addEventListener('input', () => {
      const query = search.value.toLocaleLowerCase().trim();
      cards.forEach(card => { card.hidden = !card.dataset.marketName.toLocaleLowerCase().includes(query); });
      const empty = panel.querySelector('[data-market-no-results]');
      if (empty) empty.hidden = cards.some(card => !card.hidden);
    });
    panel.querySelector('[data-market-refresh]')?.addEventListener('click', () => location.reload());
    document.addEventListener('visibilitychange', expire);
    window.addEventListener('pageshow', expire);
    expire();
  });
})();
