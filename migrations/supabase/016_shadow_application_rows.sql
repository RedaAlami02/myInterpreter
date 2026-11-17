-- STAGED ONLY. Full current display rows on the existing private shadow feed.
-- Requires SQL014/015. No recovered tables, original candidates or ledgers change.
-- No grants to app roles on storage; anonymous access remains denied.
DO $$ BEGIN
    IF to_regprocedure('app_feed.validate_reference_candidate(jsonb)') IS NULL
       OR NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND NOT enabled)
       OR NOT EXISTS(SELECT 1 FROM app_feed.control WHERE singleton AND NOT enabled)
       OR NOT EXISTS(SELECT 1 FROM app_projection.control WHERE singleton AND NOT enabled) THEN
        RAISE EXCEPTION 'Reviewed display feed and disabled controls required';
    END IF;
END $$;
CREATE TABLE app_feed.application_control (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    enabled boolean NOT NULL DEFAULT false,
    fields_sha256 text CHECK(fields_sha256 ~ '^[a-f0-9]{64}$'),
    max_database_bytes bigint NOT NULL DEFAULT 350000000
        CHECK(max_database_bytes BETWEEN 0 AND 350000000),
    CHECK(NOT enabled OR fields_sha256 IS NOT NULL)
);
INSERT INTO app_feed.application_control(singleton) VALUES(true);
CREATE TABLE app_feed.application_latest (
    provider text PRIMARY KEY REFERENCES app_feed.latest(provider),
    archive_digest text NOT NULL REFERENCES app_archive.objects(digest),
    quote_payload_sha256 text NOT NULL CHECK(quote_payload_sha256 ~ '^[a-f0-9]{64}$'),
    payload_sha256 text NOT NULL CHECK(payload_sha256 ~ '^[a-f0-9]{64}$'),
    captured_at timestamptz NOT NULL CHECK(isfinite(captured_at)),
    body jsonb NOT NULL CHECK(jsonb_typeof(body)='object')
);
ALTER TABLE app_feed.application_control ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_feed.application_latest ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE app_feed.application_control,app_feed.application_latest
    FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION public.publish_shadow_application_rows(p_document text,p_payload_sha256 text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE
    doc jsonb; ctl app_feed.application_control%ROWTYPE; head app_feed.latest%ROWTYPE;
    old app_feed.application_latest%ROWTYPE; lease app_trial.leases%ROWTYPE;
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
    lease:=app_trial.document_lease(p_document,'projections');
    PERFORM app_trial.require_lease(lease.provider,'shadow_feed',lease.id);
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
        PERFORM app_trial.require_lease(lease.provider,'projections',lease.id);
        PERFORM app_trial.require_lease(lease.provider,'shadow_feed',lease.id);
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
    PERFORM app_trial.require_lease(lease.provider,'projections',lease.id);
    PERFORM app_trial.require_lease(lease.provider,'shadow_feed',lease.id);
    RETURN p_payload_sha256;
END $$;
REVOKE ALL ON FUNCTION public.publish_shadow_application_rows(text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.publish_shadow_application_rows(text,text) TO service_role;

CREATE FUNCTION public.read_shadow_application_feed()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE
    result jsonb; full_head app_feed.application_latest%ROWTYPE; digest text;
    lease app_trial.leases%ROWTYPE; quote jsonb; item jsonb; output jsonb:='[]'::jsonb;
    price text; expiry timestamptz;
BEGIN
    result:=public.read_shadow_market_feed();
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
    BEGIN lease:=app_trial.bound_lease(full_head.archive_digest,'projections');
    EXCEPTION WHEN insufficient_privilege THEN
        RETURN result||jsonb_build_object('status','DISABLED','rows','[]'::jsonb);
    END;
    FOR quote IN SELECT value FROM jsonb_array_elements(result->'rows') LOOP
        quote:=jsonb_build_object('reference_price',NULL,'reference_conflict',false)||quote;
        price:=coalesce(quote->>'price_decimal',quote->'reference_price'->>'price_decimal');
        expiry:=least(coalesce((quote->>'expires_at')::timestamptz,
                             (quote->'reference_price'->>'expires_at')::timestamptz),lease.expires_at);
        SELECT r->'row' INTO item FROM jsonb_array_elements(full_head.body->'rows') r
            WHERE r->>'asset_key'=quote->>'asset_key';
        IF price IS NULL OR item IS NULL OR expiry<=clock_timestamp() THEN item:=NULL; END IF;
        output:=output||jsonb_build_array(quote||jsonb_build_object('application_fields',item,
            'application_expires_at',CASE WHEN item IS NOT NULL THEN expiry END));
    END LOOP;
    PERFORM app_trial.require_lease(lease.provider,'projections',lease.id);
    RETURN result||jsonb_build_object('rows',output);
END $$;
REVOKE ALL ON FUNCTION public.read_shadow_application_feed() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.read_shadow_application_feed() TO authenticated;
