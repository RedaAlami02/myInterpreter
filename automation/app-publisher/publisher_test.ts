import {
  createHandler,
  PublishBackend,
  PublishError,
  sha256,
} from "./publisher.ts";
import { SupabasePublishBackend } from "./supabase.ts";

const TOKEN = "app_publish_" + "a".repeat(64),
  PROVIDER = "feed_0123456789abcdef",
  RECEIVED = "2026-10-28T12:04:00+00:00",
  NOW = Date.parse("2026-10-28T12:05:00Z");
const IDS = { a: "a".repeat(64), b: "b".repeat(64), index: "c".repeat(64) };
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
async function hash(text: string) {
  return await sha256(new TextEncoder().encode(text));
}
function reportedTime() {
  return {
    text: "28/10/2026 14:00:00",
    date: "2026-10-28",
    timezone: "UNKNOWN",
    utc: null,
  };
}
function observation(
  id: string,
  identity: string,
  price: string,
  index: number,
) {
  return {
    observation_id: id,
    source_identity: identity,
    price_decimal: price,
    captured_at: RECEIVED,
    reported_time: reportedTime(),
    source_event_at: null,
    raw_row_index: index,
    source_date_matches_capture: true,
    price_basis: "REPORTED_QUOTE",
    source_timezone_known: false,
    authority: "UNPROMOTED",
  };
}
function candidateRow(
  asset: string,
  company: string | null,
  name: string,
  price: string,
  id: string,
  index: number,
) {
  return {
    asset_key: asset,
    company_id: company,
    c_name: name,
    symbol: name === "MASI" ? "MASI" : name.slice(-1),
    instrument_type: company === null ? "INDEX" : "STOCK",
    status: "REPORTED_DATE_ONLY",
    observed_price_decimal: price,
    display_price_decimal: price,
    captured_at: RECEIVED,
    reported_time: reportedTime(),
    source_event_at: null,
    price_basis: "REPORTED_QUOTE",
    portfolio_valuation_eligible: false,
    prediction_eligible: false,
    observations: [{
      observation_id: id,
      raw_row_index: index,
      price_decimal: price,
      captured_at: RECEIVED,
      reported_time: reportedTime(),
      source_event_at: null,
    }],
  };
}
function mapping() {
  return {
    contract: "private-app-mapping/v1",
    provider_namespace: PROVIDER,
    stocks: [
      {
        source_identity: "A",
        company_id: "a",
        asset_key: "company:a",
        c_name: "Company A",
        symbol: "A",
      },
      {
        source_identity: "B",
        company_id: "b",
        asset_key: "company:b",
        c_name: "Company B",
        symbol: "B",
      },
    ],
    indices: [{
      source_identity: "INDEX_MAIN",
      company_id: null,
      asset_key: "index:MASI",
      c_name: "MASI",
      symbol: "MASI",
    }],
  };
}
async function envelope() {
  const raw = new TextEncoder().encode('{"test":"synthetic"}'),
    digest = await sha256(raw);
  const captureId = await hash(JSON.stringify([PROVIDER, digest, RECEIVED]));
  return {
    contract: "private-acquisition/v2",
    provider_namespace: PROVIDER,
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
      received_at: RECEIVED,
      raw_hex: Array.from(raw, (x) => x.toString(16).padStart(2, "0")).join(""),
    }],
    market_frame: {
      contract: "private-market-frame/v2",
      captured_at: RECEIVED,
      market_date: "2026-10-28",
      completeness: "COMPLETE",
      views: {
        instruments: [],
        quotes: [
          observation(IDS.a, "A", "10.50", 0),
          observation(IDS.b, "B", "11.00", 1),
        ],
        indices: [observation(IDS.index, "INDEX_MAIN", "100.00", 0)],
        status: [],
      },
    },
  };
}
class MemoryBackend implements PublishBackend {
  reads = 0;
  written: { document: string; sha: string }[] = [];
  returnSha: string | null = null;
  constructor(public archive: Uint8Array | null) {}
  readArchive(_digest: string) {
    this.reads++;
    return Promise.resolve(this.archive);
  }
  publish(document: string, payloadSha: string) {
    this.written.push({ document, sha: payloadSha });
    return Promise.resolve(this.returnSha ?? payloadSha);
  }
}
class ApplicationBackend extends MemoryBackend {
  applicationWrites: { document: string; sha: string }[] = [];
  failOnce = false;
  publishApplicationRows(document: string, sha: string) {
    if (this.failOnce) {
      this.failOnce = false;
      return Promise.reject(new PublishError("PUBLISH_POLICY_REJECTED", 503));
    }
    this.applicationWrites.push({ document, sha });
    return Promise.resolve(sha);
  }
}
async function fixture() {
  const blob = await gzip(await envelope()), digest = await sha256(blob);
  const map = mapping(), mappingDocument = JSON.stringify(map);
  const mappingSha = await hash(mappingDocument);
  const candidate = {
    contract: "app-market-candidate/v1",
    mode: "SHADOW_ONLY",
    provider_namespace: PROVIDER,
    archive_sha256: digest,
    mapping_sha256: mappingSha,
    recipe_sha256: "d".repeat(64),
    captured_at: RECEIVED,
    as_of: "2026-10-28T12:04:30+00:00",
    source_execution: "CURRENT_ACQUISITION",
    market_date: "2026-10-28",
    identity_evidence: "NORMALIZER_IDS_VERIFIED",
    capture_max_age_seconds: 1200,
    source_max_age_seconds: 3600,
    acquisition_completeness: "COMPLETE",
    market_session_state: "UNKNOWN",
    rows: [
      candidateRow("company:a", "a", "Company A", "10.50", IDS.a, 0),
      candidateRow("company:b", "b", "Company B", "11.00", IDS.b, 1),
      candidateRow("index:MASI", null, "MASI", "100.00", IDS.index, 0),
    ],
    coverage: {},
    portfolio_valuation_eligible: false,
    prediction_eligible: false,
    candidate_sha256: "e".repeat(64),
  };
  const document = JSON.stringify(candidate);
  const payload = JSON.stringify({
    document,
    mapping_document: mappingDocument,
    mapping_sha256: mappingSha,
    sha256: await hash(document),
  });
  const backend = new MemoryBackend(blob);
  const handler = createHandler(backend, {
    enabled: true,
    tokenHash: await hash(TOKEN),
  }, () => NOW);
  return { backend, handler, payload, document, candidate, map, blob, digest };
}
async function applicationFixture() {
  const value = await fixture(), outer = JSON.parse(value.payload);
  const full = {
    contract: "app-price-rows/v1",
    mode: "SHADOW_ONLY",
    source_execution: "CURRENT_ACQUISITION",
    provider_namespace: PROVIDER,
    archive_sha256: value.digest,
    quote_payload_sha256: outer.sha256,
    captured_at: RECEIVED,
    as_of: value.candidate.as_of,
    application_fields_sha256: "f".repeat(64),
    acquisition_completeness: "COMPLETE",
    prediction_eligible: false,
    portfolio_valuation_eligible: false,
    excluded: [],
    rows: value.candidate.rows.map((row) => ({
      asset_key: row.asset_key,
      row: {
        c_name: row.c_name,
        pa: Number(row.display_price_decimal),
        date: RECEIVED,
        ...(row.instrument_type === "STOCK" ? { symbol: row.symbol } : {}),
      },
      provenance: {
        ...row,
        price_basis: "OBSERVED_QUOTE",
        price_decimal: row.display_price_decimal,
        fundamentals_available_at: row.instrument_type === "STOCK"
          ? "2026-10-27T12:00:00Z"
          : null,
      },
    })),
  };
  outer.application_document = JSON.stringify(full);
  outer.application_sha256 = await hash(outer.application_document);
  const backend = new ApplicationBackend(value.blob);
  const handler = createHandler(backend, {
    enabled: true,
    tokenHash: await hash(TOKEN),
    applicationRowsEnabled: true,
  }, () => NOW);
  return { ...value, outer, full, backend, handler };
}

Deno.test("full application rows require explicit enablement before any backend access", async () => {
  const value = await applicationFixture();
  const handler = createHandler(value.backend, {
    enabled: true,
    tokenHash: await hash(TOKEN),
  }, () => NOW);
  const response = await handler(request(JSON.stringify(value.outer)));
  equal(response.status, 503);
  equal((await response.json()).code, "APPLICATION_ROWS_DISABLED");
  equal(value.backend.reads, 0);
  equal(value.backend.written.length, 0);
});

Deno.test("full application publication returns exact hashes and retries the same two documents", async () => {
  const value = await applicationFixture(),
    payload = JSON.stringify(value.outer);
  value.backend.failOnce = true;
  equal((await value.handler(request(payload))).status, 503);
  equal(value.backend.written.length, 1);
  equal(value.backend.applicationWrites.length, 0);
  const response = await value.handler(request(payload));
  equal(response.status, 200);
  equal(
    (await response.json()).application_rows_sha256,
    value.outer.application_sha256,
  );
  equal(value.backend.written[0], value.backend.written[1]);
  equal(
    value.backend.applicationWrites[0].document,
    value.outer.application_document,
  );
});

Deno.test("application documents cannot change quote head, archive, time, eligibility or checksum", async () => {
  for (
    const key of [
      "quote_payload_sha256",
      "archive_sha256",
      "captured_at",
      "prediction_eligible",
    ]
  ) {
    const value = await applicationFixture();
    const full = {
      ...value.full,
      [key]: key === "prediction_eligible" ? true : "invalid",
    };
    value.outer.application_document = JSON.stringify(full);
    value.outer.application_sha256 = await hash(
      value.outer.application_document,
    );
    equal(
      (await value.handler(request(JSON.stringify(value.outer)))).status,
      400,
    );
    equal(value.backend.reads, 0);
    equal(value.backend.written.length, 0);
  }
  const value = await applicationFixture();
  value.outer.application_sha256 = "0".repeat(64);
  equal(
    (await value.handler(request(JSON.stringify(value.outer)))).status,
    400,
  );
  equal(value.backend.reads, 0);
});

Deno.test("application REST publication uses only its exact service RPC", async () => {
  const calls: string[] = [], sha = "a".repeat(64);
  const backend = new SupabasePublishBackend(
    "https://abcdefghijklmnopqrst.supabase.co",
    "sb_secret_fixture",
    ((url: string | URL | Request) => {
      calls.push(String(url));
      return Promise.resolve(Response.json(sha));
    }) as typeof fetch,
  );
  equal(await backend.publishApplicationRows("{}", sha), sha);
  equal(calls, [
    "https://abcdefghijklmnopqrst.supabase.co/rest/v1/rpc/publish_shadow_application_rows",
  ]);
});
type Fixture = Awaited<ReturnType<typeof fixture>>;
async function repayload(
  value: Fixture,
  mutate: (
    candidate: Record<string, unknown>,
    map: Record<string, unknown>,
  ) => void,
) {
  const candidate = JSON.parse(value.document);
  const map = JSON.parse(JSON.stringify(value.map));
  mutate(candidate, map);
  const mappingDocument = JSON.stringify(map);
  const mappingSha = await hash(mappingDocument);
  candidate.mapping_sha256 = mappingSha;
  const document = JSON.stringify(candidate);
  return JSON.stringify({
    document,
    mapping_document: mappingDocument,
    mapping_sha256: mappingSha,
    sha256: await hash(document),
  });
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

async function referenceFixture() {
  const value = await fixture(), source = await envelope(), id = "8".repeat(64);
  source.completeness = "INCOMPLETE";
  source.market_frame.completeness = "INCOMPLETE";
  source.market_frame.views.quotes = source.market_frame.views.quotes.filter((
    row,
  ) => row.source_identity !== "B");
  Object.assign(source.market_frame.views, {
    instruments: [{
      observation_id: id,
      source_identity: "B",
      reported_price_decimal: "21.25",
      captured_at: RECEIVED,
      raw_row_index: 1,
    }],
  });
  const blob = await gzip(source), digest = await sha256(blob);
  value.backend.archive = blob;
  const payload = await repayload(value, (candidate) => {
    candidate.contract = "app-market-candidate/v2";
    candidate.archive_sha256 = digest;
    candidate.acquisition_completeness = "INCOMPLETE";
    const rows = candidate.rows as Record<string, unknown>[];
    for (const row of rows) {
      row.reference_price = null;
      row.reference_conflict = false;
    }
    Object.assign(rows[1], {
      status: "MISSING_QUOTE",
      observed_price_decimal: null,
      display_price_decimal: null,
      captured_at: null,
      reported_time: null,
      source_event_at: null,
      observations: [],
      reference_price: {
        price_decimal: "21.25",
        price_basis: "INSTRUMENT_REFERENCE",
        captured_at: RECEIVED,
        source_event_at: null,
        reported_day: null,
        observations: [{
          observation_id: id,
          raw_row_index: 1,
          price_decimal: "21.25",
        }],
        prediction_eligible: false,
        portfolio_valuation_eligible: false,
      },
    });
  });
  return { value, payload, source };
}

Deno.test("v2 preserves catalog conflicts and rejects masked conflicts", async () => {
  const { value, payload, source } = await referenceFixture();
  const original = {
    observation_id: "8".repeat(64),
    source_identity: "B",
    reported_price_decimal: "21.25",
    captured_at: RECEIVED,
    raw_row_index: 1,
  };
  Object.assign(source.market_frame.views, {
    instruments: [original, {
      ...original,
      observation_id: "9".repeat(64),
      reported_price_decimal: "99.00",
      raw_row_index: 2,
    }],
  });
  const blob = await gzip(source);
  value.backend.archive = blob;
  const outer = JSON.parse(payload), document = JSON.parse(outer.document);
  document.archive_sha256 = await sha256(blob);
  document.rows[1].reference_price = null;
  document.rows[1].reference_conflict = true;
  outer.document = JSON.stringify(document);
  outer.sha256 = await hash(outer.document);
  equal((await value.handler(request(JSON.stringify(outer)))).status, 200);
  document.rows[1].reference_conflict = false;
  outer.document = JSON.stringify(document);
  outer.sha256 = await hash(outer.document);
  assert((await value.handler(request(JSON.stringify(outer)))).status !== 200);
  equal(value.backend.written.length, 1);
});

Deno.test("v2 publishes instrument fallback only when bound to the exact archive", async () => {
  const { value, payload } = await referenceFixture();
  const response = await value.handler(request(payload));
  equal(response.status, 200);
  equal(value.backend.written.length, 1);
  const document = JSON.parse(value.backend.written[0].document);
  equal(document.rows[1].display_price_decimal, null);
  equal(document.rows[1].reference_price.price_decimal, "21.25");
});
Deno.test("v2 rejects forged reference prices and omitted available references", async () => {
  for (
    const change of [
      "price",
      "identity",
      "position",
      "omitted",
      "trade_date",
      "authority",
    ]
  ) {
    const { value, payload } = await referenceFixture();
    const outer = JSON.parse(payload),
      document = JSON.parse(outer.document),
      ref = document.rows[1].reference_price;
    if (change === "price") {
      ref.price_decimal = "99.00";
      ref.observations[0].price_decimal = "99.00";
    }
    if (change === "identity") {
      ref.observations[0].observation_id = "9".repeat(64);
    }
    if (change === "position") ref.observations[0].raw_row_index = 2;
    if (change === "omitted") document.rows[1].reference_price = null;
    if (change === "trade_date") ref.reported_day = "2026-10-28";
    if (change === "authority") ref.portfolio_valuation_eligible = true;
    outer.document = JSON.stringify(document);
    outer.sha256 = await hash(outer.document);
    const response = await value.handler(request(JSON.stringify(outer)));
    assert(response.status !== 200);
    equal(value.backend.written.length, 0);
  }
});

Deno.test("verified candidate publishes once with an exact receipt and no payload", async () => {
  const value = await fixture();
  const response = await value.handler(request(value.payload));
  const receipt = await response.json();
  equal(response.status, 200);
  equal(receipt, {
    contract: "private-app-publish-receipt/v1",
    status: "PUBLISHED",
    sha256: JSON.parse(value.payload).sha256,
    captured_at: RECEIVED,
    prediction_eligible: false,
    portfolio_valuation_eligible: false,
  });
  equal(value.backend.reads, 1);
  equal(value.backend.written.length, 1);
  equal(value.backend.written[0].document, value.document);
  equal(response.headers.get("Cache-Control"), "no-store");
  assert(!JSON.stringify(receipt).includes("10.50"));
});
Deno.test("disabled or misconfigured publisher fails closed before any read", async () => {
  for (
    const config of [{ enabled: false, tokenHash: "a".repeat(64) }, {
      enabled: true,
      tokenHash: "",
    }]
  ) {
    const backend = new MemoryBackend(null);
    const handler = createHandler(backend, config, () => NOW);
    equal((await handler(request("{}"))).status, 503);
    equal(backend.reads, 0);
  }
});
Deno.test("unauthorized or malformed calls never read the archive", async () => {
  const value = await fixture();
  const attempts: [string, string, string, string, string, number][] = [
    [
      value.payload,
      "application/json",
      "app_publish_" + "b".repeat(64),
      "https://example.invalid/p",
      "POST",
      401,
    ],
    [
      value.payload,
      "application/json",
      "arc_write_" + "a".repeat(64),
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
    const response = await value.handler(
      request(body, type, token, url, method),
    );
    equal(response.status, status);
    equal(value.backend.reads, 0);
    equal(value.backend.written.length, 0);
  }
});
Deno.test("payload and mapping hashes must match their documents", async () => {
  const value = await fixture();
  const body = JSON.parse(value.payload);
  body.sha256 = "f".repeat(64);
  equal(
    (await (await value.handler(request(JSON.stringify(body)))).json()).code,
    "PAYLOAD_HASH_MISMATCH",
  );
  body.sha256 = await hash(body.document);
  body.mapping_sha256 = "f".repeat(64);
  equal(
    (await (await value.handler(request(JSON.stringify(body)))).json()).code,
    "MAPPING_HASH_MISMATCH",
  );
  equal(value.backend.reads, 0);
});
Deno.test("extra payload keys and unsigned documents are rejected", async () => {
  const value = await fixture();
  const parsed = JSON.parse(value.payload);
  for (
    const body of [
      { ...parsed, extra: true },
      { document: value.document, sha256: await hash(value.document) },
      { ...parsed, mapping_document: 5 },
    ]
  ) {
    const response = await value.handler(request(JSON.stringify(body)));
    equal(response.status, 400);
    equal(value.backend.reads, 0);
  }
});
Deno.test("candidate contract violations never read the archive", async () => {
  const mutations: Array<
    (c: Record<string, unknown>, m: Record<string, unknown>) => void
  > = [
    (c) => {
      c.mode = "PROMOTED";
    },
    (c) => {
      c.source_execution = "RECORDED_REPLAY";
    },
    (c) => {
      c.identity_evidence = "REPLAY_IDS_EXPLICITLY_DERIVED";
    },
    (c) => {
      c.prediction_eligible = true;
    },
    (c) => {
      c.portfolio_valuation_eligible = true;
    },
    (c) => {
      c.contract = "legacy";
    },
    (c) => {
      (c.rows as unknown[]).pop();
    },
    (c) => {
      (c.rows as Record<string, unknown>[])[0].company_id = "b";
    },
    (c) => {
      (c.rows as Record<string, unknown>[])[0].smuggled = "x";
    },
    (c) => {
      c.capture_max_age_seconds = 4000;
    },
    (c) => {
      c.market_date = "2026-10-27";
    },
    (c, m) => {
      (m.indices as Record<string, unknown>[])[0].asset_key = "index:OTHER";
    },
    (c, m) => {
      (m.stocks as Record<string, unknown>[])[0].company_id = "z";
    },
  ];
  for (const mutate of mutations) {
    const value = await fixture();
    const response = await value.handler(
      request(await repayload(value, mutate)),
    );
    equal(response.status, 400, await response.clone().text());
    equal(value.backend.reads, 0);
    equal(value.backend.written.length, 0);
  }
});
Deno.test("stale or future cutoffs are refused", async () => {
  const before = await fixture();
  const invalid = await (await before.handler(
    request(
      await repayload(before, (c) => {
        c.as_of = "2026-10-28T12:03:00+00:00";
      }),
    ),
  )).json();
  equal(invalid.code, "INVALID_DOCUMENT");
  equal(before.backend.reads, 0);
  const late = await fixture();
  const stale = await (await late.handler(
    request(
      await repayload(late, (c) => {
        c.as_of = "2026-10-28T13:00:00+00:00";
      }),
    ),
  )).json();
  equal(stale.code, "STALE_OR_FUTURE_CANDIDATE");
  equal(late.backend.reads, 0);
  const old = await fixture();
  const oldBody = await repayload(old, () => {});
  const expired = await (await createHandler(
    old.backend,
    { enabled: true, tokenHash: await hash(TOKEN) },
    () => Date.parse("2026-10-28T13:30:00Z"),
  )(request(oldBody))).json();
  equal(expired.code, "STALE_OR_FUTURE_CANDIDATE");
  equal(old.backend.reads, 0);
});
Deno.test("missing archive bytes never publish", async () => {
  const value = await fixture();
  value.backend.archive = null;
  const response = await value.handler(request(value.payload));
  equal(response.status, 503);
  equal((await response.json()).code, "ARCHIVE_UNAVAILABLE");
  equal(value.backend.written.length, 0);
});
Deno.test("altered or ineligible archived evidence is refused", async () => {
  const altered = await fixture();
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
      { provider_namespace: "feed_1111111111111111" },
      { kind: "depth" },
    ]
  ) {
    const value = await fixture();
    const archive = await gzip({ ...await envelope(), ...update });
    const archiveDigest = await sha256(archive);
    value.backend.archive = archive;
    const payload = await repayload(value, (c) => {
      c.archive_sha256 = archiveDigest;
    });
    const response = await value.handler(request(payload));
    equal(response.status, 503, await response.clone().text());
    equal(value.backend.written.length, 0);
  }
});
Deno.test("an archive cannot satisfy a different completeness", async () => {
  const value = await fixture();
  const response = await value.handler(
    request(
      await repayload(value, (c) => {
        c.acquisition_completeness = "INCOMPLETE";
      }),
    ),
  );
  equal(response.status, 503);
  equal(value.backend.written.length, 0);
});
Deno.test("candidate prices must be the archived observations, not substitutes", async () => {
  const mutations: Array<(c: Record<string, unknown>) => void> = [
    (c) => {
      const rows = c.rows as Record<string, unknown>[];
      (rows[0].observations as unknown[])[0] =
        (rows[1].observations as unknown[])[0];
    },
    (c) => {
      const row = (c.rows as Record<string, unknown>[])[0];
      (row.observations as Record<string, unknown>[])[0].price_decimal =
        "99.99";
      row.observed_price_decimal = "99.99";
      row.display_price_decimal = "99.99";
    },
    (c) => {
      const row = (c.rows as Record<string, unknown>[])[0];
      row.observations = [];
      row.status = "MISSING_QUOTE";
      row.observed_price_decimal = null;
      row.display_price_decimal = null;
      row.captured_at = null;
      row.reported_time = null;
    },
  ];
  for (const mutate of mutations) {
    const value = await fixture();
    const response = await value.handler(
      request(await repayload(value, mutate)),
    );
    equal(response.status, 503, await response.clone().text());
    equal(value.backend.written.length, 0);
  }
});
Deno.test("backend rejection surfaces a bounded error without inspectable detail", async () => {
  const value = await fixture();
  value.backend.returnSha = "f".repeat(64);
  const response = await value.handler(request(value.payload));
  equal(response.status, 503);
  equal((await response.json()).code, "INVALID_BACKEND_RECEIPT");
});
Deno.test("oversized bodies are bounded before parsing", async () => {
  const value = await fixture();
  const response = await value.handler(
    request(JSON.stringify({ padding: "x".repeat(9 * 1024 * 1024) })),
  );
  equal(response.status, 413);
  equal(value.backend.reads, 0);
});
Deno.test("REST adapter reads only the digest path and publishes through one RPC", async () => {
  const calls: { url: string; init: RequestInit }[] = [];
  const digest = "a".repeat(64);
  const backend = new SupabasePublishBackend(
    "https://" + "a".repeat(20) + ".supabase.co",
    "sb_" + "secret_fixture",
    (url, init) => {
      calls.push({ url: String(url), init: init! });
      if (calls.length === 1) {
        return Promise.resolve(new Response(new Uint8Array([1])));
      }
      return Promise.resolve(
        new Response(JSON.stringify(digest), { status: 200 }),
      );
    },
  );
  equal(await backend.readArchive(digest), new Uint8Array([1]));
  equal(await backend.publish("{}", digest), digest);
  assert(
    calls[0].url.endsWith(
      "/storage/v1/object/private-market-evidence/sha256/aa/" + digest +
        ".json.gz",
    ),
  );
  equal(calls[0].init.redirect, "error");
  assert(
    calls[1].url.endsWith("/rest/v1/rpc/publish_shadow_market_candidate"),
  );
  equal(JSON.parse(calls[1].init.body as string), {
    p_document: "{}",
    p_payload_sha256: digest,
  });
});
Deno.test("REST adapter distinguishes absent evidence from denied access", async () => {
  const absent = new SupabasePublishBackend(
    "https://" + "a".repeat(20) + ".supabase.co",
    "sb_" + "secret_fixture",
    () =>
      Promise.resolve(Response.json({ code: "NoSuchKey" }, { status: 404 })),
  );
  equal(await absent.readArchive("a".repeat(64)), null);
  for (const status of [400, 403, 500]) {
    const backend = new SupabasePublishBackend(
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

async function contextFixture(enabled = true) {
  const map = JSON.stringify(mapping()), mappingSha = await hash(map);
  const requestBody = {
    operation: "read_price_company_context",
    provider_namespace: PROVIDER,
    mapping_document: map,
    mapping_sha256: mappingSha,
    recipe_sha256: "b".repeat(64),
    application_fields_sha256: "c".repeat(64),
  };
  const result = {
    contract: "private-price-company-context/v1",
    provider_namespace: PROVIDER,
    mapping_sha256: mappingSha,
    recipe_sha256: "b".repeat(64),
    application_fields_sha256: "c".repeat(64),
    observed_at: new Date(NOW).toISOString(),
    price_companies: Object.fromEntries(["a", "b"].map((id) => [id, {
      name: "Company " + id.toUpperCase(),
      bpa: 2,
      tc5: null,
      roe: null,
      na: null,
      cp: null,
      net_profit: null,
      date: "2026-01-01T00:00:00Z",
      available_at: "2026-01-02T00:00:00Z",
    }])),
  };
  const calls: unknown[][] = [];
  const backend: PublishBackend = {
    readArchive: () => {
      throw new Error("No archive read permitted");
    },
    publish: () => {
      throw new Error("No publication permitted");
    },
    readPriceContext: (...args) => {
      calls.push(args);
      return Promise.resolve(result);
    },
  };
  const handler = createHandler(backend, {
    enabled: true,
    tokenHash: await hash(TOKEN),
    priceContextEnabled: enabled,
  }, () => NOW);
  return { map, requestBody, result, calls, handler };
}
Deno.test("price context is separately disabled and never consults another publisher", async () => {
  const v = await contextFixture(false),
    response = await v.handler(request(JSON.stringify(v.requestBody)));
  equal(response.status, 503);
  equal(v.calls.length, 0);
});
Deno.test("price context returns only exact mapped fields with original availability", async () => {
  const v = await contextFixture(),
    response = await v.handler(request(JSON.stringify(v.requestBody)));
  equal(response.status, 200);
  equal(await response.json(), v.result);
  equal(v.calls[0], [
    PROVIDER,
    v.map,
    v.requestBody.mapping_sha256,
    "b".repeat(64),
    "c".repeat(64),
  ]);
  equal(response.headers.get("Cache-Control"), "no-store");
});
Deno.test("price context rejects wrong mapping pins and extra request keys before backend access", async () => {
  const v = await contextFixture();
  for (
    const change of [
      { mapping_sha256: "d".repeat(64) },
      { provider_namespace: "feed_" + "f".repeat(16) },
      { recipe_sha256: "bad" },
      { application_fields_sha256: "bad" },
      { users: [] },
    ]
  ) {
    assert(
      (await v.handler(
        request(JSON.stringify({ ...v.requestBody, ...change })),
      )).status !== 200,
    );
  }
  equal(v.calls.length, 0);
});
Deno.test("price context never returns private extras, missing identities or future inputs", async () => {
  for (
    const changed of [
      "users",
      "private-column",
      "wrong-name",
      "missing",
      "future",
      "reverse-availability",
    ]
  ) {
    const v = await contextFixture();
    const result = v.result as unknown as Record<string, unknown>;
    const companies = result.price_companies as Record<
      string,
      Record<string, unknown>
    >;
    if (changed === "users") result.users = ["private-fixture-sentinel"];
    if (changed === "private-column") {
      companies.a.email = "private-fixture-sentinel";
    }
    if (changed === "wrong-name") companies.a.name = "private-fixture-sentinel";
    if (changed === "missing") delete companies.b;
    if (changed === "future") {
      companies.a.available_at = new Date(NOW + 1000).toISOString();
    }
    if (changed === "reverse-availability") {
      companies.a.available_at = "2000-01-01T00:00:00Z";
    }
    const response = await v.handler(request(JSON.stringify(v.requestBody)));
    assert(response.status !== 200);
    assert(!(await response.text()).includes("private-fixture-sentinel"));
  }
});
Deno.test("price context REST adapter uses only its one bounded readonly RPC", async () => {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const backend = new SupabasePublishBackend(
    "https://" + "a".repeat(20) + ".supabase.co",
    "sb_" + "secret_fixture",
    (url, init) => {
      calls.push({ url: String(url), init: init! });
      return Promise.resolve(Response.json({ fixture: true }));
    },
  );
  equal(
    await backend.readPriceContext(
      PROVIDER,
      "{}",
      "a".repeat(64),
      "b".repeat(64),
      "c".repeat(64),
    ),
    { fixture: true },
  );
  equal(calls.length, 1);
  assert(calls[0].url.endsWith("/rest/v1/rpc/read_price_company_context"));
  equal(JSON.parse(calls[0].init.body as string), {
    p_provider: PROVIDER,
    p_mapping_document: "{}",
    p_mapping_sha256: "a".repeat(64),
    p_recipe_sha256: "b".repeat(64),
    p_fields_sha256: "c".repeat(64),
  });
});

Deno.test("recurring price context uses its isolated versioned RPC", async () => {
  let called = "";
  const backend = new SupabasePublishBackend("https://abcdefghijklmnopqrst.supabase.co", "sb_secret_fixture", ((url: RequestInfo | URL) => {
    called = String(url);
    return Promise.resolve(new Response("{}", {status:200}));
  }) as typeof fetch, true);
  await backend.readPriceContext("feed_0123456789abcdef", "{}", "a".repeat(64), "b".repeat(64), "c".repeat(64));
  if (!called.endsWith("/rpc/read_price_company_context_recurring_v1")) throw new Error("unversioned RPC");
});
