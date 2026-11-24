-- The app's Marché tab lost the MASI row when the feed moved to the public
-- tables: the stock branch joins public.format, which holds companies only.
-- Indices live in public.data (asset_key 'index:MASI', instrument_type INDEX)
-- and the app's parser already accepts that shape, including "points" rendering
-- and the rule that index rows carry no ratios or symbol in application_fields.

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
    ), index_latest AS (
        SELECT DISTINCT ON (d.c_name)
               d.c_name,
               d.pa,
               d.date,
               d.variation,
               d.date + interval '1 hour' AS expires_at,
               (d.date + interval '1 hour') > now() AS fresh
          FROM public.data d
         WHERE d.c_name IN ('MASI')
           AND d.pa IS NOT NULL AND d.pa > 0
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
                           -- price_decimal is two decimals; the parser requires
                           -- the two to agree exactly.
                           'pa', round(live.pa, 2),
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
        UNION ALL
        -- Index rows carry no ratio, no symbol in application_fields and no
        -- reference price; the parser rejects each of those for INDEX.
        SELECT i.c_name,
               jsonb_build_object(
                   'asset_key', 'index:' || i.c_name,
                   'c_name', i.c_name,
                   'symbol', i.c_name,
                   'instrument_type', 'INDEX',
                   'status', CASE WHEN i.fresh THEN 'REPORTED_DATE_ONLY' ELSE 'MISSING_QUOTE' END,
                   'price_decimal', CASE WHEN i.fresh
                       THEN to_char(i.pa, 'FM9999999999990.00') END,
                   'price_basis', 'REPORTED_QUOTE',
                   'captured_at', to_char(i.date AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
                   'expires_at', CASE WHEN i.fresh
                       THEN to_char(i.expires_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') END,
                   'source_event_at', NULL,
                   'reported_day', NULL,
                   'reported_time_timezone', 'UNKNOWN',
                   'prediction_eligible', false,
                   'portfolio_valuation_eligible', false,
                   'reference_price', NULL,
                   'reference_conflict', false,
                   'application_fields', CASE WHEN i.fresh THEN jsonb_strip_nulls(
                       jsonb_build_object(
                           'date', to_char(i.date AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
                           'c_name', i.c_name,
                           'pa', round(i.pa, 2),
                           'variation', i.variation
                       )) END,
                   'application_expires_at', CASE WHEN i.fresh
                       THEN to_char(i.expires_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') END
               ) AS row
          FROM index_latest i
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
