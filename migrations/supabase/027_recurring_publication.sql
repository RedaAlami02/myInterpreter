-- Additive recurring-acquisition/v1 aliases. Legacy manual RPCs unchanged.
CREATE FUNCTION public.finalize_market_archive_recurring_v1(p_digest text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_recurring.runs%ROWTYPE; result text;
BEGIN
    IF EXISTS(SELECT 1 FROM app_archive.subjects WHERE digest=p_digest) THEN RAISE EXCEPTION 'Subject finalization required'; END IF;
    lease:=app_recurring.bound_lease(p_digest,'archive');
    result:=app_trial_legacy.finalize_market_archive(p_digest);
    PERFORM app_recurring.require_lease(lease.provider,'archive',lease.id);
    RETURN result;
END $$;

REVOKE ALL ON FUNCTION public.finalize_market_archive_recurring_v1(text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.finalize_market_archive_recurring_v1(text) TO service_role;

CREATE FUNCTION public.publish_shadow_market_candidate_recurring_v1(p_document text,p_payload_sha256 text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_recurring.runs%ROWTYPE; result text;
BEGIN
    lease:=app_recurring.document_lease(p_document,'shadow_feed');
    IF NOT EXISTS(SELECT 1 FROM app_feed.control WHERE singleton AND enabled) THEN
        RAISE EXCEPTION 'Shadow trial publication disabled' USING ERRCODE='42501';
    END IF;
    result:=app_trial_legacy.publish_shadow_market_candidate(p_document,p_payload_sha256);
    PERFORM app_recurring.require_lease(lease.provider,'shadow_feed',lease.id);
    RETURN result;
END $$;

REVOKE ALL ON FUNCTION public.publish_shadow_market_candidate_recurring_v1(text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.publish_shadow_market_candidate_recurring_v1(text,text) TO service_role;

CREATE FUNCTION public.publish_dividend_projection_recurring_v1(p_document text,p_payload_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_recurring.runs%ROWTYPE; result jsonb;
BEGIN
    lease:=app_recurring.document_lease(p_document,'projections');
    result:=app_recurring.publish_dividend_impl(p_document,p_payload_sha256);
    PERFORM app_recurring.require_lease(lease.provider,'projections',lease.id);
    RETURN result;
END $$;

REVOKE ALL ON FUNCTION public.publish_dividend_projection_recurring_v1(text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.publish_dividend_projection_recurring_v1(text,text) TO service_role;

CREATE FUNCTION public.publish_fundamental_projection_recurring_v1(p_document text,p_payload_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_recurring.runs%ROWTYPE; result jsonb;
BEGIN
    lease:=app_recurring.document_lease(p_document,'projections');
    result:=app_recurring.publish_fundamental_impl(p_document,p_payload_sha256);
    PERFORM app_recurring.require_lease(lease.provider,'projections',lease.id);
    RETURN result;
END $$;

REVOKE ALL ON FUNCTION public.publish_fundamental_projection_recurring_v1(text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.publish_fundamental_projection_recurring_v1(text,text) TO service_role;

CREATE FUNCTION public.read_shadow_market_feed_recurring_v1()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_recurring.runs%ROWTYPE; digest text; result jsonb; clipped jsonb;
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Sign in required' USING ERRCODE='42501'; END IF;
    result:=jsonb_build_object('contract','app-market-preview/v1','mode','SHADOW_ONLY',
        'as_of',clock_timestamp(),'status','DISABLED','captured_at',NULL,
        'acquisition_completeness',NULL,'market_session_state','UNKNOWN','rows','[]'::jsonb);
    PERFORM app_recurring.lock_gate();
    SELECT f.archive_digest INTO digest FROM app_feed.latest f JOIN app_feed.control c
        ON c.singleton AND c.enabled AND c.provider_namespace=f.provider;
    IF NOT FOUND THEN RETURN result; END IF;
    BEGIN lease:=app_recurring.bound_lease(digest,'shadow_feed');
    EXCEPTION WHEN insufficient_privilege THEN RETURN result; END;
    result:=app_recurring.read_market_feed_impl();
    clipped:=result->'rows';
    PERFORM app_recurring.require_lease(lease.provider,'shadow_feed',lease.id);
    RETURN result||jsonb_build_object('rows',clipped);
END $$;

REVOKE ALL ON FUNCTION public.read_shadow_market_feed_recurring_v1() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.read_shadow_market_feed_recurring_v1() TO authenticated;

CREATE FUNCTION public.publish_shadow_application_rows_recurring_v1(p_document text,p_payload_sha256 text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE
    doc jsonb; ctl app_feed.application_control%ROWTYPE; head app_feed.latest%ROWTYPE;
    old app_feed.application_latest%ROWTYPE; lease app_recurring.runs%ROWTYPE;
    item jsonb; row_fields jsonb; provenance jsonb; quote jsonb; expected_price text;
    key text; seen text[]:=ARRAY[]::text[]; entry jsonb; moment timestamptz;
    field_time timestamptz; row_time timestamptz; asset text;
    fields text[]:=ARRAY['date','c_name','symbol','pa','cb','pb','per','peg','pr',
        'per_rating','pb_rating','peg_rating','pr_rating','variation','variation_v',
        'cours_ref','open_price','high','low','volume','qty_traded','market_cap','data_chart'];
BEGIN
    IF p_document IS NULL OR octet_length(p_document)>2097152
       OR p_payload_sha256 IS NULL OR p_payload_sha256 !~ '^[a-f0-9]{64}$'
       OR encode(pg_catalog.sha256(convert_to(p_document,'UTF8')),'hex')<>p_payload_sha256 THEN
        RAISE EXCEPTION 'Invalid application-row payload' USING ERRCODE='22023';
    END IF;
    doc:=p_document::jsonb;
    lease:=app_recurring.document_lease(p_document,'projections');
    PERFORM app_recurring.require_lease(lease.provider,'shadow_feed',lease.id);
    SELECT * INTO ctl FROM app_feed.application_control WHERE singleton FOR SHARE;
    IF NOT FOUND OR NOT coalesce(ctl.enabled,false) OR ctl.fields_sha256 IS NULL
       OR coalesce(doc->>'application_fields_sha256','') !~ '^[a-f0-9]{64}$'
       OR doc->>'contract' IS DISTINCT FROM 'app-price-rows/v1'
       OR doc->>'mode' IS DISTINCT FROM 'SHADOW_ONLY'
       OR doc->>'source_execution' IS DISTINCT FROM 'CURRENT_ACQUISITION'
       OR doc->>'application_fields_sha256' IS DISTINCT FROM ctl.fields_sha256
       OR doc->'prediction_eligible' IS DISTINCT FROM 'false'::jsonb
       OR doc->'portfolio_valuation_eligible' IS DISTINCT FROM 'false'::jsonb
       OR jsonb_typeof(doc->'captured_at') IS DISTINCT FROM 'string'
       OR jsonb_typeof(doc->'as_of') IS DISTINCT FROM 'string'
       OR (doc->>'captured_at') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
       OR (doc->>'as_of') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
       OR jsonb_typeof(doc->'rows') IS DISTINCT FROM 'array'
       OR jsonb_typeof(doc->'excluded') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'Application rows disabled or contract mismatch' USING ERRCODE='42501';
    END IF;
    SELECT f.* INTO head FROM app_feed.latest f JOIN app_feed.control c
        ON c.singleton AND c.enabled AND c.provider_namespace=f.provider
        JOIN app_archive.objects a ON a.digest=f.archive_digest AND a.state='STORED' AND a.kind='quotes'
        JOIN app_archive.providers p ON p.namespace=f.provider AND p.enabled
        WHERE f.provider=lease.provider AND EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled)
        FOR SHARE OF f;
    moment:=clock_timestamp();
    IF NOT FOUND OR head.archive_digest IS DISTINCT FROM doc->>'archive_sha256'
       OR head.payload_sha256 IS DISTINCT FROM doc->>'quote_payload_sha256'
       OR head.captured_at IS DISTINCT FROM (doc->>'captured_at')::timestamptz
       OR head.captured_at>moment
       OR head.captured_at<=moment-make_interval(secs=>(head.body->>'capture_max_age_seconds')::integer)
       OR (head.captured_at AT TIME ZONE 'Africa/Casablanca')::date<>(moment AT TIME ZONE 'Africa/Casablanca')::date
       OR doc->>'acquisition_completeness' IS DISTINCT FROM head.body->>'acquisition_completeness'
       OR (doc->>'as_of')::timestamptz<head.captured_at OR (doc->>'as_of')::timestamptz>moment
       OR NOT isfinite((doc->>'as_of')::timestamptz)
       OR jsonb_array_length(doc->'rows')+jsonb_array_length(doc->'excluded')<>jsonb_array_length(head.body->'rows') THEN
        RAISE EXCEPTION 'Exact current quote head required' USING ERRCODE='22023';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(doc->'rows') LOOP
        asset:=item->>'asset_key'; row_fields:=item->'row'; provenance:=item->'provenance';
        SELECT r INTO quote FROM jsonb_array_elements(head.body->'rows') r WHERE r->>'asset_key'=asset;
        IF NOT FOUND OR asset=ANY(seen) OR jsonb_typeof(row_fields) IS DISTINCT FROM 'object'
           OR jsonb_typeof(provenance) IS DISTINCT FROM 'object'
           OR provenance->>'asset_key' IS DISTINCT FROM asset
           OR row_fields->>'c_name' IS DISTINCT FROM quote->>'c_name'
           OR provenance->>'c_name' IS DISTINCT FROM quote->>'c_name'
           OR provenance->>'symbol' IS DISTINCT FROM quote->>'symbol'
           OR provenance->'company_id' IS DISTINCT FROM quote->'company_id'
           OR provenance->>'instrument_type' IS DISTINCT FROM quote->>'instrument_type'
           OR provenance->'prediction_eligible' IS DISTINCT FROM 'false'::jsonb
           OR provenance->'portfolio_valuation_eligible' IS DISTINCT FROM 'false'::jsonb THEN
            RAISE EXCEPTION 'Application row identity mismatch' USING ERRCODE='22023';
        END IF;
        seen:=array_append(seen,asset);
        expected_price:=NULL;
        IF provenance->>'price_basis'='OBSERVED_QUOTE' AND quote->>'status' IN ('REPORTED_DATE_ONLY','REPORTED_EVENT_VERIFIED') THEN
            expected_price:=quote->>'display_price_decimal';
            IF provenance->'observations' IS DISTINCT FROM quote->'observations'
               OR provenance->'source_event_at' IS DISTINCT FROM quote->'source_event_at' THEN
                RAISE EXCEPTION 'Application quote evidence mismatch' USING ERRCODE='22023';
            END IF;
        ELSIF provenance->>'price_basis'='INSTRUMENT_REFERENCE' AND quote->>'status'='MISSING_QUOTE'
              AND quote->>'instrument_type'='STOCK' AND quote->'reference_conflict'='false'::jsonb THEN
            expected_price:=quote->'reference_price'->>'price_decimal';
            IF provenance->'observations' IS DISTINCT FROM quote->'reference_price'->'observations'
               OR provenance->'source_event_at' IS DISTINCT FROM 'null'::jsonb
               OR provenance->'source_reported_day' IS DISTINCT FROM 'null'::jsonb THEN
                RAISE EXCEPTION 'Application reference evidence mismatch' USING ERRCODE='22023';
            END IF;
        END IF;
        row_time:=(row_fields->>'date')::timestamptz;
        IF expected_price IS NULL OR provenance->>'price_decimal' IS DISTINCT FROM expected_price
           OR jsonb_typeof(row_fields->'date') IS DISTINCT FROM 'string'
           OR (row_fields->>'date') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
           OR jsonb_typeof(provenance->'captured_at') IS DISTINCT FROM 'string'
           OR (provenance->>'captured_at') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
           OR jsonb_typeof(row_fields->'pa') IS DISTINCT FROM 'number'
           OR (row_fields->>'pa')::double precision<>expected_price::double precision
           OR row_time IS DISTINCT FROM head.captured_at
           OR (provenance->>'captured_at')::timestamptz IS DISTINCT FROM head.captured_at THEN
            RAISE EXCEPTION 'Application price/time mismatch' USING ERRCODE='22023';
        END IF;
        IF quote->>'instrument_type'='STOCK' THEN
            field_time:=(provenance->>'fundamentals_available_at')::timestamptz;
            IF field_time IS NULL OR NOT isfinite(field_time) OR field_time>row_time
               OR (provenance->>'fundamentals_available_at') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
               OR row_fields->>'symbol' IS DISTINCT FROM quote->>'symbol'
               OR NOT EXISTS(SELECT 1 FROM public.company co WHERE co.id=quote->>'company_id'
                             AND co.name=quote->>'c_name' AND (co.date IS NULL OR co.date<=field_time)) THEN
                RAISE EXCEPTION 'Company inputs unavailable at price time' USING ERRCODE='22023';
            END IF;
        ELSIF row_fields ?| ARRAY['symbol','cb','pb','per','peg','pr','pb_rating','per_rating','peg_rating','pr_rating'] THEN
            RAISE EXCEPTION 'Index has company-only fields' USING ERRCODE='22023';
        END IF;
        FOR key IN SELECT jsonb_object_keys(row_fields) LOOP
            IF NOT key=ANY(fields) THEN RAISE EXCEPTION 'Unknown application field' USING ERRCODE='22023'; END IF;
            IF key IN ('date','c_name','symbol') THEN CONTINUE;
            ELSIF key='data_chart' THEN
                IF jsonb_typeof(row_fields->key)<>'string' OR length(row_fields->>key)>195 THEN
                    RAISE EXCEPTION 'Invalid application chart' USING ERRCODE='22023'; END IF;
            ELSIF key LIKE '%\_rating' ESCAPE '\' THEN
                IF row_fields->>key NOT IN ('green','orange','red') OR jsonb_typeof(row_fields->key)<>'string' THEN
                    RAISE EXCEPTION 'Invalid application rating' USING ERRCODE='22023'; END IF;
            ELSE
                IF jsonb_typeof(row_fields->key)<>'number' OR abs((row_fields->>key)::numeric)>1e30 THEN
                    RAISE EXCEPTION 'Invalid application number' USING ERRCODE='22023'; END IF;
                IF key='qty_traded' AND ((row_fields->>key)::numeric<>trunc((row_fields->>key)::numeric)
                    OR (row_fields->>key)::numeric NOT BETWEEN 0 AND 9223372036854775807) THEN
                    RAISE EXCEPTION 'Invalid application quantity' USING ERRCODE='22023'; END IF;
            END IF;
        END LOOP;
    END LOOP;
    FOR entry IN SELECT value FROM jsonb_array_elements(doc->'excluded') LOOP
        asset:=entry->>'asset_key';
        IF asset IS NULL OR asset=ANY(seen) OR NOT EXISTS(
            SELECT 1 FROM jsonb_array_elements(head.body->'rows') r WHERE r->>'asset_key'=asset) THEN
            RAISE EXCEPTION 'Invalid excluded identity' USING ERRCODE='22023';
        END IF;
        seen:=array_append(seen,asset);
    END LOOP;
    SELECT * INTO old FROM app_feed.application_latest WHERE provider=lease.provider;
    IF FOUND AND old.archive_digest=head.archive_digest AND old.payload_sha256<>p_payload_sha256 THEN
        RAISE EXCEPTION 'Conflicting application rows for accepted capture' USING ERRCODE='22023';
    END IF;
    IF FOUND AND old.payload_sha256=p_payload_sha256 THEN
        PERFORM app_recurring.require_lease(lease.provider,'projections',lease.id);
        PERFORM app_recurring.require_lease(lease.provider,'shadow_feed',lease.id);
        RETURN p_payload_sha256;
    END IF;
    IF pg_database_size(current_database())+octet_length(p_document)+1048576>ctl.max_database_bytes THEN
        RAISE EXCEPTION 'Application row capacity guard' USING ERRCODE='54000';
    END IF;
    INSERT INTO app_feed.application_latest VALUES(lease.provider,head.archive_digest,head.payload_sha256,
        p_payload_sha256,head.captured_at,doc)
    ON CONFLICT(provider) DO UPDATE SET archive_digest=excluded.archive_digest,
        quote_payload_sha256=excluded.quote_payload_sha256,payload_sha256=excluded.payload_sha256,
        captured_at=excluded.captured_at,body=excluded.body;
    PERFORM app_recurring.require_lease(lease.provider,'projections',lease.id);
    PERFORM app_recurring.require_lease(lease.provider,'shadow_feed',lease.id);
    RETURN p_payload_sha256;
END $$;

REVOKE ALL ON FUNCTION public.publish_shadow_application_rows_recurring_v1(text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.publish_shadow_application_rows_recurring_v1(text,text) TO service_role;

CREATE FUNCTION public.read_shadow_application_feed_recurring_v1()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE
    result jsonb; full_head app_feed.application_latest%ROWTYPE; digest text;
    lease app_recurring.runs%ROWTYPE; quote jsonb; item jsonb; output jsonb:='[]'::jsonb;
    price text; expiry timestamptz;
BEGIN
    result:=public.read_shadow_market_feed_recurring_v1();
    result:=result||jsonb_build_object('contract','app-market-preview/v3');
    IF NOT EXISTS(SELECT 1 FROM app_feed.application_control WHERE singleton AND enabled)
       OR result->>'status'<>'AVAILABLE' THEN
        RETURN result||jsonb_build_object('status','DISABLED','rows','[]'::jsonb);
    END IF;
    SELECT a.* INTO full_head FROM app_feed.application_latest a JOIN app_feed.latest f
        ON a.provider=f.provider AND a.archive_digest=f.archive_digest AND a.quote_payload_sha256=f.payload_sha256
        JOIN app_feed.control c ON c.singleton AND c.enabled AND c.provider_namespace=a.provider
        JOIN app_feed.application_control ac ON ac.singleton AND ac.enabled
            AND ac.fields_sha256=a.body->>'application_fields_sha256';
    IF NOT FOUND THEN RETURN result||jsonb_build_object('status','WAITING','rows','[]'::jsonb); END IF;
    BEGIN lease:=app_recurring.bound_lease(full_head.archive_digest,'projections');
    EXCEPTION WHEN insufficient_privilege THEN
        RETURN result||jsonb_build_object('status','DISABLED','rows','[]'::jsonb);
    END;
    FOR quote IN SELECT value FROM jsonb_array_elements(result->'rows') LOOP
        quote:=jsonb_build_object('reference_price',NULL,'reference_conflict',false)||quote;
        price:=coalesce(quote->>'price_decimal',quote->'reference_price'->>'price_decimal');
        expiry:=least(coalesce((quote->>'expires_at')::timestamptz,
                             (quote->'reference_price'->>'expires_at')::timestamptz));
        SELECT r->'row' INTO item FROM jsonb_array_elements(full_head.body->'rows') r
            WHERE r->>'asset_key'=quote->>'asset_key';
        IF price IS NULL OR item IS NULL OR expiry<=clock_timestamp() THEN item:=NULL; END IF;
        output:=output||jsonb_build_array(quote||jsonb_build_object('application_fields',item,
            'application_expires_at',CASE WHEN item IS NOT NULL THEN expiry END));
    END LOOP;
    PERFORM app_recurring.require_lease(lease.provider,'projections',lease.id);
    RETURN result||jsonb_build_object('rows',output);
END $$;

REVOKE ALL ON FUNCTION public.read_shadow_application_feed_recurring_v1() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.read_shadow_application_feed_recurring_v1() TO authenticated;

CREATE FUNCTION public.reserve_subject_market_archive_recurring_v1(p_digest text,p_provider text,p_kind text,p_slot timestamptz,
    p_completed_at timestamptz,p_completeness text,p_bytes bigint,p_subject_key text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_recurring.runs%ROWTYPE; old_subject text; result jsonb;
BEGIN
    lease:=app_recurring.require_lease(p_provider,'archive');
    IF p_kind IS DISTINCT FROM 'fundamentals' OR p_subject_key IS NULL
       OR p_subject_key !~ '^symbol:[A-Z0-9][A-Z0-9._-]{0,31}$' THEN
        RAISE EXCEPTION 'Invalid archive subject' USING ERRCODE='22023';
    END IF;
    SELECT subject_key INTO old_subject FROM app_archive.subjects WHERE digest=p_digest;
    IF (FOUND AND old_subject<>p_subject_key) OR (NOT FOUND AND EXISTS(
        SELECT 1 FROM app_archive.objects WHERE digest=p_digest)) THEN
        RAISE EXCEPTION 'Cannot reassign or adopt archive subject' USING ERRCODE='22023';
    END IF;
    result:=public.reserve_market_archive_recurring_v1(p_digest,p_provider,p_kind,p_slot,p_completed_at,p_completeness,p_bytes);
    INSERT INTO app_archive.subjects VALUES(p_digest,p_subject_key) ON CONFLICT(digest) DO NOTHING;
    PERFORM app_recurring.require_lease(p_provider,'archive',lease.id);
    RETURN result;
END $$;

REVOKE ALL ON FUNCTION public.reserve_subject_market_archive_recurring_v1(text,text,text,timestamptz,timestamptz,text,bigint,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.reserve_subject_market_archive_recurring_v1(text,text,text,timestamptz,timestamptz,text,bigint,text) TO service_role;

CREATE FUNCTION public.finalize_subject_market_archive_recurring_v1(p_digest text,p_subject_key text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_recurring.runs%ROWTYPE; saved app_archive.objects%ROWTYPE;
BEGIN
    lease:=app_recurring.bound_lease(p_digest,'archive');
    PERFORM pg_catalog.pg_advisory_xact_lock(731905220018);
    SELECT a.* INTO saved FROM app_archive.objects a JOIN app_archive.subjects s
        ON s.digest=a.digest AND s.subject_key=p_subject_key WHERE a.digest=p_digest FOR UPDATE OF a;
    IF NOT FOUND OR saved.kind<>'fundamentals' THEN
        RAISE EXCEPTION 'Matching subject reservation required' USING ERRCODE='22023';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled)
       OR NOT EXISTS(SELECT 1 FROM app_archive.providers WHERE namespace=saved.provider AND enabled)
       OR NOT EXISTS(SELECT 1 FROM storage.buckets WHERE id='private-market-evidence' AND public=false) THEN
        RAISE EXCEPTION 'Archive disabled or not private' USING ERRCODE='42501';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM storage.objects o WHERE o.bucket_id='private-market-evidence'
       AND o.name=saved.object_path AND o.metadata->>'size'=saved.compressed_bytes::text) THEN
        RAISE EXCEPTION 'Object not verified' USING ERRCODE='22023';
    END IF;
    UPDATE app_archive.objects SET state='STORED',verified_at=coalesce(verified_at,clock_timestamp()) WHERE digest=p_digest;
    IF saved.completeness='COMPLETE' THEN
        INSERT INTO app_recurring.subject_slots VALUES(saved.provider,saved.kind,saved.slot,p_subject_key,
            (SELECT run_id FROM app_recurring.objects WHERE digest=p_digest),saved.digest)
            ON CONFLICT(provider,kind,slot,subject_key,run_id) DO NOTHING;
    END IF;
    PERFORM app_recurring.require_lease(lease.provider,'archive',lease.id);
    RETURN p_digest;
END $$;

REVOKE ALL ON FUNCTION public.finalize_subject_market_archive_recurring_v1(text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.finalize_subject_market_archive_recurring_v1(text,text) TO service_role;

CREATE FUNCTION public.market_archive_subject_complete_recurring_v1(p_provider text,p_kind text,p_slot timestamptz,p_subject_key text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_recurring.runs%ROWTYPE; saved app_archive.objects%ROWTYPE;
BEGIN
    IF p_kind IS DISTINCT FROM 'fundamentals' OR p_subject_key IS NULL
       OR p_subject_key !~ '^symbol:[A-Z0-9][A-Z0-9._-]{0,31}$' THEN
        RAISE EXCEPTION 'Invalid archive subject' USING ERRCODE='22023';
    END IF;
    BEGIN lease:=app_recurring.require_lease(p_provider,'archive');
    EXCEPTION WHEN insufficient_privilege THEN RETURN false; END;
    SELECT a.* INTO saved FROM app_recurring.subject_slots s JOIN app_archive.subjects sub
        ON sub.digest=s.digest AND sub.subject_key=s.subject_key
        JOIN app_archive.objects a ON a.digest=s.digest AND a.state='STORED'
        JOIN app_archive.control c ON c.singleton AND c.enabled
        JOIN app_archive.providers p ON p.namespace=a.provider AND p.enabled
        JOIN app_recurring.objects b ON b.digest=a.digest AND EXISTS(SELECT 1 FROM app_recurring.runs rr WHERE rr.id=b.run_id AND rr.plan_sha256=lease.plan_sha256 AND rr.revoked_at IS NULL)
        WHERE s.provider=p_provider AND s.kind=p_kind AND s.slot=p_slot AND s.subject_key=p_subject_key
          ;
    IF NOT FOUND THEN RETURN false; END IF;
    IF NOT EXISTS(SELECT 1 FROM storage.buckets WHERE id='private-market-evidence' AND public=false)
       OR NOT EXISTS(SELECT 1 FROM storage.objects o WHERE o.bucket_id='private-market-evidence'
          AND o.name=saved.object_path AND o.metadata->>'size'=saved.compressed_bytes::text) THEN
        RAISE EXCEPTION 'Committed subject object missing or not private' USING ERRCODE='22023';
    END IF;
    PERFORM app_recurring.bound_lease(saved.digest,'archive');
    PERFORM app_recurring.require_lease(p_provider,'archive',lease.id);
    RETURN true;
END $$;

REVOKE ALL ON FUNCTION public.market_archive_subject_complete_recurring_v1(text,text,timestamptz,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.market_archive_subject_complete_recurring_v1(text,text,timestamptz,text) TO service_role;

CREATE FUNCTION public.market_archive_subject_admission_recurring_v1(p_provider text,p_subject_key text,p_projection boolean)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_recurring.runs%ROWTYPE; settings app_archive.control%ROWTYPE;
        used numeric; outstanding numeric;
BEGIN
    IF p_subject_key IS NULL OR p_subject_key !~ '^symbol:[A-Z0-9][A-Z0-9._-]{0,31}$'
       OR p_projection IS NULL THEN
        RAISE EXCEPTION 'Invalid archive subject admission' USING ERRCODE='22023';
    END IF;
    BEGIN lease:=app_recurring.require_lease(p_provider,'archive');
    EXCEPTION WHEN insufficient_privilege THEN RETURN false; END;
    IF NOT 'fundamentals'=ANY(lease.kinds) OR lease.expires_at<=clock_timestamp()+interval '300 seconds'
       OR NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled)
       OR NOT EXISTS(SELECT 1 FROM app_archive.providers WHERE namespace=p_provider AND enabled)
       OR NOT EXISTS(SELECT 1 FROM storage.buckets WHERE id='private-market-evidence' AND public=false)
       OR (SELECT count(*) FROM app_recurring.objects WHERE run_id=lease.id)>=lease.max_objects
       OR (SELECT coalesce(sum(o.compressed_bytes),0) FROM app_recurring.objects b
           JOIN app_archive.objects o ON o.digest=b.digest WHERE b.run_id=lease.id)+8388608>lease.max_bytes THEN
        RETURN false;
    END IF;
    IF p_projection AND (NOT 'projections'=ANY(lease.capabilities) OR NOT EXISTS(
        SELECT 1 FROM app_recurring.projection_control(p_provider) WHERE singleton AND enabled AND provider_namespace=p_provider)) THEN
        RETURN false;
    END IF;
    BEGIN PERFORM app_recurring.check_new_object(p_provider,'fundamentals',date_trunc('hour',clock_timestamp()),clock_timestamp(),8388608);
    EXCEPTION WHEN insufficient_privilege OR program_limit_exceeded THEN RETURN false; END;
    SELECT * INTO settings FROM app_archive.control WHERE singleton;
    IF pg_database_size(current_database())+1048576>settings.max_database_bytes
       OR EXISTS(SELECT 1 FROM storage.objects WHERE metadata->>'size' IS NULL
            OR metadata->>'size' !~ '^[0-9]{1,12}$') THEN RETURN false; END IF;
    SELECT coalesce(sum((metadata->>'size')::numeric),0) INTO used FROM storage.objects;
    SELECT coalesce(sum(a.compressed_bytes),0) INTO outstanding FROM app_archive.objects a
        WHERE a.state='RESERVED' AND NOT EXISTS(SELECT 1 FROM storage.objects o
            WHERE o.bucket_id='private-market-evidence' AND o.name=a.object_path);
    IF used+outstanding+8388608>settings.max_storage_bytes THEN RETURN false; END IF;
    INSERT INTO app_recurring.admissions(provider,kind,slot,run_id) VALUES(p_provider,'fundamentals',date_trunc('hour',clock_timestamp()),lease.id) ON CONFLICT DO NOTHING;
    PERFORM app_recurring.require_lease(p_provider,'archive',lease.id);
    RETURN true;
END $$;

REVOKE ALL ON FUNCTION public.market_archive_subject_admission_recurring_v1(text,text,boolean) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.market_archive_subject_admission_recurring_v1(text,text,boolean) TO service_role;

CREATE FUNCTION public.read_enrichment_context_recurring_v1(p_provider text,p_index_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_recurring.runs%ROWTYPE; result jsonb; companies jsonb; price_companies jsonb;
BEGIN
    lease:=app_recurring.require_lease(p_provider,'projections');
    IF p_index_sha256 IS NULL OR p_index_sha256 !~ '^[a-f0-9]{64}$'
       OR NOT EXISTS(SELECT 1 FROM app_recurring.projection_control(p_provider) WHERE singleton AND enabled
            AND provider_namespace=p_provider AND fundamental_index_sha256=p_index_sha256)
       OR NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled)
       OR NOT EXISTS(SELECT 1 FROM app_archive.providers WHERE namespace=p_provider AND enabled) THEN
        RAISE EXCEPTION 'Enrichment context disabled or index mismatch' USING ERRCODE='42501';
    END IF;
    IF (SELECT count(*)>2000 OR count(*)<>count(DISTINCT name) FROM public.company)
       OR EXISTS(SELECT 1 FROM public.company WHERE name IS NULL OR length(name) NOT BETWEEN 1 AND 200) THEN
        RAISE EXCEPTION 'Ambiguous or oversized company context' USING ERRCODE='22023';
    END IF;
    SELECT coalesce(jsonb_object_agg(name,jsonb_build_object(
        'bpa',bpa,'sector',sector,'fiscal_year',fiscal_year) ORDER BY id),'{}'::jsonb)
        INTO companies FROM public.company;
    SELECT coalesce(jsonb_object_agg(c.id,jsonb_build_object('name',c.name,
        'bpa',c.bpa,'tc5',c.tc5,'roe',c.roe,'na',c.na,'cp',c.cp,'net_profit',c.net_profit,
        'date',c.date,'available_at',greatest(c.date,(SELECT max(a.completed_at)
            FROM app_projection.accepted_rows a WHERE a.kind='fundamentals' AND
            a.target_key=encode(sha256(convert_to(jsonb_build_array(c.name)::text,'UTF8')),'hex')))) ORDER BY c.id),'{}'::jsonb)
        INTO price_companies FROM public.company c;
    result:=jsonb_build_object('contract','private-enrichment-context/v2',
        'provider_namespace',p_provider,'index_sha256',p_index_sha256,
        'observed_at',clock_timestamp(),'companies',companies,'price_companies',price_companies);
    IF octet_length(result::text)>524288 THEN
        RAISE EXCEPTION 'Enrichment context exceeds limit' USING ERRCODE='54000';
    END IF;
    PERFORM app_recurring.require_lease(p_provider,'projections',lease.id);
    RETURN result;
END $$;

REVOKE ALL ON FUNCTION public.read_enrichment_context_recurring_v1(text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.read_enrichment_context_recurring_v1(text,text) TO service_role;

CREATE FUNCTION public.market_archive_acquisition_admission_recurring_v1(
    p_provider text,p_kind text,p_slot timestamptz,p_shadow boolean,p_projection boolean)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_recurring.runs%ROWTYPE; settings app_archive.control%ROWTYPE;
    used numeric; outstanding numeric;
BEGIN
    IF p_provider IS NULL OR p_provider !~ '^feed_[a-f0-9]{16}$'
       OR p_kind IS NULL OR p_kind NOT IN ('quotes','depth','dividends')
       OR p_slot IS NULL OR NOT isfinite(p_slot) OR p_shadow IS NULL OR p_projection IS NULL
       OR (p_shadow AND p_kind<>'quotes') OR (p_projection AND p_kind NOT IN ('quotes','dividends')) THEN
        RAISE EXCEPTION 'Invalid acquisition admission' USING ERRCODE='22023';
    END IF;
    BEGIN lease:=app_recurring.require_lease(p_provider,'archive');
    EXCEPTION WHEN insufficient_privilege THEN RETURN false; END;
    IF NOT p_kind=ANY(lease.kinds) OR lease.expires_at<=clock_timestamp()+interval '300 seconds'
       OR p_slot>clock_timestamp() OR p_slot<clock_timestamp()-interval '26 hours'
       OR NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled)
       OR NOT EXISTS(SELECT 1 FROM app_archive.providers WHERE namespace=p_provider AND enabled)
       OR NOT EXISTS(SELECT 1 FROM storage.buckets WHERE id='private-market-evidence' AND public=false)
       OR (SELECT count(*) FROM app_recurring.objects WHERE run_id=lease.id)>=lease.max_objects
       OR (SELECT coalesce(sum(o.compressed_bytes),0) FROM app_recurring.objects b
           JOIN app_archive.objects o ON o.digest=b.digest WHERE b.run_id=lease.id)+8388608>lease.max_bytes THEN
        RETURN false;
    END IF;
    IF p_shadow AND (NOT 'shadow_feed'=ANY(lease.capabilities) OR NOT EXISTS(
        SELECT 1 FROM app_feed.control WHERE singleton AND enabled AND provider_namespace=p_provider)) THEN
        RETURN false;
    END IF;
    IF p_projection AND (NOT 'projections'=ANY(lease.capabilities)
       OR (p_kind='dividends' AND NOT EXISTS(SELECT 1 FROM app_recurring.projection_control(p_provider)
           WHERE singleton AND enabled AND provider_namespace=p_provider))
       OR (p_kind='quotes' AND (NOT p_shadow OR NOT EXISTS(SELECT 1 FROM app_feed.application_control
           WHERE singleton AND enabled)))) THEN
        RETURN false;
    END IF;
    IF public.market_archive_slot_complete_recurring_v1(p_provider,p_kind,p_slot) THEN RETURN false; END IF;
    BEGIN PERFORM app_recurring.check_new_object(p_provider,p_kind,p_slot,clock_timestamp(),8388608);
    EXCEPTION WHEN insufficient_privilege OR program_limit_exceeded THEN RETURN false; END;
    SELECT * INTO settings FROM app_archive.control WHERE singleton;
    IF pg_database_size(current_database())+1048576>settings.max_database_bytes
       OR EXISTS(SELECT 1 FROM storage.objects WHERE metadata->>'size' IS NULL
           OR metadata->>'size' !~ '^[0-9]{1,12}$') THEN RETURN false; END IF;
    SELECT coalesce(sum((metadata->>'size')::numeric),0) INTO used FROM storage.objects;
    SELECT coalesce(sum(a.compressed_bytes),0) INTO outstanding FROM app_archive.objects a
        WHERE a.state='RESERVED' AND NOT EXISTS(SELECT 1 FROM storage.objects o
            WHERE o.bucket_id='private-market-evidence' AND o.name=a.object_path);
    IF used+outstanding+8388608>settings.max_storage_bytes THEN RETURN false; END IF;
    INSERT INTO app_recurring.admissions(provider,kind,slot,run_id) VALUES(p_provider,p_kind,p_slot,lease.id) ON CONFLICT DO NOTHING;
    PERFORM app_recurring.require_lease(p_provider,'archive',lease.id);
    RETURN true;
END $$;

REVOKE ALL ON FUNCTION public.market_archive_acquisition_admission_recurring_v1(text,text,timestamptz,boolean,boolean) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.market_archive_acquisition_admission_recurring_v1(text,text,timestamptz,boolean,boolean) TO service_role;

CREATE FUNCTION public.read_price_company_context_recurring_v1(p_provider text,p_mapping_document text,
    p_mapping_sha256 text,p_recipe_sha256 text,p_fields_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_recurring.runs%ROWTYPE; again app_recurring.runs%ROWTYPE;
    mapping jsonb; item jsonb; result jsonb; companies jsonb;
    identifiers text[]:=ARRAY[]::text[]; names text[]:=ARRAY[]::text[];
    symbols text[]:=ARRAY[]::text[]; sources text[]:=ARRAY[]::text[];
    stock_count integer; matched integer; observed timestamptz;
BEGIN
    IF p_provider IS NULL OR p_provider !~ '^feed_[a-f0-9]{16}$'
       OR p_mapping_document IS NULL OR octet_length(p_mapping_document)>1048576
       OR p_mapping_sha256 IS NULL OR p_mapping_sha256 !~ '^[a-f0-9]{64}$'
       OR p_recipe_sha256 IS NULL OR p_recipe_sha256 !~ '^[a-f0-9]{64}$'
       OR p_fields_sha256 IS NULL OR p_fields_sha256 !~ '^[a-f0-9]{64}$'
       OR encode(sha256(convert_to(p_mapping_document,'UTF8')),'hex')<>p_mapping_sha256 THEN
        RAISE EXCEPTION 'Invalid price context pins' USING ERRCODE='22023';
    END IF;
    lease:=app_recurring.require_lease(p_provider,'archive');
    again:=app_recurring.require_lease(p_provider,'shadow_feed',lease.id);
    again:=app_recurring.require_lease(p_provider,'projections',lease.id);
    IF NOT 'quotes'=ANY(lease.kinds)
       OR NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled)
       OR NOT EXISTS(SELECT 1 FROM app_archive.providers WHERE namespace=p_provider AND enabled)
       OR NOT EXISTS(SELECT 1 FROM storage.buckets WHERE id='private-market-evidence' AND public=false)
       OR NOT EXISTS(SELECT 1 FROM app_feed.control WHERE singleton AND enabled
            AND provider_namespace=p_provider AND mapping_sha256=p_mapping_sha256
            AND recipe_sha256=p_recipe_sha256)
       OR NOT EXISTS(SELECT 1 FROM app_feed.application_control WHERE singleton AND enabled
            AND fields_sha256=p_fields_sha256) THEN
        RAISE EXCEPTION 'Price context disabled or unapproved' USING ERRCODE='42501';
    END IF;
    mapping:=p_mapping_document::jsonb;
    IF mapping->>'contract' IS DISTINCT FROM 'private-app-mapping/v1'
       OR mapping->>'provider_namespace' IS DISTINCT FROM p_provider
       OR jsonb_typeof(mapping->'stocks') IS DISTINCT FROM 'array'
       OR jsonb_typeof(mapping->'indices') IS DISTINCT FROM 'array'
       OR jsonb_array_length(mapping->'indices')<>1
       OR jsonb_array_length(mapping->'stocks') NOT BETWEEN 1 AND 2047 THEN
        RAISE EXCEPTION 'Invalid price context mapping' USING ERRCODE='22023';
    END IF;
    stock_count:=jsonb_array_length(mapping->'stocks');
    FOR item IN SELECT value FROM jsonb_array_elements((mapping->'stocks')||(mapping->'indices')) LOOP
        IF jsonb_typeof(item) IS DISTINCT FROM 'object'
           OR (SELECT count(*) FROM jsonb_object_keys(item))<>5
           OR item-ARRAY['asset_key','company_id','c_name','symbol','source_identity']<> '{}'::jsonb
           OR jsonb_typeof(item->'asset_key') IS DISTINCT FROM 'string'
           OR jsonb_typeof(item->'c_name') IS DISTINCT FROM 'string'
           OR jsonb_typeof(item->'symbol') IS DISTINCT FROM 'string'
           OR jsonb_typeof(item->'source_identity') IS DISTINCT FROM 'string'
           OR length(item->>'asset_key') NOT BETWEEN 1 AND 300
           OR length(item->>'c_name') NOT BETWEEN 1 AND 200
           OR length(item->>'symbol') NOT BETWEEN 1 AND 200
           OR length(item->>'source_identity') NOT BETWEEN 1 AND 200
           OR (item->>'c_name')=ANY(names) OR (item->>'symbol')=ANY(symbols)
           OR (item->>'source_identity')=ANY(sources) THEN
            RAISE EXCEPTION 'Ambiguous context identity' USING ERRCODE='22023';
        END IF;
        names:=array_append(names,item->>'c_name');
        symbols:=array_append(symbols,item->>'symbol');
        sources:=array_append(sources,item->>'source_identity');
        IF item->>'asset_key'='index:MASI' THEN
            IF item IS DISTINCT FROM (mapping->'indices'->0)
               OR item->'company_id' IS DISTINCT FROM 'null'::jsonb
               OR item->>'c_name'<>'MASI' OR item->>'symbol'<>'MASI' THEN
                RAISE EXCEPTION 'Invalid context index' USING ERRCODE='22023';
            END IF;
        ELSE
            IF jsonb_typeof(item->'company_id') IS DISTINCT FROM 'string'
               OR length(item->>'company_id') NOT BETWEEN 1 AND 200
               OR item->>'asset_key' IS DISTINCT FROM 'company:'||(item->>'company_id')
               OR (item->>'company_id')=ANY(identifiers)
               OR NOT EXISTS(SELECT 1 FROM public.company c WHERE c.id=item->>'company_id'
                    AND c.name=item->>'c_name')
               OR (SELECT count(*) FROM public.format f WHERE f.name=item->>'c_name'
                    AND f.symbol=item->>'symbol')<>1
               OR (SELECT count(*) FROM public.format f WHERE f.name=item->>'c_name')<>1
               OR (SELECT count(*) FROM public.format f WHERE f.symbol=item->>'symbol')<>1 THEN
                RAISE EXCEPTION 'Current company mapping differs' USING ERRCODE='22023';
            END IF;
            identifiers:=array_append(identifiers,item->>'company_id');
        END IF;
    END LOOP;
    IF cardinality(identifiers)<>stock_count THEN
        RAISE EXCEPTION 'Invalid stock/index separation' USING ERRCODE='22023';
    END IF;
    observed:=clock_timestamp();
    SELECT count(*),coalesce(jsonb_object_agg(c.id,jsonb_build_object('name',c.name,
        'bpa',c.bpa,'tc5',c.tc5,'roe',c.roe,'na',c.na,'cp',c.cp,'net_profit',c.net_profit,
        'date',c.date,'available_at',greatest(c.date,(SELECT max(a.completed_at)
            FROM app_projection.accepted_rows a WHERE a.kind='fundamentals' AND
            a.target_key=encode(sha256(convert_to(jsonb_build_array(c.name)::text,'UTF8')),'hex'))))
        ORDER BY c.id),'{}'::jsonb) INTO matched,companies FROM public.company c
        WHERE c.id=ANY(identifiers);
    IF matched<>stock_count THEN
        RAISE EXCEPTION 'Company inputs changed' USING ERRCODE='22023';
    END IF;
    result:=jsonb_build_object('contract','private-price-company-context/v1',
        'provider_namespace',p_provider,'mapping_sha256',p_mapping_sha256,
        'recipe_sha256',p_recipe_sha256,'application_fields_sha256',p_fields_sha256,
        'observed_at',observed,'price_companies',companies);
    IF octet_length(result::text)>524288 THEN
        RAISE EXCEPTION 'Price context exceeds limit' USING ERRCODE='54000';
    END IF;
    PERFORM app_recurring.require_lease(p_provider,'archive',lease.id);
    PERFORM app_recurring.require_lease(p_provider,'shadow_feed',lease.id);
    PERFORM app_recurring.require_lease(p_provider,'projections',lease.id);
    RETURN result;
END $$;

REVOKE ALL ON FUNCTION public.read_price_company_context_recurring_v1(text,text,text,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.read_price_company_context_recurring_v1(text,text,text,text,text) TO service_role;

CREATE FUNCTION app_recurring.reference_for_preview(item jsonb,c jsonb,now_at timestamptz)
RETURNS jsonb LANGUAGE plpgsql SET search_path='' AS $$
DECLARE ref jsonb:=item->'reference_price'; captured timestamptz; expiry timestamptz;
BEGIN
 IF ref IS NULL OR ref='null'::jsonb THEN RETURN NULL; END IF;
 PERFORM app_recurring.bound_lease(c->>'archive_sha256','shadow_feed');
 captured:=(ref->>'captured_at')::timestamptz;
 expiry:=least(captured+make_interval(secs=>(c->>'capture_max_age_seconds')::integer),
    (((c->>'market_date')::date+1)::timestamp AT TIME ZONE 'Africa/Casablanca'));
 IF now_at<captured OR now_at>=expiry THEN RETURN NULL; END IF;
 RETURN jsonb_build_object('price_decimal',ref->>'price_decimal','price_basis','INSTRUMENT_REFERENCE',
  'captured_at',captured,'expires_at',expiry,'source_event_at',NULL,'reported_day',NULL,
  'reported_time_timezone','UNKNOWN','prediction_eligible',false,'portfolio_valuation_eligible',false);
END $$;
REVOKE ALL ON FUNCTION app_recurring.reference_for_preview(jsonb,jsonb,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
DO $$ DECLARE source text; definition text; BEGIN
 SELECT prosrc,pg_get_functiondef(oid) INTO source,definition FROM pg_proc
 WHERE oid='app_trial_legacy.read_shadow_market_feed()'::regprocedure;
 IF encode(sha256(convert_to(source,'UTF8')),'hex')<>'f817cdc66637364bda880dc76390c433aa0ea8a99f202338c5c69b307d6f8acb' THEN
  RAISE EXCEPTION 'Unexpected legacy reader; recurring installation stopped';
 END IF;
 definition:=replace(definition,'app_trial_legacy.read_shadow_market_feed()', 'app_recurring.read_market_feed_impl()');
 definition:=replace(definition,'app_feed.reference_for_preview(', 'app_recurring.reference_for_preview(');
 EXECUTE definition;
END $$;
REVOKE ALL ON FUNCTION app_recurring.read_market_feed_impl() FROM PUBLIC,anon,authenticated,service_role;

-- Preserve the reviewed projection bodies; only the control lookup changes.
DO $$ DECLARE name text; expected text; source text; definition text; BEGIN
 FOREACH name IN ARRAY ARRAY['dividend','fundamental'] LOOP
  expected:=CASE WHEN name='dividend' THEN '316815457f0862c39fa1d3e4abd40e477fc6997ffd09e413ca505a944b8abb01'
    ELSE '03038405e3a0f69266b818254c369e0a71a81efc5b5f4ee2bfc4eee5c9338b30' END;
  SELECT prosrc,pg_get_functiondef(oid) INTO source,definition FROM pg_proc
    WHERE oid=to_regprocedure('app_trial_legacy.publish_'||name||'_projection(text,text)');
  IF encode(sha256(convert_to(source,'UTF8')),'hex') IS DISTINCT FROM expected THEN
   RAISE EXCEPTION 'Unexpected original projection validator';
  END IF;
  definition:=replace(definition,'app_trial_legacy.publish_'||name||'_projection(', 'app_recurring.publish_'||name||'_impl(');
  definition:=replace(definition,'SELECT * INTO ctl FROM app_projection.control WHERE singleton;',
    'SELECT * INTO ctl FROM app_recurring.projection_control(c->>''provider_namespace'');');
  EXECUTE definition;
  EXECUTE format('REVOKE ALL ON FUNCTION app_recurring.publish_%I_impl(text,text) FROM PUBLIC,anon,authenticated,service_role',name);
 END LOOP;
END $$;
