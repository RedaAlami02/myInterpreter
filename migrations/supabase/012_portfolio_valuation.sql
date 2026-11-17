-- STAGED ONLY. Owner-authorized daily valuation; no cross-user access.
-- The write is date-idempotent and refuses non-closing-window or missing prices.
-- Staged receipt contract v2: EXISTING always returns the persisted snapshot.
CREATE FUNCTION portfolio_private.daily_valuation(p_owner uuid, p_now timestamptz)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    local_now timestamp;
    local_day date;
    holding record;
    price numeric;
    priced_at timestamptz;
    positions integer;
    total numeric := 0;
    value numeric;
    inserted integer := 0;
BEGIN
    IF p_owner IS NULL OR p_now IS NULL OR NOT isfinite(p_now) THEN
        RAISE EXCEPTION 'Invalid valuation input' USING ERRCODE = '22023';
    END IF;
    local_now := p_now AT TIME ZONE 'Africa/Casablanca';
    local_day := local_now::date;
    SELECT b.value INTO value FROM public.benefits b
        WHERE b.user_id=p_owner AND b.date=local_day;
    IF FOUND THEN
        RETURN jsonb_build_object('status','EXISTING','date',local_day,'value',value);
    END IF;
    -- A closing-window observation is required; morning prices are not a close.
    IF extract(isodow FROM local_now) > 5 OR local_now::time < time '15:45' THEN
        RETURN jsonb_build_object('status', 'OUTSIDE_WINDOW', 'date', local_day);
    END IF;
    SELECT count(*) INTO positions FROM public.portefeuille WHERE user_id = p_owner;
    IF positions > 500 THEN
        RAISE EXCEPTION 'Too many positions' USING ERRCODE = '54000';
    END IF;
    IF positions = 0 THEN
        IF NOT EXISTS (SELECT 1 FROM public.benefits WHERE user_id = p_owner) THEN
            RETURN jsonb_build_object('status', 'EMPTY', 'date', local_day);
        END IF;
    END IF;
    FOR holding IN
        SELECT c_name, quantity, total_cost FROM public.portefeuille
        WHERE user_id = p_owner ORDER BY c_name
    LOOP
        SELECT lp.pa, lp.date INTO price, priced_at
        FROM public.latest_prices lp WHERE lp.c_name = holding.c_name;
        IF NOT FOUND THEN
            RETURN jsonb_build_object('status', 'PRICE_UNAVAILABLE', 'date', local_day);
        END IF;
        IF price <= 0 OR priced_at > p_now
           OR (priced_at AT TIME ZONE 'Africa/Casablanca')::date <> local_day
           OR (priced_at AT TIME ZONE 'Africa/Casablanca')::time < time '15:45' THEN
            RETURN jsonb_build_object('status', 'PRICE_UNAVAILABLE', 'date', local_day);
        END IF;
        total := total + holding.quantity * price - holding.total_cost;
    END LOOP;
    value := round(total, 2);
    INSERT INTO public.benefits(user_id, date, value) VALUES (p_owner, local_day, value)
        ON CONFLICT (user_id, date) DO NOTHING;
    GET DIAGNOSTICS inserted = ROW_COUNT;
    IF inserted = 0 THEN
        -- Another request may have won while this one calculated. A receipt must
        -- describe the committed row, never this request's unused calculation.
        SELECT b.value INTO value FROM public.benefits b
            WHERE b.user_id=p_owner AND b.date=local_day;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Valuation receipt unavailable; retry' USING ERRCODE='40001';
        END IF;
    END IF;
    RETURN jsonb_build_object(
        'status', CASE WHEN inserted = 1 THEN 'CREATED' ELSE 'EXISTING' END,
        'date', local_day,
        'value', value
    );
END $$;
REVOKE ALL ON FUNCTION portfolio_private.daily_valuation(uuid,timestamptz)
    FROM PUBLIC, anon, authenticated, service_role;

CREATE FUNCTION public.record_daily_valuation()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    owner_id uuid := auth.uid();
BEGIN
    IF owner_id IS NULL OR auth.role() IS DISTINCT FROM 'authenticated' THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE = '42501';
    END IF;
    RETURN portfolio_private.daily_valuation(owner_id, clock_timestamp());
END $$;
REVOKE ALL ON FUNCTION public.record_daily_valuation() FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.record_daily_valuation() TO authenticated;
COMMENT ON FUNCTION public.record_daily_valuation() IS 'myInterpreter daily valuation v2; persisted receipts';
