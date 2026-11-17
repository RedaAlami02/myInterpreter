-- Private aggregate health checks. No user identities or source names leave SQL.
CREATE TABLE app_timer.health_control (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 enabled boolean NOT NULL DEFAULT false,
 counter_day date, requests_today integer NOT NULL DEFAULT 0 CHECK(requests_today BETWEEN 0 AND 3),
 last_attempt timestamptz,last_request_id bigint,last_http_status integer
);
ALTER TABLE app_timer.health_control ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON app_timer.health_control FROM PUBLIC,anon,authenticated,service_role;
INSERT INTO app_timer.health_control(singleton) VALUES(true);
CREATE FUNCTION app_timer.health_snapshot() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE t timestamptz:=clock_timestamp(); local_t timestamp:=t AT TIME ZONE 'Africa/Casablanca';
 depth_time timestamptz; quotes_time timestamptz; feed_time timestamptz; depth_ok boolean; quotes_ok boolean;
BEGIN
 SELECT o.completed_at,o.completeness='COMPLETE' INTO depth_time,depth_ok FROM app_archive.objects o
 WHERE o.state='STORED' AND o.kind='depth' ORDER BY o.completed_at DESC LIMIT 1;
 SELECT o.completed_at,o.completeness='COMPLETE' INTO quotes_time,quotes_ok FROM app_archive.objects o
 JOIN app_recurring.policies p ON p.provider=o.provider AND p.acquisition_window<>'OFFICIAL_CLOSE'
 WHERE o.state='STORED' AND o.kind='quotes' ORDER BY o.completed_at DESC LIMIT 1;
 -- The site reads the published feed, not the archive. Measure the feed so a
 -- collected-but-not-published run is visible, falling back to the archive.
 SELECT f.captured_at INTO feed_time FROM app_feed.latest f
 JOIN app_feed.control c ON c.singleton AND c.enabled AND c.provider_namespace=f.provider;
 RETURN jsonb_build_object('measured_at',t,'database_bytes',pg_database_size(current_database()),
 'guard_bytes',(SELECT max_database_bytes FROM app_archive.control WHERE singleton),'warning_bytes',20000000,
 'market_due',extract(isodow FROM local_t)<=5 AND local_t::time>=time '09:30' AND local_t::time<time '17:00',
 'close_due',extract(isodow FROM local_t)<=5 AND local_t::time>=time '19:15',
 'depth_age_seconds',CASE WHEN depth_time IS NULL THEN NULL ELSE greatest(0,extract(epoch FROM t-depth_time)) END,
 'quotes_age_seconds',CASE WHEN coalesce(feed_time,quotes_time) IS NULL THEN NULL ELSE greatest(0,extract(epoch FROM t-coalesce(feed_time,quotes_time))) END,
 'depth_complete',coalesce(depth_ok,false),'quotes_complete',coalesce(quotes_ok,false),
 'official_batches',(SELECT count(*) FROM portfolio_private.official_close_batches WHERE session_day=local_t::date),
 'valuation_receipts',(SELECT count(*) FROM portfolio_private.official_valuation_receipts WHERE day=local_t::date),
 'portfolio_owners',(SELECT count(DISTINCT h.user_id) FROM public.portefeuille h JOIN auth.users u ON u.id=h.user_id));
END;
$$;
REVOKE ALL ON FUNCTION app_timer.health_snapshot() FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION app_timer.health_tick(p_manual boolean DEFAULT false) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE state app_timer.health_control%ROWTYPE; local_t timestamp:=clock_timestamp() AT TIME ZONE 'Africa/Casablanca';
 target text; token text; request_id bigint;
BEGIN
 IF NOT pg_try_advisory_xact_lock(179423,32) THEN RETURN 'BUSY'; END IF;
 SELECT * INTO STRICT state FROM app_timer.health_control WHERE singleton FOR UPDATE;
 IF NOT state.enabled THEN RETURN 'DISABLED'; END IF;
 IF NOT p_manual AND (extract(isodow FROM local_t)>5 OR extract(hour FROM local_t) NOT IN (12,20)) THEN RETURN 'OUTSIDE_WINDOW'; END IF;
 IF state.last_attempt>clock_timestamp()-interval '10 minutes' THEN RETURN 'RECENT_ATTEMPT'; END IF;
 IF state.counter_day IS DISTINCT FROM local_t::date THEN state.requests_today:=0; END IF;
 IF state.requests_today>=3 THEN RETURN 'DAILY_LIMIT'; END IF;
 SELECT decrypted_secret INTO STRICT target FROM vault.decrypted_secrets WHERE name='app_timer_endpoint';
 SELECT decrypted_secret INTO STRICT token FROM vault.decrypted_secrets WHERE name='app_timer_call_token';
 IF target !~ '^https://[a-z0-9]+[.]supabase[.]co/functions/v1/private-schedule-dispatcher$' OR length(token)<32 THEN RAISE EXCEPTION 'HEALTH_CONFIGURATION_INVALID'; END IF;
 target:=replace(target,'/private-schedule-dispatcher','/private-health-dispatcher');
 SELECT net.http_post(url:=target,headers:=jsonb_build_object('Content-Type','application/json','Authorization','Bearer '||token),body:=app_timer.health_snapshot(),timeout_milliseconds:=20000) INTO request_id;
 UPDATE app_timer.health_control SET counter_day=local_t::date,requests_today=state.requests_today+1,last_attempt=clock_timestamp(),last_request_id=request_id,
 last_http_status=(SELECT status_code FROM net._http_response WHERE id=state.last_request_id) WHERE singleton;
 DELETE FROM cron.job_run_details WHERE jobid IN (SELECT jobid FROM cron.job WHERE jobname='app-private-health') AND end_time<clock_timestamp()-interval '7 days';
 RETURN 'QUEUED';
END;
$$;
REVOKE ALL ON FUNCTION app_timer.health_tick(boolean) FROM PUBLIC,anon,authenticated,service_role;
SELECT cron.schedule('app-private-health','7 * * * 1-5','SELECT app_timer.health_tick()');
SELECT cron.alter_job(jobid,active:=false) FROM cron.job WHERE jobname='app-private-health';
