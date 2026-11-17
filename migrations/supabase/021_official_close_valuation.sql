-- STAGED ONLY. Official-close requirement; replaces neither source history nor v2.
-- SQL012 is not a dependency. No source policy, batch, user or schedule is seeded.
CREATE TABLE portfolio_private.official_close_control (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    enabled boolean NOT NULL DEFAULT false,
    provider_namespace text CHECK(provider_namespace ~ '^feed_[a-f0-9]{16}$'),
    source_policy_sha256 text CHECK(source_policy_sha256 ~ '^[a-f0-9]{64}$'),
    active_batch_sha256 text CHECK(active_batch_sha256 ~ '^[a-f0-9]{64}$'),
    max_database_bytes bigint NOT NULL DEFAULT 350000000 CHECK(max_database_bytes BETWEEN 1 AND 350000000),
    CHECK(NOT enabled OR(provider_namespace IS NOT NULL AND source_policy_sha256 IS NOT NULL AND active_batch_sha256 IS NOT NULL))
);
INSERT INTO portfolio_private.official_close_control(singleton) VALUES(true);
CREATE TABLE portfolio_private.official_close_batches (
    sha256 text PRIMARY KEY CHECK(sha256 ~ '^[a-f0-9]{64}$'),
    archive_digest text NOT NULL REFERENCES app_archive.objects(digest),
    provider_namespace text NOT NULL,
    source_policy_sha256 text NOT NULL,
    session_day date NOT NULL,
    document jsonb NOT NULL,
    reviewed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    reviewed_by text NOT NULL DEFAULT current_user
);
ALTER TABLE portfolio_private.official_close_control ADD FOREIGN KEY(active_batch_sha256)
    REFERENCES portfolio_private.official_close_batches(sha256);
CREATE TABLE portfolio_private.official_valuation_receipts (
    user_id uuid NOT NULL REFERENCES auth.users(id),
    day date NOT NULL,
    batch_sha256 text NOT NULL REFERENCES portfolio_private.official_close_batches(sha256),
    holdings jsonb NOT NULL,
    consumed_prices jsonb NOT NULL,
    value numeric NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    holdings_basis text NOT NULL DEFAULT 'AT_EXECUTION' CHECK(holdings_basis='AT_EXECUTION'),
    PRIMARY KEY(user_id,day)
);
DO $$ DECLARE tab text; BEGIN
    FOREACH tab IN ARRAY ARRAY['official_close_control','official_close_batches','official_valuation_receipts'] LOOP
        EXECUTE format('ALTER TABLE portfolio_private.%I ENABLE ROW LEVEL SECURITY',tab);
        EXECUTE format('REVOKE ALL ON TABLE portfolio_private.%I FROM PUBLIC,anon,authenticated,service_role',tab);
    END LOOP;
END $$;

-- Database-owner maintenance only. Approval is a reviewed source-policy pin,
-- not a caller-supplied claim of authority. Raw-value/source-policy verification
-- must precede owner approval; SQL independently checks metadata and row shape.
CREATE FUNCTION portfolio_private.register_reviewed_official_closes(p_document text,p_sha256 text)
RETURNS text LANGUAGE plpgsql SET search_path='' SET lock_timeout='2s' AS $$
DECLARE doc jsonb; ctl portfolio_private.official_close_control%ROWTYPE;
    archive app_archive.objects%ROWTYPE; item jsonb; captured timestamptz;
    closed_at timestamptz; published_at timestamptz; day date;
    names text[]:=ARRAY[]::text[]; ids text[]:=ARRAY[]::text[]; symbols text[]:=ARRAY[]::text[];
    observations text[]:=ARRAY[]::text[];
    amount numeric; old jsonb;
BEGIN
    IF p_document IS NULL OR octet_length(p_document)>524288 OR p_sha256 IS NULL
       OR p_sha256 !~ '^[a-f0-9]{64}$' OR encode(sha256(convert_to(p_document,'UTF8')),'hex')<>p_sha256 THEN
        RAISE EXCEPTION 'Invalid official-close document' USING ERRCODE='22023';
    END IF;
    doc:=p_document::jsonb;
    SELECT * INTO ctl FROM portfolio_private.official_close_control WHERE singleton FOR SHARE;
    IF NOT FOUND OR ctl.provider_namespace IS NULL OR ctl.source_policy_sha256 IS NULL
       OR doc->>'contract' IS DISTINCT FROM 'reviewed-official-closes/v1'
       OR doc->>'price_basis' IS DISTINCT FROM 'OFFICIAL_CLOSE'
       OR doc->>'source_execution' IS DISTINCT FROM 'CURRENT_ACQUISITION'
       OR doc->>'provider_namespace' IS DISTINCT FROM ctl.provider_namespace
       OR doc->>'source_policy_sha256' IS DISTINCT FROM ctl.source_policy_sha256
       OR doc->'is_trading_session' IS DISTINCT FROM 'true'::jsonb
       OR NOT (doc ?& ARRAY['contract','price_basis','source_execution','provider_namespace','source_policy_sha256',
           'archive_sha256','is_trading_session','session_day','captured_at','session_close_at','published_at','rows'])
       OR doc-ARRAY['contract','price_basis','source_execution','provider_namespace','source_policy_sha256',
           'archive_sha256','is_trading_session','session_day','captured_at','session_close_at','published_at','rows']<>'{}'::jsonb
       OR jsonb_typeof(doc->'rows') IS DISTINCT FROM 'array'
       OR jsonb_array_length(doc->'rows') NOT BETWEEN 1 AND 1000
       OR coalesce(doc->>'session_day','') !~ '^\d{4}-\d{2}-\d{2}$' THEN
        RAISE EXCEPTION 'Reviewed official-close policy required' USING ERRCODE='42501';
    END IF;
    FOREACH item IN ARRAY ARRAY[doc->'captured_at',doc->'session_close_at',doc->'published_at'] LOOP
        -- An official daily report may omit exact close/publication clocks.
        -- Keep those unknown; captured_at remains mandatory and actual.
        CONTINUE WHEN item='null'::jsonb;
        IF jsonb_typeof(item) IS DISTINCT FROM 'string' OR (item#>>'{}') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
            RAISE EXCEPTION 'Aware source timestamps required' USING ERRCODE='22023';
        END IF;
    END LOOP;
    captured:=(doc->>'captured_at')::timestamptz;
    closed_at:=(doc->>'session_close_at')::timestamptz;
    published_at:=(doc->>'published_at')::timestamptz;
    day:=(doc->>'session_day')::date;
    IF captured IS NULL OR NOT isfinite(captured)
       OR (captured AT TIME ZONE 'Africa/Casablanca')::date<>day
       OR extract(isodow FROM day)>5
       OR (closed_at IS NOT NULL AND (NOT isfinite(closed_at) OR (closed_at AT TIME ZONE 'Africa/Casablanca')::date<>day OR closed_at>captured))
       OR (published_at IS NOT NULL AND (NOT isfinite(published_at) OR published_at>captured
            OR (published_at AT TIME ZONE 'Africa/Casablanca')::date<>day
            OR (closed_at IS NOT NULL AND closed_at>published_at)))
       OR captured>clock_timestamp() THEN
        RAISE EXCEPTION 'Official session chronology differs' USING ERRCODE='22023';
    END IF;
    SELECT * INTO archive FROM app_archive.objects WHERE digest=doc->>'archive_sha256' FOR SHARE;
    IF NOT FOUND OR archive.state<>'STORED' OR archive.kind<>'quotes'
       OR archive.provider IS DISTINCT FROM ctl.provider_namespace
       OR captured<archive.slot OR captured>archive.completed_at OR archive.completed_at>clock_timestamp() THEN
        RAISE EXCEPTION 'Original stored official-close archive required' USING ERRCODE='22023';
    END IF;
    SELECT document INTO old FROM portfolio_private.official_close_batches WHERE sha256=p_sha256;
    IF FOUND THEN
        IF old IS DISTINCT FROM doc THEN RAISE EXCEPTION 'Official-close receipt differs' USING ERRCODE='22023'; END IF;
        RETURN p_sha256;
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(doc->'rows') LOOP
        IF NOT(item ?& ARRAY['company_id','c_name','symbol','price_decimal','observation_id','raw_sha256'])
           OR item-ARRAY['company_id','c_name','symbol','price_decimal','observation_id','raw_sha256']<>'{}'::jsonb
           OR jsonb_typeof(item->'price_decimal') IS DISTINCT FROM 'string'
           OR (item->>'price_decimal') !~ '^[0-9]{1,13}(\.[0-9]{1,8})?$'
           OR coalesce(item->>'observation_id','') !~ '^[a-f0-9]{64}$'
           OR coalesce(item->>'raw_sha256','') !~ '^[a-f0-9]{64}$'
           OR item->>'observation_id'=ANY(observations)
           OR item->>'company_id'=ANY(ids) OR item->>'c_name'=ANY(names) OR item->>'symbol'=ANY(symbols)
           OR (SELECT count(*) FROM public.company c WHERE c.id=item->>'company_id' AND c.name=item->>'c_name')<>1
           OR (SELECT count(*) FROM public.company c WHERE c.name=item->>'c_name')<>1
           OR (SELECT count(*) FROM public.format f WHERE f.name=item->>'c_name' AND f.symbol=item->>'symbol')<>1
           OR (SELECT count(*) FROM public.format f WHERE f.name=item->>'c_name')<>1
           OR (SELECT count(*) FROM public.format f WHERE f.symbol=item->>'symbol')<>1 THEN
            RAISE EXCEPTION 'Invalid official-close row or identity' USING ERRCODE='22023';
        END IF;
        amount:=(item->>'price_decimal')::numeric;
        IF amount<=0 OR amount>1000000000000 THEN RAISE EXCEPTION 'Invalid official closing price' USING ERRCODE='22023'; END IF;
        names:=array_append(names,item->>'c_name');ids:=array_append(ids,item->>'company_id');symbols:=array_append(symbols,item->>'symbol');
        observations:=array_append(observations,item->>'observation_id');
    END LOOP;
    IF pg_database_size(current_database())+octet_length(p_document)+1048576>ctl.max_database_bytes THEN
        RAISE EXCEPTION 'Database capacity guard reached' USING ERRCODE='54000';
    END IF;
    INSERT INTO portfolio_private.official_close_batches(sha256,archive_digest,provider_namespace,source_policy_sha256,session_day,document)
        VALUES(p_sha256,archive.digest,ctl.provider_namespace,ctl.source_policy_sha256,day,doc);
    RETURN p_sha256;
END $$;
REVOKE ALL ON FUNCTION portfolio_private.register_reviewed_official_closes(text,text) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION portfolio_private.record_official_valuation(p_owner uuid,p_now timestamptz)
RETURNS jsonb LANGUAGE plpgsql SET search_path='' SET lock_timeout='2s' AS $$
DECLARE local_now timestamp; valuation_day date; ctl portfolio_private.official_close_control%ROWTYPE;
    batch portfolio_private.official_close_batches%ROWTYPE; positions jsonb;
    holding jsonb; price jsonb; consumed jsonb:='[]'::jsonb; total numeric:=0;
    saved numeric; snapshot_value numeric; legacy boolean; inserted integer;
BEGIN
    IF current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION 'Read committed isolation required for execution-time holdings' USING ERRCODE='22023';
    END IF;
    IF p_owner IS NULL OR p_now IS NULL OR NOT isfinite(p_now) THEN RAISE EXCEPTION 'Invalid valuation request' USING ERRCODE='22023'; END IF;
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
    IF extract(isodow FROM local_now)>5 OR local_now::time<time '17:00' OR local_now::time>=time '19:00' THEN
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
END $$;
REVOKE ALL ON FUNCTION portfolio_private.record_official_valuation(uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION public.record_official_close_valuation() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
BEGIN
    IF auth.uid() IS NULL OR auth.role() IS DISTINCT FROM 'authenticated' THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE='42501';
    END IF;
    RETURN portfolio_private.record_official_valuation(auth.uid(),clock_timestamp());
END $$;
REVOKE ALL ON FUNCTION public.record_official_close_valuation() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.record_official_close_valuation() TO authenticated;
COMMENT ON FUNCTION public.record_official_close_valuation() IS 'myInterpreter valuation v3; official close only; default disabled';

-- Legacy callers also become strict; the new client uses the distinct endpoint
-- so an older deployed v2 server cannot accidentally accept an intraday write.
CREATE OR REPLACE FUNCTION public.record_daily_valuation() RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
    SELECT public.record_official_close_valuation()
$$;
REVOKE ALL ON FUNCTION public.record_daily_valuation() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.record_daily_valuation() TO authenticated;
COMMENT ON FUNCTION public.record_daily_valuation() IS 'myInterpreter valuation v3; official close only; default disabled';
