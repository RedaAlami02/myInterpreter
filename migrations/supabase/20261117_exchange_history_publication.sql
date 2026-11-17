-- Daily history publication into public.data.
--
-- Charts, the screener and the MASI panel read public.data, which the retired
-- Appwrite getprice function used to append to. Nothing wrote it after the
-- migration, so every surface showed 21 October rows. This RPC accepts one
-- snapshot per capture and upserts one row per company and trading day.

CREATE SCHEMA IF NOT EXISTS market_maintenance;
REVOKE ALL ON SCHEMA market_maintenance FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION market_maintenance.try_date(p_value text)
RETURNS date LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
BEGIN
    RETURN p_value::date;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION market_maintenance.try_date(text) FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS market_maintenance.history_publications (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_sha256 text NOT NULL CHECK (snapshot_sha256 ~ '^[a-f0-9]{64}$'),
    symbol text NOT NULL,
    company_name text,
    trade_day date,
    price numeric,
    status text NOT NULL CHECK (status IN ('APPLIED', 'UPDATED', 'SKIPPED')),
    reason text,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (snapshot_sha256, symbol)
);
ALTER TABLE market_maintenance.history_publications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE market_maintenance.history_publications FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.apply_exchange_history(
    p_snapshot text, p_snapshot_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc jsonb; item jsonb; v_symbol text; v_company text; v_trade date;
    v_date timestamptz; v_price numeric; v_cap numeric; v_id text;
    v_existing timestamptz;
    seen text[] := ARRAY[]::text[];
    applied integer := 0; updated integer := 0; skipped integer := 0; missing integer := 0;
    optional_numeric text;
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN
        RAISE EXCEPTION 'Service role required' USING ERRCODE = '42501';
    END IF;
    IF p_snapshot IS NULL OR octet_length(p_snapshot) > 4194304
       OR p_snapshot_sha256 IS NULL OR p_snapshot_sha256 !~ '^[a-f0-9]{64}$'
       OR encode(sha256(convert_to(p_snapshot, 'UTF8')), 'hex') <> p_snapshot_sha256 THEN
        RAISE EXCEPTION 'Invalid history snapshot digest' USING ERRCODE = '22023';
    END IF;
    doc := p_snapshot::jsonb;
    IF jsonb_typeof(doc) IS DISTINCT FROM 'array'
       OR jsonb_array_length(doc) NOT BETWEEN 1 AND 200 THEN
        RAISE EXCEPTION 'Invalid history snapshot' USING ERRCODE = '22023';
    END IF;

    FOR item IN SELECT value FROM jsonb_array_elements(doc) LOOP
        IF jsonb_typeof(item) IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION 'Invalid history row' USING ERRCODE = '22023';
        END IF;
        v_symbol := item->>'symbol';
        v_trade := market_maintenance.try_date(item->>'trade_day');
        v_date := market_maintenance.try_timestamptz(item->>'date');
        IF v_symbol IS NULL OR v_symbol !~ '^[A-Z0-9.]{1,16}$' OR v_symbol = ANY(seen)
           OR v_trade IS NULL
           OR v_date IS NULL
           OR v_date > clock_timestamp() + interval '5 minutes'
           OR v_date < clock_timestamp() - interval '7 days'
           OR jsonb_typeof(item->'pa') IS DISTINCT FROM 'number'
           OR (item->>'pa')::numeric <= 0 OR (item->>'pa')::numeric >= 1000000000 THEN
            RAISE EXCEPTION 'Invalid history row' USING ERRCODE = '22023';
        END IF;
        FOREACH optional_numeric IN ARRAY ARRAY['cb','market_cap','per','peg','pr','pb',
                                                'variation','variation_v','cours_ref',
                                                'open_price','high','low','volume','qty_traded'] LOOP
            IF item ? optional_numeric AND jsonb_typeof(item->optional_numeric) <> 'number' THEN
                RAISE EXCEPTION 'Invalid history field %', optional_numeric USING ERRCODE = '22023';
            END IF;
        END LOOP;
        IF (item ? 'per_rating' AND item->>'per_rating' NOT IN ('green','orange','red'))
           OR (item ? 'peg_rating' AND item->>'peg_rating' NOT IN ('green','orange','red'))
           OR (item ? 'pr_rating' AND item->>'pr_rating' NOT IN ('green','orange','red'))
           OR (item ? 'pb_rating' AND item->>'pb_rating' NOT IN ('green','orange','red')) THEN
            RAISE EXCEPTION 'Invalid history rating' USING ERRCODE = '22023';
        END IF;
        seen := array_append(seen, v_symbol);
    END LOOP;

    FOR item IN SELECT value FROM jsonb_array_elements(doc) LOOP
        v_symbol := item->>'symbol';
        v_trade := market_maintenance.try_date(item->>'trade_day');
        v_date := market_maintenance.try_timestamptz(item->>'date');
        v_price := (item->>'pa')::numeric;
        SELECT f.name INTO v_company FROM public.format f WHERE f.symbol = v_symbol;
        IF NOT FOUND THEN
            missing := missing + 1;
            INSERT INTO market_maintenance.history_publications
                (snapshot_sha256, symbol, trade_day, price, status, reason)
            VALUES (p_snapshot_sha256, v_symbol, v_trade, v_price, 'SKIPPED', 'MISSING_MAPPING')
            ON CONFLICT (snapshot_sha256, symbol) DO NOTHING;
            CONTINUE;
        END IF;
        v_cap := CASE WHEN jsonb_typeof(item->'cb') = 'number' THEN (item->>'cb')::numeric END;
        v_id := 'hist-' || substr(encode(sha256(convert_to(
                    v_company || '|' || v_trade::text, 'UTF8')), 'hex'), 1, 40);
        SELECT date INTO v_existing FROM public.data WHERE id = v_id;
        IF v_existing IS NOT NULL AND v_existing >= v_date THEN
            skipped := skipped + 1;
            INSERT INTO market_maintenance.history_publications
                (snapshot_sha256, symbol, company_name, trade_day, price, status, reason)
            VALUES (p_snapshot_sha256, v_symbol, v_company, v_trade, v_price,
                    'SKIPPED', 'OLDER_THAN_STORED')
            ON CONFLICT (snapshot_sha256, symbol) DO NOTHING;
            CONTINUE;
        END IF;
        IF v_existing IS NOT NULL THEN updated := updated + 1; ELSE applied := applied + 1; END IF;
        INSERT INTO public.data (
            id, c_name, symbol, date, pa, cb, market_cap, per, peg, pr, pb,
            per_rating, peg_rating, pr_rating, pb_rating, variation, variation_v,
            cours_ref, open_price, high, low, volume, qty_traded)
        VALUES (
            v_id, v_company, v_symbol, v_date, v_price, v_cap, v_cap,
            CASE WHEN jsonb_typeof(item->'per') = 'number' THEN (item->>'per')::numeric END,
            CASE WHEN jsonb_typeof(item->'peg') = 'number' THEN (item->>'peg')::numeric END,
            CASE WHEN jsonb_typeof(item->'pr') = 'number' THEN (item->>'pr')::numeric END,
            CASE WHEN jsonb_typeof(item->'pb') = 'number' THEN (item->>'pb')::numeric END,
            item->>'per_rating', item->>'peg_rating', item->>'pr_rating', item->>'pb_rating',
            CASE WHEN jsonb_typeof(item->'variation') = 'number' THEN (item->>'variation')::numeric END,
            CASE WHEN jsonb_typeof(item->'variation_v') = 'number' THEN (item->>'variation_v')::numeric END,
            CASE WHEN jsonb_typeof(item->'cours_ref') = 'number' THEN (item->>'cours_ref')::numeric END,
            CASE WHEN jsonb_typeof(item->'open_price') = 'number' THEN (item->>'open_price')::numeric END,
            CASE WHEN jsonb_typeof(item->'high') = 'number' THEN (item->>'high')::numeric END,
            CASE WHEN jsonb_typeof(item->'low') = 'number' THEN (item->>'low')::numeric END,
            CASE WHEN jsonb_typeof(item->'volume') = 'number' THEN (item->>'volume')::numeric END,
            CASE WHEN jsonb_typeof(item->'qty_traded') = 'number' THEN (item->>'qty_traded')::numeric END)
        ON CONFLICT (id) DO UPDATE SET
            pa = excluded.pa, date = excluded.date, cb = excluded.cb,
            market_cap = excluded.market_cap, per = excluded.per, peg = excluded.peg,
            pr = excluded.pr, pb = excluded.pb, per_rating = excluded.per_rating,
            peg_rating = excluded.peg_rating, pr_rating = excluded.pr_rating,
            pb_rating = excluded.pb_rating, variation = excluded.variation,
            variation_v = excluded.variation_v, cours_ref = excluded.cours_ref,
            open_price = excluded.open_price, high = excluded.high, low = excluded.low,
            volume = excluded.volume, qty_traded = excluded.qty_traded
        WHERE excluded.date > public.data.date;
        INSERT INTO market_maintenance.history_publications
            (snapshot_sha256, symbol, company_name, trade_day, price, status)
        VALUES (p_snapshot_sha256, v_symbol, v_company, v_trade, v_price,
                CASE WHEN v_existing IS NOT NULL THEN 'UPDATED' ELSE 'APPLIED' END)
        ON CONFLICT (snapshot_sha256, symbol) DO NOTHING;
    END LOOP;
    RETURN jsonb_build_object('status', 'COMPLETE', 'snapshot_sha256', p_snapshot_sha256,
                              'applied', applied, 'updated', updated,
                              'skipped', skipped, 'missing', missing);
END $$;
REVOKE ALL ON FUNCTION public.apply_exchange_history(text, text) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.apply_exchange_history(text, text) TO service_role;
