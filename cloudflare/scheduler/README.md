# Cloudflare scheduler and alerter

A tiny Worker that starts the daily GitHub publication and reports when
something looks wrong. It never touches market data; publishing stays in
Actions, where the preflight makes repeated dispatches harmless.

## What it does

| Trigger (UTC) | Action |
|---|---|
| `*/15 16-21 * * 1-5` | Dispatches `exchange-price-publication.yml`. The workflow's preflight publishes the first time it finds no close for the day and exits immediately afterwards. |
| `0 22 * * *` | Checks that a successful price run started after 16:00 today (weekdays), that the newest health audit did not fail, and that the site answers; sends a webhook alert when anything is wrong. |

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
- A holiday run is a success with `NO_SESSION`, so it counts as a published
  day; the alert does not cry wolf on closures.
- The Worker only holds an `Actions: write` token for this repository. It cannot
  read the database, push code, or touch other repositories.
