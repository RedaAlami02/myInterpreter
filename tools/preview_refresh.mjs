// Local-only Chromium regression runner; no account, backend, or remote browser.
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';

const root = new URL('../', import.meta.url);
const script = await readFile(new URL('design-review/prototypes/refresh/prototype.js', root), 'utf8');
const css = await readFile(new URL('design-review/prototypes/refresh/style.css', root), 'utf8');
const fixture = await readFile(new URL('design-review/prototypes/refresh/index.html', root), 'utf8');
const profile = await mkdtemp(join(tmpdir(), 'loading-ui-'));
let html = '', socket, chromium;
const server = createServer((_req, res) => { res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.end(html); });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
try {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  chromium = spawn('chromium', ['--headless', '--no-sandbox', '--disable-gpu', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank']);
  let ws, stderr = '';
  chromium.stderr.on('data', chunk => { stderr += chunk; ws = stderr.match(/DevTools listening on (ws:\/\/\S+)/)?.[1]; });
  for (let i = 0; i < 100 && !ws; i++) await delay(100);
  if (!ws) throw new Error(`Chromium did not start: ${stderr}`);
  socket = new WebSocket(ws);
  await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }); });
  let id = 0;
  const pending = new Map();
  socket.addEventListener('message', ({ data }) => {
    const message = JSON.parse(data);
    if (!pending.has(message.id)) return;
    const { resolve, reject, timeout } = pending.get(message.id);
    pending.delete(message.id); clearTimeout(timeout);
    if (message.error) reject(new Error(message.error.message)); else resolve(message.result);
  });
  const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const key = ++id;
    const timeout = setTimeout(() => { pending.delete(key); reject(new Error(`Timed out: ${method}`)); }, 15000);
    pending.set(key, { resolve, reject, timeout });
    socket.send(JSON.stringify({ id: key, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const call = (method, params) => send(method, params, sessionId);
  await call('Page.enable');
  const evaluate = async expression => {
    const result = await call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  };
  html = fixture.replace('<link rel="stylesheet" href="style.css">', '<style>' + css + '</style>').replace('<script src="prototype.js" defer></script>', '').replace('</body>', '<script>' + script + '</script></body>');
  await call('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/` });
  for (let i = 0; i < 100; i++) {
    if (await evaluate('document.readyState === "complete" && document.querySelectorAll("#positions tr").length === 6')) break;
    await delay(30);
  }
  const checks = await evaluate(`(() => {
    const check = (value, message) => { if (!value) throw new Error(message); };
    check(document.querySelectorAll('#positions tr').length === 6, 'Six rows');
    const search = document.querySelector('#search');
    search.value = 'Noria'; search.dispatchEvent(new Event('input'));
    check(document.querySelectorAll('#positions tr').length === 1, 'Filter');
    search.value = 'absent'; search.dispatchEvent(new Event('input'));
    check(!document.querySelector('#empty').hidden, 'Empty state');
    search.value = ''; search.dispatchEvent(new Event('input'));
    document.querySelector('[data-sort=name]').click();
    check(document.querySelector('.company-name').textContent === 'Atlas Industrie', 'Name sort');
    document.querySelector('[data-sort=value]').click(); document.querySelector('[data-sort=value]').click();
    const before = document.querySelector('#chart-line').getAttribute('d');
    document.querySelector('[data-period="1A"]').click();
    check(before !== document.querySelector('#chart-line').getAttribute('d'), 'Period changes chart');
    document.querySelector('[data-period="3M"]').click();
    document.querySelector('button[data-view=overview]').click();
    check(document.querySelector('h1').textContent.includes('Vue'), 'Overview navigation');
    document.querySelector('button[data-view=portfolio]').click();
    return 'PASS: rows, filtering, empty state, sorting, chart periods, view navigation';
  })()`);
  console.log(checks);
  for (const direction of ['ledger', 'workspace']) {
    for (const theme of ['light', 'dark']) {
      await evaluate(`document.querySelector('button[data-direction="${direction}"]').click(); if (document.documentElement.dataset.theme !== '${theme}') document.querySelector('#theme').click();`);
      for (const [name, width, height] of [['desktop', 1365, 900], ['mobile', 412, 915]]) {
        await call('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
        await delay(80);
        const layout = await evaluate('({width:document.documentElement.scrollWidth, viewport:innerWidth, height:document.documentElement.scrollHeight})');
        if (layout.width > layout.viewport) throw new Error(`Overflow: ${direction}/${theme}/${name}`);
        const { data } = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: 0, width, height: layout.height, scale: 1 } });
        const path = new URL(`design-review/screenshots/prototypes/refresh-${direction}-${theme}-${name}.png`, root);
        await writeFile(path, Buffer.from(data, 'base64'));
        console.log(`PASS ${direction}/${theme}/${name}: no document overflow; screenshot saved`);
      }
    }
  }

} finally {
  socket?.close();
  if (chromium && chromium.exitCode === null) {
    await new Promise(resolve => { chromium.once('exit', resolve); chromium.kill('SIGTERM'); });
  }
  await new Promise(resolve => server.close(resolve));
  await rm(profile, { recursive: true, force: true });
}
