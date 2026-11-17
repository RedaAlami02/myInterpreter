export interface Backend {
  archive(digest: string): Promise<Uint8Array>;
  publish(body: Record<string,string>): Promise<unknown>;
}
const hex = /^[a-f0-9]{64}$/;
export async function sha(raw: Uint8Array): Promise<string> {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw as BufferSource))).map(v=>v.toString(16).padStart(2,'0')).join('');
}
export async function bounded(stream: ReadableStream<Uint8Array>|null, maximum: number) {
  if (!stream) throw new Error('BODY_REQUIRED');
  const reader=stream.getReader();let size=0;const pieces:Uint8Array[]=[];
  try { while(true) { const {value,done}=await reader.read();if(done)break;size+=value.length;
    if(size>maximum){await reader.cancel();throw new Error('BODY_LIMIT');}pieces.push(value); } }
  finally {reader.releaseLock();}
  const result=new Uint8Array(size);let offset=0;for(const piece of pieces){result.set(piece,offset);offset+=piece.length;}return result;
}
export function createHandler(backend: Backend, config: {enabled:boolean;tokenHash:string;attestationKey:string;reviewCommit:string;now?:()=>number}) {
  return async(request:Request):Promise<Response>=>{
    try {
      if(!config.enabled||!hex.test(config.tokenHash)||!hex.test(config.attestationKey)||!/^[a-f0-9]{40}$/.test(config.reviewCommit))return Response.json({status:'REJECTED',code:'OFFICIAL_CLOSE_DISABLED'},{status:503});
      const auth=request.headers.get('Authorization')??'';
      if(!/^Bearer official_close_[a-f0-9]{64}$/.test(auth))throw new Error('AUTHENTICATION_REQUIRED');
      const actual=await sha(new TextEncoder().encode(auth.slice(7)));let mismatch=0;
      for(let i=0;i<64;i++)mismatch|=actual.charCodeAt(i)^config.tokenHash.charCodeAt(i);
      if(mismatch)throw new Error('AUTHENTICATION_REQUIRED');
      if(request.method==='GET'&&!new URL(request.url).search)return Response.json({status:'READY',worker_commit:config.reviewCommit},{headers:{'Cache-Control':'no-store'}});
      if(request.method!=='POST'||new URL(request.url).search||request.headers.get('Content-Type')!=='application/json')throw new Error('INVALID_REQUEST');
      const body=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(await bounded(request.body,2*1024*1024)));
      if(Object.keys(body).sort().join(',')!=='attestation_document,attestation_hmac,p_document,p_identity_document,p_parser_sha256,p_sha256'
         ||!Object.values(body).every(v=>typeof v==='string')||!hex.test(body.p_sha256)||!hex.test(body.p_parser_sha256)
         ||await sha(new TextEncoder().encode(body.p_document))!==body.p_sha256)throw new Error('INVALID_DOCUMENT');
      const proof=JSON.parse(body.attestation_document);
      if(Object.keys(proof).sort().join(',')!=='contract,document_sha256,identity_sha256,parser_sha256,raw_sha256,source_policy_sha256,verified_at,worker_commit'
         ||proof.contract!=='official-close-attestation/v1'||proof.worker_commit!==config.reviewCommit
         ||proof.document_sha256!==body.p_sha256||proof.parser_sha256!==body.p_parser_sha256
         ||proof.identity_sha256!==await sha(new TextEncoder().encode(body.p_identity_document))
         ||!hex.test(proof.raw_sha256)||!hex.test(body.attestation_hmac))throw new Error('INDEPENDENT_ATTESTATION_REQUIRED');
      const verifiedAt=Date.parse(proof.verified_at);
      if(!Number.isFinite(verifiedAt)||Math.abs((config.now?.()??Date.now())-verifiedAt)>300000)throw new Error('ATTESTATION_EXPIRED');
      const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(config.attestationKey),{name:'HMAC',hash:'SHA-256'},false,['verify']);
      const signature=Uint8Array.from(body.attestation_hmac.match(/../g),(v:string)=>parseInt(v,16));
      if(!await crypto.subtle.verify('HMAC',key,signature,new TextEncoder().encode(body.attestation_document)))throw new Error('INVALID_ATTESTATION');
      const doc=JSON.parse(body.p_document),identities=JSON.parse(body.p_identity_document);
      if(!hex.test(doc.archive_sha256)||!Array.isArray(doc.rows)||!doc.rows.length||doc.rows.length>1000||!Array.isArray(identities))throw new Error('INVALID_DOCUMENT');
      if(proof.source_policy_sha256!==doc.source_policy_sha256||verifiedAt<Date.parse(doc.captured_at))throw new Error('ATTESTATION_CONTEXT_DIFFERS');
      const archive=await backend.archive(doc.archive_sha256);
      if(await sha(archive)!==doc.archive_sha256)throw new Error('ARCHIVE_HASH_DIFFERS');
      const uncompressed=new Blob([archive as BlobPart]).stream().pipeThrough(new DecompressionStream('gzip'));
      const envelope=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(await bounded(uncompressed,32*1024*1024)));
      if(envelope.contract!=='private-acquisition/v2'||envelope.kind!=='quotes'||envelope.execution!=='CURRENT_ACQUISITION'
         ||envelope.provider_namespace!==doc.provider_namespace||envelope.parser_sha256!==body.p_parser_sha256
         ||envelope.captures?.length!==1||envelope.official_report?.contract!=='daily-report-closes/v1'
         ||envelope.official_report.session_day!==doc.session_day)throw new Error('ARCHIVE_CONTEXT_DIFFERS');
      const capture=envelope.captures[0];
      if(typeof capture.raw_hex!=='string'||capture.raw_hex.length>16*1024*1024||capture.raw_hex.length%2||!/^25504446[a-f0-9]*$/.test(capture.raw_hex)
         ||capture.received_at!==doc.captured_at)throw new Error('INVALID_REPORT_CAPTURE');
      const raw=Uint8Array.from(capture.raw_hex.match(/../g)??[],(v:string)=>parseInt(v,16));
      if(await sha(raw)!==capture.sha256||capture.sha256!==envelope.official_report.raw_sha256||capture.sha256!==proof.raw_sha256)throw new Error('RAW_HASH_DIFFERS');
      for(const row of doc.rows){
        const bindings=identities.filter((r:Record<string,string>)=>r.company_id===row.company_id&&r.c_name===row.c_name&&r.symbol===row.symbol);
        const prices=bindings.length===1?envelope.official_report.rows.filter((r:Record<string,string>)=>r.isin===bindings[0].isin):[];
        if(prices.length!==1||prices[0].price_decimal!==row.price_decimal||prices[0].observation_id!==row.observation_id||row.raw_sha256!==capture.sha256)throw new Error('REPORT_ROW_DIFFERS');
      }
      return Response.json(await backend.publish({p_document:body.p_document,p_sha256:body.p_sha256,p_parser_sha256:body.p_parser_sha256,p_identity_document:body.p_identity_document,p_attestation_document:body.attestation_document,p_attestation_hmac:body.attestation_hmac}));
    }catch{return Response.json({status:'REJECTED',code:'OFFICIAL_CLOSE_NOT_ACCEPTED'},{status:400});}
  };
}
