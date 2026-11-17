-- recurring-acquisition/v1. Additive: manual RPCs and evidence remain unchanged.
-- Install with source controls OFF; policies are not seeded or enabled here.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM app_archive.control WHERE enabled)
 OR EXISTS(SELECT 1 FROM app_feed.control WHERE enabled)
 OR EXISTS(SELECT 1 FROM app_projection.control WHERE enabled) THEN
  RAISE EXCEPTION 'Disable source controls before recurring installation';
 END IF;
END $$;
CREATE SCHEMA app_recurring;
REVOKE ALL ON SCHEMA app_recurring FROM PUBLIC,anon,authenticated,service_role;
CREATE TABLE app_recurring.policies (
 provider text PRIMARY KEY REFERENCES app_archive.providers(namespace),
 contract text NOT NULL DEFAULT 'recurring-acquisition/v1' CHECK(contract='recurring-acquisition/v1'),
 policy_sha256 text NOT NULL CHECK(policy_sha256 ~ '^[a-f0-9]{64}$'),
 enabled boolean NOT NULL DEFAULT false,
 capabilities text[] NOT NULL CHECK(capabilities <@ ARRAY['archive','shadow_feed','projections']::text[] AND capabilities @> ARRAY['archive']::text[] AND array_position(capabilities,NULL) IS NULL),
 kinds text[] NOT NULL CHECK(cardinality(kinds)>0 AND kinds <@ ARRAY['quotes','depth','fundamentals','dividends']::text[] AND array_position(kinds,NULL) IS NULL),
 max_objects_per_day integer NOT NULL CHECK(max_objects_per_day BETWEEN 1 AND 256),
 max_bytes_per_day bigint NOT NULL CHECK(max_bytes_per_day BETWEEN 8388608 AND 67108864),
 recovery_hours integer NOT NULL DEFAULT 48 CHECK(recovery_hours BETWEEN 1 AND 48),
 valid_until timestamptz NOT NULL CHECK(isfinite(valid_until))
);
CREATE TABLE app_recurring.runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 provider text NOT NULL REFERENCES app_recurring.policies(provider),
 plan_sha256 text NOT NULL,
 capabilities text[] NOT NULL,
 kinds text[] NOT NULL,
 max_objects integer NOT NULL DEFAULT 8 CHECK(max_objects BETWEEN 1 AND 8),
 max_bytes bigint NOT NULL DEFAULT 67108864 CHECK(max_bytes BETWEEN 8388608 AND 67108864),
 created_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL CHECK(expires_at>created_at AND expires_at<=created_at+interval '15 minutes'),
 revoked_at timestamptz
);
CREATE INDEX recurring_runs_provider_time ON app_recurring.runs(provider,created_at DESC);
CREATE TABLE app_recurring.objects (
 digest text PRIMARY KEY REFERENCES app_archive.objects(digest),
 run_id uuid NOT NULL REFERENCES app_recurring.runs(id)
);
CREATE TABLE app_recurring.subject_slots (
 provider text NOT NULL,kind text NOT NULL,slot timestamptz NOT NULL,subject_key text NOT NULL,
 run_id uuid NOT NULL REFERENCES app_recurring.runs(id),digest text NOT NULL REFERENCES app_archive.subjects(digest),
 PRIMARY KEY(provider,kind,slot,subject_key,run_id)
);
CREATE TABLE app_recurring.admissions (
 provider text NOT NULL REFERENCES app_recurring.policies(provider),
 kind text NOT NULL,slot timestamptz NOT NULL,
 run_id uuid NOT NULL REFERENCES app_recurring.runs(id),
 admitted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(provider,kind,slot,run_id)
);
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['policies','runs','objects','subject_slots','admissions'] LOOP
  EXECUTE format('ALTER TABLE app_recurring.%I ENABLE ROW LEVEL SECURITY',tab);
  EXECUTE format('REVOKE ALL ON TABLE app_recurring.%I FROM PUBLIC,anon,authenticated,service_role',tab);
 END LOOP;
END $$;
CREATE FUNCTION app_recurring.lock_gate() RETURNS void LANGUAGE sql SET search_path='' AS $$
 SELECT app_trial.lock_gate()
$$;
CREATE FUNCTION app_recurring.require_lease(p_provider text,p_capability text,p_expected uuid DEFAULT NULL)
RETURNS app_recurring.runs LANGUAGE plpgsql SET search_path='' AS $$
DECLARE policy app_recurring.policies%ROWTYPE; lease app_recurring.runs%ROWTYPE; moment timestamptz;
BEGIN
 PERFORM app_recurring.lock_gate();moment:=clock_timestamp();
 SELECT * INTO policy FROM app_recurring.policies WHERE provider=p_provider FOR SHARE;
 IF NOT FOUND OR NOT policy.enabled OR policy.valid_until<=moment OR NOT p_capability=ANY(policy.capabilities) THEN
  RAISE EXCEPTION 'Enabled recurring policy required' USING ERRCODE='42501';
 END IF;
 IF p_expected IS NOT NULL THEN
  SELECT * INTO lease FROM app_recurring.runs WHERE id=p_expected AND provider=p_provider
   AND plan_sha256=policy.policy_sha256 AND revoked_at IS NULL AND expires_at>moment;
  IF NOT FOUND THEN RAISE EXCEPTION 'Recurring run expired or changed' USING ERRCODE='42501'; END IF;
 ELSE
  SELECT * INTO lease FROM app_recurring.runs WHERE provider=p_provider AND plan_sha256=policy.policy_sha256
   AND revoked_at IS NULL AND expires_at>moment+interval '400 seconds' ORDER BY created_at DESC LIMIT 1;
  IF NOT FOUND THEN
   IF (SELECT count(*) FROM app_recurring.runs WHERE provider=p_provider
       AND created_at>=date_trunc('day',moment AT TIME ZONE 'Africa/Casablanca') AT TIME ZONE 'Africa/Casablanca')>=192 THEN
    RAISE EXCEPTION 'Recurring run budget reached' USING ERRCODE='54000';
   END IF;
   INSERT INTO app_recurring.runs(provider,plan_sha256,capabilities,kinds,created_at,expires_at)
    VALUES(p_provider,policy.policy_sha256,policy.capabilities,policy.kinds,moment,least(moment+interval '15 minutes',policy.valid_until)) RETURNING * INTO lease;
  END IF;
 END IF;
 IF NOT p_capability=ANY(lease.capabilities) THEN RAISE EXCEPTION 'Recurring capability denied' USING ERRCODE='42501'; END IF;
 RETURN lease;
END $$;
CREATE FUNCTION app_recurring.bound_lease(p_digest text,p_capability text)
RETURNS app_recurring.runs LANGUAGE plpgsql SET search_path='' AS $$
DECLARE original app_recurring.runs%ROWTYPE; policy app_recurring.policies%ROWTYPE;
BEGIN
 PERFORM app_recurring.lock_gate();
 SELECT r.* INTO original FROM app_recurring.objects b JOIN app_recurring.runs r ON r.id=b.run_id WHERE b.digest=p_digest;
 IF NOT FOUND THEN RAISE EXCEPTION 'Recurring-bound archive required' USING ERRCODE='42501'; END IF;
 SELECT * INTO policy FROM app_recurring.policies WHERE provider=original.provider;
 IF original.revoked_at IS NOT NULL OR original.plan_sha256 IS DISTINCT FROM policy.policy_sha256
 OR original.created_at<clock_timestamp()-make_interval(hours=>policy.recovery_hours) THEN
  RAISE EXCEPTION 'Recurring object recovery denied' USING ERRCODE='42501';
 END IF;
 RETURN app_recurring.require_lease(original.provider,p_capability);
END $$;
CREATE FUNCTION app_recurring.document_lease(p_document text,p_capability text)
RETURNS app_recurring.runs LANGUAGE plpgsql SET search_path='' AS $$
DECLARE doc jsonb; lease app_recurring.runs%ROWTYPE;
BEGIN
 IF p_document IS NULL OR octet_length(p_document)>2097152 THEN RAISE EXCEPTION 'Invalid recurring document'; END IF;
 doc:=p_document::jsonb;lease:=app_recurring.bound_lease(doc->>'archive_sha256',p_capability);
 IF doc->>'provider_namespace' IS DISTINCT FROM lease.provider THEN RAISE EXCEPTION 'Recurring namespace differs' USING ERRCODE='42501'; END IF;
 RETURN lease;
END $$;
CREATE FUNCTION app_recurring.check_new_object(p_provider text,p_kind text,p_slot timestamptz,p_completed timestamptz,p_bytes bigint)
RETURNS void LANGUAGE plpgsql SET search_path='' AS $$
DECLARE policy app_recurring.policies%ROWTYPE; local_slot timestamp; local_now timestamp; used_objects bigint; used_bytes numeric;
BEGIN
 SELECT * INTO policy FROM app_recurring.policies WHERE provider=p_provider;
 local_slot:=p_slot AT TIME ZONE 'Africa/Casablanca'; local_now:=clock_timestamp() AT TIME ZONE 'Africa/Casablanca';
 IF p_kind IS NULL OR NOT p_kind=ANY(policy.kinds) OR p_slot IS NULL OR NOT isfinite(p_slot)
 OR p_completed IS NULL OR NOT isfinite(p_completed) OR p_completed>clock_timestamp()
 OR p_slot>p_completed OR p_completed<clock_timestamp()-interval '10 minutes'
 OR local_slot::date<>local_now::date OR extract(isodow FROM local_slot)>5
 OR extract(second FROM local_slot)<>0 THEN RAISE EXCEPTION 'Recurring acquisition chronology differs' USING ERRCODE='42501'; END IF;
 IF p_kind IN ('quotes','depth') AND (local_now::time<time '09:00' OR local_now::time>=time '17:00'
 OR (p_completed AT TIME ZONE 'Africa/Casablanca')::time<time '09:00'
 OR (p_completed AT TIME ZONE 'Africa/Casablanca')::time>=time '17:00'
 OR p_completed-p_slot>make_interval(mins=>CASE WHEN p_kind='quotes' THEN 17 ELSE 7 END)) THEN
  RAISE EXCEPTION 'Recurring slot is stale or outside current acquisition window' USING ERRCODE='42501';
 END IF;
 IF (p_kind IN ('quotes','depth') AND (local_slot::time<time '09:00' OR local_slot::time>=time '17:00'
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
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_recurring FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION public.reserve_market_archive_recurring_v1(
 p_digest text,p_provider text,p_kind text,p_slot timestamptz,p_completed_at timestamptz,p_completeness text,p_bytes bigint)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_recurring.runs%ROWTYPE; acquisition app_recurring.runs%ROWTYPE; policy app_recurring.policies%ROWTYPE; bound uuid; result jsonb; used_count bigint; used_bytes numeric;
BEGIN
 lease:=app_recurring.require_lease(p_provider,'archive');
 SELECT run_id INTO bound FROM app_recurring.objects WHERE digest=p_digest;
 IF FOUND THEN
  acquisition.id:=bound;
  PERFORM app_recurring.bound_lease(p_digest,'archive');
 ELSE
  SELECT r.* INTO acquisition FROM app_recurring.admissions t JOIN app_recurring.runs r ON r.id=t.run_id
   WHERE t.provider=p_provider AND t.kind=p_kind AND (t.slot=p_slot OR (p_kind='fundamentals' AND t.slot=p_slot-interval '1 hour')) AND r.plan_sha256=lease.plan_sha256
   AND r.revoked_at IS NULL AND p_completed_at>=t.admitted_at AND p_completed_at<=r.expires_at
   ORDER BY t.admitted_at DESC LIMIT 1;
  SELECT * INTO policy FROM app_recurring.policies WHERE provider=p_provider;
  IF acquisition.id IS NULL OR acquisition.created_at<clock_timestamp()-make_interval(hours=>policy.recovery_hours)
  OR EXISTS(SELECT 1 FROM app_archive.objects WHERE digest=p_digest) OR p_kind IS NULL OR NOT p_kind=ANY(acquisition.kinds)
  OR p_completed_at IS NULL OR p_completed_at>clock_timestamp() OR p_bytes IS NULL OR p_bytes<1
  OR (SELECT count(*) FROM app_recurring.objects WHERE run_id=acquisition.id)>=acquisition.max_objects
  OR (SELECT coalesce(sum(a.compressed_bytes),0) FROM app_recurring.objects b JOIN app_archive.objects a ON a.digest=b.digest WHERE b.run_id=acquisition.id)+p_bytes>acquisition.max_bytes THEN
   RAISE EXCEPTION 'Matching admitted acquisition run and budget required' USING ERRCODE='42501';
  END IF;
  SELECT count(*),coalesce(sum(a.compressed_bytes),0) INTO used_count,used_bytes
   FROM app_recurring.objects b JOIN app_recurring.runs r ON r.id=b.run_id JOIN app_archive.objects a ON a.digest=b.digest
   WHERE r.provider=p_provider AND (a.completed_at AT TIME ZONE 'Africa/Casablanca')::date=(p_completed_at AT TIME ZONE 'Africa/Casablanca')::date;
  IF used_count>=policy.max_objects_per_day OR used_bytes+p_bytes>policy.max_bytes_per_day THEN
   RAISE EXCEPTION 'Recurring daily archive budget reached' USING ERRCODE='54000';
  END IF;
 END IF;
 result:=app_recurring.reserve_archive_impl(p_digest,p_provider,p_kind,p_slot,p_completed_at,p_completeness,p_bytes);
 INSERT INTO app_recurring.objects VALUES(p_digest,acquisition.id) ON CONFLICT(digest) DO NOTHING;
 PERFORM app_recurring.require_lease(p_provider,'archive',lease.id);
 RETURN result;
END $$;
CREATE FUNCTION public.market_archive_slot_complete_recurring_v1(p_provider text,p_kind text,p_slot timestamptz)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_recurring.runs%ROWTYPE; digest text;
BEGIN
 BEGIN lease:=app_recurring.require_lease(p_provider,'archive');
 EXCEPTION WHEN insufficient_privilege THEN RETURN false; END;
 SELECT s.digest INTO digest FROM app_archive.slots s JOIN app_recurring.objects b ON b.digest=s.digest
 JOIN app_recurring.runs r ON r.id=b.run_id AND r.plan_sha256=lease.plan_sha256 AND r.revoked_at IS NULL
 WHERE s.provider=p_provider AND s.kind=p_kind AND s.slot=p_slot;
 IF NOT FOUND THEN RETURN false; END IF;
 PERFORM app_recurring.bound_lease(digest,'archive');
 RETURN app_trial_legacy.market_archive_slot_complete(p_provider,p_kind,p_slot);
END $$;
REVOKE ALL ON FUNCTION public.reserve_market_archive_recurring_v1(text,text,text,timestamptz,timestamptz,text,bigint),
 public.market_archive_slot_complete_recurring_v1(text,text,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.reserve_market_archive_recurring_v1(text,text,text,timestamptz,timestamptz,text,bigint),
 public.market_archive_slot_complete_recurring_v1(text,text,timestamptz) TO service_role;

CREATE TABLE app_recurring.projection_pins (
 provider text PRIMARY KEY REFERENCES app_recurring.policies(provider),
 policy_sha256 text NOT NULL CHECK(policy_sha256 ~ '^[a-f0-9]{64}$'),
 dividend_index_sha256 text CHECK(dividend_index_sha256 ~ '^[a-f0-9]{64}$'),
 fundamental_index_sha256 text CHECK(fundamental_index_sha256 ~ '^[a-f0-9]{64}$')
);
ALTER TABLE app_recurring.projection_pins ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE app_recurring.projection_pins FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION app_recurring.projection_control(p_provider text)
RETURNS SETOF app_projection.control LANGUAGE sql SET search_path='' AS $$
 SELECT c.singleton,c.enabled,c.max_database_bytes,p.provider,p.dividend_index_sha256,p.fundamental_index_sha256
 FROM app_projection.control c JOIN app_recurring.projection_pins p ON p.provider=p_provider
 JOIN app_recurring.policies policy ON policy.provider=p.provider AND policy.policy_sha256=p.policy_sha256
 WHERE c.singleton AND policy.enabled AND policy.valid_until>clock_timestamp()
$$;
REVOKE ALL ON FUNCTION app_recurring.projection_control(text) FROM PUBLIC,anon,authenticated,service_role;

-- A retained pre-I/O admission, checked by the outer wrapper, replaces the
-- legacy new-object20min limit. All quota/privacy/identity checks remain exact.
DO $$ DECLARE source text; definition text; BEGIN
 SELECT prosrc,pg_get_functiondef(oid) INTO source,definition FROM pg_proc
 WHERE oid='app_trial_legacy.reserve_market_archive(text,text,text,timestamptz,timestamptz,text,bigint)'::regprocedure;
 IF encode(sha256(convert_to(source,'UTF8')),'hex')<>'6c396e587fe6712fd8dfbd566ff0af4c7e40be5d49481e059e3b6785289854ee' THEN
  RAISE EXCEPTION 'Unexpected original archive validator';
 END IF;
 definition:=replace(definition,'app_trial_legacy.reserve_market_archive(', 'app_recurring.reserve_archive_impl(');
 definition:=replace(definition,'p_completed_at < clock_timestamp()-interval ''20 minutes''','p_completed_at < clock_timestamp()-interval ''48 hours''');
 definition:=replace(definition,'p_slot < clock_timestamp()-interval ''26 hours''','p_slot < clock_timestamp()-interval ''72 hours''');
 EXECUTE definition;
END $$;
REVOKE ALL ON FUNCTION app_recurring.reserve_archive_impl(text,text,text,timestamptz,timestamptz,text,bigint) FROM PUBLIC,anon,authenticated,service_role;
