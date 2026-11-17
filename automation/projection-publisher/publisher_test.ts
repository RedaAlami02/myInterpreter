import {
  createHandler,
  ProjectionBackend,
  PublishError,
  sha256,
  verifiedArchive,
} from "./publisher.ts";
import { SupabaseProjectionBackend } from "./supabase.ts";

const TOKEN = "proj_publish_" + "a".repeat(64),
  PROVIDER = "feed_0123456789abcdef",
  RECEIVED = "2026-10-28T12:04:00+00:00";
function assert(value: unknown, message = "Assertion failed"): asserts value {
  if (!value) throw new Error(message);
}
function equal(a: unknown, b: unknown, message = "") {
  assert(JSON.stringify(a) === JSON.stringify(b), `${message}${a} !== ${b}`);
}
async function gzip(value: unknown) {
  const stream = new Blob([JSON.stringify(value)]).stream().pipeThrough(
    new CompressionStream("gzip"),
  );
  return new Uint8Array(await new Response(stream).arrayBuffer());
}
async function hash(value: string) {
  return await sha256(new TextEncoder().encode(value));
}
function dividendRow(overrides: Record<string, unknown> = {}) {
  return {
    c_name: "Alpha",
    issuer: "ALPHA",
    year: 2026,
    amount: 175,
    ex_date: "2026-03-25",
    pay_date: "2026-04-08",
    pay_date_end: null,
    confirmed: true,
    type: "Ordinaire",
    frequency: "Annuel",
    ...overrides,
  };
}
function fundamentalFields(overrides: Record<string, unknown> = {}) {
  return {
    ext_name: "Alpha SA",
    sector: "Banks",
    description: "Fixture\nwith newline",
    shareholders: JSON.stringify([{ name: "Holder", pct: 51 }]),
    bpa: 16.67,
    dpa: 0.5,
    tc5: 8.45,
    roe: 16.67,
    na: 1200000,
    cp: 120000000,
    beta_3y: 0.8,
    beta_5y: 0.9,
    revenue: 140,
    ebitda: 60,
    ebit: 50,
    net_profit: 20,
    fcf: 25,
    net_debt: 40,
    net_cash: 5,
    total_assets: 900,
    rev_growth_5y: 8.45,
    rnpg_growth_5y: 7.1,
    profit_margin: 14.29,
    fiscal_year: 2023,
    fy_est: 2025,
    rnpg_est: 30,
    ...overrides,
  };
}
function document(
  kind: "dividends" | "fundamentals",
  digest: string,
  overrides: Record<string, unknown> = {},
) {
  const base = {
    mode: "PROJECTION_ONLY",
    provider_namespace: PROVIDER,
    archive_sha256: digest,
    index_sha256: "b".repeat(64),
    source_execution: "CURRENT_ACQUISITION",
    completeness: "COMPLETE",
    prediction_eligible: false,
    portfolio_valuation_eligible: false,
  };
  return kind === "dividends"
    ? {
      contract: "dividend-projection/v1",
      ...base,
      rows: [dividendRow()],
      excluded: [],
      unmatched: [],
      ...overrides,
    }
    : {
      contract: "fundamental-projection/v1",
      ...base,
      symbol: "AAA",
      c_name: "Alpha",
      fields: fundamentalFields(),
      ...overrides,
    };
}
class MemoryBackend implements ProjectionBackend {
  reads = 0;
  written: { kind: string; document: string; sha: string }[] = [];
  receipt: unknown = undefined;
  constructor(public archive: Uint8Array | null) {}
  readArchive(_digest: string) {
    this.reads++;
    return Promise.resolve(this.archive);
  }
  publish(kind: "dividends" | "fundamentals", doc: string, sha: string) {
    this.written.push({ kind, document: doc, sha });
    const value = JSON.parse(doc);
    return Promise.resolve(
      this.receipt ?? (kind === "dividends"
        ? {
          status: "PUBLISHED",
          rows: value.rows.length,
          created: value.rows.length,
          updated: 0,
        }
        : {
          status: "UPDATED",
          name: value.c_name,
          fields: 0,
          fiscal_year: value.fields.fiscal_year,
          refreshed: false,
        }),
    );
  }
}
async function fixture(
  kind: "dividends" | "fundamentals",
  overrides: Record<string, unknown> = {},
) {
  const raw = new TextEncoder().encode(`{"fixture":"${kind}"}`);
  const rawDigest = await sha256(raw);
  const captureId = await hash(
    JSON.stringify([PROVIDER, rawDigest, RECEIVED]),
  );
  const envelope = {
    contract: "private-acquisition/v2",
    provider_namespace: PROVIDER,
    kind,
    symbol: kind === "fundamentals" ? "AAA" : undefined,
    slot: "2026-10-28T12:00:00+00:00",
    completed_at: "2026-10-28T12:05:00+00:00",
    execution: "CURRENT_ACQUISITION",
    authority: "UNPROMOTED",
    prediction_eligible: false,
    completeness: "COMPLETE",
    captures: [{
      capture_id: captureId,
      sha256: rawDigest,
      received_at: RECEIVED,
      raw_hex: Array.from(raw, (x) => x.toString(16).padStart(2, "0")).join(""),
    }],
    targets: [{}],
  };
  const blob = await gzip(envelope);
  const digest = await sha256(blob);
  const doc = document(kind, digest, overrides);
  const text = JSON.stringify(doc);
  const payload = JSON.stringify({ document: text, sha256: await hash(text) });
  const backend = new MemoryBackend(blob);
  const handler = createHandler(backend, {
    enabled: true,
    tokenHash: await hash(TOKEN),
  });
  return { backend, handler, payload, text, doc, envelope, blob, digest };
}
type Fixture = Awaited<ReturnType<typeof fixture>>;
async function repayload(
  value: Fixture,
  mutate: (doc: Record<string, unknown>) => void,
) {
  const doc = JSON.parse(value.text);
  mutate(doc);
  const text = JSON.stringify(doc);
  return JSON.stringify({ document: text, sha256: await hash(text) });
}
function request(
  body: string,
  type = "application/json",
  token = TOKEN,
  url = "https://example.invalid/publish",
  method = "POST",
) {
  return new Request(url, {
    method,
    body: method === "GET" ? undefined : body,
    headers: { Authorization: "Bearer " + token, "Content-Type": type },
  });
}

Deno.test("dividend projection publishes with an exact receipt", async () => {
  const value = await fixture("dividends");
  const response = await value.handler(request(value.payload));
  equal(response.status, 200);
  equal(await response.json(), {
    contract: "projection-receipt/v1",
    status: "PUBLISHED",
    kind: "dividends",
    sha256: JSON.parse(value.payload).sha256,
    records: 1,
  });
  equal(value.backend.written.length, 1);
  equal(value.backend.written[0].kind, "dividends");
  equal(value.backend.written[0].document, value.text);
  equal(response.headers.get("Cache-Control"), "no-store");
});

Deno.test("fundamental projection publishes and binds the archive symbol", async () => {
  const value = await fixture("fundamentals");
  const response = await value.handler(request(value.payload));
  equal(response.status, 200);
  equal((await response.json()).kind, "fundamentals");
  equal(value.backend.written.length, 1);
  const mismatch = await fixture("fundamentals");
  const body = await repayload(mismatch, (doc) => {
    doc.symbol = "BBB";
  });
  equal(
    (await (await mismatch.handler(request(body))).json()).code,
    "INELIGIBLE_ARCHIVE",
  );
  equal(mismatch.backend.written.length, 0);
});

Deno.test("context reads need a separate switch, exact pin and field whitelist", async () => {
  const base = await fixture("fundamentals");
  const context = {
    contract: "private-enrichment-context/v1",
    provider_namespace: PROVIDER,
    index_sha256: "a".repeat(64),
    observed_at: new Date().toISOString(),
    companies: { Alpha: { bpa: 1.25, sector: null, fiscal_year: 2025 } },
  };
  const backend = Object.assign(base.backend, {
    readContext: () => Promise.resolve(context),
  });
  const payload = JSON.stringify({
    operation: "read_enrichment_context",
    provider_namespace: PROVIDER,
    index_sha256: "a".repeat(64),
  });
  const config = { enabled: true, tokenHash: await hash(TOKEN) };
  equal((await createHandler(backend, config)(request(payload))).status, 503);
  const handler = createHandler(backend, { ...config, contextEnabled: true });
  equal(await (await handler(request(payload))).json(), context);
  const original = context.companies.Alpha;
  Object.assign(context.companies, {
    Alpha: { ...original, email: "fixture@example.invalid" },
  });
  assert((await handler(request(payload))).status !== 200);
  context.companies.Alpha = original;
  context.index_sha256 = "b".repeat(64);
  assert((await handler(request(payload))).status !== 200);
  const full = {
    ...context,
    index_sha256: "a".repeat(64),
    contract: "private-enrichment-context/v2",
    price_companies: {
      "company-a": {
        name: "Alpha",
        bpa: 1.25,
        tc5: 10,
        roe: 15,
        na: 100,
        cp: 50,
        net_profit: 2,
        date: "2026-01-01T00:00:00Z",
        available_at: new Date().toISOString(),
      },
    },
  };
  backend.readContext = () => Promise.resolve(full);
  equal((await handler(request(payload))).status, 200);
  Object.assign(full.price_companies["company-a"], { user_id: "private" });
  assert((await handler(request(payload))).status !== 200);
  equal(backend.written.length, 0);
});

Deno.test("v3 fundamental subject is verified without accepting v3 dividends or mismatched symbols", async () => {
  const value = await fixture("fundamentals");
  const envelope = {
    ...value.envelope,
    contract: "private-acquisition/v3",
    subject_key: "symbol:AAA",
  };
  const blob = await gzip(envelope);
  await verifiedArchive(blob, await sha256(blob), {
    provider: PROVIDER,
    kind: "fundamentals",
    symbol: "AAA",
  });
  for (
    const update of [{ subject_key: "symbol:BBB" }, { kind: "dividends" }, {
      contract: "private-acquisition/v2",
    }]
  ) {
    const bad = await gzip({ ...envelope, ...update });
    let failed = false;
    try {
      await verifiedArchive(bad, await sha256(bad), {
        provider: PROVIDER,
        kind: "fundamentals",
        symbol: "AAA",
      });
    } catch {
      failed = true;
    }
    assert(failed);
  }
});

Deno.test("disabled, unauthorized and malformed calls never read the archive", async () => {
  for (
    const config of [{ enabled: false, tokenHash: "a".repeat(64) }, {
      enabled: true,
      tokenHash: "",
    }]
  ) {
    const backend = new MemoryBackend(null);
    equal(
      (await createHandler(backend, config)(request("{}"))).status,
      503,
    );
    equal(backend.reads, 0);
  }
  const value = await fixture("dividends");
  const attempts: [string, string, string, string, string, number][] = [
    [
      value.payload,
      "application/json",
      "proj_publish_" + "b".repeat(64),
      "https://example.invalid/p",
      "POST",
      401,
    ],
    [
      value.payload,
      "application/json",
      "app_publish_" + "a".repeat(64),
      "https://example.invalid/p",
      "POST",
      401,
    ],
    [
      value.payload,
      "text/plain",
      TOKEN,
      "https://example.invalid/p",
      "POST",
      400,
    ],
    [
      value.payload,
      "application/json",
      TOKEN,
      "https://example.invalid/p?x=1",
      "POST",
      400,
    ],
    [
      value.payload,
      "application/json",
      TOKEN,
      "https://example.invalid/p",
      "GET",
      400,
    ],
  ];
  for (const [body, type, token, url, method, status] of attempts) {
    equal(
      (await value.handler(request(body, type, token, url, method))).status,
      status,
    );
    equal(value.backend.reads, 0);
  }
});

Deno.test("payload hashes and exact keys are enforced", async () => {
  const value = await fixture("dividends");
  const body = JSON.parse(value.payload);
  body.sha256 = "f".repeat(64);
  equal(
    (await (await value.handler(request(JSON.stringify(body)))).json()).code,
    "PAYLOAD_HASH_MISMATCH",
  );
  body.sha256 = await hash(body.document);
  equal(
    (await (await value.handler(
      request(JSON.stringify({ ...body, extra: true })),
    )).json()).code,
    "INVALID_PAYLOAD",
  );
  equal(
    (await (await value.handler(request(JSON.stringify({
      document: JSON.stringify({ ...value.doc, contract: "unknown/v1" }),
      sha256: await hash(
        JSON.stringify({ ...value.doc, contract: "unknown/v1" }),
      ),
    })))).json()).code,
    "UNSUPPORTED_PROJECTION",
  );
  equal(value.backend.reads, 0);
});

Deno.test("dividend quality, dates and duplicates are refused", async () => {
  const mutations: Array<(doc: Record<string, unknown>) => void> = [
    (doc) => {
      (doc.rows as Record<string, unknown>[])[0].ex_date = null;
    },
    (doc) => {
      (doc.rows as Record<string, unknown>[])[0].ex_date = "2026-02-30";
    },
    (doc) => {
      (doc.rows as Record<string, unknown>[])[0].pay_date = "2027-01-05";
    },
    (doc) => {
      (doc.rows as Record<string, unknown>[])[0].pay_date_end = "2026-01-01";
    },
    (doc) => {
      (doc.rows as Record<string, unknown>[])[0].amount = 0;
    },
    (doc) => {
      (doc.rows as Record<string, unknown>[])[0].amount = "175";
    },
    (doc) => {
      (doc.rows as Record<string, unknown>[])[0].smuggled = "x";
    },
    (doc) => {
      doc.rows = [
        dividendRow(),
        dividendRow({ amount: 180 }),
      ];
    },
    (doc) => {
      doc.excluded = {};
    },
    (doc) => {
      doc.mode = "PROMOTED";
    },
  ];
  for (const mutate of mutations) {
    const value = await fixture("dividends");
    const response = await value.handler(
      request(await repayload(value, mutate)),
    );
    equal(response.status, 400, await response.clone().text());
    equal(value.backend.written.length, 0);
  }
});

Deno.test("fundamental fields and values are enforced", async () => {
  const mutations: Array<(doc: Record<string, unknown>) => void> = [
    (doc) => {
      delete (doc.fields as Record<string, unknown>).beta_5y;
    },
    (doc) => {
      (doc.fields as Record<string, unknown>).id = "x";
    },
    (doc) => {
      (doc.fields as Record<string, unknown>).fiscal_year = 1800;
    },
    (doc) => {
      (doc.fields as Record<string, unknown>).fiscal_year = 2024.5;
    },
    (doc) => {
      (doc.fields as Record<string, unknown>).bpa = "16.67";
    },
    (doc) => {
      (doc.fields as Record<string, unknown>).ext_name = "";
    },
    (doc) => {
      (doc.fields as Record<string, unknown>).shareholders = "{broken";
    },
    (doc) => {
      (doc.fields as Record<string, unknown>).shareholders = JSON.stringify([
        { name: "Holder", pct: 150 },
      ]);
    },
    (doc) => {
      doc.c_name = 5;
    },
  ];
  for (const mutate of mutations) {
    const value = await fixture("fundamentals");
    const response = await value.handler(
      request(await repayload(value, mutate)),
    );
    equal(response.status, 400, await response.clone().text());
    equal(value.backend.written.length, 0);
  }
});

Deno.test("missing, altered or ineligible archived evidence is refused", async () => {
  const value = await fixture("dividends");
  value.backend.archive = null;
  equal(
    (await (await value.handler(request(value.payload))).json()).code,
    "ARCHIVE_UNAVAILABLE",
  );
  equal(value.backend.written.length, 0);

  const altered = await fixture("dividends");
  const changed = new Uint8Array(altered.blob);
  changed[0] ^= 1;
  altered.backend.archive = changed;
  equal(
    (await (await altered.handler(request(altered.payload))).json()).code,
    "ARCHIVE_HASH_MISMATCH",
  );

  for (
    const update of [
      { execution: "RECORDED_REPLAY" },
      { authority: "PROMOTED" },
      { prediction_eligible: true },
      { kind: "quotes" },
      { provider_namespace: "feed_1111111111111111" },
    ]
  ) {
    const current = await fixture("dividends");
    const archive = await gzip({ ...current.envelope, ...update });
    current.backend.archive = archive;
    const doc = {
      ...current.doc,
      archive_sha256: await sha256(archive),
    };
    const text = JSON.stringify(doc);
    const response = await current.handler(request(JSON.stringify({
      document: text,
      sha256: await hash(text),
    })));
    equal(response.status, 503, await response.clone().text());
    equal(current.backend.written.length, 0);
  }
});

Deno.test("backend rejection and oversized bodies are bounded", async () => {
  const value = await fixture("dividends");
  value.backend.receipt = { status: "REJECTED" };
  equal(
    (await (await value.handler(request(value.payload))).json()).code,
    "INVALID_BACKEND_RECEIPT",
  );
  const oversized = await fixture("dividends");
  equal(
    (await oversized.handler(
      request(JSON.stringify({ padding: "x".repeat(5 * 1024 * 1024) })),
    )).status,
    413,
  );
  equal(oversized.backend.reads, 0);
});

Deno.test("REST adapter reads the digest path and calls the matching RPC", async () => {
  const calls: { url: string; init: RequestInit }[] = [];
  const digest = "a".repeat(64);
  const backend = new SupabaseProjectionBackend(
    "https://" + "a".repeat(20) + ".supabase.co",
    "sb_" + "secret_fixture",
    (url, init) => {
      calls.push({ url: String(url), init: init! });
      if (calls.length === 1) {
        return Promise.resolve(new Response(new Uint8Array([1])));
      }
      return Promise.resolve(
        Response.json({ status: "PUBLISHED", rows: 1 }, { status: 200 }),
      );
    },
  );
  equal(await backend.readArchive(digest), new Uint8Array([1]));
  const receipt = await backend.publish("dividends", "{}", digest);
  equal((receipt as Record<string, unknown>).status, "PUBLISHED");
  assert(
    calls[0].url.endsWith(
      "/storage/v1/object/private-market-evidence/sha256/aa/" + digest +
        ".json.gz",
    ),
  );
  assert(calls[1].url.endsWith("/rest/v1/rpc/publish_dividend_projection"));
  equal(JSON.parse(calls[1].init.body as string), {
    p_document: "{}",
    p_payload_sha256: digest,
  });
});

Deno.test("REST adapter distinguishes absent evidence from denied access", async () => {
  const absent = new SupabaseProjectionBackend(
    "https://" + "a".repeat(20) + ".supabase.co",
    "sb_" + "secret_fixture",
    () =>
      Promise.resolve(Response.json({ code: "NoSuchKey" }, { status: 404 })),
  );
  equal(await absent.readArchive("a".repeat(64)), null);
  for (const status of [400, 403, 500]) {
    const backend = new SupabaseProjectionBackend(
      "https://" + "a".repeat(20) + ".supabase.co",
      "sb_" + "secret_fixture",
      () =>
        Promise.resolve(Response.json({ code: "AccessDenied" }, { status })),
    );
    let rejected = false;
    try {
      await backend.readArchive("a".repeat(64));
    } catch (error) {
      rejected = error instanceof PublishError;
    }
    assert(rejected);
  }
});

Deno.test("real fundamental UPDATED receipt is acknowledged, including idempotent zero-change", async () => {
  for (const fields of [0, 3]) {
    const value = await fixture("fundamentals");
    value.backend.receipt = {
      status: "UPDATED",
      name: "Alpha",
      fields,
      fiscal_year: 2023,
      refreshed: false,
    };
    const response = await value.handler(request(value.payload));
    equal(response.status, 200, await response.clone().text());
    const receipt = await response.json();
    equal(receipt.status, "PUBLISHED");
    equal(receipt.kind, "fundamentals");
    equal(receipt.sha256, JSON.parse(value.payload).sha256);
  }
});

Deno.test("missing fundamental company is an explicit non-success", async () => {
  const value = await fixture("fundamentals");
  value.backend.receipt = { status: "MISSING", name: "Alpha" };
  const response = await value.handler(request(value.payload));
  equal(response.status, 409);
  equal((await response.json()).code, "TARGET_COMPANY_MISSING");
});

Deno.test("kind-specific SQL receipts reject wrong counts, identity, fields and status", async () => {
  const cases: Array<["dividends" | "fundamentals", unknown]> = [
    ["dividends", { status: "PUBLISHED" }],
    ["dividends", { status: "PUBLISHED", rows: 2, created: 1, updated: 0 }],
    ["dividends", { status: "PUBLISHED", rows: 1, created: 1, updated: 1 }],
    ["dividends", { status: "PUBLISHED", rows: 1, created: -1, updated: 0 }],
    ["fundamentals", { status: "PUBLISHED" }],
    ["fundamentals", {
      status: "UPDATED",
      name: "Other",
      fields: 0,
      fiscal_year: 2023,
      refreshed: false,
    }],
    ["fundamentals", {
      status: "UPDATED",
      name: "Alpha",
      fields: true,
      fiscal_year: 2023,
      refreshed: false,
    }],
    ["fundamentals", {
      status: "UPDATED",
      name: "Alpha",
      fields: 100,
      fiscal_year: 2023,
      refreshed: false,
    }],
    ["fundamentals", {
      status: "UPDATED",
      name: "Alpha",
      fields: 0,
      fiscal_year: 2024,
      refreshed: false,
    }],
    ["fundamentals", {
      status: "UPDATED",
      name: "Alpha",
      fields: 0,
      fiscal_year: 2023,
      refreshed: "false",
    }],
  ];
  for (const [kind, receipt] of cases) {
    const value = await fixture(kind);
    value.backend.receipt = receipt;
    const response = await value.handler(request(value.payload));
    equal(response.status, 503, await response.clone().text());
    equal((await response.json()).code, "INVALID_BACKEND_RECEIPT");
  }
});

Deno.test("recurring enrichment context uses its isolated versioned RPC", async () => {
  let called = "";
  const backend = new SupabaseProjectionBackend("https://abcdefghijklmnopqrst.supabase.co", "sb_secret_fixture", ((url: RequestInfo | URL) => {
    called = String(url);
    return Promise.resolve(new Response("{}", {status:200}));
  }) as typeof fetch, true);
  await backend.readContext("feed_0123456789abcdef", "a".repeat(64));
  if (!called.endsWith("/rpc/read_enrichment_context_recurring_v1")) throw new Error("unversioned RPC");
});
