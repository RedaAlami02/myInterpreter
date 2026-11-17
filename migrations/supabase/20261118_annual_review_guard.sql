-- Annual review: never replace a human-reviewed fiscal period.
--
-- apply_exchange_annual_candidates already refused to apply an older year but
-- happily overwrote the same year, bypassing the protection that
-- 20261116_protect_reviewed_financials.sql applies to projections. A candidate
-- for a year that has a market_admin.financial_review_receipts row is now
-- skipped and reported as FINANCIAL_PERIOD_REVIEWED.

CREATE OR REPLACE FUNCTION public.apply_exchange_annual_candidates(
    p_report_sha256 text, p_symbols text[] DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    caller uuid := auth.uid(); item market_maintenance.annual_candidates%ROWTYPE;
    current_year integer; current_na numeric; v_fields jsonb;
    results jsonb := '[]'::jsonb;
    receipt jsonb; applied integer := 0; skipped integer := 0;
    review_protected boolean;
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
        -- A human-reviewed fiscal period must not be replaced by a re-staged
        -- exchange report. Only the same year is protected; newer years still apply.
        IF item.fiscal_year = current_year THEN
            SELECT EXISTS (
                SELECT 1 FROM market_admin.financial_review_receipts r
                  JOIN public.company co ON co.id = r.company_id
                 WHERE co.name = item.company_name) INTO review_protected;
            IF review_protected THEN
                skipped := skipped + 1;
                results := results || jsonb_build_object('symbol', item.symbol,
                    'status', 'SKIPPED', 'reason', 'FINANCIAL_PERIOD_REVIEWED');
                CONTINUE;
            END IF;
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
        BEGIN
            receipt := public.admin_update_company(item.company_name, v_fields);
        EXCEPTION WHEN OTHERS THEN
            skipped := skipped + 1;
            results := results || jsonb_build_object('symbol', item.symbol,
                'status', 'FAILED', 'reason', SQLERRM);
            CONTINUE;
        END;
        IF receipt->>'status' IS DISTINCT FROM 'UPDATED' THEN
            skipped := skipped + 1;
            results := results || jsonb_build_object('symbol', item.symbol, 'status', 'FAILED',
                'reason', coalesce(receipt->>'status', 'UNKNOWN'));
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
