-- Backfill daily company closes from CDG into public.data.
-- Historical dates are accepted; rows are keyed by company and trading day so a
-- re-run updates rather than duplicates. Existing intraday rows are kept: the
-- readers pick the newest row of the day.
CREATE OR REPLACE FUNCTION public.apply_price_history(
    p_snapshot text, p_snapshot_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc jsonb; item jsonb; v_symbol text; v_company text; v_trade date;
    v_price numeric; v_variation numeric; v_id text;
    applied integer := 0; missing integer := 0;
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN
        RAISE EXCEPTION 'Service role required' USING ERRCODE = '42501';
    END IF;
    IF p_snapshot IS NULL OR octet_length(p_snapshot) > 8388608
       OR p_snapshot_sha256 IS NULL OR p_snapshot_sha256 !~ '^[a-f0-9]{64}$'
       OR encode(sha256(convert_to(p_snapshot, 'UTF8')), 'hex') <> p_snapshot_sha256 THEN
        RAISE EXCEPTION 'Invalid price history digest' USING ERRCODE = '22023';
    END IF;
    doc := p_snapshot::jsonb;
    IF jsonb_typeof(doc) IS DISTINCT FROM 'array'
       OR jsonb_array_length(doc) NOT BETWEEN 1 AND 20000 THEN
        RAISE EXCEPTION 'Invalid price history snapshot' USING ERRCODE = '22023';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(doc) LOOP
        v_symbol := item->>'symbol';
        v_trade := market_maintenance.try_date(item->>'trade_day');
        IF jsonb_typeof(item) IS DISTINCT FROM 'object'
           OR v_symbol IS NULL OR v_symbol !~ '^[A-Z0-9.]{1,16}$'
           OR v_trade IS NULL OR v_trade > current_date
           OR v_trade < current_date - interval '6 years'
           OR jsonb_typeof(item->'pa') IS DISTINCT FROM 'number'
           OR (item->>'pa')::numeric <= 0 THEN
            RAISE EXCEPTION 'Invalid price history row' USING ERRCODE = '22023';
        END IF;
    END LOOP;
    FOR item IN SELECT value FROM jsonb_array_elements(doc) LOOP
        v_symbol := item->>'symbol';
        v_trade := market_maintenance.try_date(item->>'trade_day');
        v_price := (item->>'pa')::numeric;
        v_variation := CASE WHEN jsonb_typeof(item->'variation') = 'number'
                            THEN (item->>'variation')::numeric END;
        SELECT f.name INTO v_company FROM public.format f WHERE f.symbol = v_symbol;
        IF NOT FOUND THEN
            missing := missing + 1;
            CONTINUE;
        END IF;
        v_id := 'hist-' || substr(encode(sha256(convert_to(
                    v_company || '|' || v_trade::text, 'UTF8')), 'hex'), 1, 40);
        INSERT INTO public.data (id, c_name, symbol, date, pa, variation)
        VALUES (v_id, v_company, v_symbol, (v_trade::text || 'T00:00:00Z')::timestamptz,
                v_price, v_variation)
        ON CONFLICT (id) DO UPDATE SET pa = excluded.pa,
            variation = excluded.variation, date = excluded.date;
        applied := applied + 1;
    END LOOP;
    RETURN jsonb_build_object('status', 'COMPLETE', 'snapshot_sha256', p_snapshot_sha256,
                              'applied', applied, 'missing', missing);
END $$;
REVOKE ALL ON FUNCTION public.apply_price_history(text, text) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.apply_price_history(text, text) TO service_role;
