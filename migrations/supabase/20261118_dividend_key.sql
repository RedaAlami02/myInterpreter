-- Align the dividend uniqueness with the writers.
--
-- 20261117_dividend_constraints.sql made (c_name, year) unique, but the
-- projection publisher (013_projection_publication.sql) keys rows on
-- (c_name, year, type): one ordinary row plus one exceptional row for the same
-- year aborted that publication. The combined-row writer keeps producing one
-- row per company and year on its own, so the three-column key is the
-- compatible guarantee.
DROP INDEX IF EXISTS public.dividends_company_year_uq;

DO $$
BEGIN
    CREATE UNIQUE INDEX IF NOT EXISTS dividends_company_year_type_uq
        ON public.dividends (c_name, year, COALESCE(type, ''));
EXCEPTION WHEN unique_violation THEN
    RAISE NOTICE 'duplicate (c_name, year, type) rows exist; index not created';
END $$;
