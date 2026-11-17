-- Full non-personal evidence/archives. No auth, trades, holdings or credentials.
CREATE SCHEMA IF NOT EXISTS recovery_archive;
REVOKE ALL ON SCHEMA recovery_archive FROM PUBLIC, anon, authenticated, service_role;
CREATE TABLE IF NOT EXISTS recovery_archive.files (
    archive_key text PRIMARY KEY,
    category text NOT NULL,
    original_path text NOT NULL,
    source_sha256 text NOT NULL CHECK(source_sha256 ~ '^[0-9a-f]{64}$'),
    source_bytes bigint NOT NULL CHECK(source_bytes>=0),
    content bytea NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    restored_at timestamptz NOT NULL DEFAULT now(),
    CHECK(octet_length(content)=source_bytes)
);
COMMENT ON SCHEMA recovery_archive IS 'myInterpreter nonpersonal archive v1';
COMMENT ON TABLE recovery_archive.files IS 'myInterpreter nonpersonal archive v1';
ALTER TABLE recovery_archive.files ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA recovery_archive FROM PUBLIC, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA recovery_archive REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS public.company_profiles (
    id text PRIMARY KEY,
    c_name text NOT NULL,
    captured_at timestamptz NOT NULL,
    profile jsonb NOT NULL CHECK(jsonb_typeof(profile)='object')
);
CREATE TABLE IF NOT EXISTS public.market_snapshots (
    id text PRIMARY KEY,
    captured_at timestamptz NOT NULL,
    snapshot jsonb NOT NULL CHECK(jsonb_typeof(snapshot)='object')
);
CREATE TABLE IF NOT EXISTS public.market_reference (
    id text PRIMARY KEY,
    captured_at timestamptz NOT NULL,
    reference jsonb NOT NULL CHECK(jsonb_typeof(reference)='object')
);
CREATE TABLE IF NOT EXISTS public.market_orderbooks (
    id text PRIMARY KEY,
    symbol text NOT NULL,
    captured_at timestamptz NOT NULL,
    snapshot jsonb NOT NULL CHECK(jsonb_typeof(snapshot)='object')
);
CREATE TABLE IF NOT EXISTS public.dividend_source_snapshots (
    id text PRIMARY KEY,
    payment_year integer NOT NULL,
    captured_at timestamptz NOT NULL,
    calendar jsonb NOT NULL CHECK(jsonb_typeof(calendar)='object')
);
DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['company_profiles','market_snapshots','market_reference','market_orderbooks','dividend_source_snapshots'] LOOP
        EXECUTE format('COMMENT ON TABLE public.%I IS %L',tab,'myInterpreter nonpersonal archive v1');
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',tab);
        EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC,anon,authenticated,service_role',tab);
        EXECUTE format('GRANT SELECT ON public.%I TO authenticated,service_role',tab);
        EXECUTE format('DROP POLICY IF EXISTS supplemental_public_read ON public.%I',tab);
        EXECUTE format('CREATE POLICY supplemental_public_read ON public.%I FOR SELECT TO authenticated USING(true)',tab);
    END LOOP;
END $$;
CREATE INDEX IF NOT EXISTS market_snapshots_capture_idx ON public.market_snapshots(captured_at DESC,id);
CREATE INDEX IF NOT EXISTS market_orderbooks_symbol_idx ON public.market_orderbooks(symbol,captured_at DESC,id);
