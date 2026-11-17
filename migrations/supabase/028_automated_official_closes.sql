-- Explicit official-close automation. Default OFF; no source or owner is seeded.
-- Control initialization v2: explicit owner approval can arm a pinned source
-- while no batch exists. Existing valuation code still returns PRICE_UNAVAILABLE
-- until a genuinely archived, independently reviewed batch is present. Keep the
-- batch foreign key and master kill switch; publication never arms the master.
ALTER TABLE portfolio_private.official_close_control DROP CONSTRAINT official_close_control_check;
ALTER TABLE portfolio_private.official_close_control ADD CONSTRAINT official_close_control_approved_source_check
 CHECK(NOT enabled OR(provider_namespace IS NOT NULL AND source_policy_sha256 IS NOT NULL));

ALTER TABLE app_recurring.policies ADD COLUMN acquisition_window text NOT NULL DEFAULT 'REGULAR'
 CHECK(acquisition_window IN('REGULAR','OFFICIAL_CLOSE'));
ALTER TABLE app_recurring.policies DROP CONSTRAINT policies_contract_check;
ALTER TABLE app_recurring.policies ADD CHECK(
 (contract='recurring-acquisition/v1' AND acquisition_window='REGULAR') OR
 (contract='recurring-official-close/v1' AND acquisition_window='OFFICIAL_CLOSE'
  AND kinds=ARRAY['quotes']::text[] AND capabilities=ARRAY['archive']::text[]));
DO $$ DECLARE source text; definition text; BEGIN
 SELECT prosrc,pg_get_functiondef(oid) INTO source,definition FROM pg_proc
 WHERE oid='app_recurring.check_new_object(text,text,timestamptz,timestamptz,bigint)'::regprocedure;
 IF encode(sha256(convert_to(source,'UTF8')),'hex')<>'5baf0d61cdb74162fc5abdac40f71c132524f94036d27cf24145a40c248bea5c' THEN
  RAISE EXCEPTION 'Unexpected recurring source window';
 END IF;
 source:=replace(source,'used_objects bigint; used_bytes numeric;', 'used_objects bigint; used_bytes numeric; open_at time; close_at time;');
 source:=replace(source,' local_slot:=p_slot AT TIME ZONE',
  ' open_at:=CASE WHEN policy.acquisition_window=''OFFICIAL_CLOSE'' THEN time ''17:00'' ELSE time ''09:00'' END;
    close_at:=CASE WHEN policy.acquisition_window=''OFFICIAL_CLOSE'' THEN time ''19:00'' ELSE time ''17:00'' END;
    local_slot:=p_slot AT TIME ZONE');
 -- Replace only quote/depth tests. Fundamental17--19 and dividend07--08 stay exact.
 source:=replace(source,'local_now::time<time ''09:00'' OR local_now::time>=time ''17:00''','local_now::time<open_at OR local_now::time>=close_at');
 source:=replace(source,')::time<time ''09:00''',')::time<open_at');
 source:=replace(source,')::time>=time ''17:00''',')::time>=close_at');
 source:=replace(source,'local_slot::time<time ''09:00'' OR local_slot::time>=time ''17:00''','local_slot::time<open_at OR local_slot::time>=close_at');
 SELECT pg_get_functiondef(oid) INTO definition FROM pg_proc
 WHERE oid='app_recurring.check_new_object(text,text,timestamptz,timestamptz,bigint)'::regprocedure;
 EXECUTE replace(definition,(SELECT prosrc FROM pg_proc WHERE oid='app_recurring.check_new_object(text,text,timestamptz,timestamptz,bigint)'::regprocedure),source);
END $$;

CREATE TABLE portfolio_private.official_automation_control (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 enabled boolean NOT NULL DEFAULT false,
 parser_sha256 text CHECK(parser_sha256 ~ '^[a-f0-9]{64}$'),
 identity_sha256 text CHECK(identity_sha256 ~ '^[a-f0-9]{64}$'),
 max_owners integer NOT NULL DEFAULT 100 CHECK(max_owners BETWEEN 1 AND 100),
 CHECK(NOT enabled OR(parser_sha256 IS NOT NULL AND identity_sha256 IS NOT NULL))
);
INSERT INTO portfolio_private.official_automation_control(singleton) VALUES(true);
ALTER TABLE portfolio_private.official_automation_control ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE portfolio_private.official_automation_control FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE portfolio_private.official_review_attestations (
 batch_sha256 text PRIMARY KEY REFERENCES portfolio_private.official_close_batches(sha256),
 document text NOT NULL CHECK(octet_length(document)<=8192),
 signature text NOT NULL CHECK(signature ~ '^[a-f0-9]{64}$'),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE portfolio_private.official_review_attestations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE portfolio_private.official_review_attestations FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION public.publish_official_close_batch_v1(p_document text,p_sha256 text,p_parser_sha256 text,p_identity_document text,p_attestation_document text,p_attestation_hmac text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE ctl portfolio_private.official_automation_control%ROWTYPE; policy portfolio_private.official_close_control%ROWTYPE;
 doc jsonb; identities jsonb; proof jsonb; item jsonb; binding jsonb; owner uuid; outcome jsonb;
 owner_ids uuid[]; created integer:=0; existing integer:=0; unavailable integer:=0;
BEGIN
 PERFORM app_recurring.lock_gate();
 SELECT * INTO ctl FROM portfolio_private.official_automation_control WHERE singleton FOR SHARE;
 SELECT coalesce(array_agg(user_id ORDER BY user_id),ARRAY[]::uuid[]) INTO owner_ids
 FROM (SELECT DISTINCT h.user_id FROM public.portefeuille h JOIN auth.users u ON u.id=h.user_id) owners;
 IF cardinality(owner_ids)>ctl.max_owners THEN RAISE EXCEPTION 'Automatic valuation owner bound reached' USING ERRCODE='54000'; END IF;
 -- Match the authenticated path: owner locks before the control-row lock.
 FOREACH owner IN ARRAY owner_ids LOOP
  PERFORM pg_advisory_xact_lock(hashtextextended(owner::text,73));
 END LOOP;
 SELECT * INTO policy FROM portfolio_private.official_close_control WHERE singleton FOR UPDATE;
 IF NOT policy.enabled THEN RAISE EXCEPTION 'Official valuation master switch is off' USING ERRCODE='42501'; END IF;
 IF NOT ctl.enabled OR p_parser_sha256 IS DISTINCT FROM ctl.parser_sha256
 OR p_identity_document IS NULL OR octet_length(p_identity_document)>524288
 OR encode(sha256(convert_to(p_identity_document,'UTF8')),'hex') IS DISTINCT FROM ctl.identity_sha256 THEN
  RAISE EXCEPTION 'Approved official-close automation required' USING ERRCODE='42501';
 END IF;
 IF p_document IS NULL OR octet_length(p_document)>524288 THEN RAISE EXCEPTION 'Bounded official-close document required'; END IF;
 doc:=p_document::jsonb;identities:=p_identity_document::jsonb;
 IF p_attestation_document IS NULL OR octet_length(p_attestation_document)>8192 OR p_attestation_hmac IS NULL OR p_attestation_hmac !~ '^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION 'Bounded independent review proof required' USING ERRCODE='42501';
 END IF;
 proof:=p_attestation_document::jsonb;
 IF proof->>'contract' IS DISTINCT FROM 'official-close-attestation/v1'
 OR proof->>'document_sha256' IS DISTINCT FROM p_sha256 OR proof->>'parser_sha256' IS DISTINCT FROM ctl.parser_sha256
 OR proof->>'identity_sha256' IS DISTINCT FROM ctl.identity_sha256
 OR proof->>'source_policy_sha256' IS DISTINCT FROM policy.source_policy_sha256
 OR coalesce(proof->>'raw_sha256','') !~ '^[a-f0-9]{64}$'
 OR (proof->>'verified_at')::timestamptz<(doc->>'captured_at')::timestamptz
 OR coalesce(proof->>'worker_commit','') !~ '^[a-f0-9]{40}$'
 OR coalesce(proof->>'verified_at','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
 OR abs(extract(epoch FROM (clock_timestamp()-(proof->>'verified_at')::timestamptz)))>300 THEN
  RAISE EXCEPTION 'Independent review proof differs' USING ERRCODE='42501';
 END IF;

 IF jsonb_typeof(identities) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'Approved official instrument bindings required'; END IF;
 PERFORM app_recurring.bound_lease(doc->>'archive_sha256','archive');
 IF NOT EXISTS(SELECT 1 FROM app_recurring.policies WHERE provider=policy.provider_namespace
  AND enabled AND acquisition_window='OFFICIAL_CLOSE' AND policy_sha256=policy.source_policy_sha256) THEN
  RAISE EXCEPTION 'Official report policy differs' USING ERRCODE='42501';
 END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(doc->'rows') LOOP
  SELECT value INTO binding FROM jsonb_array_elements(identities) WHERE value->>'company_id'=item->>'company_id';
  IF item->>'raw_sha256' IS DISTINCT FROM proof->>'raw_sha256' THEN
   RAISE EXCEPTION 'Independent raw report proof differs' USING ERRCODE='42501';
  END IF;
  IF NOT FOUND OR binding->>'c_name' IS DISTINCT FROM item->>'c_name' OR binding->>'symbol' IS DISTINCT FROM item->>'symbol'
   OR (SELECT count(*) FROM jsonb_array_elements(identities) WHERE value->>'company_id'=item->>'company_id')<>1 THEN
   RAISE EXCEPTION 'Official report company binding differs' USING ERRCODE='22023';
  END IF;
 END LOOP;
 PERFORM portfolio_private.register_reviewed_official_closes(p_document,p_sha256);
 INSERT INTO portfolio_private.official_review_attestations(batch_sha256,document,signature)
  VALUES(p_sha256,p_attestation_document,p_attestation_hmac) ON CONFLICT(batch_sha256) DO NOTHING;

 UPDATE portfolio_private.official_close_control SET active_batch_sha256=p_sha256 WHERE singleton;
 -- Owners are selected internally. Callers never provide identities or override time.
 FOREACH owner IN ARRAY owner_ids LOOP
  outcome:=portfolio_private.record_official_valuation(owner,clock_timestamp());
  IF outcome->>'status'='CREATED' THEN created:=created+1;
  ELSIF outcome->>'status'='EXISTING' THEN existing:=existing+1;
  ELSE unavailable:=unavailable+1; END IF;
 END LOOP;
 RETURN jsonb_build_object('contract','official-close-publication/v1','status','ACCEPTED','sha256',p_sha256,
  'valuations_created',created,'valuations_existing',existing,'valuations_unavailable',unavailable);
END $$;
REVOKE ALL ON FUNCTION public.publish_official_close_batch_v1(text,text,text,text,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.publish_official_close_batch_v1(text,text,text,text,text,text) TO service_role;

-- Write-only collector may acknowledge an exact independently accepted batch;
-- this returns no account identifiers, amounts, raw reports or portfolio rows.
CREATE FUNCTION public.official_close_status_recurring_v1(p_provider text,p_digest text,p_document_sha256 text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF p_provider IS NULL OR p_provider !~ '^feed_[a-f0-9]{16}$' OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$'
 OR p_document_sha256 IS NULL OR p_document_sha256 !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'Invalid official receipt identity'; END IF;
 RETURN EXISTS(SELECT 1 FROM portfolio_private.official_close_batches b
 JOIN portfolio_private.official_review_attestations proof ON proof.batch_sha256=b.sha256
 JOIN app_archive.objects a ON a.digest=b.archive_digest AND a.provider=p_provider AND a.state='STORED'
 JOIN app_recurring.objects o ON o.digest=a.digest JOIN app_recurring.runs r ON r.id=o.run_id
 WHERE b.sha256=p_document_sha256 AND b.archive_digest=p_digest AND b.provider_namespace=p_provider
 AND r.provider=p_provider AND r.plan_sha256=b.source_policy_sha256);
END $$;
REVOKE ALL ON FUNCTION public.official_close_status_recurring_v1(text,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.official_close_status_recurring_v1(text,text,text) TO service_role;
