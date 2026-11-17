-- Positive source-I/O admission; leaves all controls and existing contracts unchanged.
-- This is a preflight, not a reservation or a recurring lease issuer.
CREATE FUNCTION public.market_archive_acquisition_admission(
    p_provider text,p_kind text,p_slot timestamptz,p_shadow boolean,p_projection boolean)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_trial.leases%ROWTYPE; settings app_archive.control%ROWTYPE;
    used numeric; outstanding numeric;
BEGIN
    IF p_provider IS NULL OR p_provider !~ '^feed_[a-f0-9]{16}$'
       OR p_kind IS NULL OR p_kind NOT IN ('quotes','depth','dividends')
       OR p_slot IS NULL OR NOT isfinite(p_slot) OR p_shadow IS NULL OR p_projection IS NULL
       OR (p_shadow AND p_kind<>'quotes') OR (p_projection AND p_kind NOT IN ('quotes','dividends')) THEN
        RAISE EXCEPTION 'Invalid acquisition admission' USING ERRCODE='22023';
    END IF;
    BEGIN lease:=app_trial.require_lease(p_provider,'archive');
    EXCEPTION WHEN insufficient_privilege THEN RETURN false; END;
    IF NOT p_kind=ANY(lease.kinds) OR lease.expires_at<=clock_timestamp()+interval '300 seconds'
       OR p_slot>clock_timestamp() OR p_slot<clock_timestamp()-interval '26 hours'
       OR NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled)
       OR NOT EXISTS(SELECT 1 FROM app_archive.providers WHERE namespace=p_provider AND enabled)
       OR NOT EXISTS(SELECT 1 FROM storage.buckets WHERE id='private-market-evidence' AND public=false)
       OR (SELECT count(*) FROM app_trial.objects WHERE trial_id=lease.id)>=lease.max_objects
       OR (SELECT coalesce(sum(o.compressed_bytes),0) FROM app_trial.objects b
           JOIN app_archive.objects o ON o.digest=b.digest WHERE b.trial_id=lease.id)+8388608>lease.max_bytes THEN
        RETURN false;
    END IF;
    IF p_shadow AND (NOT 'shadow_feed'=ANY(lease.capabilities) OR NOT EXISTS(
        SELECT 1 FROM app_feed.control WHERE singleton AND enabled AND provider_namespace=p_provider)) THEN
        RETURN false;
    END IF;
    IF p_projection AND (NOT 'projections'=ANY(lease.capabilities)
       OR (p_kind='dividends' AND NOT EXISTS(SELECT 1 FROM app_projection.control
           WHERE singleton AND enabled AND provider_namespace=p_provider))
       OR (p_kind='quotes' AND (NOT p_shadow OR NOT EXISTS(SELECT 1 FROM app_feed.application_control
           WHERE singleton AND enabled)))) THEN
        RETURN false;
    END IF;
    IF public.market_archive_slot_complete(p_provider,p_kind,p_slot) THEN RETURN false; END IF;
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
REVOKE ALL ON FUNCTION public.market_archive_acquisition_admission(text,text,timestamptz,boolean,boolean)
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.market_archive_acquisition_admission(text,text,timestamptz,boolean,boolean)
    TO service_role;
