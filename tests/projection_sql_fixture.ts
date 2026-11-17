// SYNTHETIC LOOPBACK FIXTURE ONLY. Never deploy this instead of a real function.
import { createHandler, sha256 } from "../automation/projection-publisher/publisher.ts";
import { SupabaseProjectionBackend } from "../automation/projection-publisher/supabase.ts";

const bridgePort = Number(Deno.args[0]);
if (!Number.isInteger(bridgePort) || bridgePort < 1 || bridgePort > 65535) throw new Error("INVALID_FIXTURE_PORT");
const bridge = "http://127.0.0.1:" + bridgePort;
const backend = new SupabaseProjectionBackend(
  "https://" + "a".repeat(20) + ".supabase.co",
  "sb_" + "secret_fixture",
  (url, options) => fetch(bridge + new URL(String(url)).pathname, options),
);
const handler = createHandler(backend, {
  enabled: true,
  tokenHash: await sha256(new TextEncoder().encode("proj_publish_" + "a".repeat(64))),
});
Deno.serve({
  hostname: "127.0.0.1", port: 0,
  onListen({ port }) { console.log(JSON.stringify({ port })); },
}, handler);
