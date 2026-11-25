# Cloudflare scheduler and alerter

A tiny Worker that starts the daily GitHub publication and reports when
something looks wrong. It never touches market data; publishing stays in
Actions, where the preflight makes repeated dispatches harmless.

## What it does

| Trigger (UTC) | Action |
|---|---|
| `*/15 8-15 * * 1-5` | Dispatches `exchange-orderbook-publication.yml` with `force=false`, so the capture still refuses to run outside the session window. |
| `5,20,35,50 8-15 * * 1-5` | Dispatches `exchange-price-publication.yml` during the session. The preflight decides: refresh quotes only while the session is open, publish the full close once the local clock passes 15:45. |
| `0,30 16-20 * * 1-5` | Same dispatch after the session, as a safety net for a missed close. Every run is a no-op once the day's `data` row exists. |
| `0 22 * * *` | Checks that a successful price run started after 15:00 today (weekdays), that the newest health audit did not fail, and that the site answers; sends a webhook alert when anything is wrong. |

## One-time setup

1. **GitHub token** — Settings → Developer settings → Fine-grained tokens →
   Generate. Repository access: only `RedaAlami02/myInterpreter`.
   Permissions: **Actions: Read and write**, Metadata: Read. Copy it.
2. **Alert webhook** — Discord: channel settings → Integrations → Webhooks →
   New. Slack: Incoming Webhooks. Telegram: create a bot, use
   `https://api.telegram.org/bot<token>/sendMessage` and note the chat id.
3. **Deploy**:

   ```bash
   cd cloudflare/scheduler
   npx wrangler login
   npx wrangler deploy
   npx wrangler secret put GITHUB_TOKEN
   npx wrangler secret put ALERT_WEBHOOK_URL
   npx wrangler secret put ALERT_KIND          # discord | slack | telegram
   npx wrangler secret put TELEGRAM_CHAT_ID    # telegram only
   npx wrangler secret put RUN_TOKEN           # guards the manual /run endpoint
   ```

4. **Smoke test**:
   ```bash
   curl https://myinterpreter-scheduler.<your-subdomain>.workers.dev/
   curl "https://myinterpreter-scheduler.<your-subdomain>.workers.dev/run?token=<RUN_TOKEN>"
   ```
   The second call starts a publication run; the workflow's preflight decides
   whether it actually captures anything.

## Limits and behaviour

- Free plan is enough: two cron triggers and a handful of requests per run.
- The alert fires at most once a day; it repeats the next day if the problem
  persists. It never writes to the database.
- A dispatch GitHub answers with 429 or 5xx is retried twice (2 s, then 5 s)
  before the alert fires. Other errors — a bad token, a missing workflow —
  fail immediately.
- A holiday run is a success with `NO_SESSION`, so it counts as a published
  day; the alert does not cry wolf on closures.
- The Worker only holds an `Actions: write` token for this repository. It cannot
  read the database, push code, or touch other repositories.

## Troubleshooting

- `{"status":"dispatch_failed","error":"GitHub 403 ..."}` means the token can
  read the repository but cannot start workflows. A fine-grained PAT needs
  **Actions: Read and write**; "Metadata: Read" alone is not enough. Replace the
  secret with `npx wrangler secret put GITHUB_TOKEN`.
- `error code: 1101` before this check existed meant an unhandled GitHub error;
  the endpoint now returns the message instead.
- Without `ALERT_WEBHOOK_URL` the scheduled checks still run but an alert is a
  no-op, so a silent Worker does not mean a healthy day.
