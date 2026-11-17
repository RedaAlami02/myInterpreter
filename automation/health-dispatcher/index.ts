import {createHandler} from './handler.ts';
Deno.serve(createHandler({enabled:Deno.env.get('APP_HEALTH_ENABLED')==='true',
 tokenHash:Deno.env.get('APP_TIMER_TOKEN_SHA256')??'',githubToken:Deno.env.get('APP_TIMER_GITHUB_TOKEN')??'',
 repository:Deno.env.get('APP_TIMER_REPOSITORY')??'',branch:Deno.env.get('APP_TIMER_BRANCH')??''}));
