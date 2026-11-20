-- Company rows are updated and prices are mapped by name, and format rows are
-- selected by symbol, but neither column had a unique guarantee. Checked on
-- 2026-11-20: 81 company names and 81 symbols, no duplicates, none empty — so
-- the indexes can be created without a cleanup step.
CREATE UNIQUE INDEX IF NOT EXISTS company_name_unique
    ON public.company (name);
CREATE UNIQUE INDEX IF NOT EXISTS format_symbol_unique
    ON public.format (symbol);
