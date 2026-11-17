-- Expose review_class so the admin page can distinguish auto candidates from
-- bank, insurer and standalone-account rows awaiting the same approval.
CREATE OR REPLACE FUNCTION public.read_exchange_annual_candidates()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE caller uuid := auth.uid(); result jsonb;
BEGIN
    IF caller IS NULL OR auth.role() IS DISTINCT FROM 'authenticated'
       OR NOT EXISTS (SELECT 1 FROM market_admin.admins a WHERE a.user_id = caller) THEN
        RAISE EXCEPTION 'Administrator access required' USING ERRCODE = '42501';
    END IF;
    SELECT coalesce(jsonb_agg(to_jsonb(c) ORDER BY c.created_at DESC), '[]'::jsonb)
      INTO result
      FROM (SELECT report_sha256, report_generated_at, symbol, company_name,
                   fiscal_year, fields, review_class, warnings, page_sha256,
                   status, created_at
              FROM market_maintenance.annual_candidates
             WHERE status = 'PENDING'
             ORDER BY created_at DESC
             LIMIT 200) c;
    RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.read_exchange_annual_candidates() FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.read_exchange_annual_candidates() TO authenticated;
