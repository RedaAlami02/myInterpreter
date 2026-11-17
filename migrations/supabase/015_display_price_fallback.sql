-- STAGED ONLY. Requires SQL009/010/013/014. Install atomically with controls off.
-- Add instrument-reference display to the existing feed; no tables or new public
-- endpoints, no automatic activation. Historical v1 candidate/read rules remain.
DO $$ BEGIN
    IF EXISTS(SELECT 1 FROM app_archive.control WHERE enabled)
       OR EXISTS(SELECT 1 FROM app_feed.control WHERE enabled)
       OR EXISTS(SELECT 1 FROM app_projection.control WHERE enabled)
       OR EXISTS(SELECT 1 FROM app_trial.leases WHERE revoked_at IS NULL AND expires_at>clock_timestamp()) THEN
        RAISE EXCEPTION 'Disable services and revoke trials before feed upgrade';
    END IF;
END $$;

CREATE FUNCTION app_feed.validate_reference_candidate(c jsonb)
RETURNS void LANGUAGE plpgsql SET search_path='' AS $$
DECLARE item jsonb; ref jsonb; obs jsonb;
BEGIN
    IF c->>'contract' IS DISTINCT FROM 'app-market-candidate/v2' THEN RETURN; END IF;
    IF jsonb_typeof(c->'rows') IS DISTINCT FROM 'array' OR jsonb_array_length(c->'rows')>2048 THEN
        RAISE EXCEPTION 'Invalid display reference rows' USING ERRCODE='22023';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(c->'rows') LOOP
        IF NOT item ? 'reference_price' THEN
            RAISE EXCEPTION 'Explicit reference field required' USING ERRCODE='22023';
        END IF;
        ref:=item->'reference_price';
        IF jsonb_typeof(item->'reference_conflict') IS DISTINCT FROM 'boolean'
           OR (item->'reference_conflict'='true'::jsonb AND (
               item->>'status' IS DISTINCT FROM 'MISSING_QUOTE' OR item->>'instrument_type' IS DISTINCT FROM 'STOCK'
               OR ref IS DISTINCT FROM 'null'::jsonb)) THEN
            RAISE EXCEPTION 'Invalid reference conflict flag' USING ERRCODE='22023';
        END IF;
        IF ref='null'::jsonb THEN CONTINUE; END IF;
        IF jsonb_typeof(ref) IS DISTINCT FROM 'object' OR item->>'status' IS DISTINCT FROM 'MISSING_QUOTE'
           OR item->>'instrument_type' IS DISTINCT FROM 'STOCK'
           OR ref->>'price_basis' IS DISTINCT FROM 'INSTRUMENT_REFERENCE'
           OR ref->'captured_at' IS DISTINCT FROM c->'captured_at'
           OR ref->'source_event_at' IS DISTINCT FROM 'null'::jsonb
           OR ref->'reported_day' IS DISTINCT FROM 'null'::jsonb
           OR ref->'prediction_eligible' IS DISTINCT FROM 'false'::jsonb
           OR ref->'portfolio_valuation_eligible' IS DISTINCT FROM 'false'::jsonb
           OR jsonb_typeof(ref->'price_decimal') IS DISTINCT FROM 'string'
           OR coalesce(ref->>'price_decimal','') !~ '^[0-9]{1,13}(\.[0-9]{1,28})?$'
           OR jsonb_typeof(ref->'observations') IS DISTINCT FROM 'array' THEN
            RAISE EXCEPTION 'Invalid display reference' USING ERRCODE='22023';
        END IF;
        IF (SELECT count(*) FROM jsonb_object_keys(ref))<>8
           OR (ref->>'price_decimal')::numeric NOT BETWEEN 1e-28 AND 1000000000000
           OR jsonb_array_length(ref->'observations') NOT BETWEEN 1 AND 2048
           OR (SELECT count(DISTINCT r->>'observation_id') FROM jsonb_array_elements(ref->'observations') r)
                <>jsonb_array_length(ref->'observations') THEN
            RAISE EXCEPTION 'Invalid reference bounds' USING ERRCODE='22023';
        END IF;
        FOR obs IN SELECT value FROM jsonb_array_elements(ref->'observations') LOOP
            IF jsonb_typeof(obs) IS DISTINCT FROM 'object'
               OR (SELECT count(*) FROM jsonb_object_keys(obs))<>3
               OR coalesce(obs->>'observation_id','') !~ '^[a-f0-9]{64}$'
               OR jsonb_typeof(obs->'raw_row_index') IS DISTINCT FROM 'number'
               OR coalesce(obs->>'raw_row_index','') !~ '^[0-9]{1,4}$'
               OR jsonb_typeof(obs->'price_decimal') IS DISTINCT FROM 'string'
               OR coalesce(obs->>'price_decimal','') !~ '^[0-9]{1,13}(\.[0-9]{1,28})?$' THEN
                RAISE EXCEPTION 'Invalid reference observation' USING ERRCODE='22023';
            END IF;
            IF (obs->>'raw_row_index')::integer>5000 OR (obs->>'price_decimal')::numeric<>(ref->>'price_decimal')::numeric THEN
                RAISE EXCEPTION 'Conflicting reference observation' USING ERRCODE='22023';
            END IF;
        END LOOP;
    END LOOP;
END $$;

CREATE FUNCTION app_feed.reference_for_preview(item jsonb,c jsonb,now_at timestamptz)
RETURNS jsonb LANGUAGE plpgsql SET search_path='' AS $$
DECLARE ref jsonb:=item->'reference_price'; captured timestamptz; expiry timestamptz;
        lease app_trial.leases%ROWTYPE;
BEGIN
    IF ref IS NULL OR ref='null'::jsonb THEN RETURN NULL; END IF;
    lease:=app_trial.bound_lease(c->>'archive_sha256','shadow_feed');
    captured:=(ref->>'captured_at')::timestamptz;
    expiry:=least(lease.expires_at,captured+make_interval(secs=>(c->>'capture_max_age_seconds')::integer),
        (((c->>'market_date')::date+1)::timestamp AT TIME ZONE 'Africa/Casablanca'));
    IF now_at<captured OR now_at>=expiry THEN RETURN NULL; END IF;
    RETURN jsonb_build_object('price_decimal',ref->>'price_decimal','price_basis','INSTRUMENT_REFERENCE',
        'captured_at',captured,'expires_at',expiry,'source_event_at',NULL,'reported_day',NULL,
        'reported_time_timezone','UNKNOWN','prediction_eligible',false,'portfolio_valuation_eligible',false);
END $$;
REVOKE ALL ON FUNCTION app_feed.validate_reference_candidate(jsonb),
    app_feed.reference_for_preview(jsonb,jsonb,timestamptz) FROM PUBLIC,anon,authenticated,service_role;

-- Reuse the pinned legacy validators/read implementation, applying only these
-- explicit v2 additions. Refuse unknown/edited installed bodies rather than
-- replacing unrelated changes. The original v1 bytes remain in SQL010/bundles.
DO $$
DECLARE source text; changed text; target_oid oid; definition text;
BEGIN
    target_oid:=to_regprocedure('app_trial_legacy.publish_shadow_market_candidate(text,text)');
    SELECT prosrc,pg_get_functiondef(p.oid) INTO source,definition FROM pg_proc p WHERE p.oid=target_oid;
    IF encode(sha256(convert_to(source,'UTF8')),'hex') IS DISTINCT FROM '9f1989016141fd281a8f4c3f6e64a8d63757dce9ea7200a26a07a5b7db1dab02' THEN
        RAISE EXCEPTION 'Unexpected installed publication implementation';
    END IF;
    changed:=replace(source,$old$c->>'contract' IS DISTINCT FROM 'app-market-candidate/v1'$old$,
        $new$coalesce(c->>'contract','') NOT IN ('app-market-candidate/v1','app-market-candidate/v2')$new$);
    changed:=replace(changed,$old$c := p_document::jsonb;$old$,
        $new$c := p_document::jsonb; PERFORM app_feed.validate_reference_candidate(c);$new$);
    EXECUTE replace(definition,source,changed);

    target_oid:=to_regprocedure('app_trial_legacy.read_shadow_market_feed()');
    SELECT prosrc,pg_get_functiondef(p.oid) INTO source,definition FROM pg_proc p WHERE p.oid=target_oid;
    IF encode(sha256(convert_to(source,'UTF8')),'hex') IS DISTINCT FROM '84ddd2980da6da4c9b18ca5145b143346a698daafa6b3901574086b3f6eab392' THEN
        RAISE EXCEPTION 'Unexpected installed preview implementation';
    END IF;
    changed:=replace(source,$old$FOR item IN SELECT value FROM jsonb_array_elements(c->'rows') LOOP$old$,
        $new$IF c->>'contract'='app-market-candidate/v2' THEN
            result:=result||jsonb_build_object('contract','app-market-preview/v2'); END IF;
        FOR item IN SELECT value FROM jsonb_array_elements(c->'rows') LOOP$new$);
    changed:=replace(changed,$old$'portfolio_valuation_eligible',false,'prediction_eligible',false));$old$,
        $new$'portfolio_valuation_eligible',false,'prediction_eligible',false)
            ||CASE WHEN c->>'contract'='app-market-candidate/v2' THEN
                jsonb_build_object('reference_price',app_feed.reference_for_preview(item,c,now_at),
                    'reference_conflict',item->'reference_conflict')
              ELSE '{}'::jsonb END);$new$);
    EXECUTE replace(definition,source,changed);
END $$;
