-- Dividend publication hardening (2026-11-17).
--
-- Two defects are fixed here, both reachable with real exchange data:
--   1. a payment or detachment date that does not parse aborted the whole
--      batch for every company and every year;
--   2. de-duplication deleted stored components the snapshot never mentioned
--      (a partial capture could erase a company's exceptional dividend).
--
-- Dates now go through a safe cast, unparseable components are dropped, rows
-- without a payment date are skipped, and a group whose stored types are not
-- fully covered by the snapshot is left untouched and counted.

CREATE SCHEMA IF NOT EXISTS market_maintenance;
REVOKE ALL ON SCHEMA market_maintenance FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION market_maintenance.try_timestamptz(p_value text)
RETURNS timestamptz LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
BEGIN
    RETURN p_value::timestamptz;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION market_maintenance.try_timestamptz(text) FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.apply_exchange_dividends(
    p_snapshot text, p_snapshot_sha256 text, p_years integer[] DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc jsonb; g record; existing record; v_id text; v_deleted integer;
    inserted integer := 0; updated integer := 0; unchanged integer := 0;
    duplicates integer := 0; missing integer := 0;
    skipped integer := 0; v_has_uncovered boolean;
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
                   market_maintenance.try_timestamptz(d->>'paiement')::date AS pay_date,
                   market_maintenance.try_timestamptz(d->>'detachement')::date AS ex_date,
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
             WHERE pay_date IS NOT NULL
               AND amount > 0 AND amount < 1e9
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
                                        AND extract(year FROM f.pay_date)::int = grp.year) s), '') AS type,
                   (SELECT array_agg(DISTINCT f.type)
                      FROM filtered f
                     WHERE f.c_name = grp.c_name
                       AND extract(year FROM f.pay_date)::int = grp.year) AS types
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
            -- Never remove a stored component the snapshot does not mention: a
            -- partial capture (ordinary only) would delete the exceptional row.
            SELECT EXISTS (
                SELECT 1 FROM public.dividends x
                 WHERE x.c_name = g.c_name AND x.year = g.year AND x.id <> v_id
                   AND x.type IS NOT NULL
                   AND NOT (x.type = ANY(coalesce(g.types, ARRAY[]::text[])))
            ) INTO v_has_uncovered;
            IF v_has_uncovered THEN
                skipped := skipped + 1;
                CONTINUE;
            END IF;
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
                              'missing', missing, 'skipped_partial', skipped);
END $$;
REVOKE ALL ON FUNCTION public.apply_exchange_dividends(text, text, integer[]) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.apply_exchange_dividends(text, text, integer[]) TO service_role;
COMMENT ON FUNCTION public.apply_exchange_dividends(text, text, integer[]) IS
    'Service-role publication of exchange dividends, one combined row per company and payment year';
