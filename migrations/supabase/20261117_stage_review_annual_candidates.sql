-- Stage the reviewed annual classes alongside auto candidates: banks, insurers
-- and standalone-account companies. Stale fiscal years and share-count
-- conflicts stay out. Rows still need explicit administrator approval.
DO $$
DECLARE constraint_name text;
BEGIN
    FOR constraint_name IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'market_maintenance.annual_candidates'::regclass
           AND contype = 'c'
           AND pg_get_constraintdef(oid) LIKE '%AUTO_ANNUAL_CANDIDATE%'
    LOOP
        EXECUTE format('ALTER TABLE market_maintenance.annual_candidates DROP CONSTRAINT %I',
                       constraint_name);
    END LOOP;
END $$;

ALTER TABLE market_maintenance.annual_candidates
    ADD CONSTRAINT annual_candidates_review_class_check
    CHECK (review_class IN ('AUTO_ANNUAL_CANDIDATE', 'BANK_REVIEW',
                            'INSURER_REVIEW', 'STANDALONE_REVIEW'));

CREATE OR REPLACE FUNCTION public.stage_exchange_annual_candidates(
    p_report text, p_report_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc jsonb; item jsonb; v_fields jsonb; sym text; v_company text; page text;
    v_class text; generated timestamptz; year integer;
    staged integer := 0; skipped integer := 0;
    allowed constant text[] := ARRAY['fiscal_year', 'bpa', 'roe', 'cp',
                                     'revenue', 'net_profit', 'profit_margin'];
    staged_classes constant text[] := ARRAY['AUTO_ANNUAL_CANDIDATE', 'BANK_REVIEW',
                                            'INSURER_REVIEW', 'STANDALONE_REVIEW'];
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
        v_class := item->>'review_class';
        CONTINUE WHEN v_class IS NULL OR NOT (v_class = ANY(staged_classes))
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
        IF EXISTS (SELECT 1 FROM market_maintenance.annual_candidates
                    WHERE symbol = sym AND fiscal_year = year AND status = 'PENDING') THEN
            skipped := skipped + 1;
            CONTINUE;
        END IF;
        INSERT INTO market_maintenance.annual_candidates
            (report_sha256, report_generated_at, symbol, company_name,
             fiscal_year, fields, review_class, warnings, page_sha256)
        VALUES (p_report_sha256, generated, sym, v_company, year, v_fields,
                v_class, coalesce(item->'warnings', '[]'::jsonb), page)
        ON CONFLICT (report_sha256, symbol) DO NOTHING;
        IF FOUND THEN staged := staged + 1; END IF;
    END LOOP;
    RETURN jsonb_build_object('status', 'COMPLETE', 'report_sha256', p_report_sha256,
                              'staged', staged, 'skipped', skipped);
END $$;
REVOKE ALL ON FUNCTION public.stage_exchange_annual_candidates(text, text) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.stage_exchange_annual_candidates(text, text) TO service_role;
