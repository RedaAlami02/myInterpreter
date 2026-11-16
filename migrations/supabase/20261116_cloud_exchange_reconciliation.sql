-- Cloud reconciliation boundary. Service role applies verified share counts;
-- authenticated administrators approve staged annual candidates.
-- STAGED ONLY: this migration does not enable schedules or collection controls.
CREATE SCHEMA IF NOT EXISTS market_maintenance;
REVOKE ALL ON SCHEMA market_maintenance FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS market_maintenance.share_reconciliations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    report_sha256 text NOT NULL CHECK (report_sha256 ~ '^[a-f0-9]{64}$'),
    report_generated_at timestamptz NOT NULL,
    symbol text NOT NULL CHECK (length(symbol) BETWEEN 1 AND 32),
    company_name text NOT NULL CHECK (length(company_name) BETWEEN 1 AND 200),
    old_na numeric,
    new_na numeric NOT NULL CHECK (new_na > 0 AND new_na = trunc(new_na) AND new_na <= 1000000000000000),
    page_sha256 text NOT NULL CHECK (page_sha256 ~ '^[a-f0-9]{64}$'),
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    applied_by text NOT NULL DEFAULT 'service_role',
    UNIQUE (report_sha256, symbol)
);
COMMENT ON TABLE market_maintenance.share_reconciliations IS
    'One audit row per verified share count applied by the cloud reconciliation job';
ALTER TABLE market_maintenance.share_reconciliations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE market_maintenance.share_reconciliations FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.apply_exchange_share_reconciliation(
    p_report text, p_report_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc jsonb; item jsonb; sym text; v_company text; page text;
    new_na numeric; old_na numeric; generated timestamptz;
    applied integer := 0; unchanged integer := 0; missing integer := 0;
    already integer := 0; seen text[] := ARRAY[]::text[];
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN
        RAISE EXCEPTION 'Service role required' USING ERRCODE = '42501';
    END IF;
    IF p_report IS NULL OR octet_length(p_report) > 4194304
       OR p_report_sha256 IS NULL OR p_report_sha256 !~ '^[a-f0-9]{64}$'
       OR encode(sha256(convert_to(p_report, 'UTF8')), 'hex') <> p_report_sha256 THEN
        RAISE EXCEPTION 'Invalid reconciliation report digest' USING ERRCODE = '22023';
    END IF;
    doc := p_report::jsonb;
    IF jsonb_typeof(doc) IS DISTINCT FROM 'object'
       OR doc->>'contract' IS DISTINCT FROM 'exchange-reconciliation/v1'
       OR jsonb_typeof(doc->'companies') IS DISTINCT FROM 'array'
       OR jsonb_array_length(doc->'companies') NOT BETWEEN 1 AND 200
       OR coalesce(doc#>>'{summary,generated_at}', '') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
        RAISE EXCEPTION 'Invalid reconciliation report contract' USING ERRCODE = '22023';
    END IF;
    generated := (doc#>>'{summary,generated_at}')::timestamptz;
    IF NOT isfinite(generated)
       OR generated > clock_timestamp() + interval '5 minutes'
       OR generated < clock_timestamp() - interval '30 days' THEN
        RAISE EXCEPTION 'Reconciliation report is stale or future-dated' USING ERRCODE = '22023';
    END IF;
    -- Validate the whole eligible set first; one malformed row rejects the batch.
    FOR item IN SELECT value FROM jsonb_array_elements(doc->'companies') LOOP
        CONTINUE WHEN jsonb_typeof(item) IS DISTINCT FROM 'object'
            OR item#>>'{current_shares,status}' IS DISTINCT FROM 'VERIFIED'
            OR item->>'status' = 'QUARANTINE'
            OR jsonb_typeof(item->'proposed_fields') IS DISTINCT FROM 'object'
            OR jsonb_typeof(item#>'{proposed_fields,na}') IS DISTINCT FROM 'number'
            OR jsonb_typeof(item->'evidence') IS DISTINCT FROM 'object';
        sym := item->>'symbol'; v_company := item->>'company';
        SELECT f.name INTO v_company FROM public.format f WHERE f.symbol = sym;
        IF NOT FOUND THEN v_company := item->>'company'; END IF;
        page := item#>>'{evidence,page_sha256}';
        new_na := (item#>>'{proposed_fields,na}')::numeric;
        IF sym IS NULL OR length(sym) NOT BETWEEN 1 AND 32
           OR v_company IS NULL OR length(v_company) NOT BETWEEN 1 AND 200
           OR page IS NULL OR page !~ '^[a-f0-9]{64}$'
           OR sym = ANY(seen)
           OR new_na <= 0 OR new_na <> trunc(new_na) OR new_na > 1000000000000000 THEN
            RAISE EXCEPTION 'Invalid share reconciliation row' USING ERRCODE = '22023';
        END IF;
        seen := array_append(seen, sym);
    END LOOP;
    FOR item IN SELECT value FROM jsonb_array_elements(doc->'companies') LOOP
        CONTINUE WHEN jsonb_typeof(item) IS DISTINCT FROM 'object'
            OR item#>>'{current_shares,status}' IS DISTINCT FROM 'VERIFIED'
            OR item->>'status' = 'QUARANTINE'
            OR jsonb_typeof(item->'proposed_fields') IS DISTINCT FROM 'object'
            OR jsonb_typeof(item#>'{proposed_fields,na}') IS DISTINCT FROM 'number';
        sym := item->>'symbol'; v_company := item->>'company';
        SELECT f.name INTO v_company FROM public.format f WHERE f.symbol = sym;
        IF NOT FOUND THEN v_company := item->>'company'; END IF;
        page := item#>>'{evidence,page_sha256}';
        new_na := (item#>>'{proposed_fields,na}')::numeric;
        SELECT na INTO old_na FROM public.company WHERE name = v_company FOR UPDATE;
        IF NOT FOUND THEN
            missing := missing + 1;
            CONTINUE;
        END IF;
        IF old_na IS NOT DISTINCT FROM new_na THEN
            unchanged := unchanged + 1;
        ELSE
            UPDATE public.company SET na = new_na WHERE name = v_company;
            applied := applied + 1;
        END IF;
        INSERT INTO market_maintenance.share_reconciliations
            (report_sha256, report_generated_at, symbol, company_name,
             old_na, new_na, page_sha256)
        VALUES (p_report_sha256, generated, sym, v_company, old_na, new_na, page)
        ON CONFLICT (report_sha256, symbol) DO NOTHING;
        IF NOT FOUND THEN already := already + 1; END IF;
    END LOOP;
    RETURN jsonb_build_object(
        'status', 'COMPLETE', 'report_sha256', p_report_sha256,
        'applied', applied, 'unchanged', unchanged,
        'missing', missing, 'already_recorded', already);
END $$;
REVOKE ALL ON FUNCTION public.apply_exchange_share_reconciliation(text, text) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.apply_exchange_share_reconciliation(text, text) TO service_role;
COMMENT ON FUNCTION public.apply_exchange_share_reconciliation(text, text) IS
    'Service-role application of VERIFIED current share counts from an exchange reconciliation report';

CREATE TABLE IF NOT EXISTS market_maintenance.annual_candidates (
    report_sha256 text NOT NULL CHECK (report_sha256 ~ '^[a-f0-9]{64}$'),
    report_generated_at timestamptz NOT NULL,
    symbol text NOT NULL CHECK (length(symbol) BETWEEN 1 AND 32),
    company_name text NOT NULL CHECK (length(company_name) BETWEEN 1 AND 200),
    fiscal_year integer NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
    fields jsonb NOT NULL,
    review_class text NOT NULL CHECK (review_class = 'AUTO_ANNUAL_CANDIDATE'),
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    page_sha256 text NOT NULL CHECK (page_sha256 ~ '^[a-f0-9]{64}$'),
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPLIED', 'REJECTED')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    applied_at timestamptz,
    applied_by uuid,
    PRIMARY KEY (report_sha256, symbol)
);
ALTER TABLE market_maintenance.annual_candidates ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE market_maintenance.annual_candidates FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.stage_exchange_annual_candidates(
    p_report text, p_report_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc jsonb; item jsonb; v_fields jsonb; sym text; v_company text; page text;
    generated timestamptz; year integer; staged integer := 0; skipped integer := 0;
    allowed constant text[] := ARRAY['fiscal_year', 'bpa', 'roe', 'cp',
                                     'revenue', 'net_profit', 'profit_margin'];
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN
        RAISE EXCEPTION 'Service role required' USING ERRCODE = '42501';
    END IF;
    IF p_report IS NULL OR octet_length(p_report) > 4194304
       OR p_report_sha256 IS NULL OR p_report_sha256 !~ '^[a-f0-9]{64}$'
       OR encode(sha256(convert_to(p_report, 'UTF8')), 'hex') <> p_report_sha256 THEN
        RAISE EXCEPTION 'Invalid reconciliation report digest' USING ERRCODE = '22023';
    END IF;
    doc := p_report::jsonb;
    IF jsonb_typeof(doc) IS DISTINCT FROM 'object'
       OR doc->>'contract' IS DISTINCT FROM 'exchange-reconciliation/v1'
       OR jsonb_typeof(doc->'companies') IS DISTINCT FROM 'array'
       OR jsonb_array_length(doc->'companies') NOT BETWEEN 1 AND 200
       OR coalesce(doc#>>'{summary,generated_at}', '') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
        RAISE EXCEPTION 'Invalid reconciliation report contract' USING ERRCODE = '22023';
    END IF;
    generated := (doc#>>'{summary,generated_at}')::timestamptz;
    IF NOT isfinite(generated)
       OR generated > clock_timestamp() + interval '5 minutes'
       OR generated < clock_timestamp() - interval '30 days' THEN
        RAISE EXCEPTION 'Reconciliation report is stale or future-dated' USING ERRCODE = '22023';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(doc->'companies') LOOP
        CONTINUE WHEN item->>'review_class' IS DISTINCT FROM 'AUTO_ANNUAL_CANDIDATE'
            OR jsonb_typeof(item->'proposed_fields') IS DISTINCT FROM 'object';
        sym := item->>'symbol'; v_company := item->>'company';
        SELECT f.name INTO v_company FROM public.format f WHERE f.symbol = sym;
        IF NOT FOUND THEN v_company := item->>'company'; END IF;
        page := item#>>'{evidence,page_sha256}';
        year := (item#>>'{proposed_fields,fiscal_year}')::integer;
        IF sym IS NULL OR v_company IS NULL OR page IS NULL
           OR page !~ '^[a-f0-9]{64}$' OR year IS NULL THEN
            skipped := skipped + 1;
            CONTINUE;
        END IF;
        SELECT jsonb_object_agg(key, value)
          INTO v_fields
          FROM jsonb_each(item->'proposed_fields')
         WHERE key = ANY(allowed) AND jsonb_typeof(value) IS DISTINCT FROM 'null';
        IF v_fields IS NULL OR NOT (v_fields ? 'fiscal_year') THEN
            skipped := skipped + 1;
            CONTINUE;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM public.company WHERE name = v_company) THEN
            skipped := skipped + 1;
            CONTINUE;
        END IF;
        INSERT INTO market_maintenance.annual_candidates
            (report_sha256, report_generated_at, symbol, company_name,
             fiscal_year, fields, review_class, warnings, page_sha256)
        VALUES (p_report_sha256, generated, sym, v_company, year, v_fields,
                'AUTO_ANNUAL_CANDIDATE',
                coalesce(item->'warnings', '[]'::jsonb), page)
        ON CONFLICT (report_sha256, symbol) DO NOTHING;
        IF FOUND THEN staged := staged + 1; END IF;
    END LOOP;
    RETURN jsonb_build_object('status', 'COMPLETE', 'report_sha256', p_report_sha256,
                              'staged', staged, 'skipped', skipped);
END $$;
REVOKE ALL ON FUNCTION public.stage_exchange_annual_candidates(text, text) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.stage_exchange_annual_candidates(text, text) TO service_role;

CREATE OR REPLACE FUNCTION public.read_exchange_annual_candidates()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE caller uuid := auth.uid(); result jsonb;
BEGIN
    IF caller IS NULL OR auth.role() IS DISTINCT FROM 'authenticated'
       OR NOT EXISTS (SELECT 1 FROM market_admin.admins a WHERE a.user_id = caller) THEN
        RAISE EXCEPTION 'Administrator access required' USING ERRCODE = '42501';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(c) ORDER BY c.created_at DESC), '[]'::jsonb)
      INTO result
      FROM (SELECT report_sha256, report_generated_at, symbol, company_name,
                   fiscal_year, fields, warnings, page_sha256, status, created_at
              FROM market_maintenance.annual_candidates
             WHERE status = 'PENDING'
             ORDER BY created_at DESC
             LIMIT 100) c;
    RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.read_exchange_annual_candidates() FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.read_exchange_annual_candidates() TO authenticated;

CREATE OR REPLACE FUNCTION public.apply_exchange_annual_candidates(
    p_report_sha256 text, p_symbols text[] DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    caller uuid := auth.uid(); item market_maintenance.annual_candidates%ROWTYPE;
    current_year integer; current_na numeric; v_fields jsonb;
    results jsonb := '[]'::jsonb;
    receipt jsonb; applied integer := 0; skipped integer := 0;
BEGIN
    IF caller IS NULL OR auth.role() IS DISTINCT FROM 'authenticated'
       OR NOT EXISTS (SELECT 1 FROM market_admin.admins a WHERE a.user_id = caller) THEN
        RAISE EXCEPTION 'Administrator access required' USING ERRCODE = '42501';
    END IF;
    IF p_report_sha256 IS NULL OR p_report_sha256 !~ '^[a-f0-9]{64}$' THEN
        RAISE EXCEPTION 'Invalid report digest' USING ERRCODE = '22023';
    END IF;
    FOR item IN SELECT * FROM market_maintenance.annual_candidates
                WHERE report_sha256 = p_report_sha256 AND status = 'PENDING'
                  AND (p_symbols IS NULL OR symbol = ANY(p_symbols))
                ORDER BY symbol LIMIT 50 FOR UPDATE LOOP
        SELECT fiscal_year, na INTO current_year, current_na
          FROM public.company WHERE name = item.company_name FOR UPDATE;
        IF NOT FOUND OR (current_year IS NOT NULL AND current_year > item.fiscal_year) THEN
            skipped := skipped + 1;
            results := results || jsonb_build_object('symbol', item.symbol, 'status', 'STALE');
            CONTINUE;
        END IF;
        v_fields := item.fields - 'na';
        IF v_fields ? 'bpa' AND v_fields ? 'net_profit' THEN
            IF current_na IS NOT NULL AND current_na > 0 THEN
                v_fields := jsonb_set(v_fields, '{bpa}', to_jsonb(round(
                    (v_fields->>'net_profit')::numeric * 1000000 / current_na, 4)));
            ELSE
                v_fields := v_fields - 'bpa';
            END IF;
        END IF;
        IF v_fields = '{}'::jsonb THEN
            skipped := skipped + 1;
            results := results || jsonb_build_object('symbol', item.symbol, 'status', 'EMPTY');
            CONTINUE;
        END IF;
        receipt := public.admin_update_company(item.company_name, v_fields);
        IF receipt->>'status' IS DISTINCT FROM 'UPDATED' THEN
            skipped := skipped + 1;
            results := results || jsonb_build_object('symbol', item.symbol, 'status', 'FAILED');
            CONTINUE;
        END IF;
        UPDATE market_maintenance.annual_candidates
           SET status = 'APPLIED', applied_at = clock_timestamp(), applied_by = caller
         WHERE report_sha256 = item.report_sha256 AND symbol = item.symbol;
        applied := applied + 1;
        results := results || jsonb_build_object('symbol', item.symbol, 'status', 'APPLIED',
                                                 'fields', receipt->>'fields');
    END LOOP;
    RETURN jsonb_build_object('status', 'COMPLETE', 'applied', applied,
                              'skipped', skipped, 'results', results);
END $$;
REVOKE ALL ON FUNCTION public.apply_exchange_annual_candidates(text, text[]) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.apply_exchange_annual_candidates(text, text[]) TO authenticated;

CREATE OR REPLACE FUNCTION public.reject_exchange_annual_candidates(
    p_report_sha256 text, p_symbols text[])
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE caller uuid := auth.uid(); changed integer;
BEGIN
    IF caller IS NULL OR auth.role() IS DISTINCT FROM 'authenticated'
       OR NOT EXISTS (SELECT 1 FROM market_admin.admins a WHERE a.user_id = caller) THEN
        RAISE EXCEPTION 'Administrator access required' USING ERRCODE = '42501';
    END IF;
    IF p_report_sha256 IS NULL OR p_report_sha256 !~ '^[a-f0-9]{64}$'
       OR p_symbols IS NULL OR array_length(p_symbols, 1) NOT BETWEEN 1 AND 50 THEN
        RAISE EXCEPTION 'Invalid rejection request' USING ERRCODE = '22023';
    END IF;
    UPDATE market_maintenance.annual_candidates
       SET status = 'REJECTED', applied_at = clock_timestamp(), applied_by = caller
     WHERE report_sha256 = p_report_sha256 AND status = 'PENDING'
       AND symbol = ANY(p_symbols);
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN jsonb_build_object('status', 'COMPLETE', 'rejected', changed);
END $$;
REVOKE ALL ON FUNCTION public.reject_exchange_annual_candidates(text, text[]) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.reject_exchange_annual_candidates(text, text[]) TO authenticated;

COMMENT ON FUNCTION public.stage_exchange_annual_candidates(text, text) IS
    'Service-role staging of consolidated, non-financial annual candidates';
COMMENT ON FUNCTION public.apply_exchange_annual_candidates(text, text[]) IS
    'Administrator approval of staged annual candidates';
