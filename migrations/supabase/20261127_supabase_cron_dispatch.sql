-- A second dispatcher, independent of Cloudflare.
--
-- Cloudflare's cron triggers stopped invoking the scheduler Worker at
-- 2026-11-26 20:30 UTC: on 2026-11-27 no invocation happened at all, a probe
-- trigger added for 17:30 never fired, and the Worker itself was healthy
-- (HTTP 200, triggers registered, secrets intact). Supabase's pg_cron runs
-- inside the database we already depend on, so a Cloudflare outage no longer
-- stops publication.
--
-- The credential is a fine-grained GitHub PAT with Actions: write, stored as
-- the Vault secret `github_dispatch_pat`:
--
--   select vault.create_secret('<token>', 'github_dispatch_pat',
--                              'GitHub Actions: write, dispatches publications');
--
-- Until that secret exists the function returns quietly. While Cloudflare
-- recovers, duplicate dispatches are harmless: the workflow's concurrency
-- group serialises them and the preflight exits in seconds when the quotes are
-- already fresh.

CREATE OR REPLACE FUNCTION public.dispatch_github_workflow(
    workflow text, inputs jsonb DEFAULT '{}'::jsonb)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    token text;
BEGIN
    IF workflow NOT IN ('exchange-price-publication.yml',
                        'exchange-orderbook-publication.yml') THEN
        RAISE EXCEPTION 'unsupported workflow %', workflow;
    END IF;
    SELECT decrypted_secret INTO token
      FROM vault.decrypted_secrets
     WHERE name = 'github_dispatch_pat'
     LIMIT 1;
    IF token IS NULL OR length(token) < 20 THEN
        RETURN;
    END IF;
    PERFORM net.http_post(
        url := 'https://api.github.com/repos/RedaAlami02/myInterpreter/actions/workflows/'
               || workflow || '/dispatches',
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || token,
            'Accept', 'application/vnd.github+json',
            'Content-Type', 'application/json',
            'X-GitHub-Api-Version', '2022-11-28',
            'User-Agent', 'myinterpreter-supabase-cron'),
        body := jsonb_build_object('ref', 'master',
                                   'inputs', coalesce(inputs, '{}'::jsonb)),
        timeout_milliseconds := 15000);
END;
$$;

REVOKE ALL ON FUNCTION public.dispatch_github_workflow(text, jsonb)
    FROM PUBLIC, anon, authenticated;

-- Same wall-clock slots as the Cloudflare Worker published: quotes during the
-- session and at the close, order books on the quarter hour, evening safety
-- net after the bell. pg_cron evaluates these in UTC, like the Worker did.
SELECT cron.schedule('exchange-price-dispatch', '5,20,35,50 8-15 * * 1-5',
    $$SELECT public.dispatch_github_workflow(
          'exchange-price-publication.yml', '{"force":"false"}'::jsonb)$$);

SELECT cron.schedule('exchange-price-evening', '0,30 16-20 * * 1-5',
    $$SELECT public.dispatch_github_workflow(
          'exchange-price-publication.yml', '{"force":"false"}'::jsonb)$$);

SELECT cron.schedule('exchange-orderbook-dispatch', '*/15 8-15 * * 1-5',
    $$SELECT public.dispatch_github_workflow(
          'exchange-orderbook-publication.yml', '{"force":"false"}'::jsonb)$$);
