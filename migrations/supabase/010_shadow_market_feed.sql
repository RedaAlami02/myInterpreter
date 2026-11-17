-- STAGED ONLY. Requires reviewed SQL009; no original application tables change.
CREATE SCHEMA app_feed;
REVOKE ALL ON SCHEMA app_feed FROM PUBLIC,anon,authenticated,service_role;
CREATE TABLE app_feed.control (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    enabled boolean NOT NULL DEFAULT false,
    provider_namespace text CHECK(provider_namespace ~ '^feed_[a-f0-9]{16}$'),
    mapping_sha256 text CHECK(mapping_sha256 ~ '^[a-f0-9]{64}$'),
    recipe_sha256 text CHECK(recipe_sha256 ~ '^[a-f0-9]{64}$'),
    CHECK(NOT enabled OR (provider_namespace IS NOT NULL AND mapping_sha256 IS NOT NULL AND recipe_sha256 IS NOT NULL))
);
INSERT INTO app_feed.control(singleton) VALUES(true);
CREATE TABLE app_feed.latest (
    provider text PRIMARY KEY REFERENCES app_archive.providers(namespace),
    archive_digest text NOT NULL REFERENCES app_archive.objects(digest),
    payload_sha256 text NOT NULL CHECK(payload_sha256 ~ '^[a-f0-9]{64}$'),
    captured_at timestamptz NOT NULL,
    body jsonb NOT NULL CHECK(pg_column_size(body) <= 2097152),
    stored_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE app_feed.control ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_feed.latest ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA app_feed FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION public.publish_shadow_market_candidate(p_document text,p_payload_sha256 text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE c jsonb; ctl app_feed.control%ROWTYPE; old app_feed.latest%ROWTYPE;
        archive app_archive.objects%ROWTYPE; item jsonb; moment timestamptz;
        prepared timestamptz; companies integer; total integer;
BEGIN
    IF p_document IS NULL OR octet_length(p_document) > 2097152 OR p_payload_sha256 IS NULL
       OR encode(pg_catalog.sha256(convert_to(p_document,'UTF8')),'hex') <> p_payload_sha256 THEN
        RAISE EXCEPTION 'Invalid candidate payload' USING ERRCODE='22023';
    END IF;
    c := p_document::jsonb;
    SELECT * INTO ctl FROM app_feed.control WHERE singleton;
    IF ctl.provider_namespace IS NULL OR ctl.mapping_sha256 IS NULL OR ctl.recipe_sha256 IS NULL
       OR c->>'provider_namespace' IS DISTINCT FROM ctl.provider_namespace
       OR c->>'mapping_sha256' IS DISTINCT FROM ctl.mapping_sha256
       OR c->>'recipe_sha256' IS DISTINCT FROM ctl.recipe_sha256
       OR c->>'contract' IS DISTINCT FROM 'app-market-candidate/v1'
       OR c->>'mode' IS DISTINCT FROM 'SHADOW_ONLY'
       OR c->>'source_execution' IS DISTINCT FROM 'CURRENT_ACQUISITION'
       OR c->>'identity_evidence' IS DISTINCT FROM 'NORMALIZER_IDS_VERIFIED'
       OR c->'prediction_eligible' IS DISTINCT FROM 'false'::jsonb
       OR c->'portfolio_valuation_eligible' IS DISTINCT FROM 'false'::jsonb
       OR c->>'market_session_state' IS DISTINCT FROM 'UNKNOWN'
       OR coalesce(c->>'acquisition_completeness','') NOT IN ('COMPLETE','INCOMPLETE')
       OR jsonb_typeof(c->'rows') IS DISTINCT FROM 'array'
       OR coalesce(c->>'capture_max_age_seconds','') !~ '^[0-9]{1,4}$'
       OR coalesce(c->>'source_max_age_seconds','') !~ '^[0-9]{1,5}$'
       OR (c->>'capture_max_age_seconds')::integer NOT BETWEEN 1 AND 3600
       OR (c->>'source_max_age_seconds')::integer NOT BETWEEN 1 AND 86400 THEN
        RAISE EXCEPTION 'Candidate contract or pin mismatch' USING ERRCODE='22023';
    END IF;
    IF coalesce(c->>'captured_at','') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$'
       OR coalesce(c->>'as_of','') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
        RAISE EXCEPTION 'Aware receipt times required' USING ERRCODE='22023';
    END IF;
    moment := (c->>'captured_at')::timestamptz;
    prepared := (c->>'as_of')::timestamptz;
    IF moment IS NULL OR prepared IS NULL OR NOT isfinite(moment) OR NOT isfinite(prepared)
       OR moment > prepared OR prepared > clock_timestamp()+interval '30 seconds'
       OR prepared < clock_timestamp()-interval '5 minutes'
       OR moment < clock_timestamp()-interval '20 minutes'
       OR c->>'market_date' IS DISTINCT FROM (moment AT TIME ZONE 'Africa/Casablanca')::date::text THEN
        RAISE EXCEPTION 'Invalid candidate cutoff' USING ERRCODE='22023';
    END IF;
    SELECT * INTO archive FROM app_archive.objects WHERE digest=c->>'archive_sha256';
    IF NOT FOUND OR archive.state <> 'STORED' OR archive.kind <> 'quotes'
       OR archive.provider <> ctl.provider_namespace OR moment < archive.slot OR moment > archive.completed_at
       OR c->>'acquisition_completeness' IS DISTINCT FROM archive.completeness
       OR NOT EXISTS(SELECT 1 FROM app_archive.providers WHERE namespace=ctl.provider_namespace AND enabled)
       OR NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled) THEN
        RAISE EXCEPTION 'Verified archive required' USING ERRCODE='42501';
    END IF;
    SELECT count(*) INTO companies FROM public.company;
    total := jsonb_array_length(c->'rows');
    IF total <> companies+1 OR total > 2048 OR (SELECT count(DISTINCT r->>'asset_key') FROM jsonb_array_elements(c->'rows') r) <> total
       OR (SELECT count(*) FROM jsonb_array_elements(c->'rows') r WHERE r->>'instrument_type'='INDEX') <> 1 THEN
        RAISE EXCEPTION 'Incomplete or duplicate candidate universe' USING ERRCODE='22023';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(c->'rows') LOOP
        IF item->>'instrument_type'='STOCK' THEN
            IF item->>'asset_key' IS DISTINCT FROM 'company:'||(item->>'company_id') OR NOT EXISTS(
                SELECT 1 FROM public.company co JOIN public.format f ON f.name=co.name
                WHERE co.id=item->>'company_id' AND co.name=item->>'c_name' AND f.symbol=item->>'symbol'
            ) THEN RAISE EXCEPTION 'Exact company mapping required' USING ERRCODE='22023'; END IF;
        ELSIF item->>'instrument_type'='INDEX' THEN
            IF item->>'asset_key' IS DISTINCT FROM 'index:MASI' OR item->>'c_name' IS DISTINCT FROM 'MASI'
               OR item->>'symbol' IS DISTINCT FROM 'MASI' OR item->'company_id' IS DISTINCT FROM 'null'::jsonb THEN
                RAISE EXCEPTION 'Explicit index mapping required' USING ERRCODE='22023';
            END IF;
        ELSE RAISE EXCEPTION 'Invalid instrument type' USING ERRCODE='22023'; END IF;
        IF item->'prediction_eligible' IS DISTINCT FROM 'false'::jsonb
           OR item->'portfolio_valuation_eligible' IS DISTINCT FROM 'false'::jsonb
           OR item->>'price_basis' IS DISTINCT FROM 'REPORTED_QUOTE'
           OR coalesce(item->>'status','') NOT IN ('MISSING_QUOTE','CONFLICTING_QUOTES','STALE_OR_MISSING_SOURCE_DATE',
               'STALE_CAPTURE_DATE','STALE_CAPTURE','STALE_SOURCE_EVENT','REPORTED_DATE_ONLY','REPORTED_EVENT_VERIFIED') THEN
            RAISE EXCEPTION 'Invalid candidate row contract' USING ERRCODE='22023';
        END IF;
        IF item->>'source_event_at' IS NOT NULL AND item->>'source_event_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
            RAISE EXCEPTION 'Aware source event required' USING ERRCODE='22023';
        END IF;
        IF item->>'status' IN ('REPORTED_DATE_ONLY','REPORTED_EVENT_VERIFIED') THEN
            IF coalesce(item->>'display_price_decimal','') !~ '^[0-9]+(\.[0-9]+)?$'
               OR (item->>'display_price_decimal')::numeric NOT BETWEEN 0.0000000000000000000000000001 AND 1000000000000
               OR item->>'display_price_decimal' IS DISTINCT FROM item->>'observed_price_decimal'
               OR (item->>'captured_at')::timestamptz IS DISTINCT FROM moment
               OR item->'reported_time'->>'date' IS DISTINCT FROM c->>'market_date'
               OR jsonb_typeof(item->'observations') IS DISTINCT FROM 'array'
               OR jsonb_array_length(item->'observations') <> 1
               OR item->'observations'->0->>'price_decimal' IS DISTINCT FROM item->>'display_price_decimal'
               OR item->'reported_time'->>'timezone' IS DISTINCT FROM 'UNKNOWN'
               OR coalesce(item->'reported_time'->>'text','') !~ '^[0-9T:/+ .-]{1,64}$' THEN
                RAISE EXCEPTION 'Invalid candidate price evidence' USING ERRCODE='22023';
            END IF;
            IF item->>'status'='REPORTED_DATE_ONLY' AND item->'source_event_at' IS DISTINCT FROM 'null'::jsonb THEN
                RAISE EXCEPTION 'Unexpected source event' USING ERRCODE='22023';
            END IF;
            IF item->>'status'='REPORTED_EVENT_VERIFIED' AND (
                item->>'source_event_at' IS NULL OR (item->>'source_event_at')::timestamptz > moment
                OR (item->>'source_event_at')::timestamptz < prepared-make_interval(secs=>(c->>'source_max_age_seconds')::integer)
            ) THEN RAISE EXCEPTION 'Invalid source event cutoff' USING ERRCODE='22023'; END IF;
        ELSIF item->'display_price_decimal' IS DISTINCT FROM 'null'::jsonb THEN
            RAISE EXCEPTION 'Unavailable rows cannot display a price' USING ERRCODE='22023';
        END IF;
    END LOOP;
    PERFORM pg_catalog.pg_advisory_xact_lock(731905220019);
    SELECT * INTO old FROM app_feed.latest WHERE provider=ctl.provider_namespace;
    IF FOUND THEN
        IF moment < old.captured_at THEN RAISE EXCEPTION 'Older feed rejected' USING ERRCODE='22023'; END IF;
        IF moment=old.captured_at THEN
            IF p_payload_sha256=old.payload_sha256 THEN RETURN p_payload_sha256; END IF;
            RAISE EXCEPTION 'Equal time feed conflict' USING ERRCODE='22023';
        END IF;
    ELSIF (SELECT count(*) FROM app_feed.latest)>=8 THEN
        RAISE EXCEPTION 'Feed provider limit' USING ERRCODE='54000';
    END IF;
    IF pg_database_size(current_database())+octet_length(p_document)+1048576 > 350000000 THEN
        RAISE EXCEPTION 'Database capacity guard reached' USING ERRCODE='54000';
    END IF;
    INSERT INTO app_feed.latest(provider,archive_digest,payload_sha256,captured_at,body)
        VALUES(ctl.provider_namespace,archive.digest,p_payload_sha256,moment,c)
        ON CONFLICT(provider) DO UPDATE SET archive_digest=excluded.archive_digest,payload_sha256=excluded.payload_sha256,
            captured_at=excluded.captured_at,body=excluded.body,stored_at=clock_timestamp();
    RETURN p_payload_sha256;
END $$;

CREATE FUNCTION public.read_shadow_market_feed()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE ctl app_feed.control%ROWTYPE; c jsonb; item jsonb; output jsonb:='[]'::jsonb;
        now_at timestamptz:=clock_timestamp(); state text; price text; result jsonb; expiry timestamptz;
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Sign in required' USING ERRCODE='42501'; END IF;
    result:=jsonb_build_object('contract','app-market-preview/v1','mode','SHADOW_ONLY','as_of',now_at,
        'status','DISABLED','captured_at',NULL,'acquisition_completeness',NULL,'market_session_state','UNKNOWN','rows',output);
    SELECT * INTO ctl FROM app_feed.control WHERE singleton;
    IF NOT FOUND OR NOT ctl.enabled THEN RETURN result; END IF;
    SELECT body INTO c FROM app_feed.latest WHERE provider=ctl.provider_namespace
        AND body->>'mapping_sha256'=ctl.mapping_sha256 AND body->>'recipe_sha256'=ctl.recipe_sha256;
    IF NOT FOUND THEN RETURN result||jsonb_build_object('status','WAITING'); END IF;
    IF NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled)
       OR NOT EXISTS(SELECT 1 FROM app_archive.providers WHERE namespace=ctl.provider_namespace AND enabled) THEN
        RETURN result||jsonb_build_object('status','SOURCE_DISABLED');
    END IF;
    IF NOT EXISTS(SELECT 1 FROM app_archive.objects a JOIN storage.objects o
        ON o.bucket_id='private-market-evidence' AND o.name=a.object_path
        JOIN storage.buckets b ON b.id=o.bucket_id AND NOT b.public
        WHERE a.digest=c->>'archive_sha256' AND a.state='STORED'
            AND o.metadata->>'size'=a.compressed_bytes::text) THEN
        RETURN result||jsonb_build_object('status','EVIDENCE_UNAVAILABLE');
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(c->'rows') LOOP
        state:=item->>'status'; price:=NULL; expiry:=NULL;
        IF state IN ('REPORTED_DATE_ONLY','REPORTED_EVENT_VERIFIED') THEN
            IF (c->>'captured_at')::timestamptz>now_at THEN state:='FUTURE_CAPTURE';
            ELSIF ((c->>'captured_at')::timestamptz AT TIME ZONE 'Africa/Casablanca')::date<>(now_at AT TIME ZONE 'Africa/Casablanca')::date THEN state:='STALE_CAPTURE_DATE';
            ELSIF (c->>'captured_at')::timestamptz<=now_at-make_interval(secs=>(c->>'capture_max_age_seconds')::integer) THEN state:='STALE_CAPTURE';
            ELSIF item->>'source_event_at' IS NOT NULL AND (item->>'source_event_at')::timestamptz<=now_at-make_interval(secs=>(c->>'source_max_age_seconds')::integer) THEN state:='STALE_SOURCE_EVENT';
            ELSE price:=item->>'display_price_decimal'; END IF;
        END IF;
        IF price IS NOT NULL THEN
            expiry:=least((c->>'captured_at')::timestamptz+make_interval(secs=>(c->>'capture_max_age_seconds')::integer),
                (((c->>'market_date')::date+1)::timestamp AT TIME ZONE 'Africa/Casablanca'));
            IF item->>'source_event_at' IS NOT NULL THEN
                expiry:=least(expiry,(item->>'source_event_at')::timestamptz+make_interval(secs=>(c->>'source_max_age_seconds')::integer));
            END IF;
        END IF;
        output:=output||jsonb_build_array(jsonb_build_object(
            'asset_key',item->>'asset_key','company_id',item->'company_id','c_name',item->>'c_name','symbol',item->>'symbol',
            'instrument_type',item->>'instrument_type','status',state,'price_decimal',price,'captured_at',item->'captured_at','expires_at',expiry,
            'reported_time_text',item->'reported_time'->>'text','reported_day',item->'reported_time'->>'date',
            'reported_time_timezone','UNKNOWN','source_event_at',item->'source_event_at','price_basis','REPORTED_QUOTE',
            'portfolio_valuation_eligible',false,'prediction_eligible',false));
    END LOOP;
    RETURN result||jsonb_build_object('status','AVAILABLE','captured_at',c->'captured_at',
        'acquisition_completeness',c->>'acquisition_completeness','rows',output);
END $$;
REVOKE ALL ON FUNCTION public.publish_shadow_market_candidate(text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.publish_shadow_market_candidate(text,text) TO service_role;
REVOKE ALL ON FUNCTION public.read_shadow_market_feed() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.read_shadow_market_feed() TO authenticated;
COMMENT ON SCHEMA app_feed IS 'myInterpreter shadow app feed v1; opt-in preview only';
