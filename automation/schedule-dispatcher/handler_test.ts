import {createHandler, eligible, sha, type Config} from './handler.ts';
function check(value: unknown) { if (!value) throw new Error('assertion failed'); }
const NOW = new Date('2026-11-04T12:17:00Z');
async function fixture(options: {active?: string; recent?: string; fail?: boolean; bad?: boolean; dispatch?: number; enabled?: boolean} = {}) {
  const calls: {url: string; init?: RequestInit}[] = [];
  const config: Config = {enabled: options.enabled !== false, tokenHash: await sha('test-token'),
    githubToken: 'synthetic', repository: 'example/worker', workflow: '123', branch: 'main'};
  const fake = ((url: string | URL | Request, init?: RequestInit) => {
    calls.push({url: String(url), init});
    if (options.fail) throw new Error('private diagnostic must not leak');
    if (String(url).endsWith('/dispatches')) return Promise.resolve(new Response(null, {status: options.dispatch ?? 204}));
    if (options.bad) return Promise.resolve(Response.json({}));
    const state = new URL(String(url)).searchParams.get('status');
    const run = state ? state === options.active : !!options.recent;
    return Promise.resolve(Response.json({total_count: run ? 1 : 0,
      workflow_runs: run ? [{created_at: options.recent ?? NOW.toISOString()}] : []}));
  }) as typeof fetch;
  const handle = createHandler(config, fake, () => NOW);
  const request = (method = 'POST', token = 'test-token') => new Request('https://example.invalid',
    {method, headers: {authorization: `Bearer ${token}`}});
  return {handle, request, calls, config, fake};
}
Deno.test('unauthorized callers cannot reach GitHub', async () => {
  const f = await fixture(); check((await f.handle(f.request('POST', 'wrong'))).status === 401); check(f.calls.length === 0);
});
Deno.test('method and disabled gates prevent dispatch', async () => {
  const f = await fixture({enabled: false}); check((await f.handle(f.request())).status === 503);
  check((await f.handle(f.request('GET'))).status === 405); check(f.calls.length === 0);
});
for (const active of ['in_progress', 'queued', 'waiting', 'pending', 'requested']) {
  Deno.test(`existing ${active} run prevents another dispatch`, async () => {
    const f = await fixture({active}); check((await (await f.handle(f.request())).json()).status === 'RUN_ACTIVE');
    check(!f.calls.some(c => c.init?.method === 'POST'));
  });
}
Deno.test('recent and future run timestamps suppress duplicates', async () => {
  for (const recent of ['2026-11-04T12:16:00Z', '2026-11-04T12:18:00Z']) {
    const f = await fixture({recent}); check((await (await f.handle(f.request())).json()).status === 'RECENT_RUN');
    check(!f.calls.some(c => c.init?.method === 'POST'));
  }
});
Deno.test('previous tick delayed by seconds does not suppress the next slot', async () => {
  const f = await fixture({recent: '2026-11-04T12:12:04Z'});
  check((await f.handle(f.request())).status === 202);
});
Deno.test('successful dispatch with run details is accepted', async () => {
  const f = await fixture({dispatch: 200}); check((await f.handle(f.request())).status === 202);
});
Deno.test('invalid or unavailable history fails closed without diagnostics', async () => {
  for (const options of [{bad: true}, {fail: true}, {recent: 'invalid'}]) {
    const f = await fixture(options); const r = await f.handle(f.request()); check(r.status === 502);
    check(!(await r.text()).includes('private diagnostic')); check(!f.calls.some(c => c.init?.method === 'POST'));
  }
});
Deno.test('only fixed auto inputs can be dispatched', async () => {
  const f = await fixture(); const r = await f.handle(new Request('https://example.invalid', {method: 'POST',
    headers: {authorization: 'Bearer test-token'}, body: JSON.stringify({ref: 'evil', kind: 'official_close', bootstrap: true})}));
  check(r.status === 202); const post = f.calls.at(-1)!;
  check(post.url === 'https://api.github.com/repos/example/worker/actions/workflows/123/dispatches');
  check(post.init?.body === JSON.stringify({ref: 'main', inputs: {kind: 'auto', bootstrap: 'false'}}));
});
Deno.test('GitHub rejection does not report success', async () => {
  const f = await fixture({dispatch: 403}); check((await f.handle(f.request())).status === 502);
});
Deno.test('Casablanca windows include official review and Monday dividends', () => {
  check(eligible(new Date('2026-11-04T08:00:00Z')));
  check(eligible(new Date('2026-11-04T17:59:00Z')));
  check(!eligible(new Date('2026-11-04T18:00:00Z')));
  check(!eligible(new Date('2026-11-07T10:00:00Z')));
  check(eligible(new Date('2026-11-02T06:05:00Z')));
  check(!eligible(new Date('2026-11-03T06:05:00Z')));
});
Deno.test('outside window causes no GitHub request', async () => {
  const f = await fixture(); const handle = createHandler(f.config, f.fake, () => new Date('2026-11-07T10:00:00Z'));
  check((await (await handle(f.request())).json()).status === 'OUTSIDE_WINDOW'); check(f.calls.length === 0);
});
