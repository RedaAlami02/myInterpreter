-- Additive, read-only company inputs under the price job's own lease and pins.
-- Requires SQL016/018; install atomically with all source controls disabled.
DO $$ BEGIN
    IF NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND NOT enabled)
       OR NOT EXISTS(SELECT 1 FROM app_feed.control WHERE singleton AND NOT enabled)
       OR NOT EXISTS(SELECT 1 FROM app_projection.control WHERE singleton AND NOT enabled) THEN
        RAISE EXCEPTION 'Disabled source controls required for context installation';
    END IF;
END $$;

CREATE FUNCTION public.read_price_company_context(p_provider text,p_mapping_document text,
    p_mapping_sha256 text,p_recipe_sha256 text,p_fields_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_trial.leases%ROWTYPE; again app_trial.leases%ROWTYPE;
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
    lease:=app_trial.require_lease(p_provider,'archive');
    again:=app_trial.require_lease(p_provider,'shadow_feed',lease.id);
    again:=app_trial.require_lease(p_provider,'projections',lease.id);
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
    PERFORM app_trial.require_lease(p_provider,'archive',lease.id);
    PERFORM app_trial.require_lease(p_provider,'shadow_feed',lease.id);
    PERFORM app_trial.require_lease(p_provider,'projections',lease.id);
    RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.read_price_company_context(text,text,text,text,text)
    FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.read_price_company_context(text,text,text,text,text) TO service_role;
