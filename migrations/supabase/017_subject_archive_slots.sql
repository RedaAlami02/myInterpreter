-- STAGED. Per-company fundamental completion; legacy slots and archives stay intact.
-- Requires SQL014, all controls off. No publication/collection switch is enabled.
DO $$ BEGIN
    IF NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND NOT enabled)
       OR NOT EXISTS(SELECT 1 FROM app_feed.control WHERE singleton AND NOT enabled)
       OR NOT EXISTS(SELECT 1 FROM app_projection.control WHERE singleton AND NOT enabled) THEN
        RAISE EXCEPTION 'Disabled controls required for subject archive installation';
    END IF;
END $$;
CREATE TABLE app_archive.subjects (
    digest text PRIMARY KEY REFERENCES app_archive.objects(digest),
    subject_key text NOT NULL CHECK(subject_key ~ '^symbol:[A-Z0-9][A-Z0-9._-]{0,31}$')
);
CREATE TABLE app_archive.subject_slots (
    provider text NOT NULL REFERENCES app_archive.providers(namespace),
    kind text NOT NULL CHECK(kind='fundamentals'),
    slot timestamptz NOT NULL CHECK(isfinite(slot)),
    subject_key text NOT NULL CHECK(subject_key ~ '^symbol:[A-Z0-9][A-Z0-9._-]{0,31}$'),
    trial_id uuid NOT NULL REFERENCES app_trial.leases(id),
    digest text NOT NULL REFERENCES app_archive.subjects(digest),
    PRIMARY KEY(provider,kind,slot,subject_key,trial_id)
);
ALTER TABLE app_archive.subjects ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_archive.subject_slots ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE app_archive.subjects,app_archive.subject_slots FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION public.reserve_subject_market_archive(p_digest text,p_provider text,p_kind text,p_slot timestamptz,
    p_completed_at timestamptz,p_completeness text,p_bytes bigint,p_subject_key text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_trial.leases%ROWTYPE; old_subject text; result jsonb;
BEGIN
    lease:=app_trial.require_lease(p_provider,'archive');
    IF p_kind IS DISTINCT FROM 'fundamentals' OR p_subject_key IS NULL
       OR p_subject_key !~ '^symbol:[A-Z0-9][A-Z0-9._-]{0,31}$' THEN
        RAISE EXCEPTION 'Invalid archive subject' USING ERRCODE='22023';
    END IF;
    SELECT subject_key INTO old_subject FROM app_archive.subjects WHERE digest=p_digest;
    IF (FOUND AND old_subject<>p_subject_key) OR (NOT FOUND AND EXISTS(
        SELECT 1 FROM app_archive.objects WHERE digest=p_digest)) THEN
        RAISE EXCEPTION 'Cannot reassign or adopt archive subject' USING ERRCODE='22023';
    END IF;
    result:=public.reserve_market_archive(p_digest,p_provider,p_kind,p_slot,p_completed_at,p_completeness,p_bytes);
    INSERT INTO app_archive.subjects VALUES(p_digest,p_subject_key) ON CONFLICT(digest) DO NOTHING;
    PERFORM app_trial.require_lease(p_provider,'archive',lease.id);
    RETURN result;
END $$;

CREATE FUNCTION public.finalize_subject_market_archive(p_digest text,p_subject_key text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_trial.leases%ROWTYPE; saved app_archive.objects%ROWTYPE;
BEGIN
    lease:=app_trial.bound_lease(p_digest,'archive');
    PERFORM pg_catalog.pg_advisory_xact_lock(731905220018);
    SELECT a.* INTO saved FROM app_archive.objects a JOIN app_archive.subjects s
        ON s.digest=a.digest AND s.subject_key=p_subject_key WHERE a.digest=p_digest FOR UPDATE OF a;
    IF NOT FOUND OR saved.kind<>'fundamentals' THEN
        RAISE EXCEPTION 'Matching subject reservation required' USING ERRCODE='22023';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled)
       OR NOT EXISTS(SELECT 1 FROM app_archive.providers WHERE namespace=saved.provider AND enabled)
       OR NOT EXISTS(SELECT 1 FROM storage.buckets WHERE id='private-market-evidence' AND public=false) THEN
        RAISE EXCEPTION 'Archive disabled or not private' USING ERRCODE='42501';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM storage.objects o WHERE o.bucket_id='private-market-evidence'
       AND o.name=saved.object_path AND o.metadata->>'size'=saved.compressed_bytes::text) THEN
        RAISE EXCEPTION 'Object not verified' USING ERRCODE='22023';
    END IF;
    UPDATE app_archive.objects SET state='STORED',verified_at=coalesce(verified_at,clock_timestamp()) WHERE digest=p_digest;
    IF saved.completeness='COMPLETE' THEN
        INSERT INTO app_archive.subject_slots VALUES(saved.provider,saved.kind,saved.slot,p_subject_key,lease.id,saved.digest)
            ON CONFLICT(provider,kind,slot,subject_key,trial_id) DO NOTHING;
    END IF;
    PERFORM app_trial.require_lease(lease.provider,'archive',lease.id);
    RETURN p_digest;
END $$;

CREATE FUNCTION public.market_archive_subject_complete(p_provider text,p_kind text,p_slot timestamptz,p_subject_key text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_trial.leases%ROWTYPE; saved app_archive.objects%ROWTYPE;
BEGIN
    IF p_kind IS DISTINCT FROM 'fundamentals' OR p_subject_key IS NULL
       OR p_subject_key !~ '^symbol:[A-Z0-9][A-Z0-9._-]{0,31}$' THEN
        RAISE EXCEPTION 'Invalid archive subject' USING ERRCODE='22023';
    END IF;
    BEGIN lease:=app_trial.require_lease(p_provider,'archive');
    EXCEPTION WHEN insufficient_privilege THEN RETURN false; END;
    SELECT a.* INTO saved FROM app_archive.subject_slots s JOIN app_archive.subjects sub
        ON sub.digest=s.digest AND sub.subject_key=s.subject_key
        JOIN app_archive.objects a ON a.digest=s.digest AND a.state='STORED'
        JOIN app_archive.control c ON c.singleton AND c.enabled
        JOIN app_archive.providers p ON p.namespace=a.provider AND p.enabled
        JOIN app_trial.objects b ON b.digest=a.digest AND b.trial_id=lease.id
        WHERE s.provider=p_provider AND s.kind=p_kind AND s.slot=p_slot AND s.subject_key=p_subject_key
          AND s.trial_id=lease.id;
    IF NOT FOUND THEN RETURN false; END IF;
    IF NOT EXISTS(SELECT 1 FROM storage.buckets WHERE id='private-market-evidence' AND public=false)
       OR NOT EXISTS(SELECT 1 FROM storage.objects o WHERE o.bucket_id='private-market-evidence'
          AND o.name=saved.object_path AND o.metadata->>'size'=saved.compressed_bytes::text) THEN
        RAISE EXCEPTION 'Committed subject object missing or not private' USING ERRCODE='22023';
    END IF;
    PERFORM app_trial.require_lease(p_provider,'archive',lease.id);
    RETURN true;
END $$;

-- Strengthen only the unscoped wrapper: v3 objects cannot create a legacy slot.
-- Positive preflight before fresh source requests. This is not a reservation;
-- concurrent callers may still exhaust a budget after admission. Final commit
-- retains all original lease/quota checks and exact-byte retry requirements.
CREATE FUNCTION public.market_archive_subject_admission(p_provider text,p_subject_key text,p_projection boolean)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_trial.leases%ROWTYPE; settings app_archive.control%ROWTYPE;
        used numeric; outstanding numeric;
BEGIN
    IF p_subject_key IS NULL OR p_subject_key !~ '^symbol:[A-Z0-9][A-Z0-9._-]{0,31}$'
       OR p_projection IS NULL THEN
        RAISE EXCEPTION 'Invalid archive subject admission' USING ERRCODE='22023';
    END IF;
    BEGIN lease:=app_trial.require_lease(p_provider,'archive');
    EXCEPTION WHEN insufficient_privilege THEN RETURN false; END;
    IF NOT 'fundamentals'=ANY(lease.kinds) OR lease.expires_at<=clock_timestamp()+interval '300 seconds'
       OR NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled)
       OR NOT EXISTS(SELECT 1 FROM app_archive.providers WHERE namespace=p_provider AND enabled)
       OR NOT EXISTS(SELECT 1 FROM storage.buckets WHERE id='private-market-evidence' AND public=false)
       OR (SELECT count(*) FROM app_trial.objects WHERE trial_id=lease.id)>=lease.max_objects
       OR (SELECT coalesce(sum(o.compressed_bytes),0) FROM app_trial.objects b
           JOIN app_archive.objects o ON o.digest=b.digest WHERE b.trial_id=lease.id)+8388608>lease.max_bytes THEN
        RETURN false;
    END IF;
    IF p_projection AND (NOT 'projections'=ANY(lease.capabilities) OR NOT EXISTS(
        SELECT 1 FROM app_projection.control WHERE singleton AND enabled AND provider_namespace=p_provider)) THEN
        RETURN false;
    END IF;
    SELECT * INTO settings FROM app_archive.control WHERE singleton;
    IF pg_database_size(current_database())+1048576>settings.max_database_bytes
       OR EXISTS(SELECT 1 FROM storage.objects WHERE metadata->>'size' IS NULL
            OR metadata->>'size' !~ '^[0-9]{1,12}$') THEN RETURN false; END IF;
    SELECT coalesce(sum((metadata->>'size')::numeric),0) INTO used FROM storage.objects;
    SELECT coalesce(sum(a.compressed_bytes),0) INTO outstanding FROM app_archive.objects a
        WHERE a.state='RESERVED' AND NOT EXISTS(SELECT 1 FROM storage.objects o
            WHERE o.bucket_id='private-market-evidence' AND o.name=a.object_path);
    IF used+outstanding+8388608>settings.max_storage_bytes THEN RETURN false; END IF;
    PERFORM app_trial.require_lease(p_provider,'archive',lease.id);
    RETURN true;
END $$;

DO $$
DECLARE old_body text; new_body text;
BEGIN
    SELECT prosrc INTO old_body FROM pg_proc WHERE oid='public.finalize_market_archive(text)'::regprocedure;
    IF encode(sha256(convert_to(old_body,'UTF8')),'hex')<>
       'f55ceb4bf66d9a10e282a3d842b7258533d153cb0dbde893f3fa11904ab8b221' THEN
        RAISE EXCEPTION 'Unrecognized legacy finalize wrapper';
    END IF;
    new_body:=replace(old_body,'lease:=app_trial.bound_lease(p_digest,''archive'');',
        'IF EXISTS(SELECT 1 FROM app_archive.subjects WHERE digest=p_digest) THEN
            RAISE EXCEPTION ''Subject archive requires subject finalization'' USING ERRCODE=''22023'';
         END IF;
         lease:=app_trial.bound_lease(p_digest,''archive'');');
    EXECUTE format('CREATE OR REPLACE FUNCTION public.finalize_market_archive(p_digest text)
        RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path='''' SET lock_timeout=''2s'' AS %L',new_body);
END $$;
REVOKE ALL ON FUNCTION public.reserve_subject_market_archive(text,text,text,timestamptz,timestamptz,text,bigint,text),
    public.finalize_subject_market_archive(text,text),public.market_archive_subject_complete(text,text,timestamptz,text),
    public.market_archive_subject_admission(text,text,boolean)
    FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.reserve_subject_market_archive(text,text,text,timestamptz,timestamptz,text,bigint,text),
    public.finalize_subject_market_archive(text,text),public.market_archive_subject_complete(text,text,timestamptz,text),
    public.market_archive_subject_admission(text,text,boolean) TO service_role;
