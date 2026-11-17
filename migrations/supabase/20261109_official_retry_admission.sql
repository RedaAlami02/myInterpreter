-- Admission permits an attempt; final archive reservation checks actual bytes.
-- Preserve all daily limits, timing, ownership, capacity and financial safeguards.
DO $$
DECLARE definition text;
BEGIN
 SELECT pg_get_functiondef('public.market_archive_acquisition_admission_recurring_v1(text,text,timestamptz,boolean,boolean)'::regprocedure) INTO definition;
 IF encode(sha256(convert_to(definition,'UTF8')),'hex') <> 'd814a90f9de141d59d3fb6dc3b29de549971a0a4ee79ffc81a71478174c16738' THEN
  RAISE EXCEPTION 'Unexpected admission definition; review before applying';
 END IF;
 EXECUTE replace(definition,'app_recurring.check_new_object(p_provider,p_kind,p_slot,clock_timestamp(),8388608)','app_recurring.check_new_object(p_provider,p_kind,p_slot,clock_timestamp(),CASE WHEN EXISTS (SELECT 1 FROM app_recurring.policies WHERE provider=p_provider AND acquisition_window=''OFFICIAL_CLOSE'') THEN 1 ELSE 8388608 END)');
END $$;
