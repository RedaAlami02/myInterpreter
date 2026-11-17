-- Original private snapshots -> confirmed owner only. All recovery starts OFF.
-- Bindings are registered by the database owner; clients supply no owner/email.
CREATE TABLE portfolio_private.recovery_control (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    enabled boolean NOT NULL DEFAULT false
);
INSERT INTO portfolio_private.recovery_control VALUES(true,false);
CREATE TABLE portfolio_private.recovery_bindings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL UNIQUE CHECK(email=lower(btrim(email)) AND position('@' IN email)>1),
    legacy_owner text NOT NULL UNIQUE CHECK(length(legacy_owner)>0),
    source_datasets jsonb NOT NULL CHECK(jsonb_typeof(source_datasets)='array' AND jsonb_array_length(source_datasets)=4),
    source_rows jsonb NOT NULL CHECK(jsonb_typeof(source_rows)='array' AND jsonb_array_length(source_rows) BETWEEN 1 AND 10000),
    plan_sha256 text NOT NULL CHECK(plan_sha256 ~ '^[a-f0-9]{64}$'),
    enabled boolean NOT NULL DEFAULT false,
    approved_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE portfolio_private.recovery_receipts (
    binding_id uuid PRIMARY KEY REFERENCES portfolio_private.recovery_bindings(id),
    target_user uuid NOT NULL UNIQUE,
    plan_sha256 text NOT NULL,
    imported_counts jsonb NOT NULL,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE portfolio_private.recovery_provenance (
    binding_id uuid NOT NULL REFERENCES portfolio_private.recovery_bindings(id),
    dataset_id text NOT NULL,
    document_id text NOT NULL,
    collection text NOT NULL CHECK(collection IN ('achats','ventes','portefeuille','benefits')),
    target_id uuid NOT NULL,
    payload_sha256 text NOT NULL,
    original_payload jsonb NOT NULL,
    PRIMARY KEY(dataset_id,document_id),
    UNIQUE(collection,target_id)
);
DO $$ DECLARE tab text; BEGIN
    FOREACH tab IN ARRAY ARRAY['recovery_control','recovery_bindings','recovery_receipts','recovery_provenance'] LOOP
        EXECUTE format('ALTER TABLE portfolio_private.%I ENABLE ROW LEVEL SECURITY',tab);
        EXECUTE format('REVOKE ALL ON TABLE portfolio_private.%I FROM PUBLIC,anon,authenticated,service_role',tab);
    END LOOP;
END $$;

CREATE FUNCTION portfolio_private.claim_saved_portfolio()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' AS $$
DECLARE target uuid:=auth.uid(); verified_email text;
    binding portfolio_private.recovery_bindings%ROWTYPE;
    receipt portfolio_private.recovery_receipts%ROWTYPE;
    reference jsonb; dataset jsonb; payload jsonb; collection text; metadata jsonb; original_source_sha text;
    new_id uuid; pins jsonb; counts jsonb:='{"achats":0,"ventes":0,"portefeuille":0,"benefits":0}'::jsonb;
    expected integer; actual integer;
BEGIN
    IF target IS NULL OR auth.role() IS DISTINCT FROM 'authenticated' THEN
        RAISE EXCEPTION 'Authentication required' USING ERRCODE='42501';
    END IF;
    PERFORM 1 FROM portfolio_private.recovery_control WHERE singleton AND enabled FOR SHARE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('status','DISABLED');
    END IF;
    SELECT lower(email) INTO verified_email FROM auth.users
        WHERE id=target AND email_confirmed_at IS NOT NULL AND email IS NOT NULL FOR SHARE;
    IF NOT FOUND THEN RETURN jsonb_build_object('status','NOT_AVAILABLE'); END IF;
    -- Same serialization key as record_trade; claims cannot race a first trade.
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(target::text,73));
    SELECT * INTO binding FROM portfolio_private.recovery_bindings
        WHERE email=verified_email AND enabled FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('status','NOT_AVAILABLE'); END IF;
    pins:=jsonb_build_object('email',binding.email,'legacy_owner',binding.legacy_owner,
        'source_datasets',binding.source_datasets,'source_rows',binding.source_rows);
    IF encode(sha256(convert_to(pins::text,'UTF8')),'hex')<>binding.plan_sha256 THEN
        RAISE EXCEPTION 'Recovery plan differs' USING ERRCODE='22023';
    END IF;
    SELECT * INTO receipt FROM portfolio_private.recovery_receipts WHERE binding_id=binding.id;
    IF FOUND THEN
        IF receipt.target_user<>target OR receipt.plan_sha256<>binding.plan_sha256 THEN
            RAISE EXCEPTION 'Recovery already assigned or plan changed' USING ERRCODE='22023';
        END IF;
        RETURN jsonb_build_object('status','CLAIMED','counts',receipt.imported_counts);
    END IF;
    IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(CASE WHEN jsonb_typeof(auth.jwt()->'amr')='array'
        THEN auth.jwt()->'amr' ELSE '[]'::jsonb END) a
        WHERE a->>'method'='password') THEN
        RETURN jsonb_build_object('status','PASSWORD_REQUIRED');
    END IF;
    IF EXISTS(SELECT 1 FROM public.achats WHERE user_id=target)
       OR EXISTS(SELECT 1 FROM public.ventes WHERE user_id=target)
       OR EXISTS(SELECT 1 FROM public.portefeuille WHERE user_id=target)
       OR EXISTS(SELECT 1 FROM public.benefits WHERE user_id=target)
       OR EXISTS(SELECT 1 FROM portfolio_private.trade_requests WHERE user_id=target) THEN
        RETURN jsonb_build_object('status','REVIEW_REQUIRED');
    END IF;
    IF (SELECT count(DISTINCT row->>'collection') FROM jsonb_array_elements(binding.source_datasets) row)<>4
       OR (SELECT count(DISTINCT row->>'dataset_id') FROM jsonb_array_elements(binding.source_datasets) row)<>4 THEN
        RAISE EXCEPTION 'All four preserved datasets required' USING ERRCODE='22023';
    END IF;
    FOR dataset IN SELECT value FROM jsonb_array_elements(binding.source_datasets) LOOP
        SELECT source_metadata,source_sha256 INTO metadata,original_source_sha
            FROM migration_stage.datasets WHERE dataset_id=dataset->>'dataset_id' FOR SHARE;
        IF NOT FOUND OR dataset->>'collection' NOT IN ('achats','ventes','portefeuille','benefits')
            OR metadata->>'collection' IS DISTINCT FROM dataset->>'collection'
            OR original_source_sha IS DISTINCT FROM dataset->>'dataset_sha256' THEN
            RAISE EXCEPTION 'Preserved dataset pin differs' USING ERRCODE='22023';
        END IF;
    END LOOP;
    expected:=jsonb_array_length(binding.source_rows);
    SELECT count(*) INTO actual FROM migration_stage.documents d
        WHERE d.dataset_id IN (SELECT row->>'dataset_id' FROM jsonb_array_elements(binding.source_datasets) row)
          AND d.payload->>'user_id'=binding.legacy_owner;
    IF expected<>actual THEN RAISE EXCEPTION 'Incomplete saved portfolio plan' USING ERRCODE='22023'; END IF;
    IF pg_database_size(current_database())+1048576+expected*8192+
       (SELECT coalesce(sum(pg_column_size(d.payload)),0) FROM migration_stage.documents d
        WHERE d.dataset_id IN (SELECT row->>'dataset_id' FROM jsonb_array_elements(binding.source_datasets) row)
          AND d.payload->>'user_id'=binding.legacy_owner)>350000000 THEN
        RAISE EXCEPTION 'Recovery capacity guard reached' USING ERRCODE='54000';
    END IF;
    FOR reference IN SELECT value FROM jsonb_array_elements(binding.source_rows) LOOP
        SELECT d.payload,s.source_metadata,s.source_sha256 INTO payload,metadata,original_source_sha
            FROM migration_stage.documents d JOIN migration_stage.datasets s USING(dataset_id)
            WHERE d.dataset_id=reference->>'dataset_id' AND d.document_id=reference->>'document_id' FOR SHARE OF d,s;
        collection:=reference->>'collection';
        IF NOT FOUND OR collection NOT IN ('achats','ventes','portefeuille','benefits')
           OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(binding.source_datasets) d
                WHERE d->>'dataset_id'=reference->>'dataset_id' AND d->>'collection'=collection
                  AND d->>'dataset_sha256'=reference->>'dataset_sha256')
           OR metadata->>'collection' IS DISTINCT FROM collection
           OR payload->>'$collectionId' IS DISTINCT FROM collection
           OR payload->>'user_id' IS DISTINCT FROM binding.legacy_owner
           OR original_source_sha IS DISTINCT FROM reference->>'dataset_sha256'
           OR encode(sha256(convert_to(payload::text,'UTF8')),'hex') IS DISTINCT FROM reference->>'payload_sha256' THEN
            RAISE EXCEPTION 'Saved portfolio source differs' USING ERRCODE='22023';
        END IF;
        new_id:=substr(encode(sha256(convert_to(jsonb_build_array(reference->>'dataset_id',reference->>'document_id')::text,'UTF8')),'hex'),1,32)::uuid;
        IF collection IN ('achats','ventes','benefits') AND (
            payload->>'date' IS NULL OR payload->>'date' !~ '^\d{4}-\d{2}-\d{2}T.*(Z|[+-]\d{2}:\d{2})$'
            OR NOT isfinite((payload->>'date')::timestamptz)) THEN
            RAISE EXCEPTION 'Original aware timestamp required' USING ERRCODE='22023';
        END IF;
        IF collection='achats' THEN
            INSERT INTO public.achats VALUES(new_id,target,payload->>'c_name',(payload->>'number')::numeric,(payload->>'prix_achat')::numeric,(payload->>'date')::timestamptz);
        ELSIF collection='ventes' THEN
            INSERT INTO public.ventes VALUES(new_id,target,payload->>'c_name',(payload->>'number')::numeric,(payload->>'prix_vente')::numeric,(payload->>'date')::timestamptz);
        ELSIF collection='portefeuille' THEN
            INSERT INTO public.portefeuille VALUES(new_id,target,payload->>'c_name',(payload->>'quantity')::numeric,(payload->>'total_cost')::numeric);
        ELSE
            INSERT INTO public.benefits VALUES(new_id,target,substr(payload->>'date',1,10)::date,(payload->>'value')::numeric);
        END IF;
        INSERT INTO portfolio_private.recovery_provenance VALUES(binding.id,reference->>'dataset_id',reference->>'document_id',collection,new_id,reference->>'payload_sha256',payload);
        counts:=jsonb_set(counts,ARRAY[collection],to_jsonb((counts->>collection)::integer+1));
    END LOOP;
    INSERT INTO portfolio_private.recovery_receipts(binding_id,target_user,plan_sha256,imported_counts)
        VALUES(binding.id,target,binding.plan_sha256,counts);
    RETURN jsonb_build_object('status','CLAIMED','counts',counts);
END $$;
REVOKE ALL ON FUNCTION portfolio_private.claim_saved_portfolio() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION portfolio_private.claim_saved_portfolio() TO authenticated;
CREATE FUNCTION public.claim_saved_portfolio()
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
    SELECT portfolio_private.claim_saved_portfolio();
$$;
REVOKE ALL ON FUNCTION public.claim_saved_portfolio() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.claim_saved_portfolio() TO authenticated;
