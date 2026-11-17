-- A genuine sub-1% ROE (STR -0.14, LES 0.48, RDS 0.12) was rejected as if it
-- were a fraction. Accept it when it matches net profit over equity, and stop
-- one failing company from aborting every other row in the approval batch.

CREATE OR REPLACE FUNCTION public.admin_update_company(p_name text, p_fields jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    caller uuid := auth.uid();
    numeric_fields constant text[] := ARRAY[
        'bpa','dpa','tc5','roe','na','cp','beta_3y','beta_5y','revenue','ebitda',
        'ebit','net_profit','fcf','net_debt','net_cash','total_assets',
        'rev_growth_5y','rnpg_growth_5y','profit_margin','rnpg_est'];
    integer_fields constant text[] := ARRAY['fiscal_year','fy_est'];
    text_fields constant text[] := ARRAY['ext_name','sector','description','shareholders'];
    item record;
    amount numeric; v_np numeric; v_cp numeric;
    changed integer := 0;
BEGIN
    IF caller IS NULL OR auth.role() IS DISTINCT FROM 'authenticated'
       OR NOT EXISTS (SELECT 1 FROM market_admin.admins a WHERE a.user_id = caller) THEN
        RAISE EXCEPTION 'Administrator access required' USING ERRCODE = '42501';
    END IF;
    IF p_name IS NULL OR p_name IS DISTINCT FROM btrim(p_name)
       OR length(p_name) NOT BETWEEN 1 AND 200
       OR p_fields IS NULL OR jsonb_typeof(p_fields) IS DISTINCT FROM 'object'
       OR p_fields = '{}'::jsonb OR octet_length(p_fields::text) > 16384 THEN
        RAISE EXCEPTION 'Invalid company update' USING ERRCODE = '22023';
    END IF;
    FOR item IN SELECT * FROM jsonb_each(p_fields) LOOP
        IF item.key = ANY(numeric_fields) THEN
            CONTINUE WHEN jsonb_typeof(item.value) = 'null';
            IF jsonb_typeof(item.value) IS DISTINCT FROM 'number' THEN
                RAISE EXCEPTION 'Invalid numeric field' USING ERRCODE = '22023';
            END IF;
            amount := (item.value #>> '{}')::numeric;
            IF abs(amount) > 1000000000000000 OR scale(amount) > 6 THEN
                RAISE EXCEPTION 'Numeric field out of range' USING ERRCODE = '22023';
            END IF;
            -- Fractions produced nonsense ratios in the old backend. A genuine
            -- sub-1% ROE is allowed when it matches net profit over equity.
            IF item.key = 'roe' AND amount <> 0 AND abs(amount) < 1 THEN
                SELECT coalesce((p_fields->>'net_profit')::numeric, c.net_profit),
                       coalesce((p_fields->>'cp')::numeric, c.cp)
                  INTO v_np, v_cp
                  FROM public.company c WHERE c.name = p_name;
                IF v_np IS NULL OR v_cp IS NULL OR v_cp = 0
                   OR abs(v_np * 1000000 / v_cp * 100 - amount) > 0.5 THEN
                    RAISE EXCEPTION 'Percentage fields must be percentages' USING ERRCODE = '22023';
                END IF;
            ELSIF item.key = 'tc5' AND amount <> 0 AND abs(amount) < 1 THEN
                RAISE EXCEPTION 'Percentage fields must be percentages' USING ERRCODE = '22023';
            END IF;
        ELSIF item.key = ANY(integer_fields) THEN
            CONTINUE WHEN jsonb_typeof(item.value) = 'null';
            IF jsonb_typeof(item.value) IS DISTINCT FROM 'number'
               OR (item.value #>> '{}') !~ '^[0-9]{4}$'
               OR (item.value #>> '{}')::integer NOT BETWEEN 1900 AND 2200 THEN
                RAISE EXCEPTION 'Invalid year field' USING ERRCODE = '22023';
            END IF;
        ELSIF item.key = ANY(text_fields) THEN
            CONTINUE WHEN jsonb_typeof(item.value) = 'null';
            IF jsonb_typeof(item.value) IS DISTINCT FROM 'string'
               OR length(item.value #>> '{}') NOT BETWEEN 1 AND 4000 THEN
                RAISE EXCEPTION 'Invalid text field' USING ERRCODE = '22023';
            END IF;
        ELSE
            RAISE EXCEPTION 'Unsupported company field' USING ERRCODE = '22023';
        END IF;
        changed := changed + 1;
    END LOOP;
    IF NOT EXISTS (SELECT 1 FROM public.company WHERE name = p_name) THEN
        RETURN jsonb_build_object('status', 'MISSING', 'name', p_name);
    END IF;
    PERFORM 1 FROM public.company WHERE name = p_name FOR UPDATE;
    FOR item IN SELECT * FROM jsonb_each(p_fields) LOOP
        EXECUTE pg_catalog.format(
            'UPDATE public.company SET %I = $1::%s WHERE name = $2',
            item.key,
            CASE WHEN item.key = ANY(integer_fields) THEN 'integer'
                 WHEN item.key = ANY(text_fields) THEN 'text'
                 ELSE 'numeric' END)
            USING (p_fields ->> item.key), p_name;
    END LOOP;
    RETURN jsonb_build_object('status', 'UPDATED', 'name', p_name, 'fields', changed);
END $$;
REVOKE ALL ON FUNCTION public.admin_update_company(text,jsonb) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.admin_update_company(text,jsonb) TO authenticated;

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
