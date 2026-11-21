-- Shared-market chart read. No user data, writer grants or stored-data changes.
CREATE FUNCTION public.read_company_daily_history_v1(p_name text)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE points jsonb;
BEGIN
    IF auth.uid() IS NULL THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE='42501';
    END IF;
    IF p_name IS NULL OR length(p_name)<1 OR length(p_name)>160
       OR NOT EXISTS(SELECT 1 FROM public.company WHERE name=p_name) THEN
        RAISE EXCEPTION 'Invalid company' USING ERRCODE='22023';
    END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object('day',day::text,'price',pa::text) ORDER BY day),'[]'::jsonb)
    INTO points
    FROM (
        SELECT DISTINCT ON ((date AT TIME ZONE 'UTC')::date)
            (date AT TIME ZONE 'UTC')::date AS day,pa
        FROM public.data WHERE c_name=p_name
        ORDER BY (date AT TIME ZONE 'UTC')::date DESC,date DESC,id DESC
        LIMIT 10001
    ) daily;
    IF jsonb_array_length(points)>10000 THEN
        RAISE EXCEPTION 'History exceeds chart limit' USING ERRCODE='54000';
    END IF;
    RETURN jsonb_build_object('contract','company-daily-history/v1','company',p_name,'rows',points);
END $$;
REVOKE ALL ON FUNCTION public.read_company_daily_history_v1(text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.read_company_daily_history_v1(text) TO authenticated;
COMMENT ON FUNCTION public.read_company_daily_history_v1(text) IS
    'Read-only bounded UTC daily observations; latest date then id wins; no official-close assertion';
