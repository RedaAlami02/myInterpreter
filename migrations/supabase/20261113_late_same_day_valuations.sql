-- Same-day verified close, actual execution-time holdings; no historical backdating.
CREATE OR REPLACE FUNCTION portfolio_private.record_official_valuation(p_owner uuid, p_now timestamp with time zone)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
 SET lock_timeout TO '2s'
AS $function$
DECLARE local_now timestamp; valuation_day date; ctl portfolio_private.official_close_control%ROWTYPE;
    batch portfolio_private.official_close_batches%ROWTYPE; positions jsonb;
    holding jsonb; price jsonb; consumed jsonb:='[]'::jsonb; total numeric:=0;
    saved numeric; snapshot_value numeric; legacy boolean; inserted integer;
BEGIN
    IF current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION 'Read committed isolation required for execution-time holdings' USING ERRCODE='22023';
    END IF;
    IF p_owner IS NULL OR p_now IS NULL OR NOT isfinite(p_now) THEN RAISE EXCEPTION 'Invalid valuation request' USING ERRCODE='22023'; END IF;
    IF abs(extract(epoch FROM (clock_timestamp()-p_now)))>60 THEN
        RAISE EXCEPTION 'Execution-time valuation cannot be backdated' USING ERRCODE='22023';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_owner::text,73));
    local_now:=p_now AT TIME ZONE 'Africa/Casablanca';valuation_day:=local_now::date;
    SELECT b.value INTO saved FROM public.benefits b WHERE b.user_id=p_owner AND b.date=valuation_day;
    IF FOUND THEN
        SELECT NOT EXISTS(SELECT 1 FROM portfolio_private.official_valuation_receipts WHERE user_id=p_owner AND official_valuation_receipts.day=valuation_day) INTO legacy;
        RETURN jsonb_build_object('status','EXISTING','date',valuation_day,'value',saved,
            'basis',CASE WHEN legacy THEN 'PREEXISTING_UNVERIFIED' ELSE 'OFFICIAL_CLOSE_HOLDINGS_AT_EXECUTION' END);
    END IF;
    SELECT * INTO ctl FROM portfolio_private.official_close_control WHERE singleton FOR SHARE;
    IF NOT FOUND OR NOT ctl.enabled THEN RETURN jsonb_build_object('status','DISABLED','date',valuation_day); END IF;
    IF extract(isodow FROM local_now)>5 OR local_now::time<time '17:00' THEN
        RETURN jsonb_build_object('status','OUTSIDE_WINDOW','date',valuation_day);
    END IF;
    -- A caller cannot bypass pending saved-account recovery through this RPC.
    IF EXISTS(SELECT 1 FROM auth.users u JOIN portfolio_private.recovery_bindings b ON b.email=lower(btrim(u.email))
        WHERE u.id=p_owner AND NOT EXISTS(SELECT 1 FROM portfolio_private.recovery_receipts r WHERE r.binding_id=b.id AND r.target_user=p_owner)) THEN
        RETURN jsonb_build_object('status','RECOVERY_REQUIRED','date',valuation_day);
    END IF;
    SELECT * INTO batch FROM portfolio_private.official_close_batches WHERE sha256=ctl.active_batch_sha256 FOR SHARE;
    IF NOT FOUND OR batch.session_day<>valuation_day OR batch.provider_namespace IS DISTINCT FROM ctl.provider_namespace
       OR batch.source_policy_sha256 IS DISTINCT FROM ctl.source_policy_sha256
       OR batch.reviewed_at>p_now
       OR (batch.document->>'captured_at')::timestamptz>p_now
       OR (batch.document->>'published_at')::timestamptz>p_now
       OR NOT EXISTS(SELECT 1 FROM app_archive.objects a WHERE a.digest=batch.archive_digest
           AND a.state='STORED' AND a.provider=batch.provider_namespace AND a.kind='quotes'
           AND a.completed_at<=p_now) THEN
        RETURN jsonb_build_object('status','PRICE_UNAVAILABLE','date',valuation_day);
    END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',h.id,'c_name',h.c_name,'quantity',h.quantity,'total_cost',h.total_cost) ORDER BY h.c_name,h.id),'[]'::jsonb)
        INTO positions FROM public.portefeuille h WHERE h.user_id=p_owner;
    IF jsonb_array_length(positions)>500 THEN RAISE EXCEPTION 'Too many holdings' USING ERRCODE='54000'; END IF;
    IF positions='[]'::jsonb AND NOT EXISTS(SELECT 1 FROM public.benefits WHERE user_id=p_owner) THEN
        RETURN jsonb_build_object('status','EMPTY','date',valuation_day);
    END IF;
    FOR holding IN SELECT value FROM jsonb_array_elements(positions) LOOP
        SELECT value INTO price FROM jsonb_array_elements(batch.document->'rows')
            WHERE value->>'c_name'=holding->>'c_name';
        IF NOT FOUND OR (SELECT count(*) FROM public.company WHERE id=price->>'company_id' AND name=holding->>'c_name')<>1
           OR (SELECT count(*) FROM public.format WHERE name=holding->>'c_name')<>1
           OR (SELECT count(*) FROM public.format WHERE name=holding->>'c_name' AND symbol=price->>'symbol')<>1 THEN
            RETURN jsonb_build_object('status','PRICE_UNAVAILABLE','date',valuation_day);
        END IF;
        IF holding->>'quantity' IN ('NaN','Infinity','-Infinity') OR holding->>'total_cost' IN ('NaN','Infinity','-Infinity')
           OR (holding->>'quantity')::numeric<=0 OR (holding->>'total_cost')::numeric<0 THEN
            RAISE EXCEPTION 'Invalid holding' USING ERRCODE='22023';
        END IF;
        total:=total+(holding->>'quantity')::numeric*(price->>'price_decimal')::numeric-(holding->>'total_cost')::numeric;
        consumed:=consumed||jsonb_build_array(price);
    END LOOP;
    snapshot_value:=round(total,2);
    IF pg_database_size(current_database())+octet_length(positions::text)+octet_length(consumed::text)+1048576>ctl.max_database_bytes THEN
        RAISE EXCEPTION 'Database capacity guard reached' USING ERRCODE='54000';
    END IF;
    INSERT INTO public.benefits(user_id,date,value) VALUES(p_owner,valuation_day,snapshot_value) ON CONFLICT(user_id,date) DO NOTHING;
    GET DIAGNOSTICS inserted=ROW_COUNT;
    IF inserted<>1 THEN RAISE EXCEPTION 'Concurrent valuation requires retry' USING ERRCODE='40001'; END IF;
    INSERT INTO portfolio_private.official_valuation_receipts(user_id,day,batch_sha256,holdings,consumed_prices,value)
        VALUES(p_owner,valuation_day,batch.sha256,positions,consumed,snapshot_value);
    RETURN jsonb_build_object('status','CREATED','date',valuation_day,'value',snapshot_value,'basis','OFFICIAL_CLOSE_HOLDINGS_AT_EXECUTION');
END $function$
;
