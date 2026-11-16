/* HTML chart legends: keyboard/touch controls and explanations without canvas crowding. */
(function () {
  'use strict';
  const tr = (text, values) => window.I18n ? window.I18n.t(text, values) : text;
  const explanations = {
    RNPG: tr('Résultat net part du groupe : le bénéfice (ou la perte) qui revient aux actionnaires du groupe, après les charges et les impôts.'),
    CA: tr('Chiffre d’affaires : le total des ventes de l’entreprise, avant de déduire ses dépenses. Ce n’est pas son bénéfice.'),
    EBE: tr('Excédent brut d’exploitation : ce que l’activité dégage après ses dépenses courantes, avant notamment les amortissements, les intérêts et les impôts.')
  };
  function legendPlugin(id, financial) {
    return {
      id,
      afterUpdate(chart) {
        let legend = chart.$workspaceLegend;
        if (!legend) {
          legend = document.createElement('div');
          legend.className = 'workspace-chart-legend';
          legend.setAttribute('role', 'group');
          legend.setAttribute('aria-label', financial ? tr('Indicateurs financiers') : tr('Répartition du portefeuille'));
          chart.canvas.parentElement.after(legend);
          chart.$workspaceLegend = legend;
        }
        const focused = legend.contains(document.activeElement) ? document.activeElement.dataset.index : null;
        legend.replaceChildren();
        const items = chart.options.plugins.legend.labels.generateLabels(chart);
        for (const item of items) {
          const button = document.createElement('button');
          button.type = 'button';
          const index = financial ? item.datasetIndex : item.index;
          button.dataset.index = index;
          button.setAttribute('aria-pressed', String(!item.hidden));
          const swatch = document.createElement('span');
          swatch.className = 'chart-legend-swatch';
          swatch.style.backgroundColor = item.fillStyle;
          swatch.setAttribute('aria-hidden', 'true');
          const label = document.createElement('span');
          label.textContent = item.text;
          button.append(swatch, label);
          if (financial && explanations[item.text]) {
            const tip = document.createElement('span');
            tip.className = 'chart-legend-help';
            tip.id = chart.canvas.id + '-help-' + index;
            tip.setAttribute('role', 'tooltip');
            tip.textContent = explanations[item.text];
            button.setAttribute('aria-describedby', tip.id);
            button.append(tip);
          } else if (!financial) {
            const values = chart.data.datasets[0].data;
            const total = values.reduce((a, b) => a + Number(b), 0);
            const value = document.createElement('span');
            value.className = 'chart-legend-value';
            value.textContent = total > 0 ? (Number(values[index]) / total * 100).toFixed(1) + '%' : '0%';
            button.append(value);
          }
          button.addEventListener('click', () => {
            if (financial) chart.setDatasetVisibility(index, !chart.isDatasetVisible(index));
            else chart.toggleDataVisibility(index);
            chart.update();
            chart.$workspaceLegend.querySelector('[data-index="' + index + '"]')?.focus({preventScroll: true});
          });
          legend.append(button);
        }
        if (focused !== null) legend.querySelector('[data-index="' + focused + '"]')?.focus({preventScroll: true});
      },
      afterDestroy(chart) { chart.$workspaceLegend?.remove(); }
    };
  }
  window.WorkspaceCharts = {
    financialLegend: legendPlugin('workspaceFinancialLegend', true),
    allocationLegend: legendPlugin('workspaceAllocationLegend', false)
  };
})();
