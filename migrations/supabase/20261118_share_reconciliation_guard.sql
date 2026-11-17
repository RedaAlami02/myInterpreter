-- Share reconciliation: no free-text company fallback, no stale replays.
--
-- Two defects are closed here:
--   1. a symbol missing from public.format was matched by the free-text company
--      string in the report, so a typo or a new listing could update — or stage
--      financials against — the wrong company;
--   2. replaying an older reconciliation report overwrote a newer share count.
--
-- Unmapped symbols are skipped; a report generated before the newest applied
-- report for that company is skipped and counted separately.

CREATE OR REPLACE FUNCTION public.apply_exchange_share_reconciliation(
    p_report text, p_report_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc jsonb; item jsonb; sym text; v_company text; page text;
    new_na numeric; old_na numeric; generated timestamptz;
    applied integer := 0; unchanged integer := 0; missing integer := 0;
    skipped_stale integer := 0;
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
        sym := item->>'symbol';
        -- The symbol mapping is authoritative. Writing to a free-text company
        -- name lets an unmapped or misspelled ticker change the wrong company.
        SELECT f.name INTO v_company FROM public.format f WHERE f.symbol = sym;
        IF NOT FOUND THEN CONTINUE; END IF;
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
        sym := item->>'symbol';
        -- The symbol mapping is authoritative. Writing to a free-text company
        -- name lets an unmapped or misspelled ticker change the wrong company.
        SELECT f.name INTO v_company FROM public.format f WHERE f.symbol = sym;
        IF NOT FOUND THEN CONTINUE; END IF;
        page := item#>>'{evidence,page_sha256}';
        new_na := (item#>>'{proposed_fields,na}')::numeric;
        SELECT na INTO old_na FROM public.company WHERE name = v_company FOR UPDATE;
        IF NOT FOUND THEN
            missing := missing + 1;
            CONTINUE;
        END IF;
        -- A replayed older report must not roll a newer share count back.
        IF EXISTS (SELECT 1 FROM market_maintenance.share_reconciliations r
                    WHERE r.company_name = v_company
                      AND r.report_generated_at > generated) THEN
            skipped_stale := skipped_stale + 1;
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
        'missing', missing, 'already_recorded', already,
        'skipped_older_report', skipped_stale);
END $$;
REVOKE ALL ON FUNCTION public.apply_exchange_share_reconciliation(text, text) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.apply_exchange_share_reconciliation(text, text) TO service_role;
COMMENT ON FUNCTION public.apply_exchange_share_reconciliation(text, text) IS
    'Service-role application of VERIFIED current share counts from an exchange reconciliation report';

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
        sym := item->>'symbol';
        SELECT f.name INTO v_company FROM public.format f WHERE f.symbol = sym;
        IF NOT FOUND THEN
            skipped := skipped + 1;
            CONTINUE;
        END IF;
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
