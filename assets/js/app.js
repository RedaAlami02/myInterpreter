const appText = (text, values) => window.I18n ? window.I18n.t(text, values) : text;
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

});

/* ── Navigation and form feedback ────────────────────────── */
(function () {
  const indicator = document.createElement('div');
  indicator.className = 'page-loading';
  indicator.hidden = true;
  indicator.innerHTML = '<div class="page-loading__track" aria-hidden="true"></div>';
  const status = document.createElement('div');
  status.className = 'page-loading__status';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  status.setAttribute('aria-atomic', 'true');
  document.body.append(indicator, status);
  let timers = [];
  const pendingForms = new Map();

  function reset() {
    timers.forEach(clearTimeout);
    timers = [];
    indicator.hidden = true;
    status.textContent = '';
    for (const [form, state] of pendingForms) {
      if (state.busy === null) form.removeAttribute('aria-busy');
      else form.setAttribute('aria-busy', state.busy);
      if (state.button) {
        state.button.innerHTML = state.html;
        state.button.classList.remove('btn-loading');
        if (state.disabled === null) state.button.removeAttribute('aria-disabled');
        else state.button.setAttribute('aria-disabled', state.disabled);
      }
    }
    pendingForms.clear();
  }

  function show(label) {
    timers.forEach(clearTimeout);
    timers = [
      setTimeout(() => { indicator.hidden = false; status.textContent = label; }, 180),
      setTimeout(() => { status.textContent = appText('Cela prend plus de temps que prévu…'); }, 8000),
      setTimeout(() => {
        const hadForm = pendingForms.size > 0;
        reset();
        status.textContent = hadForm
          ? appText('Réponse tardive. Vérifiez le résultat avant de réessayer.')
          : appText('Chargement prolongé. Vous pouvez choisir une autre page.');
      }, 20000),
    ];
  }

  function sameWindow(target) { return !target || target.toLowerCase() === '_self'; }
  window.addEventListener('pageshow', reset);
  window.addEventListener('pagehide', reset);

  document.addEventListener('click', e => {
    if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest?.('a[href]');
    if (!a || a.hasAttribute('download') || a.hasAttribute('data-no-overlay')) return;
    if (!sameWindow(a.target || document.querySelector('base[target]')?.target)) return;
    const url = new URL(a.href, location.href);
    if (!['http:', 'https:'].includes(url.protocol) || url.origin !== location.origin) return;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
    queueMicrotask(() => { if (!e.defaultPrevented) show(appText('Chargement de la page…')); });
  });

  document.addEventListener('submit', e => {
    const form = e.target;
    if (e.defaultPrevented || form.hasAttribute('data-no-overlay')) return;
    const button = e.submitter;
    const target = button?.getAttribute('formtarget') ?? form.target;
    if (!sameWindow(target || document.querySelector('base[target]')?.target)) return;
    if ((button?.getAttribute('formmethod') || form.method).toLowerCase() === 'dialog') return;
    if (pendingForms.has(form)) { e.preventDefault(); return; }
    queueMicrotask(() => {
      if (e.defaultPrevented) return;
      const state = { busy: form.getAttribute('aria-busy'), button: null };
      if (form.hasAttribute('data-loading') && button) {
        state.button = button;
        state.html = button.innerHTML;
        state.disabled = button.getAttribute('aria-disabled');
        // Keep the actual submitter enabled so its name/value reaches PHP.
        button.classList.add('btn-loading');
        button.setAttribute('aria-disabled', 'true');
        button.textContent = button.dataset.loadingText || appText('Chargement…');
      }
      pendingForms.set(form, state);
      form.setAttribute('aria-busy', 'true');
      show(button?.dataset.loadingText || 'Envoi en cours…');
    });
  });
})();

/* Only this section loads after the document; do not mask server-rendered data. */
(function () {
  const placeholder = document.getElementById('mkt-loading');
  if (!placeholder) return;
  placeholder.removeAttribute('style');
  placeholder.className = 'content-loading';
  placeholder.setAttribute('role', 'status');
  placeholder.setAttribute('aria-live', 'polite');
  placeholder.innerHTML = '<span class="content-loading__label">' + appText('Chargement des données financières…') + '</span>'
    + '<div class="content-loading__preview" aria-hidden="true">'
    + '<span class="skeleton skeleton--heading"></span><span class="skeleton"></span>'
    + '<span class="skeleton skeleton--short"></span>'
    + '<div class="content-loading__cards"><span class="skeleton"></span>'
    + '<span class="skeleton"></span><span class="skeleton"></span></div></div>';
})();

/* ── Number formatter ────────────────────────────────────── */
function fmtNum(n, dec = 2) {
  return Number(n).toLocaleString('fr-MA', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
