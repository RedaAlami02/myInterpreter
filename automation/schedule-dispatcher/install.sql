-- Prepared installation: disabled until credentials and readback are verified.
-- Apply in one transaction. No personal, source or financial records are touched.
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;
CREATE SCHEMA IF NOT EXISTS app_timer;
REVOKE ALL ON SCHEMA app_timer FROM PUBLIC,anon,authenticated,service_role;
CREATE TABLE app_timer.control (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 enabled boolean NOT NULL DEFAULT false,
 counter_day date,
 requests_today integer NOT NULL DEFAULT 0 CHECK(requests_today BETWEEN 0 AND 134),
 last_attempt timestamptz,
 last_request_id bigint,
 last_http_status integer,
 last_result text NOT NULL DEFAULT 'NOT_STARTED'
);
ALTER TABLE app_timer.control ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON app_timer.control FROM PUBLIC,anon,authenticated,service_role;
INSERT INTO app_timer.control(singleton) VALUES(true);
CREATE FUNCTION app_timer.tick() RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE
 state app_timer.control%ROWTYPE;
 local_now timestamp := clock_timestamp() AT TIME ZONE 'Africa/Casablanca';
 target text; token text; response record; request_id bigint;
BEGIN
 -- Only one timer transaction can enqueue a call; do not hold a network lock.
 IF NOT pg_try_advisory_xact_lock(179423,31) THEN RETURN 'BUSY'; END IF;
 SELECT * INTO STRICT state FROM app_timer.control WHERE singleton FOR UPDATE;
 IF NOT state.enabled THEN RETURN 'DISABLED'; END IF;
 IF extract(isodow FROM local_now)>5 OR NOT (
   (extract(hour FROM local_now)>=9 AND extract(hour FROM local_now)<19) OR
   (extract(isodow FROM local_now)=1 AND extract(hour FROM local_now)=7)
 ) THEN RETURN 'OUTSIDE_WINDOW'; END IF;
 IF date_bin(interval '5 minutes',state.last_attempt,timestamptz '2000-01-01') >=
    date_bin(interval '5 minutes',clock_timestamp(),timestamptz '2000-01-01')
    OR state.last_attempt>clock_timestamp()-interval '1 minute' THEN RETURN 'RECENT_ATTEMPT'; END IF;
 IF state.last_request_id IS NOT NULL THEN
   SELECT status_code,timed_out INTO response FROM net._http_response WHERE id=state.last_request_id;
   IF NOT FOUND AND state.last_attempt>clock_timestamp()-interval '10 minutes' THEN RETURN 'REQUEST_PENDING'; END IF;
   UPDATE app_timer.control SET last_http_status=response.status_code,
     last_result=CASE WHEN response.status_code=202 THEN 'DISPATCH_ACCEPTED'
       WHEN response.status_code=200 THEN 'DISPATCH_SKIPPED'
       ELSE 'DISPATCH_UNCONFIRMED' END WHERE singleton;
 END IF;
 IF state.counter_day IS DISTINCT FROM local_now::date THEN
   state.requests_today:=0;
 END IF;
 IF state.requests_today>=134 THEN RETURN 'DAILY_LIMIT'; END IF;
 SELECT decrypted_secret INTO STRICT target FROM vault.decrypted_secrets WHERE name='app_timer_endpoint';
 SELECT decrypted_secret INTO STRICT token FROM vault.decrypted_secrets WHERE name='app_timer_call_token';
 IF target !~ '^https://[a-z0-9]+[.]supabase[.]co/functions/v1/private-schedule-dispatcher$'
   OR length(token)<32 THEN RAISE EXCEPTION 'TIMER_CONFIGURATION_INVALID'; END IF;
 SELECT net.http_post(url:=target,headers:=jsonb_build_object('Content-Type','application/json',
   'Authorization','Bearer '||token),body:='{}'::jsonb,timeout_milliseconds:=20000) INTO request_id;
 UPDATE app_timer.control SET counter_day=local_now::date,requests_today=state.requests_today+1,
   last_attempt=clock_timestamp(),last_request_id=request_id WHERE singleton;
 -- Retain only this new timer's bounded execution history, never unrelated jobs.
 DELETE FROM cron.job_run_details WHERE jobid IN (
   SELECT jobid FROM cron.job WHERE jobname IN ('app-private-timer-weekday','app-private-timer-close','app-private-timer-monday')
 ) AND end_time<clock_timestamp()-interval '7 days';
 RETURN 'QUEUED';
END;
$$;
REVOKE ALL ON FUNCTION app_timer.tick() FROM PUBLIC,anon,authenticated,service_role;
-- Register while disabled, then explicitly pause all jobs as a second gate.
-- 15-minute session cadence fits the free private-repo Actions allowance;
-- evening close runs are separate so the session window stays narrow.
SELECT cron.schedule('app-private-timer-weekday','2-59/15 9-15 * * 1-5','SELECT app_timer.tick()');
SELECT cron.schedule('app-private-timer-close','2 17,18 * * 1-5','SELECT app_timer.tick()');
SELECT cron.schedule('app-private-timer-monday','5 6,7 * * 1','SELECT app_timer.tick()');
SELECT cron.alter_job(jobid, active := false) FROM cron.job
 WHERE jobname IN ('app-private-timer-weekday','app-private-timer-close','app-private-timer-monday');
