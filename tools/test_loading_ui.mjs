// Local-only Chromium regression runner; no account, backend, or remote browser.
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import vm from 'node:vm';

const root = new URL('../', import.meta.url);
const script = await readFile(new URL('assets/js/app.js', root), 'utf8');
const css = await readFile(new URL('assets/css/global.css', root), 'utf8');
const test = await readFile(new URL('tests/loading_ui.browser.js', root), 'utf8');
const testLoadingUI = vm.runInNewContext(`${test}\ntestLoadingUI`);
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
  let route;
  const page = {
    route: async (_url, handler) => { route = handler; },
    goto: async () => {
      await route({ fulfill: ({ body }) => { html = body; } });
      await call('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/` });
      for (let i = 0; i < 100; i++) {
        if (await evaluate('document.readyState === "complete" && !!document.querySelector("#next")')) return;
        await delay(20);
      }
      throw new Error('Fixture did not load');
    },
    addStyleTag: async ({ content }) => evaluate(`{ const style = document.createElement('style'); style.textContent = ${JSON.stringify(content)}; document.head.append(style); }`),
    addScriptTag: async ({ content }) => evaluate(content),
    evaluate: async fn => evaluate(`(${fn.toString()})()`),
    setViewportSize: async ({ width, height }) => call('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false }),
    emulateMedia: async ({ reducedMotion }) => call('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: reducedMotion }] }),
    locator: selector => ({ evaluate: fn => evaluate(`(${fn.toString()})(document.querySelector(${JSON.stringify(selector)}))`) }),
  };
  const results = await testLoadingUI(page, script, css);
  console.log(results.map(result => `PASS ${result}`).join('\n'));
  // Synthetic previews only, with the real loading components visible.
  await evaluate(`document.querySelector('.page-loading').hidden = false; document.querySelector('.page-loading__status').textContent = 'Chargement de la page…';`);
  for (const [name, width, height] of [['desktop', 1365, 768], ['mobile', 412, 915]]) {
    await page.setViewportSize({ width, height });
    const { data } = await call('Page.captureScreenshot', { format: 'png' });
    const path = join(tmpdir(), `loading-ui-${name}.png`);
    await writeFile(path, Buffer.from(data, 'base64'));
    console.log(`Preview: ${path}`);
  }
} finally {
  socket?.close();
  if (chromium && chromium.exitCode === null) {
    await new Promise(resolve => { chromium.once('exit', resolve); chromium.kill('SIGTERM'); });
  }
  await new Promise(resolve => server.close(resolve));
  await rm(profile, { recursive: true, force: true });
}
