import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const origin = process.env.LCP_ORIGIN || 'https://myinterpreter.infinityfree.me/';
const allPaths = ['index.php', 'infoAction.php', 'portfolio.php', 'screener.php', 'dividendes.php'];
const allProfiles = [
  { name: 'desktop', width: 1365, height: 768, mobile: false, scale: 1 },
  { name: 'mobile', width: 412, height: 915, mobile: true, scale: 2 },
];
const selectedProfile = process.argv[2];
const profiles = selectedProfile
  ? allProfiles.filter((profile) => profile.name === selectedProfile)
  : allProfiles;
if (profiles.length === 0) throw new Error(`Unknown profile: ${selectedProfile}`);
const selectedPath = process.argv[3];
const paths = selectedPath ? [selectedPath] : allPaths;

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const userDataDir = await mkdtemp(join(tmpdir(), 'myinterpreter-lcp-'));
const chromium = spawn('chromium', [
  '--headless', '--no-sandbox', '--disable-gpu', '--remote-debugging-port=0',
  `--user-data-dir=${userDataDir}`, 'about:blank',
], { stdio: ['ignore', 'pipe', 'pipe'] });

let websocketUrl;
let stderr = '';
chromium.stderr.on('data', (chunk) => {
  stderr += chunk;
  const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
  if (match) websocketUrl = match[1];
});

for (let attempt = 0; attempt < 100 && !websocketUrl; attempt += 1) await delay(100);
if (!websocketUrl) throw new Error(`Chrome did not expose DevTools: ${stderr}`);

const socket = new WebSocket(websocketUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true });
  socket.addEventListener('error', reject, { once: true });
});

let nextId = 1;
const pending = new Map();
socket.addEventListener('message', ({ data }) => {
  const message = JSON.parse(data);
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolve(message.result);
  }
});

function send(method, params = {}, sessionId) {
  const id = nextId++;
  socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

const target = await send('Target.createTarget', { url: 'about:blank' });
const attached = await send('Target.attachToTarget', { targetId: target.targetId, flatten: true });
const sessionId = attached.sessionId;
await send('Page.enable', {}, sessionId);
await send('Runtime.enable', {}, sessionId);
await send('Network.enable', {}, sessionId);

const observer = `
  (() => {
    window.__lcpAudit = { value: 0, selector: null, url: null };
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const element = entry.element;
        window.__lcpAudit = {
          value: entry.startTime,
          selector: element ? [element.tagName, element.id ? '#' + element.id : '', element.className ? '.' + String(element.className).trim().split(/\\s+/).slice(0, 2).join('.') : ''].join('') : null,
          url: entry.url || null,
        };
      }
    }).observe({ type: 'largest-contentful-paint', buffered: true });
  })();
`;
await send('Page.addScriptToEvaluateOnNewDocument', { source: observer }, sessionId);

const results = [];
for (const profile of profiles) {
  await send('Emulation.setDeviceMetricsOverride', {
    width: profile.width, height: profile.height, deviceScaleFactor: profile.scale, mobile: profile.mobile,
  }, sessionId);
  await send('Network.setUserAgentOverride', {
    userAgent: profile.mobile
      ? 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/131 Mobile Safari/537.36'
      : 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36',
  }, sessionId);
  for (const path of paths) {
    await send('Page.navigate', { url: new URL(path, origin).href }, sessionId);
    await delay(10000);
    const evaluation = await send('Runtime.evaluate', {
      expression: `JSON.stringify({ title: document.title, finalUrl: location.href, ready: document.readyState, ttfb: performance.getEntriesByType('navigation')[0]?.responseStart, resources: performance.getEntriesByType('resource').filter(r => ['link', 'css', 'script'].includes(r.initiatorType)).map(r => ({name:r.name, end:r.responseEnd})), lcp: window.__lcpAudit, timing: performance.getEntriesByType('navigation')[0]?.duration ?? null })`,
      returnByValue: true,
    }, sessionId);
    results.push({ profile: profile.name, path, ...JSON.parse(evaluation.result.value) });
  }
}

console.log(JSON.stringify(results, null, 2));
socket.close();
chromium.kill('SIGTERM');
await rm(userDataDir, { recursive: true, force: true });
