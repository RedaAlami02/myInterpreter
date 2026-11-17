-- One-time backfill of daily index closes into public.data.
-- Historical dates are normal here, unlike live publication which only accepts
-- the last seven days. Rows are keyed by index and trading day; older rows for
-- the same day are removed so a legacy duplicate cannot double the chart.
CREATE SCHEMA IF NOT EXISTS market_maintenance;
REVOKE ALL ON SCHEMA market_maintenance FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS market_maintenance.index_backfills (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_sha256 text NOT NULL CHECK (snapshot_sha256 ~ '^[a-f0-9]{64}$'),
    symbol text NOT NULL,
    trade_day date NOT NULL,
    close numeric NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (snapshot_sha256, symbol, trade_day)
);
ALTER TABLE market_maintenance.index_backfills ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE market_maintenance.index_backfills FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.apply_index_history(
    p_snapshot text, p_snapshot_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc jsonb; item jsonb; v_symbol text; v_trade date;
    v_price numeric; v_variation numeric; v_id text;
    seen text[] := ARRAY[]::text[];
    applied integer := 0; removed integer := 0; v_deleted integer;
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN
        RAISE EXCEPTION 'Service role required' USING ERRCODE = '42501';
    END IF;
    IF p_snapshot IS NULL OR octet_length(p_snapshot) > 4194304
       OR p_snapshot_sha256 IS NULL OR p_snapshot_sha256 !~ '^[a-f0-9]{64}$'
       OR encode(sha256(convert_to(p_snapshot, 'UTF8')), 'hex') <> p_snapshot_sha256 THEN
        RAISE EXCEPTION 'Invalid index history digest' USING ERRCODE = '22023';
    END IF;
    doc := p_snapshot::jsonb;
    IF jsonb_typeof(doc) IS DISTINCT FROM 'array'
       OR jsonb_array_length(doc) NOT BETWEEN 1 AND 5000 THEN
        RAISE EXCEPTION 'Invalid index history snapshot' USING ERRCODE = '22023';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(doc) LOOP
        v_symbol := item->>'symbol';
        v_trade := market_maintenance.try_date(item->>'trade_day');
        IF jsonb_typeof(item) IS DISTINCT FROM 'object'
           OR v_symbol IS NULL OR v_symbol NOT IN ('MASI', 'MASI20')
           OR v_trade IS NULL OR v_trade > current_date
           OR v_trade < current_date - interval '6 years'
           OR jsonb_typeof(item->'pa') IS DISTINCT FROM 'number'
           OR (item->>'pa')::numeric <= 0 THEN
            RAISE EXCEPTION 'Invalid index history row' USING ERRCODE = '22023';
        END IF;
        IF (v_symbol || v_trade::text) = ANY(seen) THEN
            RAISE EXCEPTION 'Duplicate index history row' USING ERRCODE = '22023';
        END IF;
        seen := array_append(seen, v_symbol || v_trade::text);
    END LOOP;
    FOR item IN SELECT value FROM jsonb_array_elements(doc) LOOP
        v_symbol := item->>'symbol';
        v_trade := market_maintenance.try_date(item->>'trade_day');
        v_price := (item->>'pa')::numeric;
        v_variation := CASE WHEN jsonb_typeof(item->'variation') = 'number'
                            THEN (item->>'variation')::numeric END;
        v_id := 'idx-' || substr(encode(sha256(convert_to(
                    v_symbol || '|' || v_trade::text, 'UTF8')), 'hex'), 1, 40);
        DELETE FROM public.data
         WHERE c_name = v_symbol
           AND date >= v_trade AND date < v_trade + 1
           AND id <> v_id;
        GET DIAGNOSTICS v_deleted = ROW_COUNT;
        removed := removed + v_deleted;
        INSERT INTO public.data (id, c_name, symbol, date, pa, variation)
        VALUES (v_id, v_symbol, v_symbol, (v_trade::text || 'T00:00:00Z')::timestamptz,
                v_price, v_variation)
        ON CONFLICT (id) DO UPDATE SET pa = excluded.pa,
            variation = excluded.variation, date = excluded.date;
        applied := applied + 1;
        INSERT INTO market_maintenance.index_backfills
            (snapshot_sha256, symbol, trade_day, close)
        VALUES (p_snapshot_sha256, v_symbol, v_trade, v_price)
        ON CONFLICT DO NOTHING;
    END LOOP;
    RETURN jsonb_build_object('status', 'COMPLETE', 'snapshot_sha256', p_snapshot_sha256,
                              'applied', applied, 'replaced_rows', removed);
END $$;
REVOKE ALL ON FUNCTION public.apply_index_history(text, text) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.apply_index_history(text, text) TO service_role;
