// Isolated transport fixture only. Never deploy this in place of the gateway.
import {
  createHandler,
  Reservation,
  sha256,
} from "../automation/archive-gateway/gateway.ts";

const objects = new Map<string, Uint8Array>();
const metadata = new Map<string, Record<string, unknown>>();
const slots = new Set<string>();
const key = (value: Record<string, unknown>) =>
  JSON.stringify([value.p_provider, value.p_kind, value.p_slot]);
const handler = createHandler({
  reserve(value) {
    const digest = value.p_digest as string;
    metadata.set(digest, value);
    return Promise.resolve(
      {
        state: "RESERVED",
        bucket: "private-market-evidence",
        object_path: digest,
      } as Reservation,
    );
  },
  read(location) {
    return Promise.resolve(objects.get(location.object_path) ?? null);
  },
  put(location, body) {
    if (objects.has(location.object_path)) {
      throw new Error("Overwrite forbidden");
    }
    objects.set(location.object_path, body.slice());
    return Promise.resolve();
  },
  finalize(digest) {
    const value = metadata.get(digest)!;
    if (value.p_completeness === "COMPLETE") slots.add(key(value));
    return Promise.resolve();
  },
  complete(provider, kind, slot) {
    return Promise.resolve(slots.has(JSON.stringify([provider, kind, slot])));
  },
}, {
  enabled: true,
  tokenHash: await sha256(
    new TextEncoder().encode("arc_write_" + "a".repeat(64)),
  ),
}, () => Date.parse("2026-10-27T14:10:00Z"));

Deno.serve({
  hostname: "127.0.0.1",
  port: 0,
  onListen({ port }) {
    console.log(JSON.stringify({ port }));
  },
}, handler);
