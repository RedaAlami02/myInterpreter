-- Guards that would have caught the fabricated 2027 rows.
CREATE UNIQUE INDEX IF NOT EXISTS dividends_company_year_uq
    ON public.dividends (c_name, year);

ALTER TABLE public.dividends DROP CONSTRAINT IF EXISTS dividends_payment_year_check;
ALTER TABLE public.dividends ADD CONSTRAINT dividends_payment_year_check
    CHECK (pay_date IS NULL OR extract(year FROM pay_date)::int = year);

ALTER TABLE public.dividends DROP CONSTRAINT IF EXISTS dividends_ex_year_check;
ALTER TABLE public.dividends ADD CONSTRAINT dividends_ex_year_check
    CHECK (ex_date IS NULL
           OR extract(year FROM ex_date)::int = year
           OR (pay_date IS NOT NULL
               AND extract(year FROM pay_date)::int = year
               AND extract(year FROM ex_date)::int = year - 1));

ALTER TABLE public.dividends DROP CONSTRAINT IF EXISTS dividends_amount_check;
ALTER TABLE public.dividends ADD CONSTRAINT dividends_amount_check
    CHECK (amount IS NULL OR amount > 0);

ALTER TABLE public.dividends DROP CONSTRAINT IF EXISTS dividends_confirmed_check;
ALTER TABLE public.dividends ADD CONSTRAINT dividends_confirmed_check
    CHECK (NOT confirmed OR ex_date IS NOT NULL);
