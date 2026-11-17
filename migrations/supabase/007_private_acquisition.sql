-- Source-specific, unpromoted worker evidence. No existing app/history rows change.
-- The installer must reject any pre-existing unowned schema/role before applying.
CREATE SCHEMA app_ingest;
REVOKE ALL ON SCHEMA app_ingest FROM PUBLIC, anon, authenticated, service_role;
CREATE ROLE app_collector NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2;
ALTER ROLE app_collector SET statement_timeout = '20s';
ALTER ROLE app_collector SET lock_timeout = '5s';
ALTER ROLE app_collector SET idle_in_transaction_session_timeout = '30s';
CREATE TABLE app_ingest.providers (
    namespace text PRIMARY KEY CHECK (namespace ~ '^feed_[a-f0-9]{16}$'),
    enabled boolean NOT NULL DEFAULT false
);
CREATE TABLE app_ingest.attempts (
    digest text PRIMARY KEY CHECK (digest ~ '^[a-f0-9]{64}$'),
    provider text NOT NULL REFERENCES app_ingest.providers(namespace),
    kind text NOT NULL CHECK (kind IN ('quotes','depth','fundamentals','dividends')),
    slot timestamptz NOT NULL,
    completed_at timestamptz NOT NULL,
    stored_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completeness text NOT NULL CHECK (completeness IN ('COMPLETE','INCOMPLETE')),
    raw_gzip bytea NOT NULL CHECK (octet_length(raw_gzip) BETWEEN 1 AND 8388608),
    CHECK (completed_at >= slot)
);
CREATE TABLE app_ingest.slots (
    provider text NOT NULL REFERENCES app_ingest.providers(namespace),
    kind text NOT NULL,
    slot timestamptz NOT NULL,
    digest text NOT NULL REFERENCES app_ingest.attempts(digest),
    PRIMARY KEY(provider,kind,slot)
);
REVOKE ALL ON ALL TABLES IN SCHEMA app_ingest FROM PUBLIC, anon, authenticated, service_role, app_collector;
ALTER TABLE app_ingest.providers ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_ingest.attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_ingest.slots ENABLE ROW LEVEL SECURITY;

CREATE FUNCTION app_ingest.slot_complete(p_provider text, p_kind text, p_slot timestamptz)
RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$
    SELECT EXISTS(SELECT 1 FROM app_ingest.slots s
        JOIN app_ingest.providers p ON p.namespace=s.provider AND p.enabled
        WHERE s.provider=p_provider AND s.kind=p_kind AND s.slot=p_slot);
$$;
CREATE FUNCTION app_ingest.save_attempt(
    p_digest text, p_provider text, p_kind text, p_slot timestamptz,
    p_completed_at timestamptz, p_completeness text, p_raw bytea
) RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE old app_ingest.attempts%ROWTYPE;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM app_ingest.providers WHERE namespace=p_provider AND enabled) THEN
        RAISE EXCEPTION 'Provider disabled' USING ERRCODE='42501';
    END IF;
    IF p_digest IS NULL OR p_digest <> encode(pg_catalog.sha256(p_raw),'hex')
       OR p_kind IS NULL OR p_kind NOT IN ('quotes','depth','fundamentals','dividends')
       OR p_completeness IS NULL OR p_completeness NOT IN ('COMPLETE','INCOMPLETE')
       OR p_raw IS NULL OR octet_length(p_raw) NOT BETWEEN 1 AND 8388608
       OR p_slot IS NULL OR p_completed_at IS NULL
       OR p_slot > p_completed_at
       OR p_completed_at > clock_timestamp()+interval '30 seconds'
       OR p_completed_at < clock_timestamp()-interval '20 minutes'
       OR p_slot < clock_timestamp()-interval '26 hours' THEN
        RAISE EXCEPTION 'Invalid acquisition' USING ERRCODE='22023';
    END IF;
    -- Serialize this append-only archive's capacity check and logical commits.
    PERFORM pg_catalog.pg_advisory_xact_lock(731905220017);
    SELECT * INTO old FROM app_ingest.attempts WHERE digest=p_digest;
    IF FOUND THEN
        IF (old.provider,old.kind,old.slot,old.completed_at,old.completeness,old.raw_gzip)
           IS DISTINCT FROM (p_provider,p_kind,p_slot,p_completed_at,p_completeness,p_raw) THEN
            RAISE EXCEPTION 'Digest metadata conflict' USING ERRCODE='22023';
        END IF;
        RETURN p_digest;
    END IF;
    -- Deliberate stop, not silent deletion of old evidence. Installer rechecks size.
    IF pg_database_size(current_database())+octet_length(p_raw)+1048576 > 350000000 THEN
        RAISE EXCEPTION 'Evidence capacity guard reached' USING ERRCODE='54000';
    END IF;
    INSERT INTO app_ingest.attempts(digest,provider,kind,slot,completed_at,completeness,raw_gzip)
        VALUES(p_digest,p_provider,p_kind,p_slot,p_completed_at,p_completeness,p_raw);
    IF p_completeness='COMPLETE' THEN
        INSERT INTO app_ingest.slots VALUES(p_provider,p_kind,p_slot,p_digest)
            ON CONFLICT(provider,kind,slot) DO NOTHING;
    END IF;
    RETURN p_digest;
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_ingest FROM PUBLIC, anon, authenticated, service_role;
GRANT USAGE ON SCHEMA app_ingest TO app_collector;
GRANT EXECUTE ON FUNCTION app_ingest.slot_complete(text,text,timestamptz) TO app_collector;
GRANT EXECUTE ON FUNCTION app_ingest.save_attempt(text,text,text,timestamptz,timestamptz,text,bytea) TO app_collector;
COMMENT ON SCHEMA app_ingest IS 'myInterpreter private acquisition v1; unpromoted evidence only';
