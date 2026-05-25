/* ── Auto-inject CSRF token into all fetch() calls ──────── */
(function () {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (!meta) return;
  const token = meta.content;
  const origFetch = window.fetch;
  window.fetch = function (url, opts = {}) {
    opts.headers = Object.assign({ 'X-CSRF-Token': token }, opts.headers);
    return origFetch(url, opts);
  };
})();

/* ── Toast notifications ─────────────────────────────────── */
const Toast = (() => {
  let stack = null;

  function getStack() {
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'toast-stack';
      document.body.appendChild(stack);
    }
    return stack;
  }

  function show(message, type = 'info', duration = 3500) {
    const colorMap = {
      success: { bg: 'rgba(16,185,129,0.15)', border: 'rgba(16,185,129,0.3)', color: '#10b981', icon: 'fa-check-circle' },
      error:   { bg: 'rgba(244,63,94,0.15)',  border: 'rgba(244,63,94,0.3)',  color: '#f43f5e', icon: 'fa-times-circle' },
      warn:    { bg: 'rgba(245,158,11,0.15)', border: 'rgba(245,158,11,0.3)', color: '#f59e0b', icon: 'fa-exclamation-triangle' },
      info:    { bg: 'rgba(34,211,238,0.12)', border: 'rgba(34,211,238,0.3)', color: '#22d3ee', icon: 'fa-info-circle' },
    };
    const c = colorMap[type] || colorMap.info;
    const el = document.createElement('div');
    el.className = 'toast';
    el.style.cssText = `background:${c.bg};border:1px solid ${c.border};color:${c.color}`;
    el.innerHTML = `<i class="fas ${c.icon}"></i><span>${message}</span>`;
    getStack().appendChild(el);

    setTimeout(() => {
      el.classList.add('removing');
      el.addEventListener('animationend', () => el.remove(), { once: true });
    }, duration);
  }

  return { show };
})();

/* ── Confirm modal helper ────────────────────────────────── */
function confirmAction(message, onConfirm) {
  // Reuse Bootstrap modal if present, else simple confirm()
  const modal = document.getElementById('confirmModal');
  if (modal) {
    document.getElementById('confirmModalBody').textContent = message;
    const btn = document.getElementById('confirmModalOk');
    const clone = btn.cloneNode(true);
    btn.parentNode.replaceChild(clone, btn);
    clone.addEventListener('click', () => {
      bootstrap.Modal.getInstance(modal).hide();
      onConfirm();
    });
    new bootstrap.Modal(modal).show();
  } else {
    if (confirm(message)) onConfirm();
  }
}

/* ── Animate elements on scroll ─────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  // Stagger children of .stagger-children
  document.querySelectorAll('.stagger-children').forEach(parent => {
    Array.from(parent.children).forEach((child, i) => {
      child.style.animationDelay = `${i * 80}ms`;
      child.classList.add('animate-up');
    });
  });

  // Loading spinner on form submit.
  // IMPORTANT: we must NOT set btn.disabled = true — disabled controls are excluded
  // from POST data by the HTML spec, so the button's name would never reach PHP.
  // Instead we add a CSS class that blocks further clicks visually.
  document.querySelectorAll('form[data-loading]').forEach(form => {
    form.addEventListener('submit', () => {
      const btn = form.querySelector('[type=submit]');
      if (btn) {
        btn.classList.add('btn-loading');
        btn.setAttribute('aria-disabled', 'true');
        const label = btn.dataset.loadingText || 'Chargement…';
        btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>' + label;
      }
    });
  });
});

/* ── Page loading overlay ────────────────────────────────── */
(function () {
  const overlay = document.createElement('div');
  overlay.className = 'page-overlay';
  overlay.innerHTML = '<div class="page-overlay__ring"></div>';
  document.body.appendChild(overlay);

  function show() { overlay.classList.add('visible'); }
  function hide() { overlay.classList.remove('visible'); }

  // Hide once everything (images, fonts, scripts) is fully loaded
  window.addEventListener('load', hide);

  // Safety: hide after 8s regardless, so a stalled resource never locks the page
  setTimeout(hide, 8000);

  document.addEventListener('DOMContentLoaded', function () {
    // Show overlay on any internal link click
    document.addEventListener('click', function (e) {
      const a = e.target.closest('a[href]');
      if (!a) return;
      const href = a.getAttribute('href') || '';
      if (
        href.startsWith('#') ||
        a.target === '_blank' ||
        a.hasAttribute('download') ||
        a.hasAttribute('data-no-overlay') ||
        href.startsWith('mailto:') ||
        href.startsWith('tel:')
      ) return;
      show();
    });

    // Show overlay on any form submit
    document.addEventListener('submit', function (e) {
      if (!e.target.hasAttribute('data-no-overlay')) show();
    });
  });
})();

/* ── Number formatter ────────────────────────────────────── */
function fmtNum(n, dec = 2) {
  return Number(n).toLocaleString('fr-MA', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
