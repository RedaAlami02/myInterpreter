-- OPT-IN public read-only market access. Apply only if the product should serve
-- Bourse de Casablanca market data without sign-in. Portfolio and user tables are
-- deliberately excluded. The application must also set
-- SUPABASE_ALLOW_ANONYMOUS_MARKET=true (or allow_anonymous_market => true).
DO $$
DECLARE
    tbl text;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['company', 'format', 'dividends',
                               'latest_prices', 'data', 'daily_price_reference']
    LOOP
        EXECUTE format('GRANT SELECT ON TABLE public.%I TO anon', tbl);
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_policies
            WHERE schemaname = 'public' AND tablename = tbl
              AND policyname = 'market_public_anon_read'
        ) THEN
            EXECUTE format(
                'CREATE POLICY market_public_anon_read ON public.%I FOR SELECT TO anon USING (true)',
                tbl);
        END IF;
    END LOOP;
END $$;

-- The recurring-feed display path uses this RPC for verified closes.
DO $$
BEGIN
    IF to_regprocedure('public.read_latest_price_references_v1()') IS NOT NULL THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.read_latest_price_references_v1() TO anon';
    END IF;
END $$;

COMMENT ON POLICY market_public_anon_read ON public.company IS
    'Opt-in anonymous read of public market fundamentals; no portfolio access';
