-- Biographical gap fills only. Financial maintenance remains a separate reviewed path.
CREATE TABLE market_admin.profile_sync_receipts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 actor uuid NOT NULL,
 company_id text NOT NULL,
 captured_at timestamptz NOT NULL,
 profile_sha256 text NOT NULL,
 before_values jsonb NOT NULL,
 applied_values jsonb NOT NULL,
 applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE market_admin.profile_sync_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON market_admin.profile_sync_receipts FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION market_admin.apply_profile_biography(change jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE co public.company%ROWTYPE; profile public.company_profiles%ROWTYPE; key text; value jsonb;
 fields jsonb:=change->'fields'; expected jsonb:=change->'expected'; source jsonb; previous jsonb:='{}'::jsonb;
 receipt jsonb; caller uuid:=auth.uid();
BEGIN
 IF caller IS NULL OR auth.role() IS DISTINCT FROM 'authenticated'
 OR NOT EXISTS(SELECT 1 FROM market_admin.admins WHERE user_id=caller) THEN
  RAISE EXCEPTION 'Administrator access required' USING ERRCODE='42501'; END IF;
 IF jsonb_typeof(fields) IS DISTINCT FROM 'object' OR fields='{}'::jsonb
 OR jsonb_typeof(expected) IS DISTINCT FROM 'object' OR octet_length(change::text)>20000 THEN
  RAISE EXCEPTION 'Invalid profile change' USING ERRCODE='22023'; END IF;
 SELECT * INTO co FROM public.company WHERE name=change->>'name' FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('name',change->>'name','status','MISSING'); END IF;
 SELECT * INTO profile FROM public.company_profiles WHERE id=change->>'symbol';
 IF NOT FOUND OR profile.profile->>'c_name' IS DISTINCT FROM co.name
 OR profile.profile->>'symbol' IS DISTINCT FROM change->>'symbol'
 OR (SELECT count(*) FROM public.format WHERE name=co.name)<>1
 OR (SELECT count(*) FROM public.format WHERE name=co.name AND symbol=change->>'symbol')<>1
 OR profile.captured_at IS DISTINCT FROM (change->>'captured_at')::timestamptz
 OR (profile.profile->>'captured_at')::timestamptz IS DISTINCT FROM profile.captured_at
 OR profile.captured_at>clock_timestamp() OR profile.captured_at<clock_timestamp()-interval '30 days' THEN
  RETURN jsonb_build_object('name',co.name,'status','STALE'); END IF;
 FOR key,value IN SELECT * FROM jsonb_each(fields) LOOP
  IF NOT key=ANY(ARRAY['ext_name','sector','description','shareholders']) THEN
   RAISE EXCEPTION 'Financial or unsupported profile field' USING ERRCODE='22023'; END IF;
  source:=CASE WHEN key='shareholders' THEN profile.profile->'computed'->key ELSE profile.profile->key END;
  IF jsonb_typeof(value) IS DISTINCT FROM 'string' OR length(value#>>'{}') NOT BETWEEN 1 AND 4000
   OR value IS DISTINCT FROM source THEN RETURN jsonb_build_object('name',co.name,'status','STALE'); END IF;
  previous:=previous||jsonb_build_object(key,to_jsonb(co)->key);
  IF to_jsonb(co)->key IS DISTINCT FROM value AND (
      NOT expected ? key OR to_jsonb(co)->key IS DISTINCT FROM expected->key
      OR coalesce(to_jsonb(co)->>key,'')<>'') THEN
   RETURN jsonb_build_object('name',co.name,'status','PROTECTED'); END IF;
 END LOOP;
 IF NOT EXISTS(SELECT 1 FROM jsonb_each(fields) f WHERE to_jsonb(co)->f.key IS DISTINCT FROM f.value) THEN
  RETURN jsonb_build_object('name',co.name,'status','UNCHANGED'); END IF;
 receipt:=public.admin_update_company(co.name,fields);
 INSERT INTO market_admin.profile_sync_receipts(actor,company_id,captured_at,profile_sha256,before_values,applied_values)
 VALUES(caller,co.id,profile.captured_at,encode(sha256(convert_to(profile.profile::text,'UTF8')),'hex'),previous,fields);
 RETURN receipt;
END $$;
REVOKE ALL ON FUNCTION market_admin.apply_profile_biography(jsonb) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION public.admin_apply_profile_biographies(p_changes jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE item jsonb; results jsonb:='[]'::jsonb;
BEGIN
 IF auth.uid() IS NULL OR auth.role() IS DISTINCT FROM 'authenticated'
 OR NOT EXISTS(SELECT 1 FROM market_admin.admins WHERE user_id=auth.uid()) THEN
  RAISE EXCEPTION 'Administrator access required' USING ERRCODE='42501'; END IF;
 IF jsonb_typeof(p_changes) IS DISTINCT FROM 'array' OR jsonb_array_length(p_changes) NOT BETWEEN 1 AND 25
 OR octet_length(p_changes::text)>524288 THEN RAISE EXCEPTION 'Invalid bounded batch' USING ERRCODE='22023'; END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_changes) LOOP
  results:=results||jsonb_build_array(market_admin.apply_profile_biography(item));
 END LOOP;
 RETURN jsonb_build_object('results',results);
END $$;
REVOKE ALL ON FUNCTION public.admin_apply_profile_biographies(jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.admin_apply_profile_biographies(jsonb) TO authenticated;
