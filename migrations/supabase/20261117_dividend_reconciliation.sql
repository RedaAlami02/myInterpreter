-- Repair the dividend table and add a service-role publication path.
--
-- Repairs, each copied to market_maintenance.dividend_repairs first:
--   * future-year rows (2027) that are either copies of 2025 or predictions
--   * the orphan TOTALENERGIES MAROC name
--   * two payment-year mislabels for IMMORENTE INVEST
CREATE SCHEMA IF NOT EXISTS market_maintenance;
REVOKE ALL ON SCHEMA market_maintenance FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS market_maintenance.dividend_repairs (
    reason text NOT NULL,
    dividend_id text NOT NULL,
    c_name text,
    year integer,
    amount numeric,
    ex_date date,
    pay_date date,
    confirmed boolean,
    type text,
    repaired_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (reason, dividend_id)
);
ALTER TABLE market_maintenance.dividend_repairs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE market_maintenance.dividend_repairs FROM PUBLIC, anon, authenticated, service_role;

INSERT INTO market_maintenance.dividend_repairs
    (reason, dividend_id, c_name, year, amount, ex_date, pay_date, confirmed, type)
SELECT 'FUTURE_YEAR', id, c_name, year, amount, ex_date, pay_date, confirmed, type
  FROM public.dividends
 WHERE year > extract(year FROM current_date)::int
ON CONFLICT DO NOTHING;

DELETE FROM public.dividends
 WHERE year > extract(year FROM current_date)::int;

INSERT INTO market_maintenance.dividend_repairs
    (reason, dividend_id, c_name, year, amount, ex_date, pay_date, confirmed, type)
SELECT 'RENAME_COMPANY', id, c_name, year, amount, ex_date, pay_date, confirmed, type
  FROM public.dividends
 WHERE c_name = 'TOTALENERGIES MAROC'
   AND EXISTS (SELECT 1 FROM public.company WHERE name = 'TOTALENERGIES MARKETING MAROC')
ON CONFLICT DO NOTHING;

UPDATE public.dividends
   SET c_name = 'TOTALENERGIES MARKETING MAROC', updated_at = clock_timestamp()
 WHERE c_name = 'TOTALENERGIES MAROC'
   AND EXISTS (SELECT 1 FROM public.company WHERE name = 'TOTALENERGIES MARKETING MAROC');

INSERT INTO market_maintenance.dividend_repairs
    (reason, dividend_id, c_name, year, amount, ex_date, pay_date, confirmed, type)
SELECT 'RELABEL_PAYMENT_YEAR', id, c_name, year, amount, ex_date, pay_date, confirmed, type
  FROM public.dividends
 WHERE c_name = 'IMMORENTE INVEST'
   AND year IN (2022, 2023)
   AND pay_date IS NOT NULL
   AND extract(year FROM pay_date)::int <> year
ON CONFLICT DO NOTHING;

UPDATE public.dividends
   SET year = extract(year FROM pay_date)::int, updated_at = clock_timestamp()
 WHERE c_name = 'IMMORENTE INVEST'
   AND year IN (2022, 2023)
   AND pay_date IS NOT NULL
   AND extract(year FROM pay_date)::int <> year;

CREATE TABLE IF NOT EXISTS market_maintenance.dividend_publications (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_sha256 text NOT NULL CHECK (snapshot_sha256 ~ '^[a-f0-9]{64}$'),
    c_name text NOT NULL,
    year integer NOT NULL,
    old_amount numeric,
    new_amount numeric,
    old_ex_date date,
    new_ex_date date,
    old_pay_date date,
    new_pay_date date,
    action text NOT NULL CHECK (action IN ('INSERTED', 'UPDATED', 'DUPLICATE_REMOVED')),
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE market_maintenance.dividend_publications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE market_maintenance.dividend_publications FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.apply_exchange_dividends(
    p_snapshot text, p_snapshot_sha256 text, p_years integer[] DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc jsonb; g record; existing record; v_id text; v_deleted integer;
    inserted integer := 0; updated integer := 0; unchanged integer := 0;
    duplicates integer := 0; missing integer := 0;
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN
        RAISE EXCEPTION 'Service role required' USING ERRCODE = '42501';
    END IF;
    IF p_snapshot IS NULL OR octet_length(p_snapshot) > 4194304
       OR p_snapshot_sha256 IS NULL OR p_snapshot_sha256 !~ '^[a-f0-9]{64}$'
       OR encode(sha256(convert_to(p_snapshot, 'UTF8')), 'hex') <> p_snapshot_sha256 THEN
        RAISE EXCEPTION 'Invalid dividend snapshot digest' USING ERRCODE = '22023';
    END IF;
    doc := p_snapshot::jsonb;
    IF jsonb_typeof(doc) IS DISTINCT FROM 'array'
       OR jsonb_array_length(doc) NOT BETWEEN 1 AND 200 THEN
        RAISE EXCEPTION 'Invalid dividend snapshot' USING ERRCODE = '22023';
    END IF;
    IF p_years IS NOT NULL AND (array_length(p_years, 1) IS NULL
                                OR array_length(p_years, 1) > 5) THEN
        RAISE EXCEPTION 'Invalid publication years' USING ERRCODE = '22023';
    END IF;
    FOR g IN
        WITH components AS (
            SELECT f.name AS c_name,
                   (d->>'paiement')::timestamptz::date AS pay_date,
                   (d->>'detachement')::timestamptz::date AS ex_date,
                   coalesce(d#>>'{type,fr}', '') AS type,
                   (d->>'montant')::numeric AS amount
              FROM jsonb_array_elements(doc) AS item
              JOIN public.format f ON f.symbol = item->>'symbol'
              CROSS JOIN LATERAL jsonb_array_elements(item->'dividends') AS d
             WHERE jsonb_typeof(item->'dividends') = 'array'
               AND jsonb_typeof(d->'montant') = 'number'
               AND jsonb_typeof(d->'paiement') = 'string'
        ), filtered AS (
            SELECT * FROM components
             WHERE amount > 0 AND amount < 1e9
               AND (p_years IS NULL OR extract(year FROM pay_date)::int = ANY(p_years))
        ), grouped AS (
            SELECT c_name, extract(year FROM pay_date)::int AS year,
                   sum(amount) AS amount, min(ex_date) AS ex_date,
                   min(pay_date) AS pay_date,
                   bool_and(ex_date IS NOT NULL) AS confirmed
              FROM filtered
             GROUP BY c_name, extract(year FROM pay_date)::int
        ), typed AS (
            SELECT grp.*,
                   coalesce((SELECT string_agg(t, ' + ' ORDER BY ord, t)
                               FROM (SELECT DISTINCT type AS t,
                                            CASE WHEN type = 'Ordinaire' THEN 0 ELSE 1 END AS ord
                                       FROM filtered f
                                      WHERE f.c_name = grp.c_name
                                        AND extract(year FROM f.pay_date)::int = grp.year) s), '') AS type
              FROM grouped grp
        )
        SELECT * FROM typed ORDER BY c_name, year
    LOOP
        SELECT id, amount, ex_date, pay_date, confirmed, type INTO existing
          FROM public.dividends
         WHERE c_name = g.c_name AND year = g.year
         ORDER BY id LIMIT 1 FOR UPDATE;
        IF FOUND THEN
            v_id := existing.id;
            INSERT INTO market_maintenance.dividend_publications
                (snapshot_sha256, c_name, year, old_amount, old_ex_date, old_pay_date,
                 action)
            SELECT p_snapshot_sha256, c_name, year, amount, ex_date, pay_date,
                   'DUPLICATE_REMOVED'
              FROM public.dividends
             WHERE c_name = g.c_name AND year = g.year AND id <> v_id;
            DELETE FROM public.dividends
             WHERE c_name = g.c_name AND year = g.year AND id <> v_id;
            GET DIAGNOSTICS v_deleted = ROW_COUNT;
            duplicates := duplicates + v_deleted;
            IF existing.amount IS NOT DISTINCT FROM g.amount
               AND existing.ex_date IS NOT DISTINCT FROM g.ex_date
               AND existing.pay_date IS NOT DISTINCT FROM g.pay_date
               AND existing.confirmed IS NOT DISTINCT FROM g.confirmed
               AND existing.type IS NOT DISTINCT FROM g.type THEN
                unchanged := unchanged + 1;
            ELSE
                UPDATE public.dividends
                   SET amount = g.amount, ex_date = g.ex_date, pay_date = g.pay_date,
                       confirmed = g.confirmed, type = g.type,
                       updated_at = clock_timestamp()
                 WHERE id = v_id;
                INSERT INTO market_maintenance.dividend_publications
                    (snapshot_sha256, c_name, year, old_amount, new_amount,
                     old_ex_date, new_ex_date, old_pay_date, new_pay_date, action)
                VALUES (p_snapshot_sha256, g.c_name, g.year, existing.amount, g.amount,
                        existing.ex_date, g.ex_date, existing.pay_date, g.pay_date,
                        'UPDATED');
                updated := updated + 1;
            END IF;
        ELSE
            IF NOT EXISTS (SELECT 1 FROM public.company WHERE name = g.c_name) THEN
                missing := missing + 1;
                CONTINUE;
            END IF;
            v_id := 'div-' || substr(encode(sha256(convert_to(g.c_name || ':' || g.year,
                                                              'UTF8')), 'hex'), 1, 32);
            INSERT INTO public.dividends
                (id, c_name, issuer, year, amount, ex_date, pay_date, pay_date_end,
                 confirmed, type, frequency, updated_at)
            VALUES (v_id, g.c_name, g.c_name, g.year, g.amount, g.ex_date, g.pay_date,
                    NULL, g.confirmed, g.type, NULL, clock_timestamp());
            INSERT INTO market_maintenance.dividend_publications
                (snapshot_sha256, c_name, year, new_amount, new_ex_date, new_pay_date,
                 action)
            VALUES (p_snapshot_sha256, g.c_name, g.year, g.amount, g.ex_date, g.pay_date,
                    'INSERTED');
            inserted := inserted + 1;
        END IF;
    END LOOP;
    RETURN jsonb_build_object('status', 'COMPLETE', 'snapshot_sha256', p_snapshot_sha256,
                              'inserted', inserted, 'updated', updated,
                              'unchanged', unchanged, 'duplicates_removed', duplicates,
                              'missing', missing);
END $$;
REVOKE ALL ON FUNCTION public.apply_exchange_dividends(text, text, integer[]) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.apply_exchange_dividends(text, text, integer[]) TO service_role;
COMMENT ON FUNCTION public.apply_exchange_dividends(text, text, integer[]) IS
    'Service-role publication of exchange dividends, one combined row per company and payment year';
