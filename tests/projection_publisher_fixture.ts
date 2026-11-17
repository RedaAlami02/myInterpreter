// Isolated transport fixture only. Never deploy this in place of the publisher.
import {
  createHandler,
  ProjectionBackend,
  sha256,
} from "../automation/projection-publisher/publisher.ts";

let archived: Uint8Array | null = null;
const backend: ProjectionBackend = {
  readArchive(_digest) {
    return Promise.resolve(archived);
  },
  publish(kind, document, _payloadSha) {
    const doc = JSON.parse(document);
    return Promise.resolve(
      kind === "dividends"
        ? {
          status: "PUBLISHED",
          rows: doc.rows.length,
          created: doc.rows.length,
          updated: 0,
        }
        : {
          status: "UPDATED",
          name: doc.c_name,
          fields: 0,
          fiscal_year: doc.fields.fiscal_year,
          refreshed: false,
        },
    );
  },
};
const handler = createHandler(backend, {
  enabled: true,
  tokenHash: await sha256(
    new TextEncoder().encode("proj_publish_" + "a".repeat(64)),
  ),
});

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
