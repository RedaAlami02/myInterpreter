-- STAGED ONLY. Explicit owner maintenance writes; no restored row is rewritten.
-- Seed market_admin.admins privately with the administrator's Auth user id.
-- Every function rechecks auth.uid()/auth.role() and fails closed without a row.
CREATE SCHEMA market_admin;
REVOKE ALL ON SCHEMA market_admin FROM PUBLIC, anon, authenticated, service_role;
CREATE TABLE market_admin.admins (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    added_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
COMMENT ON TABLE market_admin.admins IS 'myInterpreter admin maintenance v1';
ALTER TABLE market_admin.admins ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE market_admin.admins FROM PUBLIC, anon, authenticated, service_role;

-- Operator-entered analysis snapshots are marked; recovered and market rows stay NULL.
ALTER TABLE public.data ADD COLUMN IF NOT EXISTS source text;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = 'data_source_check' AND conrelid = 'public.data'::regclass
    ) THEN
        ALTER TABLE public.data ADD CONSTRAINT data_source_check
            CHECK (source IS NULL OR source IN ('MARKET_CAPTURE', 'OPERATOR_ENTRY'));
    END IF;
END $$;
COMMENT ON COLUMN public.data.source IS
    'NULL: recovered or unclassified; OPERATOR_ENTRY: administrator analysis snapshot';

CREATE FUNCTION public.admin_update_company(p_name text, p_fields jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    caller uuid := auth.uid();
    numeric_fields constant text[] := ARRAY[
        'bpa','dpa','tc5','roe','na','cp','beta_3y','beta_5y','revenue','ebitda',
        'ebit','net_profit','fcf','net_debt','net_cash','total_assets',
        'rev_growth_5y','rnpg_growth_5y','profit_margin','rnpg_est'];
    integer_fields constant text[] := ARRAY['fiscal_year','fy_est'];
    text_fields constant text[] := ARRAY['ext_name','sector','description','shareholders'];
    item record;
    amount numeric;
    changed integer := 0;
BEGIN
    IF caller IS NULL OR auth.role() IS DISTINCT FROM 'authenticated'
       OR NOT EXISTS (SELECT 1 FROM market_admin.admins a WHERE a.user_id = caller) THEN
        RAISE EXCEPTION 'Administrator access required' USING ERRCODE = '42501';
    END IF;
    IF p_name IS NULL OR p_name IS DISTINCT FROM btrim(p_name)
       OR length(p_name) NOT BETWEEN 1 AND 200
       OR p_fields IS NULL OR jsonb_typeof(p_fields) IS DISTINCT FROM 'object'
       OR p_fields = '{}'::jsonb OR octet_length(p_fields::text) > 16384 THEN
        RAISE EXCEPTION 'Invalid company update' USING ERRCODE = '22023';
    END IF;
    FOR item IN SELECT * FROM jsonb_each(p_fields) LOOP
        IF item.key = ANY(numeric_fields) THEN
            CONTINUE WHEN jsonb_typeof(item.value) = 'null';
            IF jsonb_typeof(item.value) IS DISTINCT FROM 'number' THEN
                RAISE EXCEPTION 'Invalid numeric field' USING ERRCODE = '22023';
            END IF;
            amount := (item.value #>> '{}')::numeric;
            IF abs(amount) > 1000000000000000 OR scale(amount) > 6 THEN
                RAISE EXCEPTION 'Numeric field out of range' USING ERRCODE = '22023';
            END IF;
            -- Fractions here produced nonsense ratios in the old backend.
            IF item.key IN ('tc5','roe') AND amount <> 0 AND abs(amount) < 1 THEN
                RAISE EXCEPTION 'Percentage fields must be percentages' USING ERRCODE = '22023';
            END IF;
        ELSIF item.key = ANY(integer_fields) THEN
            CONTINUE WHEN jsonb_typeof(item.value) = 'null';
            IF jsonb_typeof(item.value) IS DISTINCT FROM 'number'
               OR (item.value #>> '{}') !~ '^[0-9]{4}$'
               OR (item.value #>> '{}')::integer NOT BETWEEN 1900 AND 2200 THEN
                RAISE EXCEPTION 'Invalid year field' USING ERRCODE = '22023';
            END IF;
        ELSIF item.key = ANY(text_fields) THEN
            CONTINUE WHEN jsonb_typeof(item.value) = 'null';
            IF jsonb_typeof(item.value) IS DISTINCT FROM 'string'
               OR length(item.value #>> '{}') NOT BETWEEN 1 AND 4000 THEN
                RAISE EXCEPTION 'Invalid text field' USING ERRCODE = '22023';
            END IF;
        ELSE
            RAISE EXCEPTION 'Unsupported company field' USING ERRCODE = '22023';
        END IF;
        changed := changed + 1;
    END LOOP;
    IF NOT EXISTS (SELECT 1 FROM public.company WHERE name = p_name) THEN
        RETURN jsonb_build_object('status', 'MISSING', 'name', p_name);
    END IF;
    PERFORM 1 FROM public.company WHERE name = p_name FOR UPDATE;
    FOR item IN SELECT * FROM jsonb_each(p_fields) LOOP
        EXECUTE pg_catalog.format(
            'UPDATE public.company SET %I = $1::%s WHERE name = $2',
            item.key,
            CASE WHEN item.key = ANY(integer_fields) THEN 'integer'
                 WHEN item.key = ANY(text_fields) THEN 'text'
                 ELSE 'numeric' END)
            USING (p_fields ->> item.key), p_name;
    END LOOP;
    RETURN jsonb_build_object('status', 'UPDATED', 'name', p_name, 'fields', changed);
END $$;

CREATE FUNCTION public.admin_record_operator_snapshot(p_fields jsonb)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    caller uuid := auth.uid();
    c_name text;
    price numeric;
    item record;
    amount numeric;
    snapshot_id text := replace(gen_random_uuid()::text, '-', '');
BEGIN
    IF caller IS NULL OR auth.role() IS DISTINCT FROM 'authenticated'
       OR NOT EXISTS (SELECT 1 FROM market_admin.admins a WHERE a.user_id = caller) THEN
        RAISE EXCEPTION 'Administrator access required' USING ERRCODE = '42501';
    END IF;
    IF p_fields IS NULL OR jsonb_typeof(p_fields) IS DISTINCT FROM 'object'
       OR octet_length(p_fields::text) > 4096
       OR NOT (p_fields ? 'c_name') OR NOT (p_fields ? 'pa') THEN
        RAISE EXCEPTION 'Invalid snapshot input' USING ERRCODE = '22023';
    END IF;
    c_name := p_fields ->> 'c_name';
    IF c_name IS NULL OR c_name IS DISTINCT FROM btrim(c_name)
       OR length(c_name) NOT BETWEEN 1 AND 200
       OR NOT EXISTS (SELECT 1 FROM public.company WHERE name = c_name) THEN
        RAISE EXCEPTION 'Unknown company' USING ERRCODE = '22023';
    END IF;
    IF jsonb_typeof(p_fields -> 'pa') IS DISTINCT FROM 'number' THEN
        RAISE EXCEPTION 'Invalid snapshot price' USING ERRCODE = '22023';
    END IF;
    price := (p_fields ->> 'pa')::numeric;
    IF NOT (price > 0 AND price <= 1000000000000) OR scale(price) > 6 THEN
        RAISE EXCEPTION 'Invalid snapshot price' USING ERRCODE = '22023';
    END IF;
    FOR item IN SELECT * FROM jsonb_each(p_fields) LOOP
        IF item.key IN ('c_name', 'pa') THEN CONTINUE; END IF;
        IF item.key NOT IN ('cb', 'per', 'peg', 'pr', 'pb') THEN
            RAISE EXCEPTION 'Unsupported snapshot field' USING ERRCODE = '22023';
        END IF;
        CONTINUE WHEN jsonb_typeof(item.value) = 'null';
        IF jsonb_typeof(item.value) IS DISTINCT FROM 'number' THEN
            RAISE EXCEPTION 'Invalid snapshot ratio' USING ERRCODE = '22023';
        END IF;
        amount := (item.value #>> '{}')::numeric;
        IF abs(amount) > 1000000000000000 OR scale(amount) > 6 THEN
            RAISE EXCEPTION 'Invalid snapshot ratio' USING ERRCODE = '22023';
        END IF;
    END LOOP;
    INSERT INTO public.data(id, c_name, date, pa, cb, per, peg, pr, pb, source)
        VALUES (snapshot_id, c_name, clock_timestamp(), price,
            CASE WHEN jsonb_typeof(p_fields -> 'cb') = 'number' THEN (p_fields ->> 'cb')::numeric END,
            CASE WHEN jsonb_typeof(p_fields -> 'per') = 'number' THEN (p_fields ->> 'per')::numeric END,
            CASE WHEN jsonb_typeof(p_fields -> 'peg') = 'number' THEN (p_fields ->> 'peg')::numeric END,
            CASE WHEN jsonb_typeof(p_fields -> 'pr') = 'number' THEN (p_fields ->> 'pr')::numeric END,
            CASE WHEN jsonb_typeof(p_fields -> 'pb') = 'number' THEN (p_fields ->> 'pb')::numeric END,
            'OPERATOR_ENTRY');
    RETURN snapshot_id;
END $$;

REVOKE ALL ON FUNCTION public.admin_update_company(text,jsonb) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.admin_update_company(text,jsonb) TO authenticated;
REVOKE ALL ON FUNCTION public.admin_record_operator_snapshot(jsonb) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.admin_record_operator_snapshot(jsonb) TO authenticated;
COMMENT ON FUNCTION public.admin_update_company(text,jsonb) IS 'myInterpreter admin maintenance v1';
COMMENT ON FUNCTION public.admin_record_operator_snapshot(jsonb) IS 'myInterpreter admin maintenance v1';
