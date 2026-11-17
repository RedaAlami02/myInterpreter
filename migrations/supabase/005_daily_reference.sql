-- Daily source observations retain date-only semantics and measured quality.
-- They never replace recovered ticks, ratios, or latest-price records.
CREATE TABLE IF NOT EXISTS public.daily_price_reference (
    id text PRIMARY KEY,
    c_name text NOT NULL,
    symbol text NOT NULL,
    period_day date NOT NULL,
    close numeric NOT NULL CHECK(close>0),
    bar jsonb NOT NULL CHECK(jsonb_typeof(bar)='object'),
    quality jsonb NOT NULL CHECK(jsonb_typeof(quality)='object'),
    source_sha256 text NOT NULL CHECK(source_sha256 ~ '^[0-9a-f]{64}$'),
    UNIQUE(source_sha256,symbol,period_day)
);
COMMENT ON TABLE public.daily_price_reference IS 'myInterpreter daily reference v1';
ALTER TABLE public.daily_price_reference ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.daily_price_reference FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.daily_price_reference TO authenticated,service_role;
DROP POLICY IF EXISTS daily_reference_public_read ON public.daily_price_reference;
CREATE POLICY daily_reference_public_read ON public.daily_price_reference
    FOR SELECT TO authenticated USING(true);
CREATE INDEX IF NOT EXISTS daily_reference_symbol_day_idx
    ON public.daily_price_reference(symbol,period_day DESC,id);
