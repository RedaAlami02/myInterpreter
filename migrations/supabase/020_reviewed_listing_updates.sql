-- STAGED ONLY. Owner-only reviewed additions while all collection controls are off.
-- This migration does not enable jobs, change provider pins or touch historical rows.
CREATE SCHEMA market_maintenance;
REVOKE ALL ON SCHEMA market_maintenance FROM PUBLIC,anon,authenticated,service_role;
CREATE TABLE market_maintenance.listing_receipts (
    plan_sha256 text PRIMARY KEY CHECK(plan_sha256 ~ '^[a-f0-9]{64}$'),
    archive_digest text NOT NULL REFERENCES app_archive.objects(digest),
    document jsonb NOT NULL,
    receipt jsonb NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE market_maintenance.listing_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE market_maintenance.listing_receipts FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION market_maintenance.catalog_fingerprint() RETURNS text
LANGUAGE sql SET search_path='' AS $$
    SELECT encode(sha256(convert_to(jsonb_build_object(
        'companies',coalesce((SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id) FROM public.company c),'[]'::jsonb),
        'mappings',coalesce((SELECT jsonb_agg(to_jsonb(f) ORDER BY f.id) FROM public.format f),'[]'::jsonb)
        )::text,'UTF8')),'hex')
$$;
REVOKE ALL ON FUNCTION market_maintenance.catalog_fingerprint() FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION market_maintenance.apply_listing_plan(p_document text,p_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SET search_path='' SET lock_timeout='2s' AS $$
DECLARE
    doc jsonb; old market_maintenance.listing_receipts%ROWTYPE;
    archive app_archive.objects%ROWTYPE; item jsonb; evidence jsonb;
    formats integer:=0; companies integer:=0; answer jsonb;
    seen_symbols text[]:=ARRAY[]::text[]; seen_names text[]:=ARRAY[]::text[];
    key text; company_id text; format_id text; captured timestamptz;
BEGIN
    IF p_document IS NULL OR octet_length(p_document)>131072 OR p_sha256 IS NULL
       OR p_sha256 !~ '^[a-f0-9]{64}$'
       OR encode(sha256(convert_to(p_document,'UTF8')),'hex')<>p_sha256 THEN
        RAISE EXCEPTION 'Invalid listing plan digest' USING ERRCODE='22023';
    END IF;
    doc:=p_document::jsonb;
    -- Table locks precede every catalog snapshot and serialize owner retries.
    LOCK TABLE app_archive.control,app_feed.control,app_projection.control IN SHARE MODE;
    LOCK TABLE market_maintenance.listing_receipts,public.company,public.format IN SHARE ROW EXCLUSIVE MODE;
    IF NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND NOT enabled)
       OR NOT EXISTS(SELECT 1 FROM app_feed.control WHERE singleton AND NOT enabled)
       OR NOT EXISTS(SELECT 1 FROM app_projection.control WHERE singleton AND NOT enabled) THEN
        RAISE EXCEPTION 'Disable collection before reviewing listing changes' USING ERRCODE='42501';
    END IF;
    SELECT * INTO old FROM market_maintenance.listing_receipts WHERE plan_sha256=p_sha256;
    IF FOUND THEN
        IF old.document IS DISTINCT FROM doc THEN RAISE EXCEPTION 'Listing receipt differs' USING ERRCODE='22023'; END IF;
        RETURN old.receipt;
    END IF;
    IF doc->>'contract' IS DISTINCT FROM 'reviewed-listing-update/v1'
       OR doc->>'mode' IS DISTINCT FROM 'OWNER_REVIEW_REQUIRED'
       OR doc->>'source_execution' IS DISTINCT FROM 'CURRENT_ACQUISITION'
       OR doc->'prediction_eligible' IS DISTINCT FROM 'false'::jsonb
       OR doc->'portfolio_valuation_eligible' IS DISTINCT FROM 'false'::jsonb
       OR jsonb_typeof(doc->'additions') IS DISTINCT FROM 'array'
       OR jsonb_array_length(doc->'additions') NOT BETWEEN 1 AND 25
       OR doc->'conflicts' IS DISTINCT FROM '[]'::jsonb
       OR coalesce(doc->>'recipe_sha256','') !~ '^[a-f0-9]{64}$'
       OR coalesce(doc->>'bindings_sha256','') !~ '^[a-f0-9]{64}$'
       OR doc->>'before_sha256' IS DISTINCT FROM market_maintenance.catalog_fingerprint()
       OR coalesce(doc->>'captured_at','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
        RAISE EXCEPTION 'Listing plan requires a matching reviewed catalog' USING ERRCODE='22023';
    END IF;
    captured:=(doc->>'captured_at')::timestamptz;
    SELECT * INTO archive FROM app_archive.objects WHERE digest=doc->>'archive_sha256' FOR SHARE;
    IF NOT FOUND OR archive.state<>'STORED' OR archive.kind<>'quotes'
       OR archive.provider IS DISTINCT FROM doc->>'provider_namespace'
       OR NOT isfinite(captured) OR captured<archive.slot OR captured>archive.completed_at
       OR archive.completed_at>clock_timestamp() THEN
        RAISE EXCEPTION 'Original stored catalog archive required' USING ERRCODE='22023';
    END IF;
    IF pg_database_size(current_database())+octet_length(p_document)+1048576>350000000 THEN
        RAISE EXCEPTION 'Database capacity guard reached' USING ERRCODE='54000';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(doc->'additions') LOOP
        IF jsonb_typeof(item) IS DISTINCT FROM 'object'
           OR jsonb_typeof(item->'name') IS DISTINCT FROM 'string'
           OR jsonb_typeof(item->'symbol') IS DISTINCT FROM 'string'
           OR length(item->>'name') NOT BETWEEN 1 AND 200 OR length(item->>'symbol') NOT BETWEEN 1 AND 100
           OR item->>'name'<>btrim(item->>'name') OR item->>'symbol'<>btrim(item->>'symbol')
           OR item->>'name' ~ '[\x00-\x1f]' OR item->>'symbol' ~ '[\x00-\x1f]'
           OR jsonb_typeof(item->'create_company') IS DISTINCT FROM 'boolean'
           OR jsonb_typeof(item->'evidence') IS DISTINCT FROM 'array'
           OR jsonb_array_length(item->'evidence') NOT BETWEEN 1 AND 100
           OR item->>'symbol'=ANY(seen_symbols) OR item->>'name'=ANY(seen_names)
           OR EXISTS(SELECT 1 FROM public.format WHERE symbol=item->>'symbol' OR name=item->>'name') THEN
            RAISE EXCEPTION 'Listing identity conflict' USING ERRCODE='22023';
        END IF;
        key:=encode(sha256(convert_to(doc->>'provider_namespace','UTF8')||decode('00','hex')
            ||convert_to(item->>'symbol','UTF8')||decode('00','hex')||convert_to(item->>'name','UTF8')),'hex');
        company_id:=item->>'company_id'; format_id:=item->>'format_id';
        IF format_id IS DISTINCT FROM 'listing-format-'||key
           OR company_id IS NULL OR length(company_id) NOT BETWEEN 1 AND 200
           OR EXISTS(SELECT 1 FROM public.format WHERE id=format_id) THEN
            RAISE EXCEPTION 'Invalid listing row identity' USING ERRCODE='22023';
        END IF;
        FOR evidence IN SELECT value FROM jsonb_array_elements(item->'evidence') LOOP
            IF coalesce(evidence->>'observation_id','') !~ '^[a-f0-9]{64}$'
               OR jsonb_typeof(evidence->'source_identity') IS DISTINCT FROM 'string'
               OR length(evidence->>'source_identity') NOT BETWEEN 1 AND 100
               OR jsonb_typeof(evidence->'raw_row_index') IS DISTINCT FROM 'number'
               OR (evidence->>'raw_row_index') !~ '^[0-9]{1,4}$' THEN
                RAISE EXCEPTION 'Invalid catalog evidence reference' USING ERRCODE='22023';
            END IF;
        END LOOP;
        IF (item->>'create_company')::boolean THEN
            IF company_id IS DISTINCT FROM 'listing-company-'||key
               OR EXISTS(SELECT 1 FROM public.company WHERE name=item->>'name' OR id=company_id) THEN
                RAISE EXCEPTION 'Existing company cannot be replaced' USING ERRCODE='22023';
            END IF;
            -- No fundamental value or timestamp is invented for a bare listing.
            INSERT INTO public.company(id,name) VALUES(company_id,item->>'name');
            companies:=companies+1;
        ELSIF (SELECT count(*) FROM public.company WHERE name=item->>'name' AND id=company_id)<>1
           OR (SELECT count(*) FROM public.company WHERE name=item->>'name')<>1 THEN
            RAISE EXCEPTION 'Exact existing company required' USING ERRCODE='22023';
        END IF;
        INSERT INTO public.format(id,name,symbol) VALUES(format_id,item->>'name',item->>'symbol');
        formats:=formats+1;
        seen_symbols:=array_append(seen_symbols,item->>'symbol');
        seen_names:=array_append(seen_names,item->>'name');
    END LOOP;
    answer:=jsonb_build_object('status','ADDED_PENDING_PROVIDER_REPIN','formats_added',formats,
        'companies_added',companies,'plan_sha256',p_sha256,'profiles_changed',false);
    INSERT INTO market_maintenance.listing_receipts(plan_sha256,archive_digest,document,receipt)
        VALUES(p_sha256,archive.digest,doc,answer);
    RETURN answer;
END $$;
REVOKE ALL ON FUNCTION market_maintenance.apply_listing_plan(text,text) FROM PUBLIC,anon,authenticated,service_role;
