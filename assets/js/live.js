/**
 * Background quote refresh for signed-in pages.
 *
 * The page renders first with whatever the server had; this only keeps the
 * numbers it already shows in step with the newest publication. Nothing is
 * fetched while the tab is hidden, the in-flight request is aborted when the
 * page is left, and a failed poll leaves the last good numbers untouched.
 */
(function () {
  var config = document.getElementById('live-config');
  if (!config) return;
  var data;
  try { data = JSON.parse(config.textContent); } catch (e) { return; }
  var quotesMode = data && data.mode === 'quotes';
  if (!data || !data.endpoint || (!quotesMode && !Array.isArray(data.holdings))) return;

  var INTERVAL = data.interval || 60000;
  var lastStamp = data.stamp || null;
  var timer = null;
  var controller = null;
  var failures = 0;

  // Matches number_format() on the server, so an updated number keeps the
  // exact shape of the one it replaces.
  function money(value) {
    return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function setText(node, text) {
    if (node && node.textContent !== text) node.textContent = text;
  }

  function each(selector, fn) {
    var nodes = document.querySelectorAll(selector);
    for (var i = 0; i < nodes.length; i++) fn(nodes[i]);
  }

  function escapeName(name) {
    return (window.CSS && CSS.escape) ? CSS.escape(name) : String(name).replace(/["\\]/g, '\\$&');
  }

  function render(quotes, stamp) {
    var total = 0;
    var complete = true;
    var changed = 0;
    if (quotesMode) {
      // A table of quotes: update the visible number and the sort key together,
      // otherwise sorting would order by a price the reader can no longer see.
      Object.keys(quotes).forEach(function (name) {
        var price = quotes[name];
        if (typeof price !== 'number' || !(price > 0)) return;
        each('[data-live-quote="' + escapeName(name) + '"]', function (node) {
          var text = money(price);
          if (node.textContent.trim() !== text) { changed++; setText(node, text); }
          if (node.hasAttribute('data-val')) node.setAttribute('data-val', price);
          if (node.classList.contains('pa-cell')) {
            node.setAttribute('data-val', price);
          }
        });
      });
      stampNote(stamp, changed);
      return;
    }
    data.holdings.forEach(function (holding) {
      var price = quotes[holding.name];
      if (typeof price !== 'number' || !(price > 0)) { complete = false; return; }
      total += holding.qty * price;
      var name = escapeName(holding.name);
      each('[data-live-price="' + name + '"]', function (node) {
        var text = money(price);
        if (node.textContent !== text) changed++;
        setText(node, text);
      });
      each('[data-live-value="' + name + '"]', function (node) {
        setText(node, money(holding.qty * price));
      });
    });
    if (complete) {
      var invested = data.invested || 0;
      setText(document.querySelector('[data-live-total="value"]'), money(total));
      setText(document.querySelector('[data-live-total="pnl"]'),
        (total - invested >= 0 ? '+' : '') + money(total - invested));
    }
    stampNote(stamp, changed);
  }

  function stampNote(stamp, changed) {
    var when = stamp || lastStamp;
    if (when) {
      var at = new Date(when);
      if (!isNaN(at.getTime())) {
        setText(document.querySelector('[data-live-stamp]'),
          at.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }));
      }
    }
    document.body.classList.toggle('live-updated', changed > 0);
  }

  function schedule(delay) {
    clearTimeout(timer);
    timer = setTimeout(poll, delay);
  }

  function poll() {
    if (document.hidden) { schedule(INTERVAL); return; }
    if (controller) controller.abort();
    controller = ('AbortController' in window) ? new AbortController() : null;
    var options = { credentials: 'same-origin', headers: { Accept: 'application/json' } };
    if (controller) options.signal = controller.signal;
    fetch(data.endpoint, options)
      .then(function (response) {
        if (!response.ok) throw new Error('poll failed');
        return response.json();
      })
      .then(function (payload) {
        failures = 0;
        if (payload && payload.quotes) render(payload.quotes, payload.stamp);
        schedule(INTERVAL);
      })
      .catch(function (error) {
        if (error && error.name === 'AbortError') return;
        failures++;
        // Back off on trouble instead of hammering an unhappy server.
        schedule(Math.min(INTERVAL * Math.pow(2, failures), 600000));
      });
  }

  // Leaving the page must not leave a request running behind the navigation.
  window.addEventListener('pagehide', function () {
    clearTimeout(timer);
    if (controller) controller.abort();
  });
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) schedule(0);
  });

  schedule(INTERVAL);
})();
