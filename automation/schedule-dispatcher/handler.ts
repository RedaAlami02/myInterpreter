/** Timer boundary: fixed workflow, fixed inputs, no market or portfolio access. */
export type Config = {
  enabled: boolean; tokenHash: string; githubToken: string;
  repository: string; workflow: string; branch: string;
};
export async function sha(value: string): Promise<string> {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, '0')).join('');
}
export function eligible(now: Date): boolean {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone: 'Africa/Casablanca', weekday: 'short', hour: '2-digit', hourCycle: 'h23',
  }).formatToParts(now).map(p => [p.type, p.value]));
  const hour = Number(parts.hour);
  return !['Sat', 'Sun'].includes(parts.weekday) &&
    ((hour >= 9 && hour < 19) || (parts.weekday === 'Mon' && hour === 7));
}
export function createHandler(config: Config, fetcher: typeof fetch = fetch,
  clock: () => Date = () => new Date()) {
  return async (request: Request): Promise<Response> => {
    const reply = (status: string, code = 200) => Response.json({status}, {status: code});
    if (request.method !== 'POST') return reply('METHOD_NOT_ALLOWED', 405);
    const auth = request.headers.get('authorization') ?? '';
    if (!/^[a-f0-9]{64}$/.test(config.tokenHash) || auth.length > 512 ||
        !auth.startsWith('Bearer ') || await sha(auth.slice(7)) !== config.tokenHash)
      return reply('UNAUTHORIZED', 401);
    if (!config.enabled) return reply('DISABLED', 503);
    if (!/^[\w.-]+\/[\w.-]+$/.test(config.repository) || !/^\d+$/.test(config.workflow) ||
        !/^[\w./-]+$/.test(config.branch) || !config.githubToken)
      return reply('CONFIGURATION_INVALID', 503);
    // Caller content cannot choose a repository, branch, job or bypass a gate.
    const now = clock();
    if (!eligible(now)) return reply('OUTSIDE_WINDOW');
    const base = `https://api.github.com/repos/${config.repository}`;
    const headers = {Authorization: `Bearer ${config.githubToken}`,
      Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'private-schedule-dispatcher'};
    const signal = AbortSignal.timeout(15000);
    try {
      // A separate status query avoids overlooking an old in-progress run.
      for (const state of ['in_progress', 'queued', 'waiting', 'pending', 'requested']) {
        const response = await fetcher(`${base}/actions/workflows/${config.workflow}/runs?status=${state}&per_page=1`,
          {headers, redirect: 'error', signal});
        if (!response.ok) return reply('RUN_HISTORY_UNAVAILABLE', 502);
        const body = await response.json();
        if (!Number.isInteger(body.total_count) || !Array.isArray(body.workflow_runs))
          return reply('RUN_HISTORY_INVALID', 502);
        if (body.total_count > 0) return reply('RUN_ACTIVE');
      }
      const recent = await fetcher(`${base}/actions/workflows/${config.workflow}/runs?per_page=1`,
        {headers, redirect: 'error', signal});
      if (!recent.ok) return reply('RUN_HISTORY_UNAVAILABLE', 502);
      const history = await recent.json();
      if (!Number.isInteger(history.total_count) || !Array.isArray(history.workflow_runs) ||
          (history.total_count > 0 && !history.workflow_runs.length))
        return reply('RUN_HISTORY_INVALID', 502);
      if (history.workflow_runs.length) {
        const created = Date.parse(history.workflow_runs[0].created_at);
        if (!Number.isFinite(created)) return reply('RUN_HISTORY_INVALID', 502);
        // GitHub creates the run seconds after the cron tick. Comparing elapsed
        // time with exactly five minutes would suppress the next valid tick.
        if (Math.floor(created / 300_000) >= Math.floor(now.getTime() / 300_000) ||
            now.getTime() - created < 60_000) return reply('RECENT_RUN');
      }
      const dispatched = await fetcher(`${base}/actions/workflows/${config.workflow}/dispatches`, {
        method: 'POST', headers: {...headers, 'Content-Type': 'application/json'},
        body: JSON.stringify({ref: config.branch, inputs: {kind: 'auto', bootstrap: 'false'}}),
        redirect: 'error', signal,
      });
      return [200, 204].includes(dispatched.status) ? reply('DISPATCH_ACCEPTED', 202) : reply('DISPATCH_REJECTED', 502);
    } catch { return reply('GITHUB_UNAVAILABLE', 502); }
  };
}
