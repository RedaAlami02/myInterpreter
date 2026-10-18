// Local-only Chromium regression runner; no account, backend, or remote browser.
import { spawn, execFileSync } from 'node:child_process';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { Script } from 'node:vm';

const root = new URL('../', import.meta.url);
const locale = process.env.UI_LOCALE || 'fr';
if(!['fr','ar','ary'].includes(locale)) throw new Error('Invalid fixture locale');
const fixtures = Object.fromEntries(['portfolio', 'index', 'login'].map(name => [name, execFileSync('php', ['tests/render_workspace_fixture.php', name, locale], { cwd: fileURLToPath(root), encoding: 'utf8' })]));
for(const [name, html] of Object.entries(fixtures)) {
  for(const match of html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)) {
    if(!match[1].includes('application/json')) new Script(match[2], {filename:name});
  }
}
// Execute the actual asynchronous company-chart code against invented financial data.
const companySource = await readFile(new URL('infoAction.php', root), 'utf8');
const enrichment = companySource.slice(companySource.indexOf('(async function()'), companySource.indexOf('})();', companySource.indexOf('(async function()')) + 5)
  .replace('<?= json_encode($symbol) ?>', '"DEMO"');
const header = fixtures.portfolio.match(/<header class="sidebar">[\s\S]*?<\/header>/)[0];
fixtures.company = `<!doctype html><html lang="${locale}" dir="${locale==='fr'?'ltr':'rtl'}"><head><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="assets/css/global.css"><link rel="stylesheet" href="assets/css/infoAction.css">
<link rel="stylesheet" href="assets/css/workspace.css"><link rel="stylesheet" href="assets/css/rtl.css">
${fixtures.portfolio.match(/<script id="ui-locale"[\s\S]*?<\/script>/)[0]}<script src="assets/js/i18n.js"></script>
<script src="assets/js/theme.js"></script><script src="assets/js/workspace-charts.js"></script>
</head><body class="workspace">${header}<main class="main"><div id="mkt-enrichment"></div></main>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script><script>${enrichment}</script></body></html>`;
const profile = await mkdtemp(join(tmpdir(), 'loading-ui-'));
let socket, chromium;
const server = createServer(async (req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname;
  const name = path.replace(/^\//, '').replace(/\.php$/, '');
  if(path === '/favicon.svg') { res.setHeader('Content-Type','image/svg+xml'); res.end(await readFile(new URL('favicon.svg',root))); return; }
  if(path === '/handlers/market_proxy.php') {
    res.setHeader('Content-Type','application/json');
    res.end(JSON.stringify({charts:{ca:{2023:100,2024:120,2025:140},rnpg:{2023:12,2024:15,2025:18},ebe:{2023:22,2024:25,2025:28}},trim:{T42023:20,T12024:25,T22024:30,T32024:32,T42024:33,T12025:35},shareholders:[{name:'Groupe démo',pct:60},{name:'Autres investisseurs',pct:40}]})); return;
  }
  if (fixtures[name] && req.method === 'GET') {
    res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.end(fixtures[name]); return;
  }
  const target = resolve(fileURLToPath(root), '.' + path);
  if (path.startsWith('/assets/') && target.startsWith(resolve(fileURLToPath(root), 'assets') + '/') && ['.js', '.css', '.woff2'].includes(extname(target))) {
    try { res.setHeader('Content-Type', extname(target) === '.js' ? 'application/javascript' : extname(target) === '.css' ? 'text/css' : 'font/woff2'); res.end(await readFile(target)); return; } catch {}
  }
  res.statusCode = 404; res.end('Fixture only');
});
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
try {
  await mkdir(new URL('design-review/screenshots/prototypes/', root), {recursive: true});
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
  const errors = [];
  socket.addEventListener('message', ({data}) => {
    const event = JSON.parse(data);
    if (event.method === 'Runtime.exceptionThrown') errors.push(event.params.exceptionDetails.exception?.description || event.params.exceptionDetails.text);
  });
  await call('Runtime.enable');
  const navigate = async name => {
    await call('Page.navigate', {url: `http://127.0.0.1:${server.address().port}/${name}.php`});
    for (let i = 0; i < 300; i++) {
      if (await evaluate('document.readyState === "complete" && !!document.querySelector("[data-theme-toggle]")')) return;
      await delay(100);
    }
    throw new Error('Fixture load timeout');
  };
  await call('Emulation.setEmulatedMedia', {features:[{name:'prefers-color-scheme',value:'light'}]});
  await navigate('portfolio');
  console.log(await evaluate(`(() => {
    const check = (v,m) => {if(!v) throw new Error(m)};
    check(document.documentElement.dataset.theme === 'light', 'System light default');
    check(document.documentElement.lang === '${locale}', 'Root language');
    check(document.documentElement.dir === '${locale==='fr'?'ltr':'rtl'}', 'Root direction');
    check(document.querySelector('[data-language-select]').value === '${locale}', 'Language selector');
    check(document.querySelector('.brand-logo').naturalWidth > 0, 'Existing logo loads');
    check(document.querySelectorAll('#holdingsTbl tbody tr').length === 6, 'Holdings render');
    check(window.Chart && Object.keys(Chart.instances).length >= 3, 'Chart libraries load');
    document.querySelector('[data-theme-toggle]').click();
    check(document.documentElement.dataset.theme === 'dark', 'Toggle dark');
    check(localStorage.getItem('myinterpreter-theme') === 'dark', 'Preference saved');
    switchTab('transactions'); check(document.querySelector('#tab-transactions').classList.contains('active'),'Transactions tab');
    switchTab('history'); check(document.querySelector('#tab-history').classList.contains('active'),'History tab');
    switchTab('portfolio');
    document.querySelector('#showSectors').click();
    check(!document.querySelector('#allocationSectors').inert,'Sector panel');
    document.querySelector('#showValues').click();
    check(document.querySelector('#allocationSectors').inert,'Allocation panel restored');
    const before = Chart.getChart('chartCurrent').data.datasets[0].data.join(',');
    document.querySelector('[data-theme-toggle]').click();
    check(Chart.getChart('chartCurrent').data.datasets[0].data.join(',') === before,'Theme preserves chart data');
    const form = document.querySelector('form[data-loading]');
    const button = form.querySelector('button[type=submit]');
    check(new FormData(form,button).has(button.name),'Submitter retained');
    check(!document.querySelector('[name=save_snapshot]'),'Manual snapshot control removed');
    check(!document.body.textContent.includes('Historique des snapshots'),'Snapshot table removed');
    const allocation = Chart.getChart('chartCurrent');
    check(allocation.chartArea.height >= 230, 'Allocation circle gets enough room');
    check(allocation.$workspaceLegend.querySelectorAll('button').length === 6, 'Allocation HTML legend');
    const smallLabel = allocation.config.options.plugins.datalabels.display({chart:allocation,dataset:{data:[1,99]},dataIndex:0});
    check(!smallLabel, 'Small slices do not crowd labels');
    const host = document.createElement('div');
    host.innerHTML = '<div><canvas id="fixtureFinance"></canvas></div>';
    document.body.append(host);
    const finance = new Chart(host.querySelector('canvas'), {
      type:'bar', plugins:[WorkspaceCharts.financialLegend],
      data:{labels:['2025'],datasets:['RNPG','CA','EBE'].map(label=>({label,data:[10]}))},
      options:{animation:false,plugins:{legend:{display:false}}}
    });
    const buttons = finance.$workspaceLegend.querySelectorAll('button');
    check(buttons.length === 3, 'Financial legend has all indicators');
    for(const button of buttons) {
      button.focus();
      check(getComputedStyle(button.querySelector('[role=tooltip]')).display !== 'none','Definition on keyboard focus');
      check(button.querySelector('[role=tooltip]').textContent.length > 35,'Plain-language definition');
    }
    buttons[0].click();
    check(!finance.isDatasetVisible(0), 'Financial legend still toggles series');
    finance.destroy(); host.remove();
    return 'PASS portfolio: fixture values, charts, tabs, sector controls, theme, form payload';
  })()`));
  for(const reduced of [false,true]) {
    await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:reduced?'reduce':'no-preference'}]});
    await evaluate(`(() => {
      const button = document.querySelector('.col-toggle');
      button.click(); button.click(); button.click();
      if(button.getAttribute('aria-pressed') !== 'true') throw new Error('Rapid column toggle state');
      if(getComputedStyle(document.querySelector('#holdingsTbl .col-frais')).display === 'none') throw new Error('Columns did not open');
      if(${reduced} && document.querySelector('#holdingsTbl').getAnimations({subtree:true}).length) throw new Error('Reduced motion ignored');
      button.click();
      if(button.getAttribute('aria-pressed') !== 'false') throw new Error('Columns did not close');
    })()`);
  }
  await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
  console.log('PASS column transitions, rapid toggles and reduced motion');
  await navigate('index');
  if (await evaluate('document.documentElement.dataset.theme') !== 'light') throw new Error('Preference lost between pages');
  await evaluate("document.querySelector('[data-theme-toggle]').click()");
  await navigate('index');
  if (await evaluate('document.documentElement.dataset.theme') !== 'dark') throw new Error('Preference lost on reload');
  console.log('PASS preference across navigation and reload');
  await evaluate("localStorage.removeItem('myinterpreter-theme')");
  await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:'dark'}]});
  await navigate('login');
  if(await evaluate('document.documentElement.dataset.theme') !== 'dark') throw new Error('System dark default failed');
  const blocked = await call('Page.addScriptToEvaluateOnNewDocument',{source:"Object.defineProperty(window, 'localStorage', {get(){throw new Error('Storage blocked for test')}})"});
  await navigate('login');
  await evaluate("document.querySelector('[data-theme-toggle]').click()");
  if(await evaluate('document.documentElement.dataset.theme') !== 'light') throw new Error('Toggle with storage blocked failed');
  await call('Page.removeScriptToEvaluateOnNewDocument',{identifier:blocked.identifier});
  console.log('PASS system dark preference and blocked-storage fallback');
  for (const name of ['portfolio','index','login','company']) {
    await navigate(name);
    if(name === 'company') {
      for(let i=0;i<100 && !(await evaluate("!!window.Chart?.getChart('holdersChart')"));i++) await delay(100);
      if(!(await evaluate("!!window.Chart?.getChart('holdersChart')"))) throw new Error('Company enrichment did not render');
    }
    for (const theme of ['light','dark']) {
      await evaluate(`if(document.documentElement.dataset.theme !== '${theme}') document.querySelector('[data-theme-toggle]').click()`);
      await evaluate(`(() => {
        const css = getComputedStyle(document.documentElement);
        const luminance = name => {
          const hex = css.getPropertyValue(name).trim().slice(1);
          const rgb = [0,2,4].map(i => parseInt(hex.slice(i,i+2),16)/255).map(v => v <= .04045 ? v/12.92 : ((v+.055)/1.055)**2.4);
          return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
        };
        const background = luminance('--surface-1');
        for(const token of ['--text','--text-dim','--text-mute','--pos','--neg','--accent']) {
          const value = luminance(token);
          const contrast = (Math.max(value,background)+.05)/(Math.min(value,background)+.05);
          if(!Number.isFinite(contrast) || contrast < 4.5) throw new Error(token+' contrast '+contrast);
        }
      })()`);
      for (const [size,width,height] of [['desktop',1365,900],['mobile',412,915],['narrow',320,800],['tablet',768,1024],['laptop',1024,768],['wide',1920,1080],['qhd',2560,1440]]) {
        await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
        await delay(1100); // Let Chart.js resize/entrance animations finish before screenshots.
        if(name === 'portfolio') await evaluate(`(() => {
          for(const id of ['chartCurrent','chartBuy']) {
            const chart = Chart.getChart(id), arcs = chart.getDatasetMeta(0).data;
            if(arcs.some(a => a.outerRadius < 80 || !Number.isFinite(a.x))) throw new Error('Collapsed allocation chart');
            if(Math.abs(arcs.reduce((sum,a)=>sum+a.circumference,0) - Math.PI*2) > .01) throw new Error('Incomplete allocation circle');
          }
          const list = document.querySelector('.sector-list');
          if(list.scrollHeight > list.clientHeight + 1) throw new Error('Sector list clipped');
        })()`);
        if(name === 'company') await evaluate(`(() => {
          for(const id of ['finChart','trimChart']) {
            const canvas = document.getElementById(id), rect = canvas.getBoundingClientRect(), parent = canvas.parentElement.getBoundingClientRect();
            if(Math.abs(rect.width-parent.width)>2 || rect.height<240) throw new Error('Squeezed financial chart: '+id);
            const chart = Chart.getChart(id), bars = chart.getDatasetMeta(0).data;
            if(bars.length > 1 && bars.at(-1).x - bars[0].x < chart.chartArea.width * .4) throw new Error('Financial bars collapsed to one side');
          }
          const donut = document.getElementById('holdersChart').getBoundingClientRect();
          if(Math.abs(donut.width-donut.height)>2 || donut.width<150) throw new Error('Distorted shareholder donut');
          if(Chart.getChart('trimChart').data.labels[0] !== 'Q4 2023') throw new Error('Quarters not chronological');
        })()`);
        const layout = await evaluate(`(() => {
          const rect = document.querySelector('[data-theme-toggle]').getBoundingClientRect();
          return {width:document.documentElement.scrollWidth, viewport:innerWidth, height:document.documentElement.scrollHeight, toggle:rect.right <= innerWidth && rect.left >= 0};
        })()`);
        if(layout.width > layout.viewport || !layout.toggle) throw new Error(`Overflow or clipped theme toggle: ${name}/${theme}/${size} ${JSON.stringify(layout)}`);
        if(size === 'desktop' || size === 'mobile' || size === 'qhd'){
          const {data} = await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width,height:Math.min(layout.height,4000),scale:1}});
          await writeFile(new URL(`design-review/screenshots/prototypes/workspace-live-${name}-${theme}-${size}${locale==='fr'?'':'-'+locale}.png`,root),Buffer.from(data,'base64'));
        }
        console.log(`PASS ${name}/${theme}/${size}`);
      }
    }
  }
  // Optional read-only public route checks. Never navigate to a protected account.
  if (process.env.WORKSPACE_PUBLIC_ORIGIN) {
    const origin = new URL(process.env.WORKSPACE_PUBLIC_ORIGIN);
    if (!['127.0.0.1', 'localhost'].includes(origin.hostname)) throw new Error('Public checks must use a local server');
    for (const name of ['screener', 'infoAction', 'dividendes']) {
      await call('Page.navigate', {url: new URL(name + '.php?lang=' + locale, origin).href});
      for(let i=0;i<300;i++) {
        if(await evaluate('document.readyState === "complete" && !!document.querySelector("[data-theme-toggle]")')) break;
        await delay(100);
      }
      if(name === 'screener') {
        await evaluate(`(() => {
          setPreset(10); setScore(3);
          const rows = [...document.querySelectorAll('#screenerTable tbody tr[data-per]:not(.hidden-row)')];
          if(rows.some(row => !(Number(row.dataset.per) < 10 && Number(row.dataset.score) >= 3))) throw new Error('Screener filters');
          document.querySelector('[data-theme-toggle]').click();
          if(Number(document.getElementById('visibleCount').textContent) !== rows.length) throw new Error('Theme resets filters');
          sortTable(1,'num'); setPreset(22); setScore(0);
        })()`);
      }
      if(name === 'infoAction') {
        await evaluate(`(() => {
          const search = document.getElementById('nameInput');
          search.value = 'zzzz-fixture-no-match'; search.dispatchEvent(new Event('input'));
          if(document.getElementById('directoryEmpty').hidden) throw new Error('Directory search');
          document.querySelector('[data-theme-toggle]').click();
          if(search.value !== 'zzzz-fixture-no-match') throw new Error('Theme resets search');
          document.getElementById('resetDirectoryFilters').click();
          document.getElementById('sectorTrigger').click();
          if(document.getElementById('sectorMenu').hidden) throw new Error('Sector menu');
          document.querySelector('.sector-option').click();
        })()`);
      }
      for(const theme of ['light','dark']) {
        await evaluate(`if(document.documentElement.dataset.theme !== '${theme}') document.querySelector('[data-theme-toggle]').click()`);
        for(const [size,width,height] of [['desktop',1365,900],['mobile',412,915]]) {
          await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
          await delay(250);
          const layout=await evaluate('({width:document.documentElement.scrollWidth,viewport:innerWidth,height:document.documentElement.scrollHeight})');
          if(layout.width>layout.viewport) throw new Error(`Public overflow: ${name}/${theme}/${size}`);
          const {data}=await call('Page.captureScreenshot',{format:'png'});
          await writeFile(new URL(`design-review/screenshots/prototypes/workspace-public-${name}-${theme}-${size}.png`,root),Buffer.from(data,'base64'));
          console.log(`PASS public ${name}/${theme}/${size}`);
        }
      }
    }
  }
  if(errors.length) throw new Error(errors.join('\n'));
  console.log('PASS no uncaught browser exceptions; only synthetic account data rendered');

} finally {
  socket?.close();
  if (chromium && chromium.exitCode === null) {
    await new Promise(resolve => { chromium.once('exit', resolve); chromium.kill('SIGTERM'); });
  }
  await new Promise(resolve => server.close(resolve));
  await rm(profile, { recursive: true, force: true });
}
