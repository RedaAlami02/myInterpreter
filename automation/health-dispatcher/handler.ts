/** Dispatch fixed operational checks; never accepts a destination or workflow from callers. */
export async function sha(value:string){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))),b=>b.toString(16).padStart(2,'0')).join('');}
export function createHandler(config:{enabled:boolean;tokenHash:string;githubToken:string;repository:string;branch:string},fetcher=fetch){
 return async(request:Request)=>{
  const reply=(status:string,code=200)=>Response.json({status},{status:code});
  if(request.method!=='POST')return reply('METHOD_NOT_ALLOWED',405);
  const auth=request.headers.get('authorization')??'';
  if(!/^[a-f0-9]{64}$/.test(config.tokenHash)||!auth.startsWith('Bearer ')||auth.length>512||await sha(auth.slice(7))!==config.tokenHash)return reply('UNAUTHORIZED',401);
  if(!config.enabled)return reply('DISABLED',503);
  if(!/^[\w.-]+\/[\w.-]+$/.test(config.repository)||!config.githubToken||!/^[-\w./]+$/.test(config.branch))return reply('INVALID_CONFIGURATION',503);
  try{
   const reader=request.body?.getReader();if(!reader)return reply('INVALID_SNAPSHOT',400);
   let size=0;const pieces:Uint8Array[]=[];
   try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>4096){await reader.cancel();return reply('INVALID_SNAPSHOT',400);}pieces.push(value);}}finally{reader.releaseLock();}
   const bytes=new Uint8Array(size);let offset=0;for(const p of pieces){bytes.set(p,offset);offset+=p.length;}
   const value=JSON.parse(new TextDecoder().decode(bytes));
   const counts=['database_bytes','guard_bytes','warning_bytes','official_batches','valuation_receipts','portfolio_owners'];
   const flags=['market_due','close_due','depth_complete','quotes_complete'];const ages=['depth_age_seconds','quotes_age_seconds'];
   const fields=[...counts,...flags,...ages,'measured_at'];
   if(!value||Array.isArray(value)||Object.keys(value).sort().join()!==fields.sort().join()
    ||counts.some(k=>!Number.isSafeInteger(value[k])||value[k]<0)||flags.some(k=>typeof value[k]!=='boolean')
    ||ages.some(k=>value[k]!==null&&(!Number.isFinite(value[k])||value[k]<0))
    ||typeof value.measured_at!=='string'||!Number.isFinite(Date.parse(value.measured_at))||Math.abs(Date.now()-Date.parse(value.measured_at))>600000)return reply('INVALID_SNAPSHOT',400);
   const r=await fetcher(`https://api.github.com/repos/${config.repository}/actions/workflows/health.yml/dispatches`,{
    method:'POST',headers:{Authorization:`Bearer ${config.githubToken}`,Accept:'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'private-health-dispatcher'},
    body:JSON.stringify({ref:config.branch,inputs:{snapshot:JSON.stringify(value)}}),redirect:'error',signal:AbortSignal.timeout(15000)});
   return [200,204].includes(r.status)?reply('DISPATCH_ACCEPTED',202):reply('DISPATCH_REJECTED',502);
  }catch{return reply('HEALTH_DISPATCH_FAILED',502);}
 };
}
