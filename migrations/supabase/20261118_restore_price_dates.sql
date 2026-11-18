-- Undo the price dates the 2026-11-18 holiday run stamped.
-- The prices themselves are the 17 November close; only the observation date
-- was moved forward. The matching history row carries that day's observation.
DO $$
DECLARE restored integer := 0;
BEGIN
    UPDATE public.latest_prices lp
       SET date = src.observed
      FROM (SELECT c_name, max(date) AS observed
              FROM public.data
             WHERE (date AT TIME ZONE 'Africa/Casablanca')::date = DATE '2026-11-17'
             GROUP BY c_name) src
     WHERE lp.c_name = src.c_name
       AND (lp.date AT TIME ZONE 'Africa/Casablanca')::date = DATE '2026-11-18';
    GET DIAGNOSTICS restored = ROW_COUNT;
    RAISE NOTICE 'restored observation dates for % price rows', restored;
END $$;
