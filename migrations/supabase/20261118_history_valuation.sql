-- Daily valuation from the published close history.
--
-- The official-close path (021) stays disabled until a close batch is
-- published, so no valuation was ever saved automatically. These functions use
-- public.data — the daily closes this project publishes — and keep the same
-- semantics as the existing valuation: unrealised gain/loss
-- (sum of quantity x close - remaining cost) for the caller's holdings.
--
-- Backfill is deliberately conservative: a past day is only valued when no
-- transaction happened after it, so today's holdings are provably the holdings
-- of that day. Otherwise the day is skipped, never guessed.

CREATE OR REPLACE FUNCTION portfolio_private.value_from_history(
    p_owner uuid, p_day date, p_allow_backfill boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    holding record; price numeric; priced_on timestamptz;
    positions integer := 0; total numeric := 0; value numeric; inserted integer := 0;
    last_trade date;
BEGIN
    IF p_owner IS NULL OR p_day IS NULL OR p_day > current_date THEN
        RAISE EXCEPTION 'Invalid valuation day' USING ERRCODE = '22023';
    END IF;
    IF EXISTS (SELECT 1 FROM public.benefits b WHERE b.user_id = p_owner AND b.date = p_day) THEN
        RETURN jsonb_build_object('status', 'EXISTING', 'date', p_day);
    END IF;
    IF p_allow_backfill AND p_day < current_date THEN
        SELECT max(day) INTO last_trade FROM (
            SELECT (a.date AT TIME ZONE 'Africa/Casablanca')::date AS day
              FROM public.achats a WHERE a.user_id = p_owner
            UNION ALL
            SELECT (v.date AT TIME ZONE 'Africa/Casablanca')::date
              FROM public.ventes v WHERE v.user_id = p_owner) t;
        IF last_trade IS NOT NULL AND last_trade > p_day THEN
            RETURN jsonb_build_object('status', 'SKIPPED_TRADES_AFTER', 'date', p_day);
        END IF;
    END IF;
    SELECT count(*) INTO positions FROM public.portefeuille WHERE user_id = p_owner;
    IF positions = 0 THEN
        RETURN jsonb_build_object('status', 'EMPTY', 'date', p_day);
    END IF;
    IF positions > 500 THEN
        RAISE EXCEPTION 'Too many positions' USING ERRCODE = '54000';
    END IF;
    FOR holding IN
        SELECT c_name, quantity, total_cost FROM public.portefeuille
         WHERE user_id = p_owner ORDER BY c_name
    LOOP
        SELECT d.pa, d.date INTO price, priced_on
          FROM public.data d
         WHERE d.c_name = holding.c_name
           AND (d.date AT TIME ZONE 'Africa/Casablanca')::date = p_day
         ORDER BY d.date DESC
         LIMIT 1;
        IF NOT FOUND OR price IS NULL OR price <= 0 THEN
            RETURN jsonb_build_object('status', 'PRICE_UNAVAILABLE', 'date', p_day,
                                      'company', holding.c_name);
        END IF;
        total := total + holding.quantity * price - holding.total_cost;
    END LOOP;
    value := round(total, 2);
    INSERT INTO public.benefits(user_id, date, value) VALUES (p_owner, p_day, value)
        ON CONFLICT (user_id, date) DO NOTHING;
    GET DIAGNOSTICS inserted = ROW_COUNT;
    RETURN jsonb_build_object('status', CASE WHEN inserted = 1 THEN 'CREATED' ELSE 'EXISTING' END,
                              'date', p_day, 'value', value, 'basis', 'HISTORY_CLOSE');
END $$;
REVOKE ALL ON FUNCTION portfolio_private.value_from_history(uuid, date, boolean)
    FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.record_daily_valuation_from_history()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE owner_id uuid := auth.uid();
BEGIN
    IF owner_id IS NULL OR auth.role() IS DISTINCT FROM 'authenticated' THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE = '42501';
    END IF;
    RETURN portfolio_private.value_from_history(owner_id,
        (clock_timestamp() AT TIME ZONE 'Africa/Casablanca')::date, false);
END $$;
REVOKE ALL ON FUNCTION public.record_daily_valuation_from_history() FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.record_daily_valuation_from_history() TO authenticated;

-- Service-role sweep: one valuation per owner for a given day. No personal
-- values are returned, only counts.
CREATE OR REPLACE FUNCTION public.record_all_valuations_from_history(
    p_day date DEFAULT NULL, p_allow_backfill boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    owner_id uuid; day date; result jsonb;
    created integer := 0; existing integer := 0; no_price integer := 0;
    skipped integer := 0; empty integer := 0; owners integer := 0;
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN
        RAISE EXCEPTION 'Service role required' USING ERRCODE = '42501';
    END IF;
    day := coalesce(p_day, (clock_timestamp() AT TIME ZONE 'Africa/Casablanca')::date);
    FOR owner_id IN SELECT DISTINCT user_id FROM public.portefeuille LOOP
        owners := owners + 1;
        result := portfolio_private.value_from_history(owner_id, day, p_allow_backfill);
        CASE result->>'status'
            WHEN 'CREATED' THEN created := created + 1;
            WHEN 'EXISTING' THEN existing := existing + 1;
            WHEN 'PRICE_UNAVAILABLE' THEN no_price := no_price + 1;
            WHEN 'EMPTY' THEN empty := empty + 1;
            WHEN 'SKIPPED_TRADES_AFTER' THEN skipped := skipped + 1;
            ELSE skipped := skipped + 1;
        END CASE;
    END LOOP;
    RETURN jsonb_build_object('status', 'COMPLETE', 'day', day, 'owners', owners,
                              'created', created, 'existing', existing,
                              'price_unavailable', no_price, 'empty', empty,
                              'skipped', skipped);
END $$;
REVOKE ALL ON FUNCTION public.record_all_valuations_from_history(date, boolean) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.record_all_valuations_from_history(date, boolean) TO service_role;
COMMENT ON FUNCTION public.record_all_valuations_from_history(date, boolean) IS
    'Service-role daily valuation from published closes; backfill skips days with later trades';
