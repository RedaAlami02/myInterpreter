-- Additive read-only worker context. No portfolios, account fields or raw evidence.
-- Install atomically while controls are disabled. Runtime requires a valid lease.
DO $$ BEGIN
    IF NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND NOT enabled)
       OR NOT EXISTS(SELECT 1 FROM app_projection.control WHERE singleton AND NOT enabled) THEN
        RAISE EXCEPTION 'Disabled controls required for context installation';
    END IF;
END $$;
CREATE FUNCTION public.read_enrichment_context(p_provider text,p_index_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE lease app_trial.leases%ROWTYPE; result jsonb; companies jsonb; price_companies jsonb;
BEGIN
    lease:=app_trial.require_lease(p_provider,'projections');
    IF p_index_sha256 IS NULL OR p_index_sha256 !~ '^[a-f0-9]{64}$'
       OR NOT EXISTS(SELECT 1 FROM app_projection.control WHERE singleton AND enabled
            AND provider_namespace=p_provider AND fundamental_index_sha256=p_index_sha256)
       OR NOT EXISTS(SELECT 1 FROM app_archive.control WHERE singleton AND enabled)
       OR NOT EXISTS(SELECT 1 FROM app_archive.providers WHERE namespace=p_provider AND enabled) THEN
        RAISE EXCEPTION 'Enrichment context disabled or index mismatch' USING ERRCODE='42501';
    END IF;
    IF (SELECT count(*)>2000 OR count(*)<>count(DISTINCT name) FROM public.company)
       OR EXISTS(SELECT 1 FROM public.company WHERE name IS NULL OR length(name) NOT BETWEEN 1 AND 200) THEN
        RAISE EXCEPTION 'Ambiguous or oversized company context' USING ERRCODE='22023';
    END IF;
    SELECT coalesce(jsonb_object_agg(name,jsonb_build_object(
        'bpa',bpa,'sector',sector,'fiscal_year',fiscal_year) ORDER BY id),'{}'::jsonb)
        INTO companies FROM public.company;
    SELECT coalesce(jsonb_object_agg(c.id,jsonb_build_object('name',c.name,
        'bpa',c.bpa,'tc5',c.tc5,'roe',c.roe,'na',c.na,'cp',c.cp,'net_profit',c.net_profit,
        'date',c.date,'available_at',greatest(c.date,(SELECT max(a.completed_at)
            FROM app_projection.accepted_rows a WHERE a.kind='fundamentals' AND
            a.target_key=encode(sha256(convert_to(jsonb_build_array(c.name)::text,'UTF8')),'hex')))) ORDER BY c.id),'{}'::jsonb)
        INTO price_companies FROM public.company c;
    result:=jsonb_build_object('contract','private-enrichment-context/v2',
        'provider_namespace',p_provider,'index_sha256',p_index_sha256,
        'observed_at',clock_timestamp(),'companies',companies,'price_companies',price_companies);
    IF octet_length(result::text)>524288 THEN
        RAISE EXCEPTION 'Enrichment context exceeds limit' USING ERRCODE='54000';
    END IF;
    PERFORM app_trial.require_lease(p_provider,'projections',lease.id);
    RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.read_enrichment_context(text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.read_enrichment_context(text,text) TO service_role;
