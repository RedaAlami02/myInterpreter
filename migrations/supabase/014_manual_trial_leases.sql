-- LOCAL REVIEW ONLY. Not authorized for hosted installation or activation.
-- Requires SQL009/010/013, all controls OFF. Run atomically as their owner.
-- manual-activation/v1: bounded manual acceptance, never recurring execution.
DO $$ BEGIN
    IF NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND NOT enabled)
       OR NOT EXISTS(SELECT 1 FROM app_feed.control WHERE singleton AND NOT enabled)
       OR NOT EXISTS(SELECT 1 FROM app_projection.control WHERE singleton AND NOT enabled) THEN
        RAISE EXCEPTION 'Disable all controls before installing manual gates';
    END IF;
END $$;

CREATE SCHEMA app_trial;
CREATE SCHEMA app_trial_legacy;
REVOKE ALL ON SCHEMA app_trial,app_trial_legacy FROM PUBLIC,anon,authenticated,service_role;
CREATE TABLE app_trial.leases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider text NOT NULL CHECK(provider ~ '^feed_[a-f0-9]{16}$'),
    plan_sha256 text NOT NULL CHECK(plan_sha256 ~ '^[a-f0-9]{64}$'),
    capabilities text[] NOT NULL CHECK(
        capabilities <@ ARRAY['archive','shadow_feed','projections']::text[]
        AND capabilities @> ARRAY['archive']::text[] AND array_position(capabilities,NULL) IS NULL),
    kinds text[] NOT NULL CHECK(cardinality(kinds)>0 AND
        kinds <@ ARRAY['quotes','depth','dividends','fundamentals']::text[]
        AND array_position(kinds,NULL) IS NULL),
    max_objects integer NOT NULL CHECK(max_objects BETWEEN 1 AND 8),
    max_bytes bigint NOT NULL CHECK(max_bytes BETWEEN 1 AND 8388608),
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL CHECK(expires_at>created_at AND expires_at<=created_at+interval '15 minutes'),
    revoked_at timestamptz,
    CHECK(revoked_at IS NULL OR revoked_at>=created_at)
);
CREATE UNIQUE INDEX manual_trial_one_open_provider ON app_trial.leases(provider) WHERE revoked_at IS NULL;
CREATE TABLE app_trial.objects (
    digest text PRIMARY KEY REFERENCES app_archive.objects(digest),
    trial_id uuid NOT NULL REFERENCES app_trial.leases(id)
);
ALTER TABLE app_trial.leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_trial.objects ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA app_trial FROM PUBLIC,anon,authenticated,service_role;

-- All manual entrypoints serialize, including issue/revoke. Busy revocation
-- throws 55P03 and MUST be retried: it is never acknowledged while work is active.
CREATE FUNCTION app_trial.lock_gate() RETURNS void LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'Manual gate requires read committed isolation' USING ERRCODE='25000';
    END IF;
    -- The caller/role must set this BEFORE the outer statement starts. Setting
    -- it inside this function would not start the current statement's timer.
    IF (SELECT setting::bigint FROM pg_settings WHERE name='statement_timeout') NOT BETWEEN 1 AND 20000 THEN
        RAISE EXCEPTION 'Manual gate requires an outer statement timeout at most 20 seconds' USING ERRCODE='55000';
    END IF;
    IF NOT pg_try_advisory_xact_lock(731905220021) THEN
        RAISE EXCEPTION 'Manual gate busy; retry' USING ERRCODE='55P03';
    END IF;
END $$;

CREATE FUNCTION app_trial.require_lease(p_provider text,p_capability text,p_expected uuid DEFAULT NULL)
RETURNS app_trial.leases LANGUAGE plpgsql SET search_path='' AS $$
DECLARE lease app_trial.leases%ROWTYPE;
BEGIN
    PERFORM app_trial.lock_gate();
    SELECT * INTO lease FROM app_trial.leases WHERE provider=p_provider AND revoked_at IS NULL;
    IF NOT FOUND OR lease.expires_at<=clock_timestamp()
       OR NOT p_capability=ANY(lease.capabilities)
       OR (p_expected IS NOT NULL AND lease.id<>p_expected) THEN
        RAISE EXCEPTION 'Active matching manual trial required' USING ERRCODE='42501';
    END IF;
    RETURN lease;
END $$;

-- Owner-only API. No table/lease-management grants to service_role.
CREATE FUNCTION app_trial.issue(p_provider text,p_plan text,p_capabilities text[],p_kinds text[],
    p_seconds integer DEFAULT 300,p_max_objects integer DEFAULT 1,p_max_bytes bigint DEFAULT 8388608)
RETURNS uuid LANGUAGE plpgsql SET search_path='' AS $$
DECLARE moment timestamptz; result uuid;
BEGIN
    PERFORM app_trial.lock_gate();
    moment:=clock_timestamp();
    IF p_seconds IS NULL OR p_seconds NOT BETWEEN 1 AND 900 THEN
        RAISE EXCEPTION 'Invalid manual trial duration' USING ERRCODE='22023';
    END IF;
    UPDATE app_trial.leases SET revoked_at=moment
        WHERE provider=p_provider AND revoked_at IS NULL AND expires_at<=moment;
    INSERT INTO app_trial.leases(provider,plan_sha256,capabilities,kinds,max_objects,max_bytes,created_at,expires_at)
        VALUES(p_provider,p_plan,p_capabilities,p_kinds,p_max_objects,p_max_bytes,moment,
            moment+make_interval(secs=>p_seconds)) RETURNING id INTO result;
    RETURN result;
END $$;
CREATE FUNCTION app_trial.revoke(p_trial uuid) RETURNS void LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
    PERFORM app_trial.lock_gate();
    UPDATE app_trial.leases SET revoked_at=coalesce(revoked_at,clock_timestamp()) WHERE id=p_trial;
    IF NOT FOUND THEN RAISE EXCEPTION 'Unknown manual trial' USING ERRCODE='22023'; END IF;
END $$;

-- Preserve reviewed implementation bodies/OIDs. Their direct grants are removed.
ALTER FUNCTION public.reserve_market_archive(text,text,text,timestamptz,timestamptz,text,bigint) SET SCHEMA app_trial_legacy;
ALTER FUNCTION public.finalize_market_archive(text) SET SCHEMA app_trial_legacy;
ALTER FUNCTION public.market_archive_slot_complete(text,text,timestamptz) SET SCHEMA app_trial_legacy;
ALTER FUNCTION public.publish_shadow_market_candidate(text,text) SET SCHEMA app_trial_legacy;
ALTER FUNCTION public.read_shadow_market_feed() SET SCHEMA app_trial_legacy;
ALTER FUNCTION public.publish_dividend_projection(text,text) SET SCHEMA app_trial_legacy;
ALTER FUNCTION public.publish_fundamental_projection(text,text) SET SCHEMA app_trial_legacy;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_trial_legacy FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION public.reserve_market_archive(
    p_digest text,p_provider text,p_kind text,p_slot timestamptz,
    p_completed_at timestamptz,p_completeness text,p_bytes bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_trial.leases%ROWTYPE; bound uuid; result jsonb;
BEGIN
    lease:=app_trial.require_lease(p_provider,'archive');
    SELECT trial_id INTO bound FROM app_trial.objects WHERE digest=p_digest;
    IF FOUND AND bound<>lease.id THEN
        RAISE EXCEPTION 'Prior trial object needs explicit recovery approval' USING ERRCODE='42501';
    END IF;
    IF NOT FOUND THEN
        IF EXISTS(SELECT 1 FROM app_archive.objects WHERE digest=p_digest)
           OR p_kind IS NULL OR NOT p_kind=ANY(lease.kinds)
           OR p_completed_at IS NULL OR p_completed_at<lease.created_at
           OR p_bytes IS NULL OR p_bytes<1
           OR (SELECT count(*) FROM app_trial.objects WHERE trial_id=lease.id)>=lease.max_objects
           OR (SELECT coalesce(sum(o.compressed_bytes),0) FROM app_trial.objects b
               JOIN app_archive.objects o ON o.digest=b.digest WHERE b.trial_id=lease.id)+p_bytes>lease.max_bytes THEN
            RAISE EXCEPTION 'Manual trial object budget or scope exceeded' USING ERRCODE='42501';
        END IF;
    END IF;
    result:=app_trial_legacy.reserve_market_archive(p_digest,p_provider,p_kind,p_slot,p_completed_at,p_completeness,p_bytes);
    INSERT INTO app_trial.objects VALUES(p_digest,lease.id) ON CONFLICT(digest) DO NOTHING;
    PERFORM app_trial.require_lease(p_provider,'archive',lease.id);
    RETURN result;
END $$;

CREATE FUNCTION app_trial.bound_lease(p_digest text,p_capability text)
RETURNS app_trial.leases LANGUAGE plpgsql SET search_path='' AS $$
DECLARE lease app_trial.leases%ROWTYPE; provider text; bound uuid;
BEGIN
    PERFORM app_trial.lock_gate();
    SELECT o.provider,b.trial_id INTO provider,bound FROM app_archive.objects o
        JOIN app_trial.objects b ON b.digest=o.digest WHERE o.digest=p_digest;
    IF NOT FOUND THEN RAISE EXCEPTION 'Trial-bound archive required' USING ERRCODE='42501'; END IF;
    lease:=app_trial.require_lease(provider,p_capability,bound);
    RETURN lease;
END $$;
CREATE FUNCTION public.finalize_market_archive(p_digest text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_trial.leases%ROWTYPE; result text;
BEGIN
    lease:=app_trial.bound_lease(p_digest,'archive');
    result:=app_trial_legacy.finalize_market_archive(p_digest);
    PERFORM app_trial.require_lease(lease.provider,'archive',lease.id);
    RETURN result;
END $$;
CREATE FUNCTION public.market_archive_slot_complete(p_provider text,p_kind text,p_slot timestamptz)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_trial.leases%ROWTYPE; digest text; result boolean;
BEGIN
    BEGIN lease:=app_trial.require_lease(p_provider,'archive');
    EXCEPTION WHEN insufficient_privilege THEN RETURN false; END;
    SELECT s.digest INTO digest FROM app_archive.slots s JOIN app_trial.objects b ON b.digest=s.digest
        WHERE s.provider=p_provider AND s.kind=p_kind AND s.slot=p_slot AND b.trial_id=lease.id;
    IF NOT FOUND THEN RETURN false; END IF;
    result:=app_trial_legacy.market_archive_slot_complete(p_provider,p_kind,p_slot);
    PERFORM app_trial.require_lease(p_provider,'archive',lease.id);
    RETURN result;
END $$;

CREATE FUNCTION app_trial.document_lease(p_document text,p_capability text)
RETURNS app_trial.leases LANGUAGE plpgsql SET search_path='' AS $$
DECLARE doc jsonb; lease app_trial.leases%ROWTYPE;
BEGIN
    IF p_document IS NULL OR octet_length(p_document)>2097152 THEN
        RAISE EXCEPTION 'Invalid bounded document' USING ERRCODE='22023';
    END IF;
    doc:=p_document::jsonb;
    lease:=app_trial.bound_lease(doc->>'archive_sha256',p_capability);
    IF doc->>'provider_namespace' IS DISTINCT FROM lease.provider THEN
        RAISE EXCEPTION 'Trial namespace mismatch' USING ERRCODE='42501';
    END IF;
    RETURN lease;
END $$;
CREATE FUNCTION public.publish_shadow_market_candidate(p_document text,p_payload_sha256 text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_trial.leases%ROWTYPE; result text;
BEGIN
    lease:=app_trial.document_lease(p_document,'shadow_feed');
    IF NOT EXISTS(SELECT 1 FROM app_feed.control WHERE singleton AND enabled) THEN
        RAISE EXCEPTION 'Shadow trial publication disabled' USING ERRCODE='42501';
    END IF;
    result:=app_trial_legacy.publish_shadow_market_candidate(p_document,p_payload_sha256);
    PERFORM app_trial.require_lease(lease.provider,'shadow_feed',lease.id);
    RETURN result;
END $$;
CREATE FUNCTION public.publish_dividend_projection(p_document text,p_payload_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_trial.leases%ROWTYPE; result jsonb;
BEGIN
    lease:=app_trial.document_lease(p_document,'projections');
    result:=app_trial_legacy.publish_dividend_projection(p_document,p_payload_sha256);
    PERFORM app_trial.require_lease(lease.provider,'projections',lease.id);
    RETURN result;
END $$;
CREATE FUNCTION public.publish_fundamental_projection(p_document text,p_payload_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_trial.leases%ROWTYPE; result jsonb;
BEGIN
    lease:=app_trial.document_lease(p_document,'projections');
    result:=app_trial_legacy.publish_fundamental_projection(p_document,p_payload_sha256);
    PERFORM app_trial.require_lease(lease.provider,'projections',lease.id);
    RETURN result;
END $$;
CREATE FUNCTION public.read_shadow_market_feed()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_trial.leases%ROWTYPE; digest text; result jsonb; clipped jsonb;
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Sign in required' USING ERRCODE='42501'; END IF;
    result:=jsonb_build_object('contract','app-market-preview/v1','mode','SHADOW_ONLY',
        'as_of',clock_timestamp(),'status','DISABLED','captured_at',NULL,
        'acquisition_completeness',NULL,'market_session_state','UNKNOWN','rows','[]'::jsonb);
    PERFORM app_trial.lock_gate();
    SELECT f.archive_digest INTO digest FROM app_feed.latest f JOIN app_feed.control c
        ON c.singleton AND c.enabled AND c.provider_namespace=f.provider;
    IF NOT FOUND THEN RETURN result; END IF;
    BEGIN lease:=app_trial.bound_lease(digest,'shadow_feed');
    EXCEPTION WHEN insufficient_privilege THEN RETURN result; END;
    result:=app_trial_legacy.read_shadow_market_feed();
    SELECT coalesce(jsonb_agg(CASE WHEN r->>'expires_at' IS NULL THEN r ELSE
        r||jsonb_build_object('expires_at',least((r->>'expires_at')::timestamptz,lease.expires_at)) END
        ORDER BY ordinal),'[]'::jsonb) INTO clipped
        FROM jsonb_array_elements(result->'rows') WITH ORDINALITY AS rows(r,ordinal);
    PERFORM app_trial.require_lease(lease.provider,'shadow_feed',lease.id);
    RETURN result||jsonb_build_object('rows',clipped);
END $$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_trial FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.reserve_market_archive(text,text,text,timestamptz,timestamptz,text,bigint),
    public.finalize_market_archive(text),public.market_archive_slot_complete(text,text,timestamptz),
    public.publish_shadow_market_candidate(text,text),public.publish_dividend_projection(text,text),
    public.publish_fundamental_projection(text,text),public.read_shadow_market_feed()
    FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.reserve_market_archive(text,text,text,timestamptz,timestamptz,text,bigint),
    public.finalize_market_archive(text),public.market_archive_slot_complete(text,text,timestamptz),
    public.publish_shadow_market_candidate(text,text),public.publish_dividend_projection(text,text),
    public.publish_fundamental_projection(text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.read_shadow_market_feed() TO authenticated;
COMMENT ON SCHEMA app_trial IS 'manual-activation/v1; owner-issued bounded acceptance only';
