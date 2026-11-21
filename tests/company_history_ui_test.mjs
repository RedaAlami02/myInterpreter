import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
const source = await readFile(new URL('../assets/js/company_history.js', import.meta.url), 'utf8');
async function scenario(responses) {
  const listeners = {};
  const elements = Object.fromEntries(['companyHistory', 'companyHistoryStatus', 'companyHistoryRetry',
    'companyHistoryChart', 'sliderStart', 'sliderEnd', 'sparkHoverVal', 'sparklineChart'].map(id => [id, {
    hidden: true, value: 0, textContent: '', addEventListener(type, callback) { listeners[id + type] = callback; },
    getContext() { return {}; }
  }]));
  elements.companyHistory.dataset = {name: 'Alpha', url: '/handlers/company_history.php?name=Alpha', buyMarkers: '[]'};
  let calls = 0, frame, rendered = 0;
  const context = {document: {getElementById: id => elements[id], querySelectorAll: () => []}, window: {},
    AbortController, setTimeout, clearTimeout, requestAnimationFrame(callback) { frame = callback; },
    fetch: async (url, options) => {
      assert.equal(url, elements.companyHistory.dataset.url);
      assert.equal(options.credentials, 'same-origin');
      const response = responses[Math.min(calls++, responses.length - 1)];
      return {ok: response.ok, json: async () => response.body};
    }, Chart: function(_context, options) { this.data = options.data; rendered++; }
  };
  vm.runInNewContext(source, context);
  assert.equal(calls, 0, 'History must wait for the initial page frame');
  frame();
  await new Promise(resolve => setTimeout(resolve, 20));
  return {elements, listeners, calls: () => calls, rendered: () => rendered};
}
const good = {ok: true, body: {contract: 'company-daily-history/v1', company: 'Alpha',
  points: [{day:'2026-11-16',price:10},{day:'2026-11-17',price:11}]}};
const successful = await scenario([good]);
assert.equal(successful.rendered(), 1);
assert.equal(successful.elements.companyHistoryChart.hidden, false);
assert.equal(successful.elements.companyHistoryStatus.hidden, true);
const failed = await scenario([{ok: false}, good]);
assert.equal(failed.elements.companyHistoryRetry.hidden, false);
await failed.listeners.companyHistoryRetryclick();
assert.equal(failed.rendered(), 1);
assert.equal(failed.calls(), 2);
const empty = await scenario([{ok:true, body:{...good.body, points:[]}}]);
assert.equal(empty.rendered(), 0);
assert.match(empty.elements.companyHistoryStatus.textContent, /insuffisant/);
const wrong = await scenario([{ok:true, body:{...good.body, company:'Other'}}]);
assert.equal(wrong.rendered(), 0);
assert.equal(wrong.elements.companyHistoryRetry.hidden, false);
console.log('PASS deferred history, successful chart, failure/retry, empty and identity checks');
