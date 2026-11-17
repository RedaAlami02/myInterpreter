import {createHandler} from './handler.ts';
import {SupabaseBackend} from './supabase.ts';
Deno.serve(async(request)=>{
 if(Deno.env.get('APP_OFFICIAL_CLOSE_ENABLED')!=='true')return Response.json({status:'REJECTED',code:'OFFICIAL_CLOSE_DISABLED'},{status:503});
 try {
  const keys=JSON.parse(Deno.env.get('SUPABASE_SECRET_KEYS')??'{}');
  return await createHandler(new SupabaseBackend(Deno.env.get('SUPABASE_URL')??'',keys.default??''),
   {enabled:true,tokenHash:Deno.env.get('APP_OFFICIAL_CLOSE_TOKEN_SHA256')??'',
    attestationKey:Deno.env.get('APP_OFFICIAL_ATTESTATION_KEY')??'',reviewCommit:Deno.env.get('APP_OFFICIAL_REVIEW_COMMIT')??''})(request);
 }catch{return Response.json({status:'REJECTED',code:'INVALID_SERVER_CONFIGURATION'},{status:503});}
});
