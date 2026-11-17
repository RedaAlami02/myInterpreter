-- Dated display references only. Original histories and valuation writers unchanged.
CREATE TABLE app_feed.recovered_close_reports (
 raw_sha256 text PRIMARY KEY CHECK(raw_sha256 ~ '^[a-f0-9]{64}$'),
 raw_pdf bytea NOT NULL CHECK(octet_length(raw_pdf) BETWEEN 4 AND 3145728),
 session_day date NOT NULL,
 captured_at timestamptz NOT NULL,
 verified_at timestamptz NOT NULL CHECK(verified_at>=captured_at),
 parser_sha256 text NOT NULL CHECK(parser_sha256 ~ '^[a-f0-9]{64}$'),
 policy_sha256 text NOT NULL CHECK(policy_sha256 ~ '^[a-f0-9]{64}$'),
 identity_sha256 text NOT NULL CHECK(identity_sha256 ~ '^[a-f0-9]{64}$'),
 rows jsonb NOT NULL CHECK(jsonb_typeof(rows)='array' AND jsonb_array_length(rows) BETWEEN 1 AND 1000),
 evidence_class text NOT NULL DEFAULT 'RECOVERED_VERIFIED_REPORT' CHECK(evidence_class='RECOVERED_VERIFIED_REPORT'),
 CHECK(encode(sha256(raw_pdf),'hex')=raw_sha256),
 CHECK(substring(raw_pdf FROM 1 FOR 4)=convert_to('%PDF','UTF8')),
 CHECK(session_day=(captured_at AT TIME ZONE 'Africa/Casablanca')::date),
 CHECK(session_day=(captured_at AT TIME ZONE 'UTC')::date)
);
ALTER TABLE app_feed.recovered_close_reports ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON app_feed.recovered_close_reports FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION public.read_latest_price_references_v1()
RETURNS TABLE(id text,c_name text,pa numeric,date timestamptz,origin_collection text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Authentication required' USING ERRCODE='42501'; END IF;
 RETURN QUERY WITH reports AS (
  SELECT s.raw_sha256 AS report_id,s.session_day,s.captured_at,s.rows
  FROM app_feed.recovered_close_reports s
  WHERE s.captured_at<=statement_timestamp() AND s.verified_at<=statement_timestamp()
   AND s.session_day<=(statement_timestamp() AT TIME ZONE 'Africa/Casablanca')::date
  UNION ALL
  SELECT b.sha256,b.session_day,(b.document->>'captured_at')::timestamptz,b.document->'rows'
  FROM portfolio_private.official_close_batches b
  WHERE b.reviewed_at<=statement_timestamp()
   AND (b.document->>'captured_at')::timestamptz<=statement_timestamp()
   AND b.session_day<=(statement_timestamp() AT TIME ZONE 'Africa/Casablanca')::date
 ), candidates AS (
  SELECT l.id::text,l.c_name::text,l.pa::numeric,l.date AS stamp,l.origin_collection::text,
    (l.date AT TIME ZONE 'UTC')::date AS source_day,0 AS reviewed
  FROM public.latest_prices l WHERE l.date<=statement_timestamp()
  UNION ALL
  SELECT 'close:'||r.report_id||':'||(item->>'company_id'),item->>'c_name',
   CASE WHEN item->>'price_decimal' ~ '^[0-9]+([.][0-9]+)?$' THEN (item->>'price_decimal')::numeric END,
   r.captured_at,'verified_official_close_display/v1',r.session_day,1
  FROM reports r CROSS JOIN LATERAL jsonb_array_elements(r.rows) AS item
  WHERE jsonb_typeof(item)='object' AND coalesce(item->>'c_name','')<>''
 ), ranked AS (
  SELECT c.*,row_number() OVER(PARTITION BY c.c_name ORDER BY c.source_day DESC,c.reviewed DESC,c.stamp DESC,c.id) AS n
  FROM candidates c WHERE c.pa>0 AND c.pa<=1000000000000
 ) SELECT r.id,r.c_name,r.pa,r.stamp,r.origin_collection FROM ranked r WHERE n=1;
END $$;
REVOKE ALL ON FUNCTION public.read_latest_price_references_v1() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.read_latest_price_references_v1() TO authenticated;
COMMENT ON FUNCTION public.read_latest_price_references_v1() IS
 'Authenticated latest dated display references. Never authorizes a saved valuation or changes original observations.';
