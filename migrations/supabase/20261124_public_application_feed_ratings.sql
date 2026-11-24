-- The Marché tab renders a PER/PEG/PR/PB chip row from the application feed.
-- 20261121_public_application_feed.sql published the ratio values but not their
-- ratings, so every chip arrived colourless and carried no information. The
-- ratings already exist in public.data and the app's parser whitelists them
-- ('green' | 'orange' | 'red'); nulls are dropped by jsonb_strip_nulls.

CREATE OR REPLACE FUNCTION public.read_public_application_feed()
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
STABLE
AS $$
    WITH live AS (
        SELECT p.c_name,
               f.symbol,
               p.pa,
               p.date,
               p.date + interval '1 hour' AS expires_at,
               (p.date + interval '1 hour') > now() AS fresh
          FROM public.latest_prices p
          JOIN public.format f ON f.name = p.c_name
         WHERE p.pa IS NOT NULL AND p.pa > 0
    ), newest_data AS (
        SELECT DISTINCT ON (d.c_name) d.*
          FROM public.data d
         ORDER BY d.c_name, d.date DESC
    ), built AS (
        SELECT live.symbol,
               jsonb_build_object(
                   'asset_key', live.symbol,
                   'c_name', live.c_name,
                   'symbol', live.symbol,
                   'instrument_type', 'STOCK',
                   'status', CASE WHEN live.fresh THEN 'REPORTED_DATE_ONLY' ELSE 'MISSING_QUOTE' END,
                   'price_decimal', CASE WHEN live.fresh
                       THEN to_char(live.pa, 'FM9999999999990.00') END,
                   'price_basis', 'REPORTED_QUOTE',
                   'captured_at', to_char(live.date AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
                   'expires_at', CASE WHEN live.fresh
                       THEN to_char(live.expires_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') END,
                   'source_event_at', NULL,
                   'reported_day', NULL,
                   'reported_time_timezone', 'UNKNOWN',
                   'prediction_eligible', false,
                   'portfolio_valuation_eligible', false,
                   'reference_price', NULL,
                   'reference_conflict', false,
                   -- The app rejects a null number, so absent keys are the only
                   -- way to say "not published"; strip_nulls does exactly that.
                   'application_fields', CASE WHEN live.fresh THEN jsonb_strip_nulls(
                       jsonb_build_object(
                           'date', to_char(live.date AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
                           'c_name', live.c_name,
                           'symbol', live.symbol,
                           'pa', live.pa,
                           'cb', nd.cb,
                           'per', nd.per,
                           'peg', nd.peg,
                           'pr', nd.pr,
                           'pb', nd.pb,
                           'per_rating', nd.per_rating,
                           'peg_rating', nd.peg_rating,
                           'pr_rating', nd.pr_rating,
                           'pb_rating', nd.pb_rating,
                           'variation', nd.variation,
                           'variation_v', nd.variation_v,
                           'cours_ref', nd.cours_ref,
                           'open_price', nd.open_price,
                           'high', nd.high,
                           'low', nd.low,
                           'volume', nd.volume,
                           'market_cap', nd.market_cap
                       )) END,
                   'application_expires_at', CASE WHEN live.fresh
                       THEN to_char(live.expires_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') END
               ) AS row
          FROM live
          LEFT JOIN newest_data nd ON nd.c_name = live.c_name
    )
    SELECT jsonb_build_object(
        'contract', 'app-market-preview/v3',
        'mode', 'SHADOW_ONLY',
        'as_of', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
        'status', 'AVAILABLE',
        'captured_at', (SELECT to_char(max(date) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') FROM live),
        'acquisition_completeness', NULL,
        'market_session_state', 'UNKNOWN',
        'rows', coalesce(jsonb_agg(row ORDER BY symbol), '[]'::jsonb)
    )
      FROM built;
$$;

REVOKE ALL ON FUNCTION public.read_public_application_feed() FROM PUBLIC, anon, service_role;
GRANT EXECUTE ON FUNCTION public.read_public_application_feed() TO authenticated;
