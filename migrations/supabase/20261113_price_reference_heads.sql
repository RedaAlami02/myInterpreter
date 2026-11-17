-- Bound reference reads by company count, not the lifetime of report history.
CREATE TABLE app_feed.verified_price_heads (
 c_name text PRIMARY KEY,
 id text NOT NULL,
 pa numeric NOT NULL CHECK(pa>0 AND pa<=1000000000000),
 stamp timestamptz NOT NULL,
 source_day date NOT NULL,
 official_sha text REFERENCES portfolio_private.official_close_batches(sha256) ON DELETE CASCADE,
 recovered_sha text REFERENCES app_feed.recovered_close_reports(raw_sha256) ON DELETE CASCADE,
 CHECK(num_nonnulls(official_sha,recovered_sha)=1)
);
ALTER TABLE app_feed.verified_price_heads ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON app_feed.verified_price_heads FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION app_feed.advance_price_heads(report_id text,day date,captured timestamptz,items jsonb,is_official boolean)
RETURNS void LANGUAGE sql SET search_path='' AS $$
 INSERT INTO app_feed.verified_price_heads(c_name,id,pa,stamp,source_day,official_sha,recovered_sha)
 SELECT item->>'c_name','close:'||report_id||':'||(item->>'company_id'),
  (item->>'price_decimal')::numeric,captured,day,
  CASE WHEN is_official THEN report_id END,CASE WHEN NOT is_official THEN report_id END
 FROM jsonb_array_elements(items) item
 WHERE jsonb_typeof(item)='object' AND coalesce(item->>'c_name','')<>''
  AND item->>'price_decimal' ~ '^[0-9]+([.][0-9]+)?$'
  AND (item->>'price_decimal')::numeric>0 AND (item->>'price_decimal')::numeric<=1000000000000
 ON CONFLICT(c_name) DO UPDATE SET id=excluded.id,pa=excluded.pa,stamp=excluded.stamp,
  source_day=excluded.source_day,official_sha=excluded.official_sha,recovered_sha=excluded.recovered_sha
 WHERE (excluded.source_day,excluded.stamp)>(verified_price_heads.source_day,verified_price_heads.stamp)
    OR ((excluded.source_day,excluded.stamp)=(verified_price_heads.source_day,verified_price_heads.stamp)
        AND excluded.id<verified_price_heads.id);
$$;
REVOKE ALL ON FUNCTION app_feed.advance_price_heads(text,date,timestamptz,jsonb,boolean) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION app_feed.capture_price_heads() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
 IF TG_TABLE_SCHEMA='portfolio_private' THEN
  PERFORM app_feed.advance_price_heads(NEW.sha256,NEW.session_day,(NEW.document->>'captured_at')::timestamptz,NEW.document->'rows',true);
 ELSE
  PERFORM app_feed.advance_price_heads(NEW.raw_sha256,NEW.session_day,NEW.captured_at,NEW.rows,false);
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION app_feed.capture_price_heads() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER official_price_heads AFTER INSERT ON portfolio_private.official_close_batches
 FOR EACH ROW EXECUTE FUNCTION app_feed.capture_price_heads();
CREATE TRIGGER recovered_price_heads AFTER INSERT ON app_feed.recovered_close_reports
 FOR EACH ROW EXECUTE FUNCTION app_feed.capture_price_heads();

DO $$ DECLARE r record; BEGIN
 FOR r IN SELECT sha256,session_day,document FROM portfolio_private.official_close_batches LOOP
  PERFORM app_feed.advance_price_heads(r.sha256,r.session_day,(r.document->>'captured_at')::timestamptz,r.document->'rows',true);
 END LOOP;
 FOR r IN SELECT raw_sha256,session_day,captured_at,rows FROM app_feed.recovered_close_reports LOOP
  PERFORM app_feed.advance_price_heads(r.raw_sha256,r.session_day,r.captured_at,r.rows,false);
 END LOOP;
END $$;

CREATE OR REPLACE FUNCTION public.read_latest_price_references_v1()
RETURNS TABLE(id text,c_name text,pa numeric,date timestamptz,origin_collection text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Authentication required' USING ERRCODE='42501'; END IF;
 RETURN QUERY WITH candidates AS (
  SELECT l.id::text,l.c_name::text,l.pa::numeric,l.date AS stamp,l.origin_collection::text,
   (l.date AT TIME ZONE 'UTC')::date AS source_day,0 AS reviewed
  FROM public.latest_prices l WHERE l.date<=statement_timestamp()
  UNION ALL
  SELECT h.id,h.c_name,h.pa,h.stamp,'verified_official_close_display/v1',h.source_day,1
  FROM app_feed.verified_price_heads h
  WHERE h.stamp<=statement_timestamp()
    AND h.source_day<=(statement_timestamp() AT TIME ZONE 'Africa/Casablanca')::date
 ), ranked AS (
  SELECT c.*,row_number() OVER(PARTITION BY c.c_name ORDER BY c.source_day DESC,c.reviewed DESC,c.stamp DESC,c.id) AS n
  FROM candidates c WHERE c.pa>0 AND c.pa<=1000000000000
 ) SELECT r.id,r.c_name,r.pa,r.stamp,r.origin_collection FROM ranked r WHERE n=1;
END $$;
