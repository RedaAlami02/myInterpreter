/* Workspace theme: preferences only; no account or application data is stored. */
(function () {
  'use strict';
  const root = document.documentElement;
  const key = 'myinterpreter-theme';
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = null;
  try {
    const saved = localStorage.getItem(key);
    if (saved === 'light' || saved === 'dark') preference = saved;
  } catch (_) { /* Storage may be unavailable in private/restricted contexts. */ }

  function apply() {
    const theme = preference || (system.matches ? 'dark' : 'light');
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      button.setAttribute('aria-label', theme === 'dark' ? 'Activer le mode clair' : 'Activer le mode sombre');
      button.setAttribute('aria-pressed', String(theme === 'dark'));
      const label = button.querySelector('[data-theme-label]');
      if (label) label.textContent = theme === 'dark' ? 'Clair' : 'Sombre';
    });
    document.dispatchEvent(new CustomEvent('workspace:theme', { detail: { theme } }));
  }
  apply();
  system.addEventListener('change', () => { if (!preference) apply(); });
  window.addEventListener('storage', event => {
    if (event.key !== key && event.key !== null) return;
    preference = event.newValue === 'light' || event.newValue === 'dark' ? event.newValue : null;
    apply();
  });
  document.addEventListener('click', event => {
    if (!event.target.closest?.('[data-theme-toggle]')) return;
    preference = root.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem(key, preference); } catch (_) { /* Still works in this document. */ }
    apply();
  });

  // Chart.js can be loaded after this boot script. Register after parsing, so
  // existing charts and subsequently created async charts share the same palette.
  document.addEventListener('DOMContentLoaded', () => {
    apply();
    document.querySelectorAll('.nav-item.is-active').forEach(link => link.setAttribute('aria-current', 'page'));
    const Chart = window.Chart;
    if (!Chart?.register) return;
    function styleChart(chart) {
      const styles = getComputedStyle(root);
      const color = name => styles.getPropertyValue(name).trim();
      const options = chart.options;
      options.color = color('--text-dim');
      if (options.plugins?.legend?.labels) {
        options.plugins.legend.labels.color = color('--text-dim');
        options.plugins.legend.labels.font = { ...options.plugins.legend.labels.font, family: color('--font-body') };
      }
      if (options.plugins?.tooltip) {
        Object.assign(options.plugins.tooltip, {
          backgroundColor: color('--surface-1'), titleColor: color('--text'),
          bodyColor: color('--text-dim'), borderColor: color('--border'), borderWidth: 1,
        });
      }
      for (const axis of Object.values(options.scales || {})) {
        if (axis.ticks) {
          axis.ticks.color = color('--text-dim');
          axis.ticks.font = { ...axis.ticks.font, family: color('--font-body') };
        }
        if (axis.grid) axis.grid.color = color('--border');
        if (axis.border) axis.border.color = color('--border');
      }
      if (['chartCurrent', 'chartBuy', 'chartSectors'].includes(chart.canvas.id)) {
        // Categorical allocation colors, not gain/loss indicators.
        const palette = ['#86a8c7', '#a8b4c6', '#8fb9ac', '#d2b789', '#c8a4a4', '#b1a6c6',
          '#8fb8bd', '#bdc494', '#bba88c', '#b89eb4', '#9ab6d2', '#b2c6b8',
          '#cba991', '#9ab5ad', '#c4b4cc', '#a3b7cd', '#c9bb92', '#b8c5cf',
          '#a7b795', '#caa9b4', '#a8c2bd', '#c5bdad', '#b5add0', '#9fbbd0'];
        chart.data.datasets.forEach(dataset => {
          dataset.backgroundColor = dataset.data.map((_, i) => palette[i % palette.length]);
          dataset.borderColor = color('--surface-1');
          dataset.borderWidth = 2;
        });
        if (options.plugins?.datalabels) options.plugins.datalabels.color = '#172533';
      }
    }
    Chart.register({ id: 'workspaceTheme', beforeUpdate: styleChart });
    const refresh = () => Object.values(Chart.instances || {}).forEach(chart => chart.update('none'));
    document.addEventListener('workspace:theme', refresh);
    refresh();
  });
})();
