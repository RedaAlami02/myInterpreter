import {createHandler,sha} from './handler.ts';
function check(v:unknown){if(!v)throw Error('assertion failed');}
const snapshot=()=>({database_bytes:220000000,guard_bytes:350000000,warning_bytes:20000000,official_batches:0,valuation_receipts:0,portfolio_owners:0,market_due:false,close_due:true,depth_complete:false,quotes_complete:false,depth_age_seconds:600,quotes_age_seconds:900,measured_at:new Date().toISOString()});
async function setup(status=204){
 const calls:{url:string;init?:RequestInit}[]=[];
 const fetcher=((url:string,init?:RequestInit)=>{calls.push({url,init});return Promise.resolve(new Response(null,{status}));}) as typeof fetch;
 const handler=createHandler({enabled:true,tokenHash:await sha('fixture'),githubToken:'synthetic',repository:'example/worker',branch:'main'},fetcher);
 const request=(body:unknown=snapshot(),token='fixture')=>new Request('https://example.invalid',{method:'POST',headers:{authorization:'Bearer '+token},body:JSON.stringify(body)});
 return {handler,request,calls};
}
Deno.test('unauthorized request never dispatches',async()=>{const f=await setup();check((await f.handler(f.request(snapshot(),'wrong'))).status===401);check(f.calls.length===0);});
Deno.test('strict snapshot prevents arbitrary inputs and stale reports',async()=>{
 for(const value of [{...snapshot(),repository:'other/repo'},{...snapshot(),measured_at:'2020-01-01T00:00:00Z'},{...snapshot(),database_bytes:'private'},'x'.repeat(5000)]){
 const f=await setup();check((await f.handler(f.request(value))).status===400);check(f.calls.length===0);}
});
Deno.test('fixed health workflow receives only bounded aggregate snapshot',async()=>{
 const f=await setup();const s=snapshot();check((await f.handler(f.request(s))).status===202);
 check(f.calls[0].url==='https://api.github.com/repos/example/worker/actions/workflows/health.yml/dispatches');
 const sent=JSON.parse(String(f.calls[0].init?.body));check(sent.ref==='main');check(JSON.stringify(JSON.parse(sent.inputs.snapshot))===JSON.stringify(s));
});
Deno.test('failure is visible and both success API variants work',async()=>{
 for(const [status,expected] of [[200,202],[204,202],[403,502]]){const f=await setup(status);check((await f.handler(f.request())).status===expected);}
});
