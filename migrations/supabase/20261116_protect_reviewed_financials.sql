-- Explicit primary review protects financial values from unreviewed projections.
-- Unreviewed companies retain existing same-year/newer-year publication behavior.
CREATE FUNCTION app_projection.financial_period_blocked(stored_year integer,incoming_year integer,primary_reviewed boolean)
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT (primary_reviewed IS TRUE) OR
  (stored_year IS NOT NULL AND (incoming_year IS NULL OR incoming_year<stored_year))
$$;
REVOKE ALL ON FUNCTION app_projection.financial_period_blocked(integer,integer,boolean) FROM PUBLIC,anon,authenticated,service_role;
CREATE OR REPLACE FUNCTION app_recurring.publish_fundamental_impl(p_document text, p_payload_sha256 text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
    c jsonb; ctl app_projection.control%ROWTYPE;
    archive app_archive.objects%ROWTYPE;
    fields jsonb; key text; value_text text; current_text text;
    numeric_fields constant text[] := ARRAY[
        'bpa','dpa','tc5','roe','na','cp','beta_3y','beta_5y','revenue','ebitda',
        'ebit','net_profit','fcf','net_debt','net_cash','total_assets',
        'rev_growth_5y','rnpg_growth_5y','profit_margin','rnpg_est'];
    integer_fields constant text[] := ARRAY['fiscal_year','fy_est'];
    text_fields constant text[] := ARRAY['ext_name','sector','description','shareholders'];
    expected integer;
    r_cname text; incoming_year integer; stored_year integer;
    newer boolean; changed integer := 0; review_protected boolean; period_blocked boolean;
BEGIN
    IF p_document IS NULL OR octet_length(p_document) > 2097152 OR p_payload_sha256 IS NULL
       OR encode(pg_catalog.sha256(convert_to(p_document,'UTF8')),'hex') <> p_payload_sha256 THEN
        RAISE EXCEPTION 'Invalid projection payload' USING ERRCODE='22023';
    END IF;
    c := p_document::jsonb;
    SELECT * INTO ctl FROM app_recurring.projection_control(c->>'provider_namespace');
    IF NOT FOUND OR NOT ctl.enabled OR ctl.provider_namespace IS NULL
       OR c->>'contract' IS DISTINCT FROM 'fundamental-projection/v1'
       OR c->>'mode' IS DISTINCT FROM 'PROJECTION_ONLY'
       OR c->>'provider_namespace' IS DISTINCT FROM ctl.provider_namespace
       OR c->>'index_sha256' IS DISTINCT FROM ctl.fundamental_index_sha256
       OR c->>'source_execution' IS DISTINCT FROM 'CURRENT_ACQUISITION'
       OR coalesce(c->>'completeness','') NOT IN ('COMPLETE','INCOMPLETE')
       OR c->'prediction_eligible' IS DISTINCT FROM 'false'::jsonb
       OR c->'portfolio_valuation_eligible' IS DISTINCT FROM 'false'::jsonb
       OR c->>'c_name' IS NULL OR length(c->>'c_name') NOT BETWEEN 1 AND 200
       OR c->>'symbol' IS NULL OR length(c->>'symbol') NOT BETWEEN 1 AND 32
       OR jsonb_typeof(c->'fields') IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'Projection contract or pin mismatch' USING ERRCODE='22023';
    END IF;
    SELECT * INTO archive FROM app_archive.objects WHERE digest = c->>'archive_sha256';
    IF NOT FOUND OR archive.state <> 'STORED' OR archive.kind <> 'fundamentals'
       OR archive.provider <> ctl.provider_namespace
       OR archive.completed_at < clock_timestamp() - interval '30 days'
       OR NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled)
       OR NOT EXISTS(SELECT 1 FROM app_archive.providers WHERE namespace = ctl.provider_namespace AND enabled) THEN
        RAISE EXCEPTION 'Verified fundamental archive required' USING ERRCODE='42501';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(731905220020);
    IF pg_database_size(current_database()) + octet_length(p_document) + 1048576 > ctl.max_database_bytes THEN
        RAISE EXCEPTION 'Database capacity guard reached' USING ERRCODE='54000';
    END IF;
    fields := c->'fields';
    expected := array_length(numeric_fields,1) + array_length(integer_fields,1) + array_length(text_fields,1);
    IF (SELECT count(*) FROM jsonb_object_keys(fields)) <> expected
       OR EXISTS(SELECT 1 FROM jsonb_object_keys(fields) k
                 WHERE k <> ALL(numeric_fields || integer_fields || text_fields)) THEN
        RAISE EXCEPTION 'Invalid fundamental field set' USING ERRCODE='22023';
    END IF;
    FOR key IN SELECT jsonb_object_keys(fields) LOOP
        IF fields->key IS NOT NULL AND jsonb_typeof(fields->key) <> 'null' THEN
            IF key = ANY(numeric_fields) THEN
                IF jsonb_typeof(fields->key) IS DISTINCT FROM 'number'
                   OR abs((fields->>key)::numeric) > 1000000000000000 THEN
                    RAISE EXCEPTION 'Invalid fundamental value' USING ERRCODE='22023';
                END IF;
            ELSIF key = ANY(integer_fields) THEN
                IF jsonb_typeof(fields->key) IS DISTINCT FROM 'number'
                   OR (fields->>key) !~ '^[0-9]{4}$'
                   OR (fields->>key)::integer NOT BETWEEN 1900 AND 2100 THEN
                    RAISE EXCEPTION 'Invalid fundamental year' USING ERRCODE='22023';
                END IF;
            ELSE
                IF jsonb_typeof(fields->key) IS DISTINCT FROM 'string'
                   OR length(fields->>key) < 1
                   OR length(fields->>key) > (CASE WHEN key = 'shareholders' THEN 4000 ELSE 3800 END) THEN
                    RAISE EXCEPTION 'Invalid fundamental text' USING ERRCODE='22023';
                END IF;
                IF key = 'shareholders' THEN
                    BEGIN
                        IF jsonb_typeof((fields->>key)::jsonb) <> 'array' THEN
                            RAISE EXCEPTION 'Invalid shareholders' USING ERRCODE='22023';
                        END IF;
                    EXCEPTION WHEN others THEN
                        RAISE EXCEPTION 'Invalid shareholders' USING ERRCODE='22023';
                    END;
                END IF;
            END IF;
        END IF;
    END LOOP;
    r_cname := c->>'c_name';
    SELECT fiscal_year INTO stored_year FROM public.company WHERE name = r_cname FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('status','MISSING','name',r_cname);
    END IF;
    PERFORM app_projection.accept_row(ctl.provider_namespace,'fundamentals',
        jsonb_build_array(r_cname),archive.digest,archive.completed_at,fields);
    incoming_year := nullif(fields->>'fiscal_year','')::integer;
    SELECT EXISTS(SELECT 1 FROM market_admin.financial_review_receipts r
        JOIN public.company co ON co.id=r.company_id WHERE co.name=r_cname) INTO review_protected;
    period_blocked:=app_projection.financial_period_blocked(stored_year,incoming_year,review_protected);
    newer := NOT period_blocked AND incoming_year IS NOT NULL AND (stored_year IS NULL OR incoming_year > stored_year);
    FOR key IN SELECT jsonb_object_keys(fields) LOOP
        IF period_blocked AND key=ANY(numeric_fields||integer_fields) THEN CONTINUE; END IF;
        value_text := fields->>key;
        CONTINUE WHEN value_text IS NULL;
        EXECUTE pg_catalog.format('SELECT (%I)::text FROM public.company WHERE name = $1', key)
            INTO current_text USING r_cname;
        IF current_text IS NULL OR newer THEN
            EXECUTE pg_catalog.format('UPDATE public.company SET %I = $1::%s WHERE name = $2',
                key,
                CASE WHEN key = ANY(integer_fields) THEN 'integer'
                     WHEN key = ANY(text_fields) THEN 'text'
                     ELSE 'numeric' END)
                USING value_text, r_cname;
            changed := changed + 1;
        END IF;
    END LOOP;
    RETURN jsonb_build_object('status','UPDATED','name',r_cname,'fields',changed,
        'fiscal_year',CASE WHEN period_blocked THEN stored_year ELSE incoming_year END,
        'source_fiscal_year',incoming_year,'financial_review_required',period_blocked,
        'refreshed',COALESCE(newer,false));
END $function$
;
