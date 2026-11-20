-- Count a replayed snapshot as unchanged, not applied. The insert uses
-- ON CONFLICT (id) DO NOTHING, but the receipt incremented unconditionally, so
-- re-sending the same capture reported the whole book as newly applied.
-- Only the receipt is affected; stored data is unchanged.

CREATE OR REPLACE FUNCTION public.apply_exchange_orderbooks(
    p_snapshot text, p_snapshot_sha256 text, p_prune boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc jsonb; item jsonb; level jsonb;
    v_symbol text; v_source text; v_captured timestamptz; v_market_time text;
    v_status text; v_phase text;
    v_bids jsonb; v_asks jsonb; v_hash text;
    v_last_captured timestamptz; v_last_hash text;
    v_price numeric; v_quantity numeric; v_orders numeric; v_prev numeric;
    v_max_levels constant integer := 20;
    seen text[] := ARRAY[]::text[];
    applied integer := 0; unchanged integer := 0; skipped integer := 0; missing integer := 0;
    inserted integer := 0;
    prune_result jsonb := NULL;
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN
        RAISE EXCEPTION 'Service role required' USING ERRCODE = '42501';
    END IF;
    IF p_snapshot IS NULL OR octet_length(p_snapshot) > 8388608
       OR p_snapshot_sha256 IS NULL OR p_snapshot_sha256 !~ '^[a-f0-9]{64}$'
       OR encode(sha256(convert_to(p_snapshot, 'UTF8')), 'hex') <> p_snapshot_sha256 THEN
        RAISE EXCEPTION 'Invalid order-book snapshot digest' USING ERRCODE = '22023';
    END IF;
    doc := p_snapshot::jsonb;
    IF jsonb_typeof(doc) IS DISTINCT FROM 'array'
       OR jsonb_array_length(doc) NOT BETWEEN 1 AND 200 THEN
        RAISE EXCEPTION 'Invalid order-book snapshot' USING ERRCODE = '22023';
    END IF;

    -- Validate the whole batch before writing any row: a malformed capture must
    -- never leave half a session in the archive.
    FOR item IN SELECT value FROM jsonb_array_elements(doc) LOOP
        IF jsonb_typeof(item) IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION 'Invalid order-book row' USING ERRCODE = '22023';
        END IF;
        v_symbol := item->>'symbol';
        v_source := item->>'source';
        v_captured := market_maintenance.try_timestamptz(item->>'captured_at');
        IF v_symbol IS NULL OR v_symbol !~ '^[A-Z0-9.]{1,16}$' OR v_symbol = ANY(seen)
           OR v_source IS NULL OR v_source NOT IN ('MEDIAS24_PUBLIC', 'CDG_DELAYED')
           OR v_captured IS NULL
           OR v_captured > clock_timestamp() + interval '5 minutes'
           OR v_captured < clock_timestamp() - interval '7 days'
           OR jsonb_typeof(item->'bids') IS DISTINCT FROM 'array'
           OR jsonb_typeof(item->'asks') IS DISTINCT FROM 'array'
           OR (CASE WHEN jsonb_typeof(item->'bids') = 'array'
                    THEN jsonb_array_length(item->'bids') ELSE v_max_levels + 1 END) > v_max_levels
           OR (CASE WHEN jsonb_typeof(item->'asks') = 'array'
                    THEN jsonb_array_length(item->'asks') ELSE v_max_levels + 1 END) > v_max_levels
           OR (CASE WHEN jsonb_typeof(item->'bids') = 'array' AND jsonb_typeof(item->'asks') = 'array'
                    THEN jsonb_array_length(item->'bids') + jsonb_array_length(item->'asks')
                    ELSE 1 END) = 0 THEN
            RAISE EXCEPTION 'Invalid order-book row' USING ERRCODE = '22023';
        END IF;
        FOR level IN SELECT value FROM jsonb_array_elements(item->'bids') LOOP
            IF jsonb_typeof(level) IS DISTINCT FROM 'object'
               OR jsonb_typeof(level->'price') IS DISTINCT FROM 'number'
               OR jsonb_typeof(level->'quantity') IS DISTINCT FROM 'number' THEN
                RAISE EXCEPTION 'Invalid bid level' USING ERRCODE = '22023';
            END IF;
            v_price := (level->>'price')::numeric;
            v_quantity := (level->>'quantity')::numeric;
            IF v_price <= 0 OR v_price >= 1000000000 OR v_quantity < 0
               OR (v_prev IS NOT NULL AND v_price >= v_prev) THEN
                RAISE EXCEPTION 'Invalid bid level' USING ERRCODE = '22023';
            END IF;
            v_prev := v_price;
        END LOOP;
        v_prev := NULL;
        FOR level IN SELECT value FROM jsonb_array_elements(item->'asks') LOOP
            IF jsonb_typeof(level) IS DISTINCT FROM 'object'
               OR jsonb_typeof(level->'price') IS DISTINCT FROM 'number'
               OR jsonb_typeof(level->'quantity') IS DISTINCT FROM 'number' THEN
                RAISE EXCEPTION 'Invalid ask level' USING ERRCODE = '22023';
            END IF;
            v_price := (level->>'price')::numeric;
            v_quantity := (level->>'quantity')::numeric;
            IF v_price <= 0 OR v_price >= 1000000000 OR v_quantity < 0
               OR (v_prev IS NOT NULL AND v_price <= v_prev) THEN
                RAISE EXCEPTION 'Invalid ask level' USING ERRCODE = '22023';
            END IF;
            v_prev := v_price;
        END LOOP;
        v_prev := NULL;
        seen := array_append(seen, v_symbol);
    END LOOP;

    FOR item IN SELECT value FROM jsonb_array_elements(doc) LOOP
        v_symbol := item->>'symbol';
        v_source := item->>'source';
        v_captured := market_maintenance.try_timestamptz(item->>'captured_at');
        v_market_time := item->>'market_time';
        v_status := item->>'status';
        v_phase := item->>'phase';
        IF NOT EXISTS (SELECT 1 FROM public.format WHERE symbol = v_symbol) THEN
            missing := missing + 1;
            INSERT INTO market_maintenance.orderbook_publications
                (snapshot_sha256, symbol, source, captured_at, status, reason)
            VALUES (p_snapshot_sha256, v_symbol, v_source, v_captured, 'SKIPPED', 'MISSING_MAPPING')
            ON CONFLICT (snapshot_sha256, symbol) DO NOTHING;
            CONTINUE;
        END IF;
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'price', (e->>'price')::numeric,
                   'quantity', (e->>'quantity')::numeric,
                   'orders', CASE WHEN jsonb_typeof(e->'orders') = 'number'
                                  THEN (e->>'orders')::numeric END) ORDER BY ord), '[]'::jsonb)
          INTO v_bids
          FROM jsonb_array_elements(item->'bids') WITH ORDINALITY AS t(e, ord);
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'price', (e->>'price')::numeric,
                   'quantity', (e->>'quantity')::numeric,
                   'orders', CASE WHEN jsonb_typeof(e->'orders') = 'number'
                                  THEN (e->>'orders')::numeric END) ORDER BY ord), '[]'::jsonb)
          INTO v_asks
          FROM jsonb_array_elements(item->'asks') WITH ORDINALITY AS t(e, ord);
        v_hash := encode(sha256(convert_to(jsonb_build_array(v_bids, v_asks)::text, 'UTF8')), 'hex');
        SELECT captured_at, snapshot->>'content_hash'
          INTO v_last_captured, v_last_hash
          FROM public.market_orderbooks
          WHERE symbol = v_symbol
          ORDER BY captured_at DESC
          LIMIT 1
          FOR UPDATE;
        IF v_last_captured IS NOT NULL AND v_captured < v_last_captured THEN
            skipped := skipped + 1;
            INSERT INTO market_maintenance.orderbook_publications
                (snapshot_sha256, symbol, source, captured_at, content_hash,
                 bid_levels, ask_levels, status, reason)
            VALUES (p_snapshot_sha256, v_symbol, v_source, v_captured, v_hash,
                    jsonb_array_length(v_bids), jsonb_array_length(v_asks),
                    'SKIPPED', 'OLDER_THAN_CURRENT')
            ON CONFLICT (snapshot_sha256, symbol) DO NOTHING;
            CONTINUE;
        END IF;
        IF v_last_hash IS NOT DISTINCT FROM v_hash THEN
            unchanged := unchanged + 1;
            INSERT INTO market_maintenance.orderbook_publications
                (snapshot_sha256, symbol, source, captured_at, content_hash,
                 bid_levels, ask_levels, status, reason)
            VALUES (p_snapshot_sha256, v_symbol, v_source, v_captured, v_hash,
                    jsonb_array_length(v_bids), jsonb_array_length(v_asks),
                    'UNCHANGED', 'IDENTICAL_TO_LATEST')
            ON CONFLICT (snapshot_sha256, symbol) DO NOTHING;
            CONTINUE;
        END IF;
        INSERT INTO public.market_orderbooks (id, symbol, captured_at, snapshot)
        VALUES ('ob-' || substr(encode(sha256(convert_to(
                    v_symbol || '|' || v_captured::text || '|' || v_hash, 'UTF8')), 'hex'), 1, 40),
                v_symbol, v_captured,
                jsonb_build_object(
                    'symbol', v_symbol, 'source', v_source, 'captured_at', v_captured,
                    'market_time', v_market_time, 'status', v_status, 'phase', v_phase,
                    'bids', v_bids, 'asks', v_asks, 'content_hash', v_hash,
                    'levels', jsonb_build_object('bids', jsonb_array_length(v_bids),
                                                 'asks', jsonb_array_length(v_asks))))
        ON CONFLICT (id) DO NOTHING;
        GET DIAGNOSTICS inserted = ROW_COUNT;
        IF inserted = 0 THEN
            -- A replay of the same snapshot: the row already exists.
            unchanged := unchanged + 1;
            CONTINUE;
        END IF;
        applied := applied + 1;
        INSERT INTO market_maintenance.orderbook_publications
            (snapshot_sha256, symbol, source, captured_at, content_hash,
             bid_levels, ask_levels, status)
        VALUES (p_snapshot_sha256, v_symbol, v_source, v_captured, v_hash,
                jsonb_array_length(v_bids), jsonb_array_length(v_asks), 'APPLIED')
        ON CONFLICT (snapshot_sha256, symbol) DO NOTHING;
    END LOOP;
    IF p_prune THEN
        prune_result := market_maintenance.prune_market_orderbooks();
    END IF;
    RETURN jsonb_build_object('status', 'COMPLETE', 'snapshot_sha256', p_snapshot_sha256,
                              'applied', applied, 'unchanged', unchanged,
                              'skipped', skipped, 'missing', missing,
                              'prune', prune_result);
END $$;
REVOKE ALL ON FUNCTION public.apply_exchange_orderbooks(text, text, boolean) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.apply_exchange_orderbooks(text, text, boolean) TO service_role;
