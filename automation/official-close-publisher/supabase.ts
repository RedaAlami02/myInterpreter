import {Backend,bounded} from './handler.ts';
export class SupabaseBackend implements Backend {
 constructor(private url:string,private key:string,private fetcher=fetch){
  if(!/^https:\/\/[a-z0-9]{10,40}\.supabase\.co$/.test(url)||!/^sb_secret_[A-Za-z0-9_-]+$/.test(key))throw new Error('INVALID_SERVER_CONFIGURATION');
 }
 private async call(path:string,init:RequestInit){
  const response=await this.fetcher(this.url+path,{...init,headers:{apikey:this.key,...init.headers},redirect:'error',signal:AbortSignal.timeout(20000)});
  if(!response.ok){await response.body?.cancel();throw new Error('BACKEND_REJECTED');}return response;
 }
 async archive(digest:string){
  if(!/^[a-f0-9]{64}$/.test(digest))throw new Error('INVALID_DIGEST');
  const r=await this.call('/storage/v1/object/private-market-evidence/sha256/'+digest.slice(0,2)+'/'+digest+'.json.gz',{method:'GET'});
  return await bounded(r.body,8*1024*1024);
 }
 async publish(body:Record<string,string>){
  const r=await this.call('/rest/v1/rpc/publish_official_close_batch_v1',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  return JSON.parse(new TextDecoder().decode(await bounded(r.body,4096)));
 }
}
