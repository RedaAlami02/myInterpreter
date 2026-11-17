-- Fresh accounts only. No legacy private records or password hashes are imported.
-- Apply through tools/migrate_supabase_portfolio.py (ownership guards + transaction).
CREATE SCHEMA IF NOT EXISTS portfolio_private;
REVOKE ALL ON SCHEMA portfolio_private FROM PUBLIC, anon, authenticated, service_role;
GRANT USAGE ON SCHEMA portfolio_private TO authenticated;

CREATE TABLE IF NOT EXISTS public.achats (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    c_name text NOT NULL CHECK (length(btrim(c_name)) BETWEEN 1 AND 200),
    number numeric NOT NULL CHECK (number > 0 AND number <= 1000000000000),
    prix_achat numeric NOT NULL CHECK (prix_achat > 0 AND prix_achat <= 1000000000000),
    date timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.ventes (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    c_name text NOT NULL CHECK (length(btrim(c_name)) BETWEEN 1 AND 200),
    number numeric NOT NULL CHECK (number > 0 AND number <= 1000000000000),
    prix_vente numeric NOT NULL CHECK (prix_vente > 0 AND prix_vente <= 1000000000000),
    date timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.portefeuille (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    c_name text NOT NULL CHECK (length(btrim(c_name)) BETWEEN 1 AND 200),
    quantity numeric NOT NULL CHECK (quantity > 0 AND quantity <= 1000000000000),
    total_cost numeric NOT NULL CHECK (total_cost > 0 AND total_cost <= 1e24),
    UNIQUE(user_id, c_name)
);
CREATE TABLE IF NOT EXISTS public.benefits (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    date date NOT NULL,
    value numeric NOT NULL CHECK (value > '-Infinity'::numeric AND value < 'Infinity'::numeric),
    UNIQUE(user_id, date)
);
CREATE TABLE IF NOT EXISTS portfolio_private.trade_requests (
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    request_id uuid NOT NULL,
    side text NOT NULL,
    c_name text NOT NULL,
    quantity numeric NOT NULL,
    price numeric NOT NULL,
    PRIMARY KEY(user_id, request_id)
);

-- SELECT only. Even the owner cannot tamper with derived holdings or trade
-- history by direct REST writes. The atomic RPC is the only client write path.
DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['achats','ventes','portefeuille','benefits'] LOOP
        EXECUTE format('COMMENT ON TABLE public.%I IS %L', tab, 'myInterpreter private portfolio v1');
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', tab);
        EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated, service_role', tab);
        EXECUTE format('GRANT SELECT ON public.%I TO authenticated', tab);
        EXECUTE format('DROP POLICY IF EXISTS portfolio_owner_read ON public.%I', tab);
        EXECUTE format('CREATE POLICY portfolio_owner_read ON public.%I FOR SELECT TO authenticated USING ((select auth.uid()) = user_id)', tab);
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON public.%I (user_id)', tab || '_owner_idx', tab);
    END LOOP;
END $$;
COMMENT ON TABLE portfolio_private.trade_requests IS 'myInterpreter private portfolio v1';
ALTER TABLE portfolio_private.trade_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON portfolio_private.trade_requests FROM PUBLIC, anon, authenticated, service_role;
CREATE INDEX IF NOT EXISTS achats_owner_date_idx ON public.achats(user_id,date,id);
CREATE INDEX IF NOT EXISTS ventes_owner_date_idx ON public.ventes(user_id,date,id);

-- Privileged implementation stays outside the exposed API schema. No dynamic
-- SQL, caller-supplied owner, or caller-controlled search path is used here.
CREATE OR REPLACE FUNCTION portfolio_private.record_trade(
    p_request_id uuid, p_side text, p_c_name text, p_quantity numeric, p_price numeric
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    owner_id uuid := auth.uid();
    old_request portfolio_private.trade_requests%ROWTYPE;
    holding public.portefeuille%ROWTYPE;
BEGIN
    IF owner_id IS NULL OR auth.role() IS DISTINCT FROM 'authenticated' THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE = '42501';
    END IF;
    IF p_request_id IS NULL OR p_side IS NULL OR p_side NOT IN ('buy','sell')
       OR p_c_name IS NULL OR p_c_name <> btrim(p_c_name)
       OR length(p_c_name) NOT BETWEEN 1 AND 200
       OR p_quantity IS NULL OR NOT (p_quantity > 0 AND p_quantity <= 1000000000000)
       OR p_price IS NULL OR NOT (p_price > 0 AND p_price <= 1000000000000)
       OR scale(p_quantity) > 8 OR scale(p_price) > 8 THEN
        RAISE EXCEPTION 'Invalid trade input' USING ERRCODE = '22023';
    END IF;
    -- Serialize trades for one owner, including empty-position first buys and
    -- concurrent retries. Other owners remain independent.
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(owner_id::text, 73));
    SELECT * INTO old_request FROM portfolio_private.trade_requests
        WHERE user_id = owner_id AND request_id = p_request_id;
    IF FOUND THEN
        IF (old_request.side,old_request.c_name,old_request.quantity,old_request.price)
           IS DISTINCT FROM (p_side,p_c_name,p_quantity,p_price) THEN
            RAISE EXCEPTION 'Request identifier reused with different trade' USING ERRCODE = '22023';
        END IF;
        RETURN p_request_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.company WHERE name = p_c_name) THEN
        RAISE EXCEPTION 'Unknown company' USING ERRCODE = '22023';
    END IF;
    SELECT * INTO holding FROM public.portefeuille
        WHERE user_id = owner_id AND c_name = p_c_name FOR UPDATE;
    IF p_side = 'buy' THEN
        INSERT INTO public.achats(id,user_id,c_name,number,prix_achat)
            VALUES(p_request_id,owner_id,p_c_name,p_quantity,p_price);
        INSERT INTO public.portefeuille(user_id,c_name,quantity,total_cost)
            VALUES(owner_id,p_c_name,p_quantity,p_quantity*p_price)
            ON CONFLICT(user_id,c_name) DO UPDATE SET
                quantity = public.portefeuille.quantity + EXCLUDED.quantity,
                total_cost = public.portefeuille.total_cost + EXCLUDED.total_cost;
    ELSE
        IF holding.id IS NULL OR p_quantity > holding.quantity THEN
            RAISE EXCEPTION 'Insufficient holding quantity' USING ERRCODE = '22023';
        END IF;
        INSERT INTO public.ventes(id,user_id,c_name,number,prix_vente)
            VALUES(p_request_id,owner_id,p_c_name,p_quantity,p_price);
        IF p_quantity = holding.quantity THEN
            DELETE FROM public.portefeuille WHERE id = holding.id;
        ELSE
            -- Preserve the apps' existing weighted-average remaining cost.
            -- No FIFO, commission or tax calculation is changed by this RPC.
            UPDATE public.portefeuille SET quantity = holding.quantity - p_quantity,
                total_cost = holding.total_cost * ((holding.quantity - p_quantity) / holding.quantity)
                WHERE id = holding.id;
        END IF;
    END IF;
    INSERT INTO portfolio_private.trade_requests VALUES
        (owner_id,p_request_id,p_side,p_c_name,p_quantity,p_price);
    RETURN p_request_id;
END $$;
REVOKE ALL ON FUNCTION portfolio_private.record_trade(uuid,text,text,numeric,numeric) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION portfolio_private.record_trade(uuid,text,text,numeric,numeric) TO authenticated;
COMMENT ON FUNCTION portfolio_private.record_trade(uuid,text,text,numeric,numeric) IS 'myInterpreter private portfolio v1';

CREATE OR REPLACE FUNCTION public.record_trade(
    p_request_id uuid, p_side text, p_c_name text, p_quantity numeric, p_price numeric
) RETURNS uuid LANGUAGE sql SECURITY INVOKER SET search_path = '' AS $$
    SELECT portfolio_private.record_trade(p_request_id,p_side,p_c_name,p_quantity,p_price);
$$;
REVOKE ALL ON FUNCTION public.record_trade(uuid,text,text,numeric,numeric) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.record_trade(uuid,text,text,numeric,numeric) TO authenticated;
COMMENT ON FUNCTION public.record_trade(uuid,text,text,numeric,numeric) IS 'myInterpreter private portfolio v1';
