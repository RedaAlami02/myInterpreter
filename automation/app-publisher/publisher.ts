// Staged publish boundary. Returns no payload, native identity or exception text.
export class PublishError extends Error {
  constructor(public code: string, public status = 400) {
    super(code);
  }
}
export interface PublishBackend {
  readPriceContext?(
    provider: string,
    mappingDocument: string,
    mappingSha: string,
    recipeSha: string,
    fieldsSha: string,
  ): Promise<unknown>;
  readArchive(digest: string): Promise<Uint8Array | null>;
  publish(document: string, payloadSha: string): Promise<string>;
  publishApplicationRows?(
    document: string,
    payloadSha: string,
  ): Promise<string>;
}
const MAX_BODY = 8 * 1024 * 1024;
const MAX_DOCUMENT = 2 * 1024 * 1024;
const MAX_MAPPING = 1024 * 1024;
const MAX_ARCHIVE = 8 * 1024 * 1024;
const MAX_EXPANDED = 24 * 1024 * 1024;
const hex = /^[a-f0-9]{64}$/;
const namespace = /^feed_[a-f0-9]{16}$/;
const decimal = /^[0-9]+(\.[0-9]+)?$/;
const statuses = new Set([
  "MISSING_QUOTE",
  "CONFLICTING_QUOTES",
  "STALE_OR_MISSING_SOURCE_DATE",
  "STALE_CAPTURE_DATE",
  "STALE_CAPTURE",
  "STALE_SOURCE_EVENT",
  "REPORTED_DATE_ONLY",
  "REPORTED_EVENT_VERIFIED",
]);
const rowKeys = [
  "asset_key",
  "c_name",
  "captured_at",
  "company_id",
  "display_price_decimal",
  "instrument_type",
  "observations",
  "observed_price_decimal",
  "portfolio_valuation_eligible",
  "prediction_eligible",
  "price_basis",
  "reported_time",
  "source_event_at",
  "status",
  "symbol",
];
const observationKeys = [
  "captured_at",
  "observation_id",
  "price_decimal",
  "raw_row_index",
  "reported_time",
  "source_event_at",
];
const referenceKeys = [
  "price_decimal",
  "price_basis",
  "captured_at",
  "source_event_at",
  "reported_day",
  "observations",
  "prediction_eligible",
  "portfolio_valuation_eligible",
];

function referencePrice(value: unknown): value is string {
  if (
    typeof value !== "string" || !/^[0-9]{1,13}(\.[0-9]{1,28})?$/.test(value) ||
    !/[1-9]/.test(value)
  ) return false;
  const [whole, fraction = ""] = value.split(".");
  const integer = BigInt(whole), maximum = 1000000000000n;
  return integer < maximum || (integer === maximum && !/[1-9]/.test(fraction));
}
const mappingKeys = [
  "asset_key",
  "c_name",
  "company_id",
  "source_identity",
  "symbol",
];

export async function sha256(body: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", body as BufferSource);
  return Array.from(
    new Uint8Array(digest),
    (x) => x.toString(16).padStart(2, "0"),
  ).join("");
}
export async function bounded(
  stream: ReadableStream<Uint8Array> | null,
  limit: number,
): Promise<Uint8Array> {
  if (!stream) throw new PublishError("EMPTY_BODY");
  const reader = stream.getReader(), chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > limit) {
        await reader.cancel();
        throw new PublishError("BODY_LIMIT", 413);
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const result = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }
  return result;
}
function stamp(value: unknown): number {
  if (
    typeof value !== "string" || value.length > 40 ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/
      .test(value) ||
    !Number.isFinite(Date.parse(value))
  ) throw new PublishError("INVALID_TIMESTAMP");
  const [year, month, day, hour, minute, second] = value.slice(0, 19).split(
    /[-T:]/,
  ).map(Number);
  const calendar = new Date(Date.UTC(year, month - 1, day));
  if (
    calendar.getUTCFullYear() !== year ||
    calendar.getUTCMonth() !== month - 1 ||
    calendar.getUTCDate() !== day || hour > 23 || minute > 59 || second > 59
  ) throw new PublishError("INVALID_TIMESTAMP");
  return Date.parse(value);
}
function integer(value: unknown, minimum: number, maximum: number): number {
  if (
    typeof value !== "number" || !Number.isInteger(value) || value < minimum ||
    value > maximum
  ) throw new PublishError("INVALID_FIELD");
  return value;
}
function text(
  value: unknown,
  maximum = 200,
  code = "INVALID_FIELD",
): string {
  if (
    typeof value !== "string" || value.length === 0 || value.length > maximum ||
    /[\u0000-\u001f]/.test(value)
  ) throw new PublishError(code);
  return value;
}
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new PublishError("INVALID_FIELD");
  }
  return value as Record<string, unknown>;
}
function exactKeys(value: Record<string, unknown>, keys: string[]) {
  const actual = Object.keys(value).sort().join(",");
  if (actual !== [...keys].sort().join(",")) {
    throw new PublishError("INVALID_FIELD");
  }
}
function localDay(moment: number) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Africa/Casablanca",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(moment));
  const part = (type: string) =>
    parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}
function reportedTime(value: unknown): string {
  const item = record(value);
  const day = text(item.date, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || item.timezone !== "UNKNOWN") {
    throw new PublishError("INVALID_FIELD");
  }
  text(item.text, 64);
  return day;
}
function sameTime(left: unknown, right: unknown) {
  if (left === null || left === undefined) {
    return (right ?? null) === null;
  }
  if (right === null || right === undefined) return false;
  const a = record(left), b = record(right);
  return a.text === b.text && a.date === b.date &&
    a.timezone === b.timezone && (a.utc ?? null) === (b.utc ?? null);
}

export function parseMapping(document: string) {
  if (document.length > MAX_MAPPING) {
    throw new PublishError("MAPPING_LIMIT", 413);
  }
  let value;
  try {
    value = JSON.parse(document);
  } catch (_error) {
    throw new PublishError("INVALID_MAPPING");
  }
  const mapping = record(value);
  if (
    mapping.contract !== "private-app-mapping/v1" ||
    typeof mapping.provider_namespace !== "string" ||
    !namespace.test(mapping.provider_namespace) ||
    !Array.isArray(mapping.stocks) || !Array.isArray(mapping.indices) ||
    mapping.indices.length !== 1
  ) throw new PublishError("INVALID_MAPPING");
  const stocks = mapping.stocks as unknown[];
  if (stocks.length + 1 > 2048) throw new PublishError("MAPPING_LIMIT", 413);
  const entries = new Map<string, Record<string, unknown>>();
  const identities = new Set<string>();
  const names = new Set<string>(), symbols = new Set<string>();
  const all: Array<[string, Record<string, unknown>]> = [
    ...stocks.map((row) =>
      ["stock", record(row)] as [string, Record<string, unknown>]
    ),
    [
      "index",
      record((mapping.indices as unknown[])[0]),
    ],
  ];
  for (const [kind, row] of all) {
    exactKeys(row, mappingKeys);
    const identity = text(row.source_identity, 200, "INVALID_MAPPING");
    const asset = text(row.asset_key, 300, "INVALID_MAPPING");
    const name = text(row.c_name, 200, "INVALID_MAPPING");
    const symbol = text(row.symbol, 200, "INVALID_MAPPING");
    if (kind === "stock") {
      const company = text(row.company_id, 200, "INVALID_MAPPING");
      if (asset !== "company:" + company) {
        throw new PublishError("INVALID_MAPPING");
      }
    } else if (
      row.company_id !== null || asset !== "index:MASI" ||
      row.c_name !== "MASI" || row.symbol !== "MASI"
    ) throw new PublishError("INVALID_MAPPING");
    if (
      identities.has(identity) || entries.has(asset) || names.has(name) ||
      symbols.has(symbol)
    ) throw new PublishError("AMBIGUOUS_MAPPING");
    identities.add(identity);
    entries.set(asset, row);
    names.add(name);
    symbols.add(symbol);
  }
  return {
    provider: mapping.provider_namespace as string,
    entries,
    identities,
    total: stocks.length + 1,
  };
}
type Mapping = ReturnType<typeof parseMapping>;

function archivedObservations(
  frame: Record<string, unknown>,
): Map<string, Record<string, unknown>> {
  const views = record(frame.views), found = new Map();
  for (const view of ["quotes", "indices"]) {
    if (!Array.isArray(views[view])) throw new PublishError("INVALID_ARCHIVE");
    for (const item of views[view] as unknown[]) {
      const row = record(item);
      const id = text(row.observation_id, 64, "INVALID_ARCHIVE");
      if (!hex.test(id) || found.has(id)) {
        throw new PublishError("INVALID_ARCHIVE");
      }
      found.set(id, {
        source_identity: text(row.source_identity, 200, "INVALID_ARCHIVE"),
        price_decimal: text(row.price_decimal, 64, "INVALID_ARCHIVE"),
        captured_at: text(row.captured_at, 40, "INVALID_ARCHIVE"),
        raw_row_index: row.raw_row_index,
        reported_time: row.reported_time ?? null,
        source_event_at: row.source_event_at ?? null,
      });
    }
  }
  return found;
}

function archivedReferences(frame: Record<string, unknown>) {
  const views = record(frame.views),
    found = new Map<string, Record<string, unknown>>();
  if (!Array.isArray(views.instruments)) {
    throw new PublishError("INVALID_ARCHIVE");
  }
  for (const value of views.instruments) {
    const row = record(value), id = text(row.observation_id, 64);
    if (!hex.test(id) || found.has(id)) {
      throw new PublishError("INVALID_ARCHIVE");
    }
    found.set(id, {
      source_identity: text(row.source_identity, 200),
      price_decimal: row.reported_price_decimal,
      captured_at: row.captured_at,
      raw_row_index: row.raw_row_index,
    });
  }
  return found;
}

export async function verifiedArchive(
  blob: Uint8Array,
  digest: string,
  expected: {
    provider: string;
    captured: number;
    completeness: string;
    marketDate: string;
    references?: boolean;
  },
) {
  if (blob.length > MAX_ARCHIVE || await sha256(blob) !== digest) {
    throw new PublishError("ARCHIVE_HASH_MISMATCH", 503);
  }
  let value;
  try {
    const stream = new Blob([blob as BlobPart]).stream().pipeThrough(
      new DecompressionStream("gzip"),
    );
    value = JSON.parse(
      new TextDecoder("utf-8", { fatal: true }).decode(
        await bounded(stream, MAX_EXPANDED),
      ),
    );
  } catch (error) {
    if (error instanceof PublishError) throw error;
    throw new PublishError("INVALID_ARCHIVE", 503);
  }
  const envelope = record(value);
  if (
    envelope.contract !== "private-acquisition/v2" ||
    envelope.provider_namespace !== expected.provider ||
    envelope.kind !== "quotes" ||
    envelope.execution !== "CURRENT_ACQUISITION" ||
    envelope.authority !== "UNPROMOTED" ||
    envelope.prediction_eligible !== false ||
    !["COMPLETE", "INCOMPLETE"].includes(envelope.completeness as string) ||
    envelope.completeness !== expected.completeness ||
    !Array.isArray(envelope.captures) || envelope.captures.length !== 1
  ) throw new PublishError("INELIGIBLE_ARCHIVE", 503);
  const capture = record((envelope.captures as unknown[])[0]);
  if (stamp(capture.received_at) !== expected.captured) {
    throw new PublishError("ARCHIVE_CAPTURE_MISMATCH", 503);
  }
  if (
    typeof capture.raw_hex !== "string" ||
    capture.raw_hex.length > 8 * 1024 * 1024 || capture.raw_hex.length % 2 ||
    !/^[a-f0-9]*$/.test(capture.raw_hex) ||
    typeof capture.sha256 !== "string" || !hex.test(capture.sha256) ||
    typeof capture.capture_id !== "string" || !hex.test(capture.capture_id)
  ) throw new PublishError("INVALID_RAW_CAPTURE", 503);
  const raw = new Uint8Array(capture.raw_hex.length / 2);
  const digit = (code: number) => code < 58 ? code - 48 : code - 87;
  for (let i = 0; i < raw.length; i++) {
    raw[i] = (digit(capture.raw_hex.charCodeAt(i * 2)) << 4) |
      digit(capture.raw_hex.charCodeAt(i * 2 + 1));
  }
  if (await sha256(raw) !== capture.sha256) {
    throw new PublishError("RAW_HASH_MISMATCH", 503);
  }
  if (
    await sha256(
      new TextEncoder().encode(JSON.stringify([
        expected.provider,
        capture.sha256,
        capture.received_at,
      ])),
    ) !== capture.capture_id
  ) throw new PublishError("CAPTURE_ID_MISMATCH", 503);
  const frame = record(envelope.market_frame);
  const slot = stamp(envelope.slot), completed = stamp(envelope.completed_at);
  if (
    frame.contract !== "private-market-frame/v2" ||
    stamp(frame.captured_at) !== expected.captured ||
    frame.market_date !== expected.marketDate ||
    frame.completeness !== envelope.completeness ||
    slot > expected.captured || expected.captured > completed
  ) throw new PublishError("ARCHIVE_FRAME_MISMATCH", 503);
  const observations = archivedObservations(frame);
  const references = expected.references
    ? archivedReferences(frame)
    : new Map<string, Record<string, unknown>>();
  for (const id of references.keys()) {
    if (observations.has(id)) throw new PublishError("INVALID_ARCHIVE");
  }
  return { observations, references };
}

export function validatedDocument(
  document: string,
  mapping: Mapping,
  mappingSha: string,
) {
  if (document.length > MAX_DOCUMENT) {
    throw new PublishError("DOCUMENT_LIMIT", 413);
  }
  let value;
  try {
    value = JSON.parse(document);
  } catch (_error) {
    throw new PublishError("INVALID_DOCUMENT");
  }
  const doc = record(value);
  if (
    !["app-market-candidate/v1", "app-market-candidate/v2"].includes(
      doc.contract as string,
    ) ||
    doc.mode !== "SHADOW_ONLY" ||
    doc.provider_namespace !== mapping.provider ||
    typeof doc.archive_sha256 !== "string" || !hex.test(doc.archive_sha256) ||
    doc.mapping_sha256 !== mappingSha || !hex.test(mappingSha) ||
    typeof doc.recipe_sha256 !== "string" || !hex.test(doc.recipe_sha256) ||
    doc.source_execution !== "CURRENT_ACQUISITION" ||
    doc.identity_evidence !== "NORMALIZER_IDS_VERIFIED" ||
    doc.market_session_state !== "UNKNOWN" ||
    doc.prediction_eligible !== false ||
    doc.portfolio_valuation_eligible !== false ||
    !["COMPLETE", "INCOMPLETE"].includes(
      doc.acquisition_completeness as string,
    ) ||
    !Array.isArray(doc.rows)
  ) throw new PublishError("INVALID_DOCUMENT");
  integer(doc.capture_max_age_seconds, 1, 3600);
  integer(doc.source_max_age_seconds, 1, 86400);
  const rows = (doc.rows as unknown[]).map((item) => record(item));
  if (rows.length !== mapping.total) {
    throw new PublishError("INCOMPLETE_UNIVERSE");
  }
  const captured = stamp(doc.captured_at), prepared = stamp(doc.as_of);
  if (captured > prepared || doc.market_date !== localDay(captured)) {
    throw new PublishError("INVALID_DOCUMENT");
  }
  const assets = new Set<string>();
  const withReferences = doc.contract === "app-market-candidate/v2";
  let indices = 0;
  for (const row of rows) {
    exactKeys(
      row,
      withReferences
        ? [...rowKeys, "reference_price", "reference_conflict"]
        : rowKeys,
    );
    const asset = text(row.asset_key, 300);
    const entry = mapping.entries.get(asset);
    if (!entry || assets.has(asset)) {
      throw new PublishError("EXACT_MAPPING_REQUIRED");
    }
    assets.add(asset);
    if (
      row.company_id !== entry.company_id || row.c_name !== entry.c_name ||
      row.symbol !== entry.symbol || row.price_basis !== "REPORTED_QUOTE" ||
      row.prediction_eligible !== false ||
      row.portfolio_valuation_eligible !== false ||
      typeof row.status !== "string" || !statuses.has(row.status) ||
      !Array.isArray(row.observations)
    ) throw new PublishError("INVALID_ROW");
    if (row.instrument_type === "INDEX") {
      indices++;
      if (row.company_id !== null) throw new PublishError("INVALID_ROW");
    } else if (row.instrument_type !== "STOCK") {
      throw new PublishError("INVALID_ROW");
    }
    if (
      withReferences && (typeof row.reference_conflict !== "boolean" ||
        (row.reference_conflict &&
          (row.status !== "MISSING_QUOTE" || row.instrument_type !== "STOCK" ||
            row.reference_price !== null)))
    ) {
      throw new PublishError("INVALID_REFERENCE_CONFLICT");
    }
    if (withReferences && row.reference_price !== null) {
      const ref = record(row.reference_price);
      exactKeys(ref, referenceKeys);
      if (
        row.status !== "MISSING_QUOTE" || row.instrument_type !== "STOCK" ||
        !referencePrice(ref.price_decimal) ||
        ref.price_basis !== "INSTRUMENT_REFERENCE" ||
        ref.captured_at !== doc.captured_at || ref.source_event_at !== null ||
        ref.reported_day !== null ||
        ref.prediction_eligible !== false ||
        ref.portfolio_valuation_eligible !== false ||
        !Array.isArray(ref.observations) || ref.observations.length < 1 ||
        ref.observations.length > 2048
      ) throw new PublishError("INVALID_REFERENCE_PRICE");
    }
    const evidence = row.observations as unknown[];
    if (row.status === "MISSING_QUOTE" || row.status === "CONFLICTING_QUOTES") {
      if (
        row.observed_price_decimal !== null ||
        row.display_price_decimal !== null || row.captured_at !== null ||
        row.reported_time !== null || row.source_event_at !== null
      ) throw new PublishError("INVALID_ROW");
      if (
        row.status === "MISSING_QUOTE"
          ? evidence.length !== 0
          : evidence.length < 2
      ) throw new PublishError("INVALID_ROW");
    } else {
      if (evidence.length !== 1) throw new PublishError("INVALID_ROW");
      const shown = row.status.startsWith("REPORTED_");
      if (
        typeof row.observed_price_decimal !== "string" ||
        !decimal.test(row.observed_price_decimal) ||
        row.captured_at !== doc.captured_at ||
        (shown
          ? row.display_price_decimal !== row.observed_price_decimal ||
            reportedTime(row.reported_time) !== doc.market_date
          : row.display_price_decimal !== null)
      ) throw new PublishError("INVALID_ROW");
      if (!shown) {
        // Optional in the recipe; absent stays absent in both records.
        if (row.reported_time !== null) reportedTime(row.reported_time);
      }
      if (row.source_event_at !== null) stamp(row.source_event_at);
    }
    for (const item of evidence) {
      const record_ = record(item);
      exactKeys(record_, observationKeys);
      if (!hex.test(text(record_.observation_id, 64))) {
        throw new PublishError("INVALID_ROW");
      }
      if (!decimal.test(text(record_.price_decimal, 64))) {
        throw new PublishError("INVALID_ROW");
      }
      stamp(record_.captured_at);
      integer(record_.raw_row_index, 0, 5000);
    }
  }
  if (indices !== 1 || assets.size !== mapping.total) {
    throw new PublishError("INCOMPLETE_UNIVERSE");
  }
  return { document: doc, rows, captured, prepared };
}

function bindReference(
  row: Record<string, unknown>,
  evidence: Map<string, Record<string, unknown>>,
  mapping: Mapping,
) {
  const entry = mapping.entries.get(row.asset_key as string)!;
  const expected = [...evidence.entries()].filter(([, value]) =>
    value.source_identity === entry.source_identity &&
    referencePrice(value.price_decimal)
  );
  const values = new Set(
    expected.map(([, value]) =>
      String(value.price_decimal).replace(/(\.[0-9]*?)0+$/, "$1").replace(
        /\.$/,
        "",
      ).replace(/^0+(?=\d)/, "")
    ),
  );
  if (
    row.reference_conflict !==
      (row.status === "MISSING_QUOTE" && row.instrument_type === "STOCK" &&
        values.size > 1)
  ) {
    throw new PublishError("ARCHIVE_REFERENCE_CONFLICT_MISMATCH", 503);
  }
  if (row.reference_price === null) {
    if (
      row.status === "MISSING_QUOTE" && row.instrument_type === "STOCK" &&
      values.size === 1
    ) {
      throw new PublishError("ARCHIVE_REFERENCE_OMITTED", 503);
    }
    return;
  }
  const ref = record(row.reference_price),
    observations = ref.observations as unknown[];
  if (
    values.size !== 1 || ref.price_decimal !== expected[0]?.[1].price_decimal ||
    observations.length !== expected.length
  ) {
    throw new PublishError("ARCHIVE_REFERENCE_MISMATCH", 503);
  }
  const seen = new Set<string>();
  const allowed = new Set(expected.map(([id]) => id));
  for (const value of observations) {
    const observation = record(value);
    exactKeys(observation, [
      "observation_id",
      "raw_row_index",
      "price_decimal",
    ]);
    const id = text(observation.observation_id, 64), saved = evidence.get(id);
    if (
      !saved || !allowed.has(id) || seen.has(id) ||
      saved.source_identity !== entry.source_identity ||
      saved.price_decimal !== observation.price_decimal ||
      saved.raw_row_index !== observation.raw_row_index ||
      saved.captured_at !== ref.captured_at
    ) throw new PublishError("ARCHIVE_REFERENCE_MISMATCH", 503);
    seen.add(id);
  }
}

function binding(
  row: Record<string, unknown>,
  evidence: Map<string, Record<string, unknown>>,
  mapping: Mapping,
) {
  const entry = mapping.entries.get(row.asset_key as string)!;
  const seen = new Set<string>();
  for (const item of row.observations as unknown[]) {
    const value = record(item);
    const id = value.observation_id as string;
    const archived = evidence.get(id);
    if (
      !archived || seen.has(id) ||
      archived.source_identity !== entry.source_identity ||
      archived.price_decimal !== value.price_decimal ||
      archived.captured_at !== value.captured_at ||
      archived.raw_row_index !== value.raw_row_index ||
      !sameTime(archived.reported_time, value.reported_time) ||
      (archived.source_event_at ?? null) !== (value.source_event_at ?? null) ||
      (row.observed_price_decimal !== null &&
        value.price_decimal !== row.observed_price_decimal)
    ) throw new PublishError("ARCHIVE_PRICE_MISMATCH", 503);
    seen.add(id);
  }
  return seen;
}

export function createHandler(
  backend: PublishBackend,
  config: {
    tokenHash: string;
    enabled: boolean;
    applicationRowsEnabled?: boolean;
    priceContextEnabled?: boolean;
  },
  clock = Date.now,
) {
  const json = (value: unknown, status = 200) =>
    new Response(JSON.stringify(value), {
      status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  return async (request: Request): Promise<Response> => {
    try {
      if (!config.enabled || !hex.test(config.tokenHash)) {
        throw new PublishError("PUBLISHER_DISABLED", 503);
      }
      const auth = request.headers.get("Authorization") ?? "";
      if (!/^Bearer app_publish_[a-f0-9]{64}$/.test(auth)) {
        throw new PublishError("UNAUTHORIZED", 401);
      }
      const actual = await sha256(new TextEncoder().encode(auth.slice(7)));
      let mismatch = 0;
      for (let i = 0; i < 64; i++) {
        mismatch |= actual.charCodeAt(i) ^ config.tokenHash.charCodeAt(i);
      }
      if (mismatch) throw new PublishError("UNAUTHORIZED", 401);
      if (
        request.method !== "POST" || new URL(request.url).search ||
        request.headers.get("Content-Type") !== "application/json"
      ) throw new PublishError("INVALID_REQUEST");
      const body = await bounded(request.body, MAX_BODY);
      let payload;
      try {
        payload = JSON.parse(
          new TextDecoder("utf-8", { fatal: true }).decode(body),
        );
      } catch (_error) {
        throw new PublishError("INVALID_PAYLOAD");
      }
      const value = record(payload);
      if (value.operation === "read_price_company_context") {
        if (!config.priceContextEnabled || !backend.readPriceContext) {
          throw new PublishError("PRICE_CONTEXT_DISABLED", 503);
        }
        exactKeys(value, [
          "operation",
          "provider_namespace",
          "mapping_document",
          "mapping_sha256",
          "recipe_sha256",
          "application_fields_sha256",
        ]);
        const provider = text(value.provider_namespace, 32);
        const mappingDocument = text(value.mapping_document, MAX_MAPPING);
        const mappingSha = text(value.mapping_sha256, 64);
        const recipeSha = text(value.recipe_sha256, 64);
        const fieldsSha = text(value.application_fields_sha256, 64);
        if (
          !namespace.test(provider) ||
          ![mappingSha, recipeSha, fieldsSha].every((v) => hex.test(v)) ||
          await sha256(new TextEncoder().encode(mappingDocument)) !== mappingSha
        ) {
          throw new PublishError("INVALID_CONTEXT_PINS");
        }
        const mapping = parseMapping(mappingDocument);
        if (mapping.provider !== provider) {
          throw new PublishError("INVALID_CONTEXT_PINS");
        }
        const result = record(
          await backend.readPriceContext(
            provider,
            mappingDocument,
            mappingSha,
            recipeSha,
            fieldsSha,
          ),
        );
        exactKeys(result, [
          "contract",
          "provider_namespace",
          "mapping_sha256",
          "recipe_sha256",
          "application_fields_sha256",
          "observed_at",
          "price_companies",
        ]);
        const observed = stamp(result.observed_at);
        if (
          result.contract !== "private-price-company-context/v1" ||
          result.provider_namespace !== provider ||
          result.mapping_sha256 !== mappingSha ||
          result.recipe_sha256 !== recipeSha ||
          result.application_fields_sha256 !== fieldsSha ||
          observed > clock() + 30000 ||
          observed < clock() - 600000
        ) throw new PublishError("INVALID_PRICE_CONTEXT", 503);
        const companies = record(result.price_companies);
        const expected = [...mapping.entries.values()].filter((row) =>
          row.company_id !== null
        );
        if (
          Object.keys(companies).sort().join(",") !==
            expected.map((row) => row.company_id).sort().join(",")
        ) {
          throw new PublishError("INVALID_PRICE_CONTEXT", 503);
        }
        for (const identity of expected) {
          const row = record(companies[String(identity.company_id)]);
          exactKeys(row, [
            "name",
            "bpa",
            "tc5",
            "roe",
            "na",
            "cp",
            "net_profit",
            "date",
            "available_at",
          ]);
          if (row.name !== identity.c_name) {
            throw new PublishError("INVALID_PRICE_CONTEXT", 503);
          }
          for (const key of ["bpa", "tc5", "roe", "na", "cp", "net_profit"]) {
            if (
              row[key] !== null &&
              (typeof row[key] !== "number" || !Number.isFinite(row[key]) ||
                Math.abs(row[key] as number) > 1e15)
            ) throw new PublishError("INVALID_PRICE_CONTEXT", 503);
          }
          for (const key of ["date", "available_at"]) {
            if (row[key] !== null && stamp(row[key]) > observed) {
              throw new PublishError("INVALID_PRICE_CONTEXT", 503);
            }
          }
          if (
            row.date !== null &&
            (row.available_at === null ||
              stamp(row.available_at) < stamp(row.date))
          ) {
            throw new PublishError("INVALID_PRICE_CONTEXT", 503);
          }
        }
        if (new TextEncoder().encode(JSON.stringify(result)).length > 524288) {
          throw new PublishError("CONTEXT_LIMIT", 413);
        }
        return json(result);
      }
      const withApplicationRows = Object.hasOwn(value, "application_document");
      if (
        Object.keys(value).sort().join(",") !==
          (withApplicationRows
            ? "application_document,application_sha256,document,mapping_document,mapping_sha256,sha256"
            : "document,mapping_document,mapping_sha256,sha256")
      ) throw new PublishError("INVALID_PAYLOAD");
      if (
        withApplicationRows &&
        (!config.applicationRowsEnabled || !backend.publishApplicationRows)
      ) {
        throw new PublishError("APPLICATION_ROWS_DISABLED", 503);
      }
      const { document, mapping_document: mappingDocument } = value;
      if (
        typeof document !== "string" || typeof mappingDocument !== "string" ||
        typeof value.sha256 !== "string" || !hex.test(value.sha256) ||
        typeof value.mapping_sha256 !== "string" ||
        !hex.test(value.mapping_sha256)
      ) throw new PublishError("INVALID_PAYLOAD");
      if (await sha256(new TextEncoder().encode(document)) !== value.sha256) {
        throw new PublishError("PAYLOAD_HASH_MISMATCH");
      }
      if (
        await sha256(new TextEncoder().encode(mappingDocument)) !==
          value.mapping_sha256
      ) throw new PublishError("MAPPING_HASH_MISMATCH");
      const mapping = parseMapping(mappingDocument);
      const checked = validatedDocument(
        document,
        mapping,
        value.mapping_sha256,
      );
      if (withApplicationRows) {
        if (
          typeof value.application_document !== "string" ||
          new TextEncoder().encode(value.application_document).length >
            MAX_DOCUMENT ||
          typeof value.application_sha256 !== "string" ||
          !hex.test(value.application_sha256) ||
          await sha256(new TextEncoder().encode(value.application_document)) !==
            value.application_sha256
        ) {
          throw new PublishError("INVALID_APPLICATION_ROWS");
        }
        const full = record(JSON.parse(value.application_document));
        if (
          full.contract !== "app-price-rows/v1" ||
          full.mode !== "SHADOW_ONLY" ||
          full.source_execution !== "CURRENT_ACQUISITION" ||
          full.provider_namespace !== mapping.provider ||
          full.quote_payload_sha256 !== value.sha256 ||
          full.archive_sha256 !== checked.document.archive_sha256 ||
          full.captured_at !== checked.document.captured_at ||
          full.prediction_eligible !== false ||
          full.portfolio_valuation_eligible !== false ||
          !Array.isArray(full.rows) || !Array.isArray(full.excluded) ||
          full.rows.length + full.excluded.length !== mapping.total
        ) {
          throw new PublishError("INVALID_APPLICATION_ROWS");
        }
      }
      const now = clock();
      if (
        checked.prepared > now + 30000 || checked.prepared < now - 300000 ||
        checked.captured < now - 1200000
      ) throw new PublishError("STALE_OR_FUTURE_CANDIDATE");
      const digest = checked.document.archive_sha256 as string;
      const archive = await backend.readArchive(digest);
      if (!archive) throw new PublishError("ARCHIVE_UNAVAILABLE", 503);
      const verified = await verifiedArchive(archive, digest, {
        provider: mapping.provider,
        captured: checked.captured,
        completeness: checked.document.acquisition_completeness as string,
        marketDate: checked.document.market_date as string,
        references: checked.document.contract === "app-market-candidate/v2",
      });
      const used = new Set<string>();
      for (const row of checked.rows) {
        if (checked.document.contract === "app-market-candidate/v2") {
          bindReference(row, verified.references, mapping);
        }
        for (const id of binding(row, verified.observations, mapping)) {
          if (used.has(id)) {
            throw new PublishError("ARCHIVE_PRICE_MISMATCH", 503);
          }
          used.add(id);
        }
      }
      if (used.size !== verified.observations.size) {
        throw new PublishError("ARCHIVE_COVERAGE_MISMATCH", 503);
      }
      if (await backend.publish(document, value.sha256) !== value.sha256) {
        throw new PublishError("INVALID_BACKEND_RECEIPT", 503);
      }
      if (
        withApplicationRows &&
        await backend.publishApplicationRows!(
            value.application_document as string,
            value.application_sha256 as string,
          ) !== value.application_sha256
      ) {
        throw new PublishError("INVALID_BACKEND_RECEIPT", 503);
      }
      return json({
        contract: "private-app-publish-receipt/v1",
        status: "PUBLISHED",
        sha256: value.sha256,
        captured_at: checked.document.captured_at,
        prediction_eligible: false,
        portfolio_valuation_eligible: false,
        ...(withApplicationRows
          ? { application_rows_sha256: value.application_sha256 }
          : {}),
      });
    } catch (error) {
      return json({
        status: "REJECTED",
        code: error instanceof PublishError ? error.code : "PUBLISH_FAILURE",
      }, error instanceof PublishError ? error.status : 503);
    }
  };
}
