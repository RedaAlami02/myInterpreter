-- STAGED ONLY. Service-only publication for dividend and fundamental projections.
-- Depends on reviewed SQL009 archive tables. Everything starts disabled.
-- Staged publication contract v2: bounded capacity and monotonic acceptance heads.
CREATE SCHEMA app_projection;
REVOKE ALL ON SCHEMA app_projection FROM PUBLIC, anon, authenticated, service_role;
CREATE TABLE app_projection.control (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    enabled boolean NOT NULL DEFAULT false,
    max_database_bytes bigint NOT NULL DEFAULT 350000000
        CHECK (max_database_bytes BETWEEN 0 AND 350000000),
    provider_namespace text CHECK (provider_namespace ~ '^feed_[a-f0-9]{16}$'),
    dividend_index_sha256 text CHECK (dividend_index_sha256 ~ '^[a-f0-9]{64}$'),
    fundamental_index_sha256 text CHECK (fundamental_index_sha256 ~ '^[a-f0-9]{64}$'),
    CHECK (NOT enabled OR (
        provider_namespace IS NOT NULL
        AND dividend_index_sha256 IS NOT NULL
        AND fundamental_index_sha256 IS NOT NULL
    ))
);
INSERT INTO app_projection.control(singleton) VALUES (true);
ALTER TABLE app_projection.control ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE app_projection.control FROM PUBLIC, anon, authenticated, service_role;

-- These are derived publication heads, never replacements for original archives.
CREATE TABLE app_projection.accepted_rows (
    provider_namespace text NOT NULL CHECK (provider_namespace ~ '^feed_[a-f0-9]{16}$'),
    kind text NOT NULL CHECK (kind IN ('dividends', 'fundamentals')),
    target_key text NOT NULL CHECK (target_key ~ '^[a-f0-9]{64}$'),
    archive_digest text NOT NULL REFERENCES app_archive.objects(digest),
    completed_at timestamptz NOT NULL CHECK (isfinite(completed_at)),
    row_sha256 text NOT NULL CHECK (row_sha256 ~ '^[a-f0-9]{64}$'),
    PRIMARY KEY (provider_namespace, kind, target_key)
);
ALTER TABLE app_projection.accepted_rows ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE app_projection.accepted_rows FROM PUBLIC, anon, authenticated, service_role;

CREATE FUNCTION app_projection.accept_row(
    p_provider text, p_kind text, p_identity jsonb, p_archive text,
    p_completed_at timestamptz, p_value jsonb
) RETURNS void LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    identity_hash text := encode(pg_catalog.sha256(convert_to(p_identity::text,'UTF8')),'hex');
    value_hash text := encode(pg_catalog.sha256(convert_to(p_value::text,'UTF8')),'hex');
    old app_projection.accepted_rows%ROWTYPE;
BEGIN
    -- Both callers hold the same projection lock before inspecting/writing heads.
    SELECT * INTO old FROM app_projection.accepted_rows
        WHERE provider_namespace=p_provider AND kind=p_kind AND target_key=identity_hash;
    IF FOUND THEN
        IF old.completed_at > p_completed_at THEN
            RAISE EXCEPTION 'Older projection cannot replace accepted data' USING ERRCODE='22023';
        END IF;
        IF old.completed_at = p_completed_at
           AND (old.archive_digest IS DISTINCT FROM p_archive OR old.row_sha256 IS DISTINCT FROM value_hash) THEN
            RAISE EXCEPTION 'Equal-time projection conflict requires review' USING ERRCODE='22023';
        END IF;
        IF old.completed_at = p_completed_at THEN RETURN; END IF;
    END IF;
    INSERT INTO app_projection.accepted_rows(provider_namespace,kind,target_key,archive_digest,completed_at,row_sha256)
        VALUES(p_provider,p_kind,identity_hash,p_archive,p_completed_at,value_hash)
        ON CONFLICT(provider_namespace,kind,target_key) DO UPDATE
        SET archive_digest=excluded.archive_digest,completed_at=excluded.completed_at,row_sha256=excluded.row_sha256;
END $$;
REVOKE ALL ON FUNCTION app_projection.accept_row(text,text,jsonb,text,timestamptz,jsonb)
    FROM PUBLIC, anon, authenticated, service_role;

CREATE FUNCTION public.publish_dividend_projection(p_document text, p_payload_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    c jsonb; ctl app_projection.control%ROWTYPE;
    archive app_archive.objects%ROWTYPE;
    item jsonb;
    r_cname text; r_issuer text; r_type text; r_frequency text;
    r_year integer; r_amount numeric; r_ex date; r_pay date; r_end date;
    r_confirmed boolean;
    old public.dividends%ROWTYPE;
    seen text[] := ARRAY[]::text[];
    key text;
    rows_count integer; created integer := 0; updated integer := 0;
BEGIN
    IF p_document IS NULL OR octet_length(p_document) > 2097152 OR p_payload_sha256 IS NULL
       OR encode(pg_catalog.sha256(convert_to(p_document,'UTF8')),'hex') <> p_payload_sha256 THEN
        RAISE EXCEPTION 'Invalid projection payload' USING ERRCODE='22023';
    END IF;
    c := p_document::jsonb;
    SELECT * INTO ctl FROM app_projection.control WHERE singleton;
    IF NOT FOUND OR NOT ctl.enabled OR ctl.provider_namespace IS NULL
       OR c->>'contract' IS DISTINCT FROM 'dividend-projection/v1'
       OR c->>'mode' IS DISTINCT FROM 'PROJECTION_ONLY'
       OR c->>'provider_namespace' IS DISTINCT FROM ctl.provider_namespace
       OR c->>'index_sha256' IS DISTINCT FROM ctl.dividend_index_sha256
       OR c->>'source_execution' IS DISTINCT FROM 'CURRENT_ACQUISITION'
       OR coalesce(c->>'completeness','') NOT IN ('COMPLETE','INCOMPLETE')
       OR c->'prediction_eligible' IS DISTINCT FROM 'false'::jsonb
       OR c->'portfolio_valuation_eligible' IS DISTINCT FROM 'false'::jsonb
       OR jsonb_typeof(c->'rows') IS DISTINCT FROM 'array'
       OR jsonb_typeof(c->'excluded') IS DISTINCT FROM 'array'
       OR jsonb_typeof(c->'unmatched') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'Projection contract or pin mismatch' USING ERRCODE='22023';
    END IF;
    SELECT * INTO archive FROM app_archive.objects WHERE digest = c->>'archive_sha256';
    IF NOT FOUND OR archive.state <> 'STORED' OR archive.kind <> 'dividends'
       OR archive.provider <> ctl.provider_namespace
       OR archive.completed_at < clock_timestamp() - interval '30 days'
       OR NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled)
       OR NOT EXISTS(SELECT 1 FROM app_archive.providers WHERE namespace = ctl.provider_namespace AND enabled) THEN
        RAISE EXCEPTION 'Verified dividend archive required' USING ERRCODE='42501';
    END IF;
    rows_count := jsonb_array_length(c->'rows');
    IF rows_count > 2000 THEN
        RAISE EXCEPTION 'Dividend projection too large' USING ERRCODE='54000';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(731905220020);
    IF pg_database_size(current_database()) + octet_length(p_document) + 1048576 > ctl.max_database_bytes THEN
        RAISE EXCEPTION 'Database capacity guard reached' USING ERRCODE='54000';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(c->'rows') LOOP
        r_cname := item->>'c_name';
        r_issuer := item->>'issuer';
        r_type := item->>'type';
        r_frequency := item->>'frequency';
        IF r_cname IS NULL OR length(r_cname) NOT BETWEEN 1 AND 200
           OR r_issuer IS NULL OR length(r_issuer) NOT BETWEEN 1 AND 200
           OR (r_type IS NOT NULL AND (length(r_type) NOT BETWEEN 1 AND 100 OR r_type ~ '[\x00-\x1f]'))
           OR (r_frequency IS NOT NULL AND (length(r_frequency) NOT BETWEEN 1 AND 100 OR r_frequency ~ '[\x00-\x1f]'))
           OR jsonb_typeof(item->'year') IS DISTINCT FROM 'number'
           OR jsonb_typeof(item->'confirmed') IS DISTINCT FROM 'boolean'
           OR NOT EXISTS(SELECT 1 FROM public.company co WHERE co.name = r_cname) THEN
            RAISE EXCEPTION 'Invalid dividend row' USING ERRCODE='22023';
        END IF;
        r_year := (item->>'year')::integer;
        r_confirmed := (item->>'confirmed')::boolean;
        IF r_year NOT BETWEEN 1900 AND 9999 THEN
            RAISE EXCEPTION 'Invalid dividend year' USING ERRCODE='22023';
        END IF;
        IF item->'amount' IS NOT NULL AND jsonb_typeof(item->'amount') <> 'null' THEN
            IF jsonb_typeof(item->'amount') IS DISTINCT FROM 'number' THEN
                RAISE EXCEPTION 'Invalid dividend amount' USING ERRCODE='22023';
            END IF;
            r_amount := (item->>'amount')::numeric;
            IF NOT (r_amount > 0 AND r_amount <= 1000000000000) THEN
                RAISE EXCEPTION 'Invalid dividend amount' USING ERRCODE='22023';
            END IF;
        ELSE
            r_amount := NULL;
        END IF;
        FOREACH key IN ARRAY ARRAY['ex_date','pay_date','pay_date_end'] LOOP
            IF item->key IS NULL OR jsonb_typeof(item->key) = 'null' THEN
                CONTINUE;
            END IF;
            IF jsonb_typeof(item->key) IS DISTINCT FROM 'string'
               OR (item->>key) !~ '^\d{4}-\d{2}-\d{2}$' THEN
                RAISE EXCEPTION 'Invalid dividend date' USING ERRCODE='22023';
            END IF;
        END LOOP;
        BEGIN
            r_ex := nullif(item->>'ex_date','')::date;
            r_pay := nullif(item->>'pay_date','')::date;
            r_end := nullif(item->>'pay_date_end','')::date;
        EXCEPTION WHEN others THEN
            RAISE EXCEPTION 'Invalid dividend date' USING ERRCODE='22023';
        END;
        IF (r_pay IS NOT NULL AND extract(year FROM r_pay) <> r_year)
           OR (r_end IS NOT NULL AND extract(year FROM r_end) <> r_year)
           OR (r_ex IS NOT NULL AND extract(year FROM r_ex) <> r_year
               AND NOT (r_pay IS NOT NULL AND extract(year FROM r_ex) = r_year - 1))
           OR (r_ex IS NOT NULL AND r_pay IS NOT NULL AND r_pay < r_ex)
           OR (r_end IS NOT NULL AND (r_pay IS NULL OR r_end < r_pay))
           OR (r_confirmed AND r_ex IS NULL) THEN
            RAISE EXCEPTION 'Invalid dividend payment period' USING ERRCODE='22023';
        END IF;
        key := jsonb_build_array(r_cname,r_year,r_type)::text;
        IF key = ANY(seen) THEN
            RAISE EXCEPTION 'Duplicate dividend row' USING ERRCODE='22023';
        END IF;
        seen := seen || key;
        PERFORM app_projection.accept_row(ctl.provider_namespace,'dividends',
            jsonb_build_array(r_cname,r_year,r_type),archive.digest,archive.completed_at,item);
        SELECT * INTO old FROM public.dividends d
            WHERE d.c_name = r_cname AND d.year = r_year AND d.type IS NOT DISTINCT FROM r_type
            ORDER BY d.id LIMIT 1;
        IF FOUND THEN
            IF (old.issuer, old.amount, old.ex_date, old.pay_date, old.pay_date_end,
                old.confirmed, old.frequency)
               IS DISTINCT FROM
               (r_issuer, r_amount, r_ex, r_pay, r_end, r_confirmed, r_frequency) THEN
                UPDATE public.dividends SET issuer = r_issuer, amount = r_amount,
                    ex_date = r_ex, pay_date = r_pay, pay_date_end = r_end,
                    confirmed = r_confirmed, frequency = r_frequency,
                    updated_at = clock_timestamp()
                    WHERE id = old.id;
                updated := updated + 1;
            END IF;
        ELSE
            INSERT INTO public.dividends(id,c_name,issuer,year,amount,ex_date,pay_date,
                pay_date_end,confirmed,type,frequency,updated_at)
                VALUES (replace(gen_random_uuid()::text,'-',''), r_cname, r_issuer, r_year,
                    r_amount, r_ex, r_pay, r_end, r_confirmed, r_type, r_frequency,
                    clock_timestamp());
            created := created + 1;
        END IF;
    END LOOP;
    RETURN jsonb_build_object('status','PUBLISHED','rows',rows_count,
        'created',created,'updated',updated);
END $$;

CREATE FUNCTION public.publish_fundamental_projection(p_document text, p_payload_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
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
    newer boolean; changed integer := 0;
BEGIN
    IF p_document IS NULL OR octet_length(p_document) > 2097152 OR p_payload_sha256 IS NULL
       OR encode(pg_catalog.sha256(convert_to(p_document,'UTF8')),'hex') <> p_payload_sha256 THEN
        RAISE EXCEPTION 'Invalid projection payload' USING ERRCODE='22023';
    END IF;
    c := p_document::jsonb;
    SELECT * INTO ctl FROM app_projection.control WHERE singleton;
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
    newer := incoming_year IS NOT NULL AND (stored_year IS NULL OR incoming_year > stored_year);
    FOR key IN SELECT jsonb_object_keys(fields) LOOP
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
        'fiscal_year',incoming_year,'refreshed',COALESCE(newer,false));
END $$;

REVOKE ALL ON FUNCTION public.publish_dividend_projection(text,text) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.publish_dividend_projection(text,text) TO service_role;
REVOKE ALL ON FUNCTION public.publish_fundamental_projection(text,text) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.publish_fundamental_projection(text,text) TO service_role;
COMMENT ON SCHEMA app_projection IS 'myInterpreter projection publication v2; service only; monotonic acceptance';
