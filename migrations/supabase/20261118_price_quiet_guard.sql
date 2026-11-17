-- Price freshness: never restamp an instrument that did not trade.
--
-- The capture now reports `traded` per instrument (quantity or transaction
-- count above zero). When it is false and a price already exists, the stored
-- date is kept: the price is the last traded one, not today's quote.

CREATE OR REPLACE FUNCTION public.apply_exchange_latest_prices(
    p_snapshot text, p_snapshot_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc jsonb; item jsonb; v_symbol text; v_company text; v_page text;
    v_price numeric; v_shares numeric; v_fetched timestamptz; v_traded boolean;
    v_company_na numeric; old_pa numeric; old_date timestamptz;
    applied integer := 0; unchanged integer := 0; skipped integer := 0;
    missing integer := 0; seen text[] := ARRAY[]::text[];
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN
        RAISE EXCEPTION 'Service role required' USING ERRCODE = '42501';
    END IF;
    IF p_snapshot IS NULL OR octet_length(p_snapshot) > 4194304
       OR p_snapshot_sha256 IS NULL OR p_snapshot_sha256 !~ '^[a-f0-9]{64}$'
       OR encode(sha256(convert_to(p_snapshot, 'UTF8')), 'hex') <> p_snapshot_sha256 THEN
        RAISE EXCEPTION 'Invalid price snapshot digest' USING ERRCODE = '22023';
    END IF;
    doc := p_snapshot::jsonb;
    IF jsonb_typeof(doc) IS DISTINCT FROM 'array'
       OR jsonb_array_length(doc) NOT BETWEEN 1 AND 200 THEN
        RAISE EXCEPTION 'Invalid price snapshot' USING ERRCODE = '22023';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(doc) LOOP
        CONTINUE WHEN jsonb_typeof(item) IS DISTINCT FROM 'object'
            OR jsonb_typeof(item->'price') IS DISTINCT FROM 'number'
            OR jsonb_typeof(item->'fetched_at') IS DISTINCT FROM 'string';
        v_symbol := item->>'symbol';
        v_price := (item->>'price')::numeric;
        v_fetched := (item->>'fetched_at')::timestamptz;
        v_page := item->>'page_sha256';
        IF v_symbol IS NULL OR v_symbol = ANY(seen)
           OR v_price <= 0 OR v_price > 1000000000000
           OR v_page IS NULL OR v_page !~ '^[a-f0-9]{64}$'
           OR NOT isfinite(v_fetched)
           OR v_fetched > clock_timestamp() + interval '5 minutes'
           OR v_fetched < clock_timestamp() - interval '7 days' THEN
            RAISE EXCEPTION 'Invalid price row' USING ERRCODE = '22023';
        END IF;
        seen := array_append(seen, v_symbol);
    END LOOP;
    FOR item IN SELECT value FROM jsonb_array_elements(doc) LOOP
        CONTINUE WHEN jsonb_typeof(item) IS DISTINCT FROM 'object'
            OR jsonb_typeof(item->'price') IS DISTINCT FROM 'number'
            OR jsonb_typeof(item->'fetched_at') IS DISTINCT FROM 'string';
        v_symbol := item->>'symbol';
        v_price := (item->>'price')::numeric;
        v_fetched := (item->>'fetched_at')::timestamptz;
        v_page := item->>'page_sha256';
        v_shares := CASE WHEN jsonb_typeof(item->'shares') = 'number'
                         THEN (item->>'shares')::numeric END;
        SELECT f.name INTO v_company FROM public.format f WHERE f.symbol = v_symbol;
        IF NOT FOUND THEN
            missing := missing + 1;
            INSERT INTO market_maintenance.price_publications
                (snapshot_sha256, symbol, new_pa, new_date, page_sha256, status, reason)
            VALUES (p_snapshot_sha256, v_symbol, v_price, v_fetched, v_page,
                    'SKIPPED', 'MISSING_MAPPING')
            ON CONFLICT (snapshot_sha256, symbol) DO NOTHING;
            CONTINUE;
        END IF;
        SELECT na INTO v_company_na FROM public.company WHERE name = v_company FOR UPDATE;
        IF NOT FOUND THEN
            missing := missing + 1;
            INSERT INTO market_maintenance.price_publications
                (snapshot_sha256, symbol, company_name, new_pa, new_date, page_sha256, status, reason)
            VALUES (p_snapshot_sha256, v_symbol, v_company, v_price, v_fetched, v_page,
                    'SKIPPED', 'MISSING_COMPANY')
            ON CONFLICT (snapshot_sha256, symbol) DO NOTHING;
            CONTINUE;
        END IF;
        IF v_shares IS NOT NULL AND v_shares > 0 AND v_company_na IS NOT NULL
           AND v_company_na > 0 AND abs(v_shares / v_company_na - 1) > 0.01 THEN
            skipped := skipped + 1;
            INSERT INTO market_maintenance.price_publications
                (snapshot_sha256, symbol, company_name, new_pa, new_date, page_sha256, status, reason)
            VALUES (p_snapshot_sha256, v_symbol, v_company, v_price, v_fetched, v_page,
                    'SKIPPED', 'SHARE_COUNT_MISMATCH')
            ON CONFLICT (snapshot_sha256, symbol) DO NOTHING;
            CONTINUE;
        END IF;
        v_traded := CASE WHEN jsonb_typeof(item->'traded') = 'boolean'
                         THEN (item->>'traded')::boolean END;
        SELECT pa, date INTO old_pa, old_date
          FROM public.latest_prices WHERE c_name = v_company FOR UPDATE;
        -- An instrument that did not trade today still quotes its last price.
        -- Restamping it with the publication time made a suspended stock look
        -- freshly priced to every freshness check.
        IF v_traded IS FALSE AND old_date IS NOT NULL THEN
            IF old_pa IS NOT DISTINCT FROM v_price THEN
                unchanged := unchanged + 1;
                INSERT INTO market_maintenance.price_publications
                    (snapshot_sha256, symbol, company_name, old_pa, old_date,
                     new_pa, new_date, page_sha256, status, reason)
                VALUES (p_snapshot_sha256, v_symbol, v_company, old_pa, old_date,
                        v_price, old_date, v_page, 'UNCHANGED', 'NOT_TRADED')
                ON CONFLICT (snapshot_sha256, symbol) DO NOTHING;
            ELSE
                UPDATE public.latest_prices SET pa = v_price
                 WHERE c_name = v_company;
                applied := applied + 1;
                INSERT INTO market_maintenance.price_publications
                    (snapshot_sha256, symbol, company_name, old_pa, old_date,
                     new_pa, new_date, page_sha256, status, reason)
                VALUES (p_snapshot_sha256, v_symbol, v_company, old_pa, old_date,
                        v_price, old_date, v_page, 'APPLIED', 'NOT_TRADED_PRICE_ONLY')
                ON CONFLICT (snapshot_sha256, symbol) DO NOTHING;
            END IF;
            CONTINUE;
        END IF;
        IF old_date IS NOT NULL AND old_date > v_fetched THEN
            skipped := skipped + 1;
            INSERT INTO market_maintenance.price_publications
                (snapshot_sha256, symbol, company_name, old_pa, old_date,
                 new_pa, new_date, page_sha256, status, reason)
            VALUES (p_snapshot_sha256, v_symbol, v_company, old_pa, old_date,
                    v_price, v_fetched, v_page, 'SKIPPED', 'OLDER_THAN_CURRENT')
            ON CONFLICT (snapshot_sha256, symbol) DO NOTHING;
            CONTINUE;
        END IF;
        INSERT INTO public.latest_prices(id, c_name, pa, date, origin_collection)
        VALUES (replace(gen_random_uuid()::text, '-', ''), v_company, v_price, v_fetched, 'latest_prices')
        ON CONFLICT (c_name) DO UPDATE
          SET pa = excluded.pa, date = excluded.date, origin_collection = 'latest_prices';
        IF old_pa IS NOT NULL AND old_pa = v_price AND old_date = v_fetched THEN
            unchanged := unchanged + 1;
        ELSE
            applied := applied + 1;
        END IF;
        INSERT INTO market_maintenance.price_publications
            (snapshot_sha256, symbol, company_name, old_pa, old_date,
             new_pa, new_date, page_sha256, status)
        VALUES (p_snapshot_sha256, v_symbol, v_company, old_pa, old_date,
                v_price, v_fetched, v_page,
                CASE WHEN old_pa IS NOT NULL AND old_pa = v_price AND old_date = v_fetched
                     THEN 'UNCHANGED' ELSE 'APPLIED' END)
        ON CONFLICT (snapshot_sha256, symbol) DO NOTHING;
    END LOOP;
    RETURN jsonb_build_object('status', 'COMPLETE', 'snapshot_sha256', p_snapshot_sha256,
                              'applied', applied, 'unchanged', unchanged,
                              'skipped', skipped, 'missing', missing);
END $$;
REVOKE ALL ON FUNCTION public.apply_exchange_latest_prices(text, text) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.apply_exchange_latest_prices(text, text) TO service_role;
