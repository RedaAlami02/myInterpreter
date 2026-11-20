-- A company that did not trade on the valuation day keeps its last close; that
-- is still its market value. Requiring an exact-day row blanked the whole
-- portfolio (and skipped the saved valuation) whenever one held line was
-- suspended or simply untraded, which is common: PROMOPHARM on 2026-11-20.
-- The basis stays HISTORY_CLOSE because the number still comes from the daily
-- close history; only the lookup is "latest on or before the day".
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
           AND (d.date AT TIME ZONE 'Africa/Casablanca')::date <= p_day
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
