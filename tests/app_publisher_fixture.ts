// Isolated transport fixture only. Never deploy this in place of the publisher.
import {
  createHandler,
  PublishBackend,
  sha256,
} from "../automation/app-publisher/publisher.ts";

let archived: Uint8Array | null = null;
const backend: PublishBackend = {
  readArchive(_digest) {
    return Promise.resolve(archived);
  },
  publish(_document, payloadSha) {
    return Promise.resolve(payloadSha);
  },
};
const handler = createHandler(backend, {
  enabled: true,
  tokenHash: await sha256(
    new TextEncoder().encode("app_publish_" + "a".repeat(64)),
  ),
}, () => Date.parse("2026-10-27T14:11:00Z"));

Deno.serve({
  hostname: "127.0.0.1",
  port: 0,
  onListen({ port }) {
    console.log(JSON.stringify({ port }));
  },
}, async (request) => {
  if (new URL(request.url).pathname === "/seed") {
    if (request.method !== "POST") return new Response("no", { status: 405 });
    archived = new Uint8Array(await request.arrayBuffer());
    return new Response("ok");
  }
  return await handler(request);
});
