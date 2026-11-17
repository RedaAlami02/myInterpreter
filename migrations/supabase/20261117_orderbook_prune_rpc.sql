-- Public entry point for order-book retention.
-- The prune function lives in market_maintenance, which PostgREST does not
-- expose; without this wrapper the scheduled prune could never be called.
CREATE OR REPLACE FUNCTION public.prune_exchange_orderbooks(
    p_intraday_days integer DEFAULT 7, p_daily_days integer DEFAULT 400)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN
        RAISE EXCEPTION 'Service role required' USING ERRCODE = '42501';
    END IF;
    RETURN market_maintenance.prune_market_orderbooks(p_intraday_days, p_daily_days);
END $$;
REVOKE ALL ON FUNCTION public.prune_exchange_orderbooks(integer, integer) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.prune_exchange_orderbooks(integer, integer) TO service_role;
