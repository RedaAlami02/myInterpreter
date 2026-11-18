-- Remove the rows a non-trading day produced before the session gate existed.
-- 2026-11-18 was a Casablanca market holiday: the public pages still showed the
-- 17 November aggregates, so the early-morning publication wrote a fake daily
-- session and a valuation for that day.
CREATE SCHEMA IF NOT EXISTS market_maintenance;
REVOKE ALL ON SCHEMA market_maintenance FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS market_maintenance.non_session_purges (
    day date PRIMARY KEY,
    data_rows integer NOT NULL,
    valuation_rows integer NOT NULL,
    purged_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE market_maintenance.non_session_purges ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE market_maintenance.non_session_purges FROM PUBLIC, anon, authenticated, service_role;

DO $$
DECLARE deleted_data integer := 0; deleted_values integer := 0;
BEGIN
    DELETE FROM public.data
     WHERE (date AT TIME ZONE 'Africa/Casablanca')::date = DATE '2026-11-18';
    GET DIAGNOSTICS deleted_data = ROW_COUNT;
    DELETE FROM public.benefits WHERE date = DATE '2026-11-18';
    GET DIAGNOSTICS deleted_values = ROW_COUNT;
    RAISE NOTICE 'purged % data rows and % valuation rows for 2026-11-18', deleted_data, deleted_values;
    INSERT INTO market_maintenance.non_session_purges(day, data_rows, valuation_rows)
    VALUES (DATE '2026-11-18', deleted_data, deleted_values)
    ON CONFLICT (day) DO UPDATE
      SET data_rows = excluded.data_rows,
          valuation_rows = excluded.valuation_rows,
          purged_at = clock_timestamp();
END $$;
