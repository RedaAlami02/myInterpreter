/* Daily recorded observations load independently of the essential company panels. */
(function () {
  const root = document.getElementById('companyHistory');
  if (!root) return;
  const status = document.getElementById('companyHistoryStatus');
  const retry = document.getElementById('companyHistoryRetry');
  const chart = document.getElementById('companyHistoryChart');
  const translate = text => window.I18n ? window.I18n.t(text) : text;
  let loading = false;
  async function loadHistory() {
    if (loading) return;
    loading = true;
    retry.hidden = true;
    status.hidden = false;
    status.textContent = translate('Chargement de l’historique…');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 25000);
    try {
      const response = await fetch(root.dataset.url, {credentials: 'same-origin', signal: controller.signal});
      if (!response.ok) throw new Error('Unavailable');
      const document = await response.json();
      if (document.contract !== 'company-daily-history/v1' || document.company !== root.dataset.name
          || !Array.isArray(document.points) || document.points.length > 10000) throw new Error('Invalid history');
      let previous = '';
      for (const point of document.points) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(point.day) || point.day <= previous
            || typeof point.price !== 'number' || !Number.isFinite(point.price) || point.price < 0) throw new Error('Invalid point');
        previous = point.day;
      }
      if (document.points.length < 2) {
        status.textContent = translate('Historique insuffisant pour afficher le graphique.');
        return;
      }
      if (typeof Chart === 'undefined') throw new Error('Chart unavailable');
      chart.hidden = false;
      renderHistory(document.points);
      status.hidden = true;
    } catch (error) {
      chart.hidden = true;
      status.textContent = translate('Historique indisponible pour le moment.');
      retry.hidden = false;
    } finally {
      clearTimeout(timeout);
      loading = false;
    }
  }
  function renderHistory(points) {
    var fullLabels = points.map(point => point.day);
    var fullData = points.map(point => point.price);
    var buyMarkers = JSON.parse(root.dataset.buyMarkers || '[]');
  var currentSlice = fullLabels.map((d, i) => ({ d, v: fullData[i] }));
  var sliderStart  = document.getElementById('sliderStart');
  var sliderEnd    = document.getElementById('sliderEnd');
  var hoverVal     = document.getElementById('sparkHoverVal');

  // ── period filter ─────────────────────────────────────────
  var periodDays = { '5A': 5*365, '1A': 365, '6M': 182, '3M': 91, '1M': 30 };

  function dateStr(daysAgo) {
    var d = new Date(); d.setDate(d.getDate() - daysAgo);
    return d.toISOString().slice(0, 10);
  }

  function setPeriod(period) {
    var cutoff = dateStr(periodDays[period]);
    var filtered = fullLabels.map((d, i) => ({ d, v: fullData[i] })).filter(p => p.d >= cutoff);
    currentSlice = filtered.length >= 2 ? filtered : fullLabels.map((d, i) => ({ d, v: fullData[i] }));
    sliderStart.value = 0; sliderEnd.value = 100;
    renderChart(currentSlice);
  }

  document.querySelectorAll('.spark-period-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      document.querySelectorAll('.spark-period-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      setPeriod(btn.dataset.period);
    });
  });

  // ── sliders ───────────────────────────────────────────────
  function slicedData() {
    var s = parseInt(sliderStart.value), e = parseInt(sliderEnd.value);
    if (s > e - 2) { s = Math.max(0, e - 2); sliderStart.value = s; }
    var n = currentSlice.length;
    var from = Math.floor(s / 100 * (n - 1));
    var to   = Math.ceil(e  / 100 * (n - 1));
    return currentSlice.slice(from, to + 1);
  }

  [sliderStart, sliderEnd].forEach(function(sl) {
    sl.addEventListener('input', function() { renderChart(slicedData()); });
  });

  // ── crosshair plugin ──────────────────────────────────────
  // Snap to the active tooltip data point x so it's always aligned.
  var crosshairPlugin = {
    id: 'crosshair',
    afterDraw: function(chart) {
      var active = chart.tooltip && chart.tooltip._active;
      if (!active || !active.length) return;
      var x = active[0].element.x;
      var c = chart.ctx, ca = chart.chartArea;
      c.save();
      c.strokeStyle = 'rgba(148,163,184,0.5)';
      c.lineWidth = 1;
      c.setLineDash([4, 4]);
      c.beginPath(); c.moveTo(x, ca.top); c.lineTo(x, ca.bottom); c.stroke();
      c.restore();
    },
    afterEvent: function(chart, args) {
      if (args.event.type === 'mouseout') {
        hoverVal.textContent = '';
        chart.draw();
      }
    }
  };

  // ── buy-pin plugin ────────────────────────────────────────
  var buyPinPlugin = {
    id: 'buyPin',
    afterDraw: function(chart) {
      if (!buyMarkers.length) return;
      var c = chart.ctx, ca = chart.chartArea, scales = chart.scales;
      var chartLabels = chart.data.labels;
      buyMarkers.forEach(function(marker) {
        var idx = chartLabels.indexOf(marker.date);
        if (idx === -1) return;
        var x = scales.x.getPixelForValue(idx);
        c.save();
        c.setLineDash([4, 3]);
        c.strokeStyle = 'rgba(6,182,212,0.65)'; c.lineWidth = 1.5;
        c.beginPath(); c.moveTo(x, ca.top); c.lineTo(x, ca.bottom); c.stroke();
        c.setLineDash([]);
        c.fillStyle = '#06b6d4';
        c.beginPath(); c.moveTo(x, ca.top+3); c.lineTo(x-5, ca.top-6); c.lineTo(x+5, ca.top-6); c.closePath(); c.fill();
        c.fillStyle = '#06b6d4'; c.font = 'bold 9px sans-serif'; c.textAlign = 'center';
        c.fillText('Achat', x, ca.top - 9);
        c.restore();
      });
    }
  };

  // ── chart instance ────────────────────────────────────────
  var chartInst = null;

  function renderChart(slice) {
    var lbls = slice.map(p => p.d);
    var vals = slice.map(p => p.v);
    var first = vals[0], last = vals[vals.length - 1];
    var color = last >= first ? '#10b981' : '#f43f5e';
    var gradColor = last >= first ? 'rgba(16,185,129,' : 'rgba(244,63,94,';

    if (chartInst) {
      chartInst.data.labels = lbls;
      chartInst.data.datasets[0].data = vals;
      chartInst.data.datasets[0].borderColor = color;
      chartInst.data.datasets[0].pointBackgroundColor = color;
      chartInst.data.datasets[0].pointRadius = vals.length < 25 ? 4 : 0;
      chartInst.data.datasets[0].backgroundColor = function(ctx) {
        var g = ctx.chart.ctx.createLinearGradient(0, 0, 0, ctx.chart.height);
        g.addColorStop(0, gradColor + '0.18)');
        g.addColorStop(1, 'rgba(0,0,0,0)');
        return g;
      };
      chartInst.update('none');
      return;
    }

    var ctxEl = document.getElementById('sparklineChart').getContext('2d');
    chartInst = new Chart(ctxEl, {
      type: 'line',
      plugins: [crosshairPlugin, buyPinPlugin],
      data: {
        labels: lbls,
        datasets: [{
          data: vals,
          borderColor: color,
          borderWidth: 2,
          pointRadius: vals.length < 25 ? 4 : 0,
          pointHoverRadius: 5,
          pointBackgroundColor: color,
          fill: true,
          backgroundColor: function(ctx) {
            var g = ctx.chart.ctx.createLinearGradient(0, 0, 0, ctx.chart.height);
            g.addColorStop(0, gradColor + '0.18)');
            g.addColorStop(1, 'rgba(0,0,0,0)');
            return g;
          },
          tension: 0.35,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            enabled: true,
            backgroundColor: 'rgba(15,23,42,0.92)',
            titleColor: '#94a3b8',
            bodyColor: '#f1f5f9',
            borderColor: 'rgba(148,163,184,0.15)',
            borderWidth: 1,
            padding: 10,
            callbacks: {
              title: function(items) { return items[0].label; },
              label: function(c) {
                hoverVal.textContent = c.raw.toFixed(2) + ' MAD  •  ' + c.label;
                var line = ' PA : ' + c.raw.toFixed(2) + ' MAD';
                var m = buyMarkers.find(b => b.date === lbls[c.dataIndex]);
                if (m) line += '   •   Achat ' + m.quantity + ' × ' + m.price.toFixed(2) + ' MAD';
                return line;
              }
            }
          }
        },
        scales: {
          x: { ticks: { color: '#475569', maxTicksLimit: 8 }, grid: { color: 'rgba(255,255,255,0.04)' } },
          y: { ticks: { color: '#475569' },                   grid: { color: 'rgba(255,255,255,0.04)' } }
        }
      }
    });
  }


    setPeriod('1A');
  }
  retry.addEventListener('click', loadHistory);
  // Yield until the essential page has had a chance to paint.
  requestAnimationFrame(() => setTimeout(loadHistory, 0));
})();
