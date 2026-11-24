-- latest_prices holds company quotes only; the index moved to public.data and
-- the app feed reads it there. Two rows had no company: a MASI row frozen at
-- 2026-10-21 and a row named 'test'. The app's after-hours fallback list read
-- them as recorded prices, so a month-old index value could appear as current.
--
-- Re-runnable; deletes nothing while every row still maps to a company.

DELETE FROM public.latest_prices p
 WHERE NOT EXISTS (SELECT 1 FROM public.company c WHERE c.name = p.c_name);
