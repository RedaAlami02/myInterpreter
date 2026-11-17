import {
  Backend,
  createHandler,
  GatewayError,
  Reservation,
  sha256,
} from "./gateway.ts";
import { SupabaseArchiveBackend } from "./supabase.ts";

const TOKEN = "arc_write_" + "a".repeat(64),
  NOW = Date.parse("2026-10-28T12:05:00Z");
const received = "2026-10-28T12:04:00+00:00";
function assert(value: unknown, message = "Assertion failed"): asserts value {
  if (!value) throw new Error(message);
}
function equal(a: unknown, b: unknown) {
  assert(JSON.stringify(a) === JSON.stringify(b));
}
async function gzip(value: unknown) {
  const stream = new Blob([JSON.stringify(value)]).stream().pipeThrough(
    new CompressionStream("gzip"),
  );
  return new Uint8Array(await new Response(stream).arrayBuffer());
}
async function envelope() {
  const raw = new TextEncoder().encode('{"test":"synthetic"}'),
    digest = await sha256(raw);
  const provider = "feed_0123456789abcdef";
  const captureId = await sha256(
    new TextEncoder().encode(JSON.stringify([provider, digest, received])),
  );
  return {
    contract: "private-acquisition/v2",
    provider_namespace: provider,
    kind: "quotes",
    slot: "2026-10-28T12:00:00+00:00",
    completed_at: "2026-10-28T12:05:00+00:00",
    execution: "CURRENT_ACQUISITION",
    authority: "UNPROMOTED",
    prediction_eligible: false,
    completeness: "COMPLETE",
    captures: [{
      capture_id: captureId,
      sha256: digest,
      received_at: received,
      raw_hex: Array.from(raw, (x) => x.toString(16).padStart(2, "0")).join(""),
    }],
  };
}
class MemoryBackend implements Backend {
  writes = 0;
  reserves = 0;
  finals = 0;
  completeValue = false;
  state: "RESERVED" | "STORED" = "RESERVED";
  saved: Uint8Array | null = null;
  failFinalizeOnce = false;
  corruptReadback = false;
  failReserve = false;
  reserve(_metadata: Record<string, unknown>): Promise<Reservation> {
    this.reserves++;
    if (this.failReserve) {
      throw new GatewayError("ARCHIVE_POLICY_REJECTED", 503);
    }
    return Promise.resolve({
      state: this.state,
      bucket: "private-market-evidence",
      object_path: "test",
    });
  }
  read(_location: Reservation) {
    return Promise.resolve(
      this.saved && this.corruptReadback ? new Uint8Array([1]) : this.saved,
    );
  }
  put(_location: Reservation, body: Uint8Array) {
    assert(this.saved === null, "Must never overwrite");
    this.saved = body.slice();
    this.writes++;
    return Promise.resolve();
  }
  finalize(_digest: string) {
    if (this.failFinalizeOnce) {
      this.failFinalizeOnce = false;
      throw new Error("PRIVATE_INTERNAL_ERROR");
    }
    this.finals++;
    this.state = "STORED";
    return Promise.resolve();
  }
  complete(_provider: string, _kind: string, _slot: string) {
    return Promise.resolve(this.completeValue);
  }
}
async function fixture() {
  const backend = new MemoryBackend();
  const handler = createHandler(backend, {
    enabled: true,
    tokenHash: await sha256(new TextEncoder().encode(TOKEN)),
  }, () => NOW);
  return { backend, handler };
}

Deno.test("positive acquisition admission is separate from slot completion and performs no writes", async () => {
  const calls: unknown[][] = [];
  const backend = Object.assign(new MemoryBackend(), {
    admit: (...args: [string, string, string, boolean, boolean]) => {
      calls.push(args);
      return Promise.resolve(false);
    },
  });
  const handler = createHandler(backend, {
    enabled: true,
    tokenHash: await sha256(new TextEncoder().encode(TOKEN)),
  }, () => NOW);
  const body = {
    operation: "acquisition_admission",
    provider_namespace: "feed_0123456789abcdef",
    kind: "quotes",
    slot: "2026-10-28T12:00:00Z",
    shadow: true,
    projection: false,
  };
  equal(
    await (await handler(request(JSON.stringify(body), "application/json")))
      .json(),
    { contract: "private-archive-receipt/v1", admitted: false },
  );
  equal(calls.length, 1);
  equal(backend.reserves, 0);
  equal(backend.writes, 0);
  for (
    const change of [
      { projection: true, kind: "depth", shadow: false },
      { kind: "fundamentals" },
      { shadow: "true" },
      { extra: 1 },
      { provider_namespace: "other" },
    ]
  ) {
    equal(
      (await handler(
        request(JSON.stringify({ ...body, ...change }), "application/json"),
      )).status,
      400,
    );
  }
  equal(calls.length, 1);
});

Deno.test("positive acquisition RPC rejects nonboolean receipts", async () => {
  for (const value of [true, false, "true", null]) {
    const backend = new SupabaseArchiveBackend(
      "https://abcdefghijklmnopqrst.supabase.co",
      "sb_secret_fixture",
      (_url, init) => {
        equal(JSON.parse(String(init?.body)), {
          p_provider: "feed_0123456789abcdef",
          p_kind: "quotes",
          p_slot: "2026-10-28T12:00:00Z",
          p_shadow: true,
          p_projection: false,
        });
        return Promise.resolve(Response.json(value));
      },
    );
    if (typeof value === "boolean") {
      equal(
        await backend.admit(
          "feed_0123456789abcdef",
          "quotes",
          "2026-10-28T12:00:00Z",
          true,
          false,
        ),
        value,
      );
    } else {
      let rejected = false;
      try {
        await backend.admit(
          "feed_0123456789abcdef",
          "quotes",
          "2026-10-28T12:00:00Z",
          true,
          false,
        );
      } catch {
        rejected = true;
      }
      assert(rejected);
    }
  }
});
function request(
  body: Uint8Array | string,
  type = "application/gzip",
  token = TOKEN,
) {
  return new Request("https://example.invalid/archive", {
    method: "POST",
    body: body as BodyInit,
    headers: { Authorization: "Bearer " + token, "Content-Type": type },
  });
}
Deno.test("unauthorized calls never reserve or read a body", async () => {
  const { backend, handler } = await fixture();
  const response = await handler(
    request("private", "application/gzip", "arc_write_" + "b".repeat(64)),
  );
  equal(response.status, 401);
  equal(backend.reserves, 0);
});
Deno.test("disabled or misconfigured gateway fails closed", async () => {
  for (
    const config of [{ enabled: false, tokenHash: "a".repeat(64) }, {
      enabled: true,
      tokenHash: "",
    }]
  ) {
    const backend = new MemoryBackend();
    equal(
      (await createHandler(backend, config)(request("private"))).status,
      503,
    );
    equal(backend.reserves, 0);
  }
});
Deno.test("exact bytes are read back before commit and receipt reveals no payload", async () => {
  const { backend, handler } = await fixture();
  const body = await gzip(await envelope());
  const response = await handler(request(body));
  const receipt = await response.json();
  equal(response.status, 200);
  equal(backend.writes, 1);
  equal(backend.finals, 1);
  equal(receipt, {
    contract: "private-archive-receipt/v1",
    status: "STORED",
    sha256: await sha256(body),
    bytes: body.length,
    prediction_eligible: false,
  });
  equal(await sha256(backend.saved!), await sha256(body));
  equal(response.headers.get("Cache-Control"), "no-store");
});

Deno.test("v3 subject archives are disabled by default before any reservation", async () => {
  const { backend, handler } = await fixture();
  const value = {
    ...await envelope(),
    contract: "private-acquisition/v3",
    kind: "fundamentals",
    symbol: "AAA",
    subject_key: "symbol:AAA",
  };
  equal((await handler(request(await gzip(value)))).status, 503);
  equal(backend.reserves, 0);
  equal(backend.writes, 0);
});

Deno.test("enabled v3 archive uses exact subject reservation and finalization", async () => {
  class SubjectBackend extends MemoryBackend {
    metadata: Record<string, unknown> = {};
    subjects: string[] = [];
    override reserve(value: Record<string, unknown>) {
      this.metadata = value;
      return super.reserve(value);
    }
    completeSubject() {
      return Promise.resolve(false);
    }
    finalizeSubject(digest: string, subject: string) {
      this.subjects.push(subject);
      return super.finalize(digest);
    }
  }
  const backend = new SubjectBackend();
  const handler = createHandler(backend, {
    enabled: true,
    subjectEnabled: true,
    tokenHash: await sha256(new TextEncoder().encode(TOKEN)),
  }, () => NOW);
  const value = {
    ...await envelope(),
    contract: "private-acquisition/v3",
    kind: "fundamentals",
    symbol: "AAA",
    subject_key: "symbol:AAA",
  };
  equal((await handler(request(await gzip(value)))).status, 200);
  equal(backend.metadata.p_subject_key, "symbol:AAA");
  equal(backend.subjects, ["symbol:AAA"]);
  for (
    const update of [{ subject_key: "symbol:BBB" }, { kind: "quotes" }, {
      symbol: "bad symbol",
    }, { contract: "private-acquisition/v2" }]
  ) {
    equal(
      (await handler(request(await gzip({ ...value, ...update })))).status,
      400,
    );
  }
  equal(backend.reserves, 1);
});

Deno.test("subject status and positive admission remain separate bounded operations", async () => {
  const backend = Object.assign(new MemoryBackend(), {
    completeSubject: (
      _provider: string,
      _kind: string,
      _slot: string,
      subject: string,
    ) => Promise.resolve(subject === "symbol:AAA"),
    finalizeSubject: () => Promise.resolve(),
    admitSubject: (_provider: string, _subject: string, projection: boolean) =>
      Promise.resolve(!projection),
  });
  const handler = createHandler(backend, {
    enabled: true,
    subjectEnabled: true,
    tokenHash: await sha256(new TextEncoder().encode(TOKEN)),
  }, () => NOW);
  const status = {
    operation: "subject_slot_complete",
    provider_namespace: "feed_0123456789abcdef",
    kind: "fundamentals",
    slot: "2026-10-28T12:00:00Z",
    subject_key: "symbol:AAA",
  };
  equal(
    (await (await handler(request(JSON.stringify(status), "application/json")))
      .json()).complete,
    true,
  );
  equal(
    (await (await handler(
      request(
        JSON.stringify({ ...status, subject_key: "symbol:BBB" }),
        "application/json",
      ),
    )).json()).complete,
    false,
  );
  const admission = {
    operation: "subject_acquisition_admission",
    provider_namespace: status.provider_namespace,
    subject_key: "symbol:AAA",
    projection: true,
  };
  equal(
    (await (await handler(
      request(JSON.stringify(admission), "application/json"),
    )).json()).admitted,
    false,
  );
  equal(
    (await (await handler(
      request(
        JSON.stringify({ ...admission, projection: false }),
        "application/json",
      ),
    )).json()).admitted,
    true,
  );
  for (
    const update of [
      { projection: "true" },
      { subject_key: "symbol:bad symbol" },
      { extra: true },
      { provider_namespace: "legacy" },
    ]
  ) {
    equal(
      (await handler(
        request(
          JSON.stringify({ ...admission, ...update }),
          "application/json",
        ),
      )).status,
      400,
    );
  }
  equal(backend.reserves, 0);
});
Deno.test("retries reuse identical immutable object", async () => {
  const { backend, handler } = await fixture();
  const body = await gzip(await envelope());
  equal((await handler(request(body))).status, 200);
  equal((await handler(request(body))).status, 200);
  equal(backend.writes, 1);
  equal(backend.finals, 2);
});
Deno.test("interrupted finalize recovers uploaded object on retry without overwriting", async () => {
  const { backend, handler } = await fixture();
  backend.failFinalizeOnce = true;
  const body = await gzip(await envelope());
  const failed = await handler(request(body));
  equal(failed.status, 503);
  assert(!(await failed.text()).includes("PRIVATE_INTERNAL_ERROR"));
  equal(backend.finals, 0);
  equal(backend.writes, 1);
  equal((await handler(request(body))).status, 200);
  equal(backend.writes, 1);
  equal(backend.finals, 1);
});
Deno.test("different readback bytes never finalize", async () => {
  const { backend, handler } = await fixture();
  backend.corruptReadback = true;
  const response = await handler(request(await gzip(await envelope())));
  equal(response.status, 503);
  equal(backend.finals, 0);
  equal((await response.json()).code, "ARCHIVE_READBACK_MISMATCH");
});
Deno.test("stored object missing is surfaced rather than silently recreated", async () => {
  const { backend, handler } = await fixture();
  backend.state = "STORED";
  const response = await handler(request(await gzip(await envelope())));
  equal((await response.json()).code, "STORED_OBJECT_MISSING");
  equal(backend.writes, 0);
});
Deno.test("quota or disabled provider prevents upload", async () => {
  const { backend, handler } = await fixture();
  backend.failReserve = true;
  equal((await handler(request(await gzip(await envelope())))).status, 503);
  equal(backend.writes, 0);
  equal(backend.finals, 0);
});
Deno.test("replay diagnostic promoted and fabricated complete envelopes rejected", async () => {
  for (
    const update of [
      { execution: "RECORDED_REPLAY" },
      { execution: "AFTER_HOURS_DIAGNOSTIC" },
      { authority: "PROMOTED" },
      { prediction_eligible: true },
      { captures: [] },
      { contract: "legacy" },
    ]
  ) {
    const { backend, handler } = await fixture();
    equal(
      (await handler(request(await gzip({ ...await envelope(), ...update }))))
        .status,
      400,
    );
    equal(backend.reserves, 0);
  }
});
Deno.test("wrong namespace raw hash and capture identity rejected", async () => {
  for (const field of ["provider_namespace", "sha256", "capture_id"]) {
    const { backend, handler } = await fixture();
    const value = await envelope();
    if (field === "provider_namespace") {
      value.provider_namespace = "legacy_namespace";
    } else value.captures[0][field as "sha256" | "capture_id"] = "b".repeat(64);
    equal((await handler(request(await gzip(value)))).status, 400);
    equal(backend.reserves, 0);
  }
});
Deno.test("future completion receipt outside batch naive time and duplicate captures rejected", async () => {
  for (
    const mode of [
      "future",
      "before_slot",
      "after_complete",
      "naive",
      "duplicate",
    ]
  ) {
    const { backend, handler } = await fixture();
    const value = await envelope();
    if (mode === "future") value.completed_at = "2026-10-29T12:05:00Z";
    if (mode === "before_slot") {
      value.captures[0].received_at = "2026-10-28T11:00:00Z";
    }
    if (mode === "after_complete") {
      value.captures[0].received_at = "2026-10-28T12:06:00Z";
    }
    if (mode === "naive") value.slot = "2026-10-28T12:00:00";
    if (mode === "duplicate") value.captures.push(value.captures[0]);
    equal((await handler(request(await gzip(value)))).status, 400);
    equal(backend.reserves, 0);
  }
});
Deno.test("invalid gzip and decompression expansion are bounded before reservation", async () => {
  const { backend, handler } = await fixture();
  equal((await handler(request("not-gzip"))).status, 400);
  const bomb = await gzip({ padding: "x".repeat(24 * 1024 * 1024) });
  equal((await handler(request(bomb))).status, 413);
  equal(backend.reserves, 0);
});
Deno.test("slot lookup returns only a boolean no raw or native identities", async () => {
  const { backend, handler } = await fixture();
  backend.completeValue = true;
  const value = await envelope();
  const response = await handler(
    request(
      JSON.stringify({
        operation: "slot_complete",
        provider_namespace: value.provider_namespace,
        kind: value.kind,
        slot: value.slot,
      }),
      "application/json",
    ),
  );
  equal(await response.json(), {
    contract: "private-archive-receipt/v1",
    complete: true,
  });
  equal(backend.reserves, 0);
});
Deno.test("status request cannot select arbitrary operations or extra data", async () => {
  const { handler } = await fixture();
  for (
    const value of [{ operation: "read" }, {
      operation: "slot_complete",
      extra: "not_allowed",
    }, null]
  ) {
    equal(
      (await handler(request(JSON.stringify(value), "application/json")))
        .status,
      400,
    );
  }
});
Deno.test("invalid calendar dates cannot normalize into a different session", async () => {
  const { handler, backend } = await fixture();
  const response = await handler(
    request(
      JSON.stringify({
        operation: "slot_complete",
        provider_namespace: "feed_0123456789abcdef",
        kind: "quotes",
        slot: "2026-02-30T12:00:00Z",
      }),
      "application/json",
    ),
  );
  equal(response.status, 400);
  equal(backend.reserves, 0);
});
Deno.test("REST adapter prevents redirects upserts or nonprivate bucket paths", async () => {
  const calls: { url: string; init: RequestInit }[] = [];
  const backend = new SupabaseArchiveBackend(
    "https://" + "a".repeat(20) + ".supabase.co",
    "sb_" + "secret_fixture",
    async (url, init) => {
      calls.push({ url: String(url), init: init! });
      return new Response("{}", { status: 200 });
    },
  );
  await backend.put({
    state: "RESERVED",
    bucket: "private-market-evidence",
    object_path: "sha256/aa/" + "a".repeat(64) + ".json.gz",
  }, new Uint8Array([1]));
  equal(calls[0].init.redirect, "error");
  equal((calls[0].init.headers as Record<string, string>)["x-upsert"], "false");
  equal(calls[0].init.method, "POST");
  let rejected = false;
  try {
    await backend.read({
      state: "RESERVED",
      bucket: "other",
      object_path: "../private",
    });
  } catch {
    rejected = true;
  }
  assert(rejected);
  equal(calls.length, 1);
});
Deno.test("REST adapter handles exact missing-key semantics without masking bucket or access failure", async () => {
  const location = {
    state: "RESERVED",
    bucket: "private-market-evidence",
    object_path: "sha256/aa/" + "a".repeat(64) + ".json.gz",
  } as Reservation;
  for (const status of [400, 404]) {
    const backend = new SupabaseArchiveBackend(
      "https://" + "a".repeat(20) + ".supabase.co",
      "sb_" + "secret_fixture",
      () =>
        Promise.resolve(
          Response.json({ code: "NoSuchKey", statusCode: "404" }, { status }),
        ),
    );
    equal(await backend.read(location), null);
  }
  for (const code of ["NoSuchBucket", "AccessDenied", "TenantNotFound"]) {
    const backend = new SupabaseArchiveBackend(
      "https://" + "a".repeat(20) + ".supabase.co",
      "sb_" + "secret_fixture",
      () =>
        Promise.resolve(
          Response.json({ code, statusCode: "404" }, { status: 400 }),
        ),
    );
    let rejected = false;
    try {
      await backend.read(location);
    } catch {
      rejected = true;
    }
    assert(rejected);
  }
});
Deno.test("REST adapter resolves only recognized duplicate upload conflicts", async () => {
  const location = {
    state: "RESERVED",
    bucket: "private-market-evidence",
    object_path: "sha256/aa/" + "a".repeat(64) + ".json.gz",
  } as Reservation;
  const backend = new SupabaseArchiveBackend(
    "https://" + "a".repeat(20) + ".supabase.co",
    "sb_" + "secret_fixture",
    () =>
      Promise.resolve(
        Response.json({ code: "KeyAlreadyExists", statusCode: "409" }, {
          status: 400,
        }),
      ),
  );
  await backend.put(location, new Uint8Array([1]));
});
Deno.test("maximum-size raw capture decodes without a per-byte string array", async () => {
  const { handler, backend } = await fixture();
  const value = await envelope();
  const raw = new Uint8Array(4 * 1024 * 1024);
  value.captures[0].raw_hex = "00".repeat(raw.length);
  value.captures[0].sha256 = await sha256(raw);
  value.captures[0].capture_id = await sha256(
    new TextEncoder().encode(JSON.stringify([
      value.provider_namespace,
      value.captures[0].sha256,
      value.captures[0].received_at,
    ])),
  );
  equal((await handler(request(await gzip(value)))).status, 200);
  equal(backend.finals, 1);
});

Deno.test("recurring archive mode uses only versioned admission RPC", async () => {
  let called = "";
  const backend = new SupabaseArchiveBackend("https://abcdefghijklmnopqrst.supabase.co", "sb_secret_fixture", ((url: RequestInfo | URL) => {
    called = String(url);
    return Promise.resolve(new Response("true", {status: 200}));
  }) as typeof fetch, true);
  if (!await backend.admit("feed_0123456789abcdef", "quotes", "2026-11-03T10:00:00Z", true, true)) throw new Error("admission");
  if (!called.endsWith("/rpc/market_archive_acquisition_admission_recurring_v1")) throw new Error("unversioned RPC");
});
