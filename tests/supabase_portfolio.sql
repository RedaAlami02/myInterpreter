-- Executed only inside a transaction that tools/check_supabase_portfolio.py
-- unconditionally rolls back. Synthetic users have no email/password/session.
INSERT INTO auth.users(id) VALUES
    ('d75b3ae7-c67c-4cd9-b56b-bb28119b29a1'),
    ('d75b3ae7-c67c-4cd9-b56b-bb28119b29a2');
INSERT INTO public.company(id,name) VALUES ('portfolio-test-company','PORTFOLIO TEST COMPANY');
SELECT set_config('request.jwt.claims','{"sub":"d75b3ae7-c67c-4cd9-b56b-bb28119b29a1","role":"authenticated"}',true);
SET LOCAL ROLE authenticated;
SELECT public.record_trade('a0000000-0000-4000-8000-000000000001','buy','PORTFOLIO TEST COMPANY',10,100);
SELECT public.record_trade('a0000000-0000-4000-8000-000000000002','buy','PORTFOLIO TEST COMPANY',10,200);
SELECT public.record_trade('a0000000-0000-4000-8000-000000000002','buy','PORTFOLIO TEST COMPANY',10,200);
DO $$ BEGIN
    IF (SELECT count(*) FROM public.achats) <> 2
       OR NOT EXISTS (SELECT 1 FROM public.portefeuille WHERE quantity=20 AND total_cost=3000) THEN
        RAISE EXCEPTION 'Buy or retry mismatch';
    END IF;
    -- Fail after the trade INSERT, during the holding upsert. Both must roll
    -- back, including the retry journal, rather than leaving a phantom buy.
    BEGIN
        PERFORM public.record_trade('a0000000-0000-4000-8000-000000000009','buy','PORTFOLIO TEST COMPANY',1000000000000,1);
        RAISE EXCEPTION 'Holding limit exceeded';
    EXCEPTION WHEN check_violation THEN NULL; END;
    IF (SELECT count(*) FROM public.achats) <> 2
       OR NOT EXISTS (SELECT 1 FROM public.portefeuille WHERE quantity=20 AND total_cost=3000) THEN
        RAISE EXCEPTION 'Partial write survived failed trade';
    END IF;
END $$;
SELECT public.record_trade('a0000000-0000-4000-8000-000000000003','sell','PORTFOLIO TEST COMPANY',5,250);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.portefeuille WHERE quantity=15 AND total_cost=2250)
       OR (SELECT count(*) FROM public.ventes) <> 1 THEN
        RAISE EXCEPTION 'Partial sale average-cost mismatch';
    END IF;
    BEGIN
        PERFORM public.record_trade('a0000000-0000-4000-8000-000000000004','sell','PORTFOLIO TEST COMPANY',16,250);
        RAISE EXCEPTION 'Oversell accepted';
    EXCEPTION WHEN invalid_parameter_value THEN NULL; END;
    BEGIN
        PERFORM public.record_trade('a0000000-0000-4000-8000-000000000002','buy','PORTFOLIO TEST COMPANY',11,200);
        RAISE EXCEPTION 'Changed retry accepted';
    EXCEPTION WHEN invalid_parameter_value THEN NULL; END;
    BEGIN
        PERFORM public.record_trade('a0000000-0000-4000-8000-000000000005','buy','PORTFOLIO TEST COMPANY','NaN',200);
        RAISE EXCEPTION 'NaN accepted';
    EXCEPTION WHEN invalid_parameter_value THEN NULL; END;
    BEGIN
        PERFORM public.record_trade('a0000000-0000-4000-8000-000000000005','buy','PORTFOLIO TEST COMPANY',1,'Infinity');
        RAISE EXCEPTION 'Infinity accepted';
    EXCEPTION WHEN invalid_parameter_value THEN NULL; END;
    BEGIN
        PERFORM public.record_trade('a0000000-0000-4000-8000-000000000005','buy','UNKNOWN TEST COMPANY',1,200);
        RAISE EXCEPTION 'Unknown company accepted';
    EXCEPTION WHEN invalid_parameter_value THEN NULL; END;
    IF (SELECT count(*) FROM public.ventes) <> 1 OR
       NOT EXISTS (SELECT 1 FROM public.portefeuille WHERE quantity=15 AND total_cost=2250) THEN
        RAISE EXCEPTION 'Failed trade changed history or holdings';
    END IF;
END $$;
-- User B cannot see A, even by explicit ID or owner filter. B gets independent holdings.
SELECT set_config('request.jwt.claims','{"sub":"d75b3ae7-c67c-4cd9-b56b-bb28119b29a2","role":"authenticated"}',true);
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM public.achats) OR EXISTS (SELECT 1 FROM public.ventes)
       OR EXISTS (SELECT 1 FROM public.portefeuille) OR EXISTS (SELECT 1 FROM public.benefits) THEN
        RAISE EXCEPTION 'Cross-owner read allowed';
    END IF;
END $$;
SELECT public.record_trade('b0000000-0000-4000-8000-000000000001','buy','PORTFOLIO TEST COMPANY',0.5,80);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.portefeuille WHERE quantity=0.5 AND total_cost=40)
       OR (SELECT count(*) FROM public.portefeuille) <> 1 THEN
        RAISE EXCEPTION 'Independent fractional holding mismatch';
    END IF;
END $$;
-- No owner can edit user_id, manufacture holdings, erase trades or alter snapshots.
DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['achats','ventes','portefeuille','benefits'] LOOP
        BEGIN
            EXECUTE format('UPDATE public.%I SET user_id=%L',tab,'d75b3ae7-c67c-4cd9-b56b-bb28119b29a1');
            RAISE EXCEPTION 'Owner reassignment allowed';
        EXCEPTION WHEN insufficient_privilege THEN NULL; END;
        BEGIN
            EXECUTE format('DELETE FROM public.%I',tab);
            RAISE EXCEPTION 'Direct delete allowed';
        EXCEPTION WHEN insufficient_privilege THEN NULL; END;
        IF has_table_privilege(current_user,'public.' || tab,'INSERT,UPDATE,DELETE,TRUNCATE') THEN
            RAISE EXCEPTION 'Unexpected direct write grant';
        END IF;
    END LOOP;
    BEGIN
        PERFORM 1 FROM portfolio_private.trade_requests;
        RAISE EXCEPTION 'Private request journal readable';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
SELECT set_config('request.jwt.claims','{"sub":"d75b3ae7-c67c-4cd9-b56b-bb28119b29a1","role":"authenticated"}',true);
SELECT public.record_trade('a0000000-0000-4000-8000-000000000006','sell','PORTFOLIO TEST COMPANY',15,250);
SELECT public.record_trade('a0000000-0000-4000-8000-000000000006','sell','PORTFOLIO TEST COMPANY',15,250);
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM public.portefeuille) OR (SELECT count(*) FROM public.ventes) <> 2 THEN
        RAISE EXCEPTION 'Full sale or retry mismatch';
    END IF;
END $$;
RESET ROLE;
INSERT INTO public.benefits(user_id,date,value) VALUES ('d75b3ae7-c67c-4cd9-b56b-bb28119b29a1','2026-10-24',-17.50);
SET LOCAL ROLE authenticated;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.benefits WHERE value=-17.50) THEN
        RAISE EXCEPTION 'Owner snapshot missing';
    END IF;
END $$;
SELECT set_config('request.jwt.claims','{"sub":"d75b3ae7-c67c-4cd9-b56b-bb28119b29a2","role":"authenticated"}',true);
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM public.benefits) THEN RAISE EXCEPTION 'Snapshot owner leak'; END IF;
END $$;
RESET ROLE;
SELECT set_config('request.jwt.claims','{}',true);
SET LOCAL ROLE anon;
DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['achats','ventes','portefeuille','benefits'] LOOP
        BEGIN
            EXECUTE format('SELECT 1 FROM public.%I',tab);
            RAISE EXCEPTION 'Anonymous private read allowed';
        EXCEPTION WHEN insufficient_privilege THEN NULL; END;
    END LOOP;
    BEGIN
        PERFORM public.record_trade('c0000000-0000-4000-8000-000000000001','buy','PORTFOLIO TEST COMPANY',1,1);
        RAISE EXCEPTION 'Anonymous trade allowed';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
RESET ROLE;
-- A role label without a signed user identity is also insufficient.
SET LOCAL ROLE authenticated;
DO $$ BEGIN
    BEGIN
        PERFORM public.record_trade('c0000000-0000-4000-8000-000000000001','buy','PORTFOLIO TEST COMPANY',1,1);
        RAISE EXCEPTION 'Missing user identity accepted';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
RESET ROLE;
