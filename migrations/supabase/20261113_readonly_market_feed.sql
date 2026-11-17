-- Feed reads validate existing evidence policy without renewing writer leases.
CREATE FUNCTION app_recurring.read_bound_object(p_digest text,p_capability text)
RETURNS app_recurring.runs LANGUAGE plpgsql STABLE SET search_path='' AS $$
DECLARE original app_recurring.runs%ROWTYPE; policy app_recurring.policies%ROWTYPE;
BEGIN
 SELECT r.* INTO original FROM app_recurring.objects b JOIN app_recurring.runs r ON r.id=b.run_id WHERE b.digest=p_digest;
 IF NOT FOUND THEN RAISE EXCEPTION 'Recurring-bound archive required' USING ERRCODE='42501'; END IF;
 SELECT * INTO policy FROM app_recurring.policies WHERE provider=original.provider;
 IF NOT FOUND OR NOT policy.enabled OR policy.valid_until<=statement_timestamp()
 OR original.revoked_at IS NOT NULL OR original.plan_sha256 IS DISTINCT FROM policy.policy_sha256
 OR original.created_at<statement_timestamp()-make_interval(hours=>policy.recovery_hours)
 OR NOT p_capability=ANY(policy.capabilities) OR NOT p_capability=ANY(original.capabilities) THEN
  RAISE EXCEPTION 'Recurring read policy denied' USING ERRCODE='42501';
 END IF;
 RETURN original;
END $$;
REVOKE ALL ON FUNCTION app_recurring.read_bound_object(text,text) FROM PUBLIC,anon,authenticated,service_role;
CREATE OR REPLACE FUNCTION public.read_shadow_market_feed_recurring_v1()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
 SET lock_timeout TO '2s'
AS $function$
DECLARE lease app_recurring.runs%ROWTYPE; digest text; result jsonb; clipped jsonb;
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Sign in required' USING ERRCODE='42501'; END IF;
    result:=jsonb_build_object('contract','app-market-preview/v1','mode','SHADOW_ONLY',
        'as_of',clock_timestamp(),'status','DISABLED','captured_at',NULL,
        'acquisition_completeness',NULL,'market_session_state','UNKNOWN','rows','[]'::jsonb);
    -- Read path intentionally does not acquire the writer lock.
    SELECT f.archive_digest INTO digest FROM app_feed.latest f JOIN app_feed.control c
        ON c.singleton AND c.enabled AND c.provider_namespace=f.provider;
    IF NOT FOUND THEN RETURN result; END IF;
    BEGIN lease:=app_recurring.read_bound_object(digest,'shadow_feed');
    EXCEPTION WHEN insufficient_privilege THEN RETURN result; END;
    result:=app_recurring.read_market_feed_impl();
    clipped:=result->'rows';
    PERFORM app_recurring.read_bound_object(digest,'shadow_feed');
    RETURN result||jsonb_build_object('rows',clipped);
END $function$
;
CREATE OR REPLACE FUNCTION public.read_shadow_application_feed_recurring_v1()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
 SET lock_timeout TO '2s'
AS $function$
DECLARE
    result jsonb; full_head app_feed.application_latest%ROWTYPE; digest text;
    lease app_recurring.runs%ROWTYPE; quote jsonb; item jsonb; output jsonb:='[]'::jsonb;
    price text; expiry timestamptz;
BEGIN
    result:=public.read_shadow_market_feed_recurring_v1();
    result:=result||jsonb_build_object('contract','app-market-preview/v3');
    IF NOT EXISTS(SELECT 1 FROM app_feed.application_control WHERE singleton AND enabled)
       OR result->>'status'<>'AVAILABLE' THEN
        RETURN result||jsonb_build_object('status','DISABLED','rows','[]'::jsonb);
    END IF;
    SELECT a.* INTO full_head FROM app_feed.application_latest a JOIN app_feed.latest f
        ON a.provider=f.provider AND a.archive_digest=f.archive_digest AND a.quote_payload_sha256=f.payload_sha256
        JOIN app_feed.control c ON c.singleton AND c.enabled AND c.provider_namespace=a.provider
        JOIN app_feed.application_control ac ON ac.singleton AND ac.enabled
            AND ac.fields_sha256=a.body->>'application_fields_sha256';
    IF NOT FOUND THEN RETURN result||jsonb_build_object('status','WAITING','rows','[]'::jsonb); END IF;
    BEGIN lease:=app_recurring.read_bound_object(full_head.archive_digest,'projections');
    EXCEPTION WHEN insufficient_privilege THEN
        RETURN result||jsonb_build_object('status','DISABLED','rows','[]'::jsonb);
    END;
    FOR quote IN SELECT value FROM jsonb_array_elements(result->'rows') LOOP
        quote:=jsonb_build_object('reference_price',NULL,'reference_conflict',false)||quote;
        price:=coalesce(quote->>'price_decimal',quote->'reference_price'->>'price_decimal');
        expiry:=least(coalesce((quote->>'expires_at')::timestamptz,
                             (quote->'reference_price'->>'expires_at')::timestamptz));
        SELECT r->'row' INTO item FROM jsonb_array_elements(full_head.body->'rows') r
            WHERE r->>'asset_key'=quote->>'asset_key';
        IF price IS NULL OR item IS NULL OR expiry<=clock_timestamp() THEN item:=NULL; END IF;
        output:=output||jsonb_build_array(quote||jsonb_build_object('application_fields',item,
            'application_expires_at',CASE WHEN item IS NOT NULL THEN expiry END));
    END LOOP;
    PERFORM app_recurring.read_bound_object(full_head.archive_digest,'projections');
    RETURN result||jsonb_build_object('rows',output);
END $function$
;
CREATE OR REPLACE FUNCTION app_recurring.reference_for_preview(item jsonb, c jsonb, now_at timestamp with time zone)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE ref jsonb:=item->'reference_price'; captured timestamptz; expiry timestamptz;
BEGIN
 IF ref IS NULL OR ref='null'::jsonb THEN RETURN NULL; END IF;
 PERFORM app_recurring.read_bound_object(c->>'archive_sha256','shadow_feed');
 captured:=(ref->>'captured_at')::timestamptz;
 expiry:=least(captured+make_interval(secs=>(c->>'capture_max_age_seconds')::integer),
    (((c->>'market_date')::date+1)::timestamp AT TIME ZONE 'Africa/Casablanca'));
 IF now_at<captured OR now_at>=expiry THEN RETURN NULL; END IF;
 RETURN jsonb_build_object('price_decimal',ref->>'price_decimal','price_basis','INSTRUMENT_REFERENCE',
  'captured_at',captured,'expires_at',expiry,'source_event_at',NULL,'reported_day',NULL,
  'reported_time_timezone','UNKNOWN','prediction_eligible',false,'portfolio_valuation_eligible',false);
END $function$
;
