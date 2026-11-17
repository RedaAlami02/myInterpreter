-- Owner-authorized, short-lived quote recovery. Source dates are unchanged.
CREATE TABLE app_recurring.quote_recovery_windows (
 provider text PRIMARY KEY REFERENCES app_recurring.policies(provider),
 starts_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 CHECK(expires_at>starts_at AND expires_at<=starts_at+interval '30 minutes')
);
ALTER TABLE app_recurring.quote_recovery_windows ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON app_recurring.quote_recovery_windows FROM PUBLIC,anon,authenticated,service_role;
CREATE OR REPLACE FUNCTION app_recurring.check_new_object(p_provider text, p_kind text, p_slot timestamp with time zone, p_completed timestamp with time zone, p_bytes bigint)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE policy app_recurring.policies%ROWTYPE; local_slot timestamp; local_now timestamp; used_objects bigint; used_bytes numeric; open_at time; close_at time;
BEGIN
 SELECT * INTO policy FROM app_recurring.policies WHERE provider=p_provider;
 open_at:=CASE WHEN policy.acquisition_window='OFFICIAL_CLOSE' THEN time '17:00' ELSE time '09:00' END;
    close_at:=CASE WHEN policy.acquisition_window='OFFICIAL_CLOSE' THEN time '19:00' ELSE time '17:00' END;
    IF p_kind='quotes' AND policy.acquisition_window='REGULAR' AND EXISTS (
      SELECT 1 FROM app_recurring.quote_recovery_windows w
      WHERE w.provider=p_provider AND clock_timestamp() BETWEEN w.starts_at AND w.expires_at
        AND p_completed BETWEEN w.starts_at AND w.expires_at
        AND (SELECT count(*) FROM app_recurring.objects b JOIN app_archive.objects a ON a.digest=b.digest
             JOIN app_recurring.runs r ON r.id=b.run_id
             WHERE r.provider=p_provider AND a.completed_at>=w.starts_at)<2
    ) THEN open_at:=time '00:00'; close_at:=time '23:59:59'; END IF;
    local_slot:=p_slot AT TIME ZONE 'Africa/Casablanca'; local_now:=clock_timestamp() AT TIME ZONE 'Africa/Casablanca';
 IF p_kind IS NULL OR NOT p_kind=ANY(policy.kinds) OR p_slot IS NULL OR NOT isfinite(p_slot)
 OR p_completed IS NULL OR NOT isfinite(p_completed) OR p_completed>clock_timestamp()
 OR p_slot>p_completed OR p_completed<clock_timestamp()-interval '10 minutes'
 OR local_slot::date<>local_now::date OR extract(isodow FROM local_slot)>5
 OR extract(second FROM local_slot)<>0 THEN RAISE EXCEPTION 'Recurring acquisition chronology differs' USING ERRCODE='42501'; END IF;
 IF p_kind IN ('quotes','depth') AND (local_now::time<open_at OR local_now::time>=close_at
 OR (p_completed AT TIME ZONE 'Africa/Casablanca')::time<open_at
 OR (p_completed AT TIME ZONE 'Africa/Casablanca')::time>=close_at
 OR p_completed-p_slot>make_interval(mins=>CASE WHEN p_kind='quotes' THEN 17 ELSE 7 END)) THEN
  RAISE EXCEPTION 'Recurring slot is stale or outside current acquisition window' USING ERRCODE='42501';
 END IF;
 IF (p_kind IN ('quotes','depth') AND (local_slot::time<open_at OR local_slot::time>=close_at
       OR mod(extract(minute FROM local_slot)::integer,CASE WHEN p_kind='quotes' THEN 15 ELSE 5 END)<>0))
 OR (p_kind='fundamentals' AND (local_now::time<time '17:00' OR local_now::time>=time '19:00'))
 OR (p_kind='dividends' AND (extract(isodow FROM local_now)<>1 OR local_now::time<time '07:00' OR local_now::time>=time '08:00')) THEN
  RAISE EXCEPTION 'Outside recurring source window' USING ERRCODE='42501';
 END IF;
 SELECT count(*),coalesce(sum(a.compressed_bytes),0) INTO used_objects,used_bytes
 FROM app_recurring.objects b JOIN app_recurring.runs r ON r.id=b.run_id JOIN app_archive.objects a ON a.digest=b.digest
 WHERE r.provider=p_provider AND (a.completed_at AT TIME ZONE 'Africa/Casablanca')::date=local_now::date;
 IF p_bytes IS NULL OR p_bytes<1 OR used_objects>=policy.max_objects_per_day OR used_bytes+p_bytes>policy.max_bytes_per_day THEN
  RAISE EXCEPTION 'Recurring daily archive budget reached' USING ERRCODE='54000';
 END IF;
END $function$
;
