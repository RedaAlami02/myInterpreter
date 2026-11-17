-- Owner-confirmed economic dates are metadata; original entry timestamps stay intact.
ALTER TABLE public.achats ADD COLUMN purchase_day date;
ALTER TABLE public.achats ADD COLUMN purchase_day_basis text;
ALTER TABLE public.achats ADD CONSTRAINT achats_purchase_day_basis_check CHECK (
    (purchase_day IS NULL AND purchase_day_basis IS NULL) OR
    (purchase_day IS NOT NULL AND purchase_day_basis IS NOT NULL AND purchase_day_basis='USER_CONFIRMED'));
COMMENT ON COLUMN public.achats.purchase_day IS 'User-confirmed date only; execution clock unknown. date remains the original recorded timestamp.';
CREATE TABLE portfolio_private.purchase_day_annotations (
    trade_id uuid PRIMARY KEY REFERENCES public.achats(id) ON DELETE RESTRICT,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    purchase_day date NOT NULL,
    assertion_basis text NOT NULL CHECK(assertion_basis='OWNER_CONFIRMED_SESSION'),
    execution_time_status text NOT NULL DEFAULT 'UNKNOWN' CHECK(execution_time_status='UNKNOWN'),
    original_record jsonb NOT NULL,
    annotated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE portfolio_private.purchase_day_annotations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE portfolio_private.purchase_day_annotations FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION portfolio_private.annotate_purchase_day(p_user uuid,p_trade uuid,p_day date)
RETURNS text LANGUAGE plpgsql SET search_path='' AS $$
DECLARE original public.achats%ROWTYPE; previous portfolio_private.purchase_day_annotations%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_user::text,73));
    SELECT * INTO original FROM public.achats WHERE id=p_trade AND user_id=p_user FOR UPDATE;
    IF NOT FOUND OR p_day IS NULL OR p_day<'1900-01-01'::date
       OR p_day>(original.date AT TIME ZONE 'Africa/Casablanca')::date THEN
        RAISE EXCEPTION 'Invalid confirmed purchase day' USING ERRCODE='22023';
    END IF;
    IF EXISTS(SELECT 1 FROM portfolio_private.recovery_provenance WHERE collection='achats' AND target_id=p_trade)
       OR NOT EXISTS(SELECT 1 FROM portfolio_private.trade_requests WHERE user_id=p_user AND request_id=p_trade
            AND side='buy' AND c_name=original.c_name AND quantity=original.number AND price=original.prix_achat) THEN
        RAISE EXCEPTION 'Only the exact newly entered purchase may be annotated' USING ERRCODE='22023';
    END IF;
    SELECT * INTO previous FROM portfolio_private.purchase_day_annotations WHERE trade_id=p_trade;
    IF FOUND THEN
        IF previous.user_id<>p_user OR previous.purchase_day<>p_day
           OR original.purchase_day IS DISTINCT FROM p_day OR original.purchase_day_basis IS DISTINCT FROM 'USER_CONFIRMED' THEN
            RAISE EXCEPTION 'Confirmed day already differs' USING ERRCODE='22023';
        END IF;
        RETURN 'EXISTING';
    END IF;
    INSERT INTO portfolio_private.purchase_day_annotations(trade_id,user_id,purchase_day,assertion_basis,original_record)
        VALUES(p_trade,p_user,p_day,'OWNER_CONFIRMED_SESSION',to_jsonb(original));
    UPDATE public.achats SET purchase_day=p_day,purchase_day_basis='USER_CONFIRMED' WHERE id=p_trade AND user_id=p_user;
    RETURN 'ANNOTATED';
END $$;
REVOKE ALL ON FUNCTION portfolio_private.annotate_purchase_day(uuid,uuid,date) FROM PUBLIC,anon,authenticated,service_role;
