import {createHandler} from './handler.ts';
Deno.serve(request => createHandler({
  enabled: Deno.env.get('APP_TIMER_ENABLED') === 'true',
  tokenHash: Deno.env.get('APP_TIMER_TOKEN_SHA256') ?? '',
  githubToken: Deno.env.get('APP_TIMER_GITHUB_TOKEN') ?? '',
  repository: Deno.env.get('APP_TIMER_REPOSITORY') ?? '',
  workflow: Deno.env.get('APP_TIMER_WORKFLOW') ?? '',
  branch: Deno.env.get('APP_TIMER_BRANCH') ?? '',
})(request));
