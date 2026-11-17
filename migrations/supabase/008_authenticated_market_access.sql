-- Owner requested no anonymous database data access. Data stays unchanged.
-- Keep Supabase Auth signup/login available, and preserve private owner RLS.
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM PUBLIC, anon;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, anon;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC, anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC, anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC, anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon;
DO $$
DECLARE tab text; col text; item record;
BEGIN
    -- Column grants can survive a table-level REVOKE.
    FOR item IN SELECT table_name,column_name FROM information_schema.columns
        WHERE table_schema='public' LOOP
        EXECUTE format('REVOKE ALL PRIVILEGES (%I) ON TABLE public.%I FROM PUBLIC,anon', item.column_name,item.table_name);
    END LOOP;
    FOR item IN SELECT tablename,policyname,roles FROM pg_policies
        WHERE schemaname='public' AND policyname IN
            ('market_public_read','supplemental_public_read','daily_reference_public_read') LOOP
        EXECUTE format('ALTER POLICY %I ON public.%I TO authenticated',item.policyname,item.tablename);
    END LOOP;
END $$;
