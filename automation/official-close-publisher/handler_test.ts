import {createHandler,sha} from './handler.ts';
const KEY='a'.repeat(64),COMMIT='b'.repeat(40),TOKEN='official_close_'+'c'.repeat(64),NOW=Date.parse('2026-11-03T18:05:00Z');
async function fixture(){
 const raw=new TextEncoder().encode('%PDF synthetic isolated test');const rawSha=await sha(raw);
 const identities=JSON.stringify([{company_id:'example',c_name:'EXAMPLE EQUITY',symbol:'EXA',isin:'MA0000000001'}]);
 const parser='d'.repeat(64),policy='e'.repeat(64),observation='f'.repeat(64);
 const envelope={contract:'private-acquisition/v2',kind:'quotes',execution:'CURRENT_ACQUISITION',provider_namespace:'feed_0123456789abcdef',parser_sha256:parser,
  captures:[{received_at:'2026-11-03T18:04:00Z',raw_hex:Array.from(raw).map(v=>v.toString(16).padStart(2,'0')).join(''),sha256:rawSha}],
  official_report:{contract:'daily-report-closes/v1',session_day:'2026-11-03',raw_sha256:rawSha,rows:[{isin:'MA0000000001',price_decimal:'25.00',observation_id:observation}]}};
 const compressed=await new Response(new Blob([JSON.stringify(envelope)]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();
 const archive=new Uint8Array(compressed),archiveSha=await sha(archive);
 const document=JSON.stringify({provider_namespace:envelope.provider_namespace,source_policy_sha256:policy,archive_sha256:archiveSha,session_day:'2026-11-03',captured_at:envelope.captures[0].received_at,
   rows:[{company_id:'example',c_name:'EXAMPLE EQUITY',symbol:'EXA',price_decimal:'25.00',observation_id:observation,raw_sha256:rawSha}]});
 const body={p_document:document,p_sha256:await sha(new TextEncoder().encode(document)),p_parser_sha256:parser,p_identity_document:identities,attestation_document:'',attestation_hmac:''};
 const proof={contract:'official-close-attestation/v1',document_sha256:body.p_sha256,raw_sha256:rawSha,identity_sha256:await sha(new TextEncoder().encode(identities)),parser_sha256:parser,source_policy_sha256:policy,worker_commit:COMMIT,verified_at:'2026-11-03T18:05:00Z'};
 body.attestation_document=JSON.stringify(proof);
 const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(KEY),{name:'HMAC',hash:'SHA-256'},false,['sign']);
 body.attestation_hmac=Array.from(new Uint8Array(await crypto.subtle.sign('HMAC',key,new TextEncoder().encode(body.attestation_document)))).map(v=>v.toString(16).padStart(2,'0')).join('');
 let writes=0;
 const backend={archive:async()=>archive,publish:async(v:Record<string,string>)=>{writes++;if('attestation_hmac' in v)throw new Error('proof leaked into SQL');return {status:'ACCEPTED',sha256:v.p_sha256};}};
 const handler=createHandler(backend,{enabled:true,tokenHash:await sha(new TextEncoder().encode(TOKEN)),attestationKey:KEY,reviewCommit:COMMIT,now:()=>NOW});
 return {body,handler,writes:()=>writes};
}
function request(body:unknown,token=TOKEN){return new Request('https://example.invalid',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify(body)});}
Deno.test('independently attested exact report reaches bounded backend without owner input',async()=>{
 const f=await fixture();if((await f.handler(request(f.body))).status!==200||f.writes()!==1)throw new Error('valid attestation rejected');
});
Deno.test('caller-held publication credential and approved parser hash do not replace attestation',async()=>{
 const f=await fixture();f.body.attestation_hmac='0'.repeat(64);
 if((await f.handler(request(f.body))).status===200||f.writes())throw new Error('forged attestation accepted');
});
Deno.test('modified prices or commit, expired proof, and injected owner are rejected',async()=>{
 for(const mutation of ['prices','commit','expired','owner']){
  const f=await fixture();
  if(mutation==='prices'){f.body.p_document=f.body.p_document.replace('25.00','999.00');f.body.p_sha256=await sha(new TextEncoder().encode(f.body.p_document));}
  if(mutation==='commit')f.body.attestation_document=f.body.attestation_document.replace(COMMIT,'0'.repeat(40));
  if(mutation==='expired')f.body.attestation_document=f.body.attestation_document.replace('18:05:00','17:00:00');
  if(mutation==='owner')(f.body as Record<string,string>).p_owner='untrusted';
  if((await f.handler(request(f.body))).status===200||f.writes())throw new Error(mutation+' accepted');
 }
});
Deno.test('collector token cannot authenticate as the financial reviewer',async()=>{
 const f=await fixture();if((await f.handler(request(f.body,'arc_write_'+'c'.repeat(64)))).status===200||f.writes())throw new Error('collector gained financial authority');
});

Deno.test('authenticated deployment preflight is read-only and never cached',async()=>{
 const f=await fixture();const r=await f.handler(new Request('https://example.invalid',{headers:{Authorization:'Bearer '+TOKEN}}));
 const body=await r.json();if(r.status!==200||body.worker_commit!==COMMIT||body.status!=='READY'||f.writes()!==0||r.headers.get('Cache-Control')!=='no-store')throw new Error('invalid preflight');
 const denied=await f.handler(new Request('https://example.invalid'));
 if(denied.status===200||f.writes()!==0)throw new Error('unauthenticated preflight accepted');
});
