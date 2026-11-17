// Actual PHP templates and browser behavior, with CLI-only invented market data.
import {spawn, execFileSync} from 'node:child_process';
import {readFile, writeFile, mkdir, mkdtemp, rm} from 'node:fs/promises';
import {createServer} from 'node:http';
import {join, resolve, extname} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';

const root=fileURLToPath(new URL('../',import.meta.url));
const output=join(root,'private/market-screens-20261030');await mkdir(output,{recursive:true});
const profile=await mkdtemp(join(tmpdir(),'market-preview-'));
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const locale=process.env.UI_LOCALE||'fr';
const theme=process.env.UI_THEME||'dark';
if(!['fr','en','ar','ary'].includes(locale))throw new Error('Invalid fixture locale');
if(!['dark','light'].includes(theme))throw new Error('Invalid fixture theme');
const fixtures={};
for(const page of ['index','screener'])for(const state of ['AVAILABLE','DISABLED']){
  fixtures[page+state]=execFileSync('php',['tests/render_market_screen_fixture.php',page,'true',state,'html',locale],{cwd:root,encoding:'utf8'});
}
let browser,socket;const requests=[];
const server=createServer(async(req,res)=>{
  try{
    const u=new URL(req.url,'http://127.0.0.1');requests.push(u.pathname);
    const page=u.pathname.slice(1).replace('.php','');
    if(['index','screener'].includes(page)){
      res.setHeader('Content-Type','text/html; charset=utf-8');
      res.end(fixtures[page+(u.searchParams.get('state')==='DISABLED'?'DISABLED':'AVAILABLE')]);return;
    }
    if(!u.pathname.startsWith('/assets/')&&u.pathname!=='/favicon.svg'){res.writeHead(404).end();return;}
    const path=resolve(root,'.'+u.pathname);
    if(!path.startsWith(root)){res.writeHead(403).end();return;}
    const types={'.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.woff2':'font/woff2','.woff':'font/woff'};
    res.setHeader('Content-Type',types[extname(path)]||'application/octet-stream');res.end(await readFile(path));
  }catch{res.writeHead(404).end();}
});
try{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${server.address().port}`;
  browser=spawn('chromium',['--headless','--no-sandbox','--disable-gpu','--disable-background-networking',
    '--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
    '--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank']);
  let address,stderr='';browser.stderr.on('data',v=>{stderr+=v;address=stderr.match(/DevTools listening on (ws:\/\/\S+)/)?.[1];});
  for(let i=0;i<100&&!address;i++)await delay(50);
  if(!address)throw new Error('Chromium startup failed');
  socket=new WebSocket(address);await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  let id=0;const pending=new Map(),errors=[],external=[];
  const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{
    const key=++id;pending.set(key,{resolve,reject});socket.send(JSON.stringify({id:key,method,params,...(sessionId?{sessionId}:{})}));
  });
  socket.addEventListener('message',({data})=>{
    const m=JSON.parse(data);
    if(m.id){const p=pending.get(m.id);pending.delete(m.id);if(m.error)p.reject(new Error(m.error.message));else p.resolve(m.result);}
    if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);
    if(m.method==='Fetch.requestPaused'){
      const allowed=m.params.request.url.startsWith(origin+'/');
      if(!allowed)external.push(new URL(m.params.request.url).protocol);
      send(allowed?'Fetch.continueRequest':'Fetch.failRequest',allowed?{requestId:m.params.requestId}:{requestId:m.params.requestId,errorReason:'BlockedByClient'},m.sessionId).catch(()=>{});
    }
  });
  const {targetId}=await send('Target.createTarget',{url:'about:blank'});
  const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
  const call=(method,params={})=>send(method,params,sessionId);
  await call('Page.enable');await call('Runtime.enable');await call('Fetch.enable',{patterns:[{urlPattern:'*'}]});
  await call('Page.addScriptToEvaluateOnNewDocument',{source:'window.__marketTestNow=Date.parse("2026-10-28T12:05:00Z");Date.now=()=>window.__marketTestNow;'});
  const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error('Browser evaluation failed');return r.result.value;};
  const assert=(value,message)=>{if(!value)throw new Error(message);};
  async function navigate(path){
    await call('Page.navigate',{url:origin+path});
    for(let i=0;i<100;i++){if(await evaluate('document.readyState==="complete"&&!!document.querySelector(".market-preview")'))return;await delay(30);}
    throw new Error('Fixture navigation failed');
  }
  const results=[];
  for(const page of ['index','screener'])for(const [size,width,height] of [['desktop',1365,900],['mobile',390,844]]){
    errors.length=0;
    await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'},{name:'prefers-color-scheme',value:theme}]});
    await navigate('/'+page+'.php');await delay(100);
    const state=await evaluate(`({count:document.querySelectorAll('[data-market-card]').length,
      fits:[...document.querySelectorAll('[data-market-card]')].every(c=>c.getBoundingClientRect().left>=-1&&c.getBoundingClientRect().right<=innerWidth+1),
      index:[...document.querySelectorAll('[data-market-card]')].find(c=>c.dataset.marketName==='MASI MASI')?.textContent,
      badLink:!!document.querySelector('.market-preview a[href="infoAction.php?name=MASI"]')})`);
    assert(state.count===3&&state.fits,'Market cards missing or overflow');
    assert(!state.badLink&&state.index.includes(locale==='ar'||locale==='ary'?'نقطة':'points'),'Index unit/navigation mismatch');
    const screenshot=await call('Page.captureScreenshot',{format:'png'});
    await writeFile(join(output,`${page}-${size}-${locale}-${theme}.png`),Buffer.from(screenshot.data,'base64'));
    await evaluate(`{const q=document.querySelector('[data-market-search]');q.value='B';q.dispatchEvent(new Event('input'));}`);
    assert(await evaluate(`document.querySelectorAll('[data-market-card]:not([hidden])').length===1`),'Search failed');
    await evaluate(`{const q=document.querySelector('[data-market-search]');q.value='';q.dispatchEvent(new Event('input'));window.__marketTestNow=Date.parse('2026-10-28T12:10:00Z');document.dispatchEvent(new Event('visibilitychange'));}`);
    assert(await evaluate(`{const c=[...document.querySelectorAll('[data-market-card]')].find(c=>c.dataset.marketName==='Company B B');[...c.querySelectorAll('[data-market-value]')].every(n=>n.textContent==='—')}`),'Reference expiry did not clear ratios/price');
    await evaluate(`window.__marketTestNow=Date.parse('2026-10-28T12:20:00Z');window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));`);
    assert(await evaluate(`[...document.querySelectorAll('[data-market-value]')].every(n=>n.textContent==='—')`),'Restored page retained expired values');
    assert(errors.length===0,'Browser JavaScript exception');results.push({page,size,passed:true});
  }
  await navigate('/index.php?state=DISABLED');
  assert(await evaluate(`!document.querySelector('[data-market-card]')&&!!document.querySelector('.market-preview-empty')`),'Disabled feed showed prices');
  assert(!requests.some(path=>path.startsWith('/rest/')||path.startsWith('/functions/')),'Unexpected backend request');
  const receipt={ok:true,synthetic_only:true,locale,theme,backend_or_source_requests:0,layouts:results,external_requests_blocked:external.length,disabled_state:true,expiry_and_restore:true};
  await writeFile(join(output,`browser-${locale}-${theme}.json`),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt));
}finally{
  socket?.close();
  if(browser&&browser.exitCode===null)await new Promise(resolve=>{browser.once('exit',resolve);browser.kill('SIGTERM');});
  await new Promise(resolve=>server.close(resolve));await rm(profile,{recursive:true,force:true});
}
