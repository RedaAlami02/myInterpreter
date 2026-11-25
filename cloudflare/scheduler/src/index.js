/**
 * Cloudflare scheduler and alerter for myInterpreter.
 *
 * The Worker never touches market data: it only starts GitHub workflows and
 * reports when something looks wrong. The publishing logic stays in Actions,
 * where it is tested and already idempotent.
 *
 * Secrets (wrangler secret put):
 *   GITHUB_TOKEN        fine-grained PAT: Actions read+write on this repo only
 *   ALERT_WEBHOOK_URL   Discord/Slack/Telegram webhook URL
 *   ALERT_KIND          "discord" (default) | "slack" | "telegram"
 *   TELEGRAM_CHAT_ID    only for ALERT_KIND=telegram
 */

const ORDERBOOK_CRON = "*/15 8-15 * * 1-5";
// Offset from the order-book slots so both triggers fire in the same hour.
const DISPATCH_CRON = "5,20,35,50 8-15 * * 1-5";
const EVENING_CRON = "0,30 16-20 * * 1-5";
const ALERT_CRON = "0 22 * * *";

export default {
  async scheduled(event, env, ctx) {
    if (event.cron === ORDERBOOK_CRON) {
      // force=false on purpose: a manual dispatch defaults to true, which would
      // publish the previous session's book as today's during the pre-open.
      ctx.waitUntil(dispatch(env, "exchange-orderbook-publication.yml", { force: "false" })
        .catch((error) => alert(env, `Order-book dispatch failed: ${error.message}`)));
      return;
    }
    if (event.cron === DISPATCH_CRON || event.cron === EVENING_CRON) {
      // The workflow's preflight decides the job: refresh quotes during the
      // session, publish the close once it exists, otherwise exit in seconds.
      // force must be false for that to happen: a manual dispatch defaults to
      // true, which short-circuits the preflight into a full CLOSE capture and
      // made every scheduled run take ten minutes instead of one.
      ctx.waitUntil(dispatch(env, "exchange-price-publication.yml", { force: "false" })
        .catch((error) => alert(env, `Dispatch failed: ${error.message}`)));
      return;
    }
    if (event.cron === ALERT_CRON) {
      ctx.waitUntil(checkAndAlert(env)
        .catch((error) => alert(env, `Health check failed: ${error.message}`)));
    }
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/run") {
      // Manual trigger, only with the shared token: an open endpoint would let
      // anyone spend Actions minutes.
      if (!env.RUN_TOKEN || url.searchParams.get("token") !== env.RUN_TOKEN) {
        return json({ status: "forbidden" }, 403);
      }
      try {
        await dispatch(env, "exchange-price-publication.yml");
      } catch (error) {
        return json({ status: "dispatch_failed", error: error.message }, 502);
      }
      return json({ status: "dispatched" });
    }
    if (url.pathname === "/alert-test") {
      if (!env.RUN_TOKEN || url.searchParams.get("token") !== env.RUN_TOKEN) {
        return json({ status: "forbidden" }, 403);
      }
      if (!env.ALERT_WEBHOOK_URL) {
        return json({ status: "no_webhook" }, 409);
      }
      try {
        await alert(env, "Test alert from the myInterpreter scheduler.");
      } catch (error) {
        return json({ status: "alert_failed", error: error.message }, 502);
      }
      return json({ status: "sent" });
    }
    return json({ status: "alive", repo: env.GITHUB_REPO, site: env.SITE_URL });
  },
};

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status, headers: { "Content-Type": "application/json" },
  });
}

// GitHub answered 500 to two dispatches on 2026-11-25 and created no run. The
// next slot is 15 minutes away during the session, so a retry costs nothing and
// turns a lost slot into a slightly late one. Only transient statuses retry: a
// bad token or a missing workflow still fails immediately.
const RETRY_DELAYS_MS = [2000, 5000];
const TRANSIENT_STATUS = new Set([429, 500, 502, 503, 504]);

async function github(env, path, init = {}) {
  if (!env.GITHUB_TOKEN) throw new Error("GITHUB_TOKEN is not configured");
  for (let attempt = 0; ; attempt++) {
    const response = await fetch(`https://api.github.com${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "myinterpreter-scheduler",
        "X-GitHub-Api-Version": "2022-11-28",
        ...(init.headers || {}),
      },
    });
    if (response.ok) {
      return response.status === 204 ? null : response.json();
    }
    if (!TRANSIENT_STATUS.has(response.status) || attempt >= RETRY_DELAYS_MS.length) {
      throw new Error(`GitHub ${response.status} on ${path}`);
    }
    await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS_MS[attempt]));
  }
}

async function dispatch(env, workflow, inputs) {
  const body = { ref: "master" };
  if (inputs) body.inputs = inputs;
  await github(env, `/repos/${env.GITHUB_REPO}/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

function utcDay(date) {
  return date.toISOString().slice(0, 10);
}

async function latestRuns(env, workflow) {
  const data = await github(env, `/repos/${env.GITHUB_REPO}/actions/workflows/${workflow}/runs?per_page=10`);
  return (data && data.workflow_runs) || [];
}

async function checkAndAlert(env) {
  const problems = [];
  const now = new Date();
  const today = utcDay(now);
  const weekday = now.getUTCDay() >= 1 && now.getUTCDay() <= 5;

  // The close only matters on weekdays; the holiday case is handled upstream by
  // the session probe, which makes the run succeed with NO_SESSION.
  if (weekday) {
    // Only runs started after the close count: an early run exits with
    // NO_SESSION and must not hide a missing close. The close slot is 15:45
    // local, which is 14:45 or 15:45 UTC depending on the offset.
    const closeWindow = new Date(`${today}T15:00:00Z`).getTime();
    const runs = await latestRuns(env, "exchange-price-publication.yml");
    const published = runs.some((run) =>
      run.conclusion === "success" && new Date(run.created_at).getTime() >= closeWindow);
    if (!published) problems.push(`no price publication after the close today (${today})`);
  }

  const health = await latestRuns(env, "market-health.yml");
  if (health.length && health[0].conclusion === "failure") {
    problems.push(`health audit failed: ${health[0].html_url}`);
  }

  try {
    const site = await fetch(env.SITE_URL, { redirect: "manual" });
    if (site.status >= 500) problems.push(`site returned ${site.status}`);
  } catch (error) {
    problems.push(`site unreachable: ${error.message}`);
  }

  if (problems.length) {
    await alert(env, `myInterpreter health\n- ${problems.join("\n- ")}`);
  }
}

async function alert(env, message) {
  const url = env.ALERT_WEBHOOK_URL;
  if (!url) return;
  const kind = (env.ALERT_KIND || "discord").toLowerCase();
  let body;
  if (kind === "slack") body = { text: message };
  else if (kind === "telegram") {
    body = { chat_id: env.TELEGRAM_CHAT_ID, text: message };
  } else body = { content: message };
  await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
