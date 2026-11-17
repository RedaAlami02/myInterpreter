-- Sanitized authenticated read only. Native field names, raw bodies and providers stay private.
CREATE FUNCTION market_history_v1.session_number(p_value jsonb)
RETURNS numeric LANGUAGE plpgsql IMMUTABLE SET search_path='' AS $$
DECLARE value text; result numeric;
BEGIN
    IF p_value IS NULL OR jsonb_typeof(p_value) NOT IN ('number','string') THEN RETURN NULL; END IF;
    value:=p_value#>>'{}';
    IF length(value)>96 OR value !~ '^-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]{1,3})?$' THEN RETURN NULL; END IF;
    result:=value::numeric;
    IF abs(result)>1000000000000000 THEN RETURN NULL; END IF;
    RETURN result;
EXCEPTION WHEN numeric_value_out_of_range OR invalid_text_representation THEN RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION market_history_v1.session_number(jsonb) FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION market_history_v1.recent_market_sessions(p_symbol text,p_limit integer DEFAULT 5)
RETURNS jsonb LANGUAGE plpgsql SET search_path='' SET statement_timeout='8s' AS $$
DECLARE result jsonb; today date:=(clock_timestamp() AT TIME ZONE 'Africa/Casablanca')::date;
BEGIN
    IF p_symbol IS NULL OR p_symbol !~ '^[A-Z0-9][A-Z0-9._-]{0,31}$'
       OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 20 THEN
        RAISE EXCEPTION 'Invalid session query' USING ERRCODE='22023';
    END IF;
    IF (SELECT count(DISTINCT name) FROM public.format WHERE symbol=p_symbol)<>1 THEN
        RETURN jsonb_build_object('contract','recent-market-sessions/v1','symbol',p_symbol,'candidates','[]'::jsonb);
    END IF;
    WITH candidates AS (
        SELECT o.period_day,0 tier,o.observation_id identity,
            market_history_v1.session_number(to_jsonb(o.close_text)) price,
            market_history_v1.session_number(o.bar->(context.bindings->>'open_field')) opening,
            market_history_v1.session_number(o.bar->(context.bindings->>'high_field')) high,
            market_history_v1.session_number(o.bar->(context.bindings->>'low_field')) low,
            NULL::numeric quantity,o.quality_warnings issues
        FROM market_history_v1.observations o JOIN market_history_v1.batches b USING(batch_id)
        JOIN market_history_v1.captures c USING(batch_id,symbol)
        CROSS JOIN LATERAL (SELECT CASE
            WHEN b.manifest->>'contract'='private-source-history-v1' THEN b.manifest->'bindings'
            WHEN b.manifest->>'contract'='private-source-history-delta-v2'
                AND b.manifest->'full_source_manifest'->>'contract'='private-source-history-v1'
                THEN b.manifest->'full_source_manifest'->'bindings'
            ELSE NULL END bindings) context
        WHERE o.symbol=p_symbol AND o.period_day<=today AND jsonb_typeof(context.bindings)='object'
            AND c.completed_at<=clock_timestamp()
        UNION ALL
        SELECT d.period_day,1,d.id,d.close,
            market_history_v1.session_number(d.bar->'open'),market_history_v1.session_number(d.bar->'high'),
            market_history_v1.session_number(d.bar->'low'),market_history_v1.session_number(d.bar->'quantity_traded'),
            ARRAY(SELECT jsonb_array_elements_text(coalesce(d.quality->'issues','[]'::jsonb)))
        FROM public.daily_price_reference d WHERE d.symbol=p_symbol AND d.period_day<=today
            AND d.c_name=(SELECT min(name) FROM public.format WHERE symbol=p_symbol)
    ), days AS (
        SELECT DISTINCT period_day FROM candidates WHERE price>0 ORDER BY period_day DESC LIMIT p_limit
    ) SELECT coalesce(jsonb_agg(jsonb_build_object('day',period_day,'tier',tier,'identity',identity,
        'price',price::text,'open',opening::text,'high',high::text,'low',low::text,'quantity',quantity::text,
        'issues',ARRAY(SELECT DISTINCT CASE WHEN issue=ANY(ARRAY['SOURCE_OHLC_INCONSISTENT','SOURCE_OHLC_UNAVAILABLE',
            'incomplete_ohlc','inconsistent_ohlc_range','negative_activity','fractional_activity']) THEN issue
            ELSE 'SOURCE_QUALITY_UNCLASSIFIED' END FROM unnest(issues) issue))
        ORDER BY period_day DESC,tier,identity),'[]'::jsonb) INTO result
      FROM (SELECT * FROM candidates WHERE period_day IN (SELECT period_day FROM days) AND price>0
            ORDER BY period_day DESC,tier,identity LIMIT 251) bounded;
    IF jsonb_array_length(result)>250 THEN RAISE EXCEPTION 'Session evidence exceeds display bound'; END IF;
    RETURN jsonb_build_object('contract','recent-market-sessions/v1','symbol',p_symbol,'candidates',result);
END $$;
REVOKE ALL ON FUNCTION market_history_v1.recent_market_sessions(text,integer) FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION public.read_recent_market_sessions(p_symbol text,p_limit integer DEFAULT 5)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET statement_timeout='8s' AS $$
BEGIN
    IF auth.uid() IS NULL OR auth.role() IS DISTINCT FROM 'authenticated' THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE='42501';
    END IF;
    RETURN market_history_v1.recent_market_sessions(p_symbol,p_limit);
END $$;
REVOKE ALL ON FUNCTION public.read_recent_market_sessions(text,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.read_recent_market_sessions(text,integer) TO authenticated;
