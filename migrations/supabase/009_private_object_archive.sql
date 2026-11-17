-- STAGED ONLY. Standalone alternative to draft007; never writes recovered tables.
-- Storage buckets/objects MUST be created via the Storage API, not by this SQL.
-- Installation, organization-wide quota review, function deployment and enabling
-- the provider are separate operator steps. Everything starts disabled.
CREATE SCHEMA app_archive;
REVOKE ALL ON SCHEMA app_archive FROM PUBLIC, anon, authenticated, service_role;
CREATE TABLE app_archive.control (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    enabled boolean NOT NULL DEFAULT false,
    max_storage_bytes bigint NOT NULL DEFAULT 750000000 CHECK (max_storage_bytes BETWEEN 1 AND 750000000),
    max_database_bytes bigint NOT NULL DEFAULT 350000000 CHECK (max_database_bytes BETWEEN 1 AND 350000000)
);
INSERT INTO app_archive.control(singleton) VALUES(true);
CREATE TABLE app_archive.providers (
    namespace text PRIMARY KEY CHECK (namespace ~ '^feed_[a-f0-9]{16}$'),
    enabled boolean NOT NULL DEFAULT false
);
CREATE TABLE app_archive.objects (
    digest text PRIMARY KEY CHECK (digest ~ '^[a-f0-9]{64}$'),
    provider text NOT NULL REFERENCES app_archive.providers(namespace),
    kind text NOT NULL CHECK (kind IN ('quotes','depth','fundamentals','dividends')),
    slot timestamptz NOT NULL,
    completed_at timestamptz NOT NULL CHECK (completed_at >= slot),
    completeness text NOT NULL CHECK (completeness IN ('COMPLETE','INCOMPLETE')),
    compressed_bytes bigint NOT NULL CHECK (compressed_bytes BETWEEN 1 AND 8388608),
    object_path text NOT NULL UNIQUE,
    state text NOT NULL DEFAULT 'RESERVED' CHECK (state IN ('RESERVED','STORED')),
    reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    verified_at timestamptz,
    CHECK ((state='STORED') = (verified_at IS NOT NULL)),
    CHECK (object_path='sha256/'||left(digest,2)||'/'||digest||'.json.gz')
);
CREATE TABLE app_archive.slots (
    provider text NOT NULL REFERENCES app_archive.providers(namespace),
    kind text NOT NULL,
    slot timestamptz NOT NULL,
    digest text NOT NULL REFERENCES app_archive.objects(digest),
    PRIMARY KEY(provider,kind,slot)
);
REVOKE ALL ON ALL TABLES IN SCHEMA app_archive FROM PUBLIC, anon, authenticated, service_role;
ALTER TABLE app_archive.control ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_archive.providers ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_archive.objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_archive.slots ENABLE ROW LEVEL SECURITY;

CREATE FUNCTION public.reserve_market_archive(
    p_digest text, p_provider text, p_kind text, p_slot timestamptz,
    p_completed_at timestamptz, p_completeness text, p_bytes bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE settings app_archive.control%ROWTYPE;
        old app_archive.objects%ROWTYPE;
        used numeric; outstanding numeric; object_key text;
BEGIN
    PERFORM pg_catalog.pg_advisory_xact_lock(731905220018);
    SELECT * INTO settings FROM app_archive.control WHERE singleton;
    IF NOT FOUND OR NOT settings.enabled OR NOT EXISTS (
        SELECT 1 FROM app_archive.providers WHERE namespace=p_provider AND enabled
    ) OR NOT EXISTS (
        SELECT 1 FROM storage.buckets WHERE id='private-market-evidence' AND public=false
    ) THEN
        RAISE EXCEPTION 'Archive disabled or not private' USING ERRCODE='42501';
    END IF;
    SELECT * INTO old FROM app_archive.objects WHERE digest=p_digest;
    IF FOUND THEN
        IF (old.provider,old.kind,old.slot,old.completed_at,old.completeness,old.compressed_bytes)
           IS DISTINCT FROM (p_provider,p_kind,p_slot,p_completed_at,p_completeness,p_bytes) THEN
            RAISE EXCEPTION 'Archive metadata conflict' USING ERRCODE='22023';
        END IF;
        -- Exact retries may finish an earlier reservation without reclassifying time.
        RETURN jsonb_build_object('state',old.state,'bucket','private-market-evidence','object_path',old.object_path);
    END IF;
    IF p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$'
       OR p_kind IS NULL OR p_kind NOT IN ('quotes','depth','fundamentals','dividends')
       OR p_completeness IS NULL OR p_completeness NOT IN ('COMPLETE','INCOMPLETE')
       OR p_bytes IS NULL OR p_bytes NOT BETWEEN 1 AND 8388608
       OR p_slot IS NULL OR p_completed_at IS NULL OR NOT isfinite(p_slot) OR NOT isfinite(p_completed_at)
       OR p_slot > p_completed_at OR p_completed_at > clock_timestamp()+interval '30 seconds'
       OR p_completed_at < clock_timestamp()-interval '20 minutes'
       OR p_slot < clock_timestamp()-interval '26 hours' THEN
        RAISE EXCEPTION 'Invalid archive reservation' USING ERRCODE='22023';
    END IF;
    IF pg_database_size(current_database())+1048576 > settings.max_database_bytes THEN
        RAISE EXCEPTION 'Database capacity guard reached' USING ERRCODE='54000';
    END IF;
    -- Unknown object sizes fail closed. Includes all buckets in THIS project;
    -- other projects' organization usage must be reviewed before setting budget.
    IF EXISTS (SELECT 1 FROM storage.objects WHERE metadata->>'size' IS NULL
               OR metadata->>'size' !~ '^[0-9]{1,12}$') THEN
        RAISE EXCEPTION 'Storage size unknown' USING ERRCODE='54000';
    END IF;
    SELECT coalesce(sum((metadata->>'size')::numeric),0) INTO used FROM storage.objects;
    SELECT coalesce(sum(a.compressed_bytes),0) INTO outstanding FROM app_archive.objects a
        WHERE a.state='RESERVED' AND NOT EXISTS (SELECT 1 FROM storage.objects o
            WHERE o.bucket_id='private-market-evidence' AND o.name=a.object_path);
    IF used+outstanding+p_bytes > settings.max_storage_bytes THEN
        RAISE EXCEPTION 'Object capacity guard reached' USING ERRCODE='54000';
    END IF;
    object_key := 'sha256/'||left(p_digest,2)||'/'||p_digest||'.json.gz';
    INSERT INTO app_archive.objects(digest,provider,kind,slot,completed_at,completeness,compressed_bytes,object_path)
        VALUES(p_digest,p_provider,p_kind,p_slot,p_completed_at,p_completeness,p_bytes,object_key);
    RETURN jsonb_build_object('state','RESERVED','bucket','private-market-evidence','object_path',object_key);
END $$;

CREATE FUNCTION public.finalize_market_archive(p_digest text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved app_archive.objects%ROWTYPE;
BEGIN
    PERFORM pg_catalog.pg_advisory_xact_lock(731905220018);
    SELECT * INTO saved FROM app_archive.objects WHERE digest=p_digest FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Unknown reservation' USING ERRCODE='22023'; END IF;
    IF NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled)
       OR NOT EXISTS(SELECT 1 FROM app_archive.providers WHERE namespace=saved.provider AND enabled)
       OR NOT EXISTS(SELECT 1 FROM storage.buckets WHERE id='private-market-evidence' AND public=false) THEN
        RAISE EXCEPTION 'Archive disabled or not private' USING ERRCODE='42501';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM storage.objects o WHERE o.bucket_id='private-market-evidence'
       AND o.name=saved.object_path AND o.metadata->>'size'=saved.compressed_bytes::text) THEN
        RAISE EXCEPTION 'Object not verified' USING ERRCODE='22023';
    END IF;
    UPDATE app_archive.objects SET state='STORED',verified_at=coalesce(verified_at,clock_timestamp())
        WHERE digest=p_digest;
    IF saved.completeness='COMPLETE' THEN
        INSERT INTO app_archive.slots VALUES(saved.provider,saved.kind,saved.slot,saved.digest)
            ON CONFLICT(provider,kind,slot) DO NOTHING;
    END IF;
    RETURN p_digest;
END $$;

CREATE FUNCTION public.market_archive_slot_complete(p_provider text,p_kind text,p_slot timestamptz)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved app_archive.objects%ROWTYPE;
BEGIN
    SELECT o.* INTO saved FROM app_archive.slots s
        JOIN app_archive.objects o ON o.digest=s.digest AND o.state='STORED'
        JOIN app_archive.providers p ON p.namespace=s.provider AND p.enabled
        JOIN app_archive.control c ON c.singleton AND c.enabled
        WHERE s.provider=p_provider AND s.kind=p_kind AND s.slot=p_slot;
    IF NOT FOUND THEN RETURN false; END IF;
    IF NOT EXISTS(SELECT 1 FROM storage.buckets WHERE id='private-market-evidence' AND public=false)
       OR NOT EXISTS(SELECT 1 FROM storage.objects o WHERE o.bucket_id='private-market-evidence'
          AND o.name=saved.object_path AND o.metadata->>'size'=saved.compressed_bytes::text) THEN
        RAISE EXCEPTION 'Committed object missing or not private' USING ERRCODE='22023';
    END IF;
    RETURN true;
END;
$$;
REVOKE ALL ON FUNCTION public.reserve_market_archive(text,text,text,timestamptz,timestamptz,text,bigint) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.finalize_market_archive(text) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.market_archive_slot_complete(text,text,timestamptz) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_market_archive(text,text,text,timestamptz,timestamptz,text,bigint) TO service_role;
GRANT EXECUTE ON FUNCTION public.finalize_market_archive(text) TO service_role;
GRANT EXECUTE ON FUNCTION public.market_archive_slot_complete(text,text,timestamptz) TO service_role;
COMMENT ON SCHEMA app_archive IS 'myInterpreter private object archive v1; unpromoted metadata only';
