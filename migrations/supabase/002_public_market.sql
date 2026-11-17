-- Generated from market_contract.json. Recovery pilot; clients remain on Appwrite.
-- Original payloads, upstream source metadata and ownership stay in private staging.
-- No uniqueness constraint on company/day: historical intraday rows are preserved.

CREATE TABLE IF NOT EXISTS public.company (
    id text PRIMARY KEY CHECK (length(id) > 0),
    name text NOT NULL,
    bpa numeric,
    tc5 numeric,
    roe numeric,
    na numeric,
    cp numeric,
    date timestamptz,
    dpa numeric,
    sector text,
    description text,
    shareholders text,
    beta_3y numeric,
    beta_5y numeric,
    revenue numeric,
    ebitda numeric,
    ebit numeric,
    net_profit numeric,
    fcf numeric,
    net_debt numeric,
    net_cash numeric,
    total_assets numeric,
    rev_growth_5y numeric,
    rnpg_growth_5y numeric,
    profit_margin numeric,
    ext_name text,
    fiscal_year integer,
    fy_est integer,
    rnpg_est numeric
);
COMMENT ON TABLE public.company IS 'myInterpreter public market pilot v1';
ALTER TABLE public.company ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.company FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.company TO authenticated, service_role;
DROP POLICY IF EXISTS market_public_read ON public.company;
CREATE POLICY market_public_read ON public.company FOR SELECT TO authenticated USING (true);

CREATE TABLE IF NOT EXISTS public.format (
    id text PRIMARY KEY CHECK (length(id) > 0),
    name text NOT NULL,
    symbol text NOT NULL
);
COMMENT ON TABLE public.format IS 'myInterpreter public market pilot v1';
ALTER TABLE public.format ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.format FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.format TO authenticated, service_role;
DROP POLICY IF EXISTS market_public_read ON public.format;
CREATE POLICY market_public_read ON public.format FOR SELECT TO authenticated USING (true);

CREATE TABLE IF NOT EXISTS public.data (
    id text PRIMARY KEY CHECK (length(id) > 0),
    c_name text NOT NULL,
    cb numeric,
    cours_ref numeric,
    data_chart text,
    date timestamptz NOT NULL,
    high numeric,
    low numeric,
    market_cap numeric,
    open_price numeric,
    pa numeric NOT NULL,
    pb numeric,
    pb_rating text,
    peg numeric,
    peg_rating text,
    per numeric,
    per_rating text,
    pr numeric,
    pr_rating text,
    qty_traded bigint,
    symbol text,
    variation numeric,
    variation_v numeric,
    volume numeric
);
COMMENT ON TABLE public.data IS 'myInterpreter public market pilot v1';
ALTER TABLE public.data ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.data FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.data TO authenticated, service_role;
DROP POLICY IF EXISTS market_public_read ON public.data;
CREATE POLICY market_public_read ON public.data FOR SELECT TO authenticated USING (true);

CREATE TABLE IF NOT EXISTS public.dividends (
    id text PRIMARY KEY CHECK (length(id) > 0),
    c_name text NOT NULL,
    issuer text,
    year integer NOT NULL,
    amount numeric,
    ex_date date,
    pay_date date,
    pay_date_end date,
    confirmed boolean NOT NULL,
    type text,
    frequency text,
    updated_at timestamptz
);
COMMENT ON TABLE public.dividends IS 'myInterpreter public market pilot v1';
ALTER TABLE public.dividends ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.dividends FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.dividends TO authenticated, service_role;
DROP POLICY IF EXISTS market_public_read ON public.dividends;
CREATE POLICY market_public_read ON public.dividends FOR SELECT TO authenticated USING (true);

CREATE TABLE IF NOT EXISTS public.latest_prices (
    id text PRIMARY KEY CHECK (length(id) > 0),
    c_name text NOT NULL,
    pa numeric NOT NULL,
    date timestamptz NOT NULL,
    origin_collection text NOT NULL,
    UNIQUE (c_name),
    CHECK (origin_collection IN ('data','latest_prices'))
);
COMMENT ON TABLE public.latest_prices IS 'myInterpreter public market pilot v1';
ALTER TABLE public.latest_prices ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.latest_prices FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.latest_prices TO authenticated, service_role;
DROP POLICY IF EXISTS market_public_read ON public.latest_prices;
CREATE POLICY market_public_read ON public.latest_prices FOR SELECT TO authenticated USING (true);

CREATE INDEX IF NOT EXISTS data_company_date_idx ON public.data (c_name, date DESC, id DESC);
CREATE INDEX IF NOT EXISTS data_date_idx ON public.data (date DESC, id DESC);
CREATE INDEX IF NOT EXISTS company_name_idx ON public.company (name);
CREATE INDEX IF NOT EXISTS format_symbol_idx ON public.format (symbol);
CREATE INDEX IF NOT EXISTS format_name_idx ON public.format (name);
CREATE INDEX IF NOT EXISTS dividends_company_year_idx ON public.dividends (c_name, year DESC, id);
CREATE INDEX IF NOT EXISTS dividends_year_idx ON public.dividends (year, id);
