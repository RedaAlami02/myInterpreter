// Staged projection publication boundary. Returns no payload or exception text.
export class PublishError extends Error {
  constructor(public code: string, public status = 400) {
    super(code);
  }
}
export interface ProjectionBackend {
  readContext?(provider: string, indexSha: string): Promise<unknown>;
  readArchive(digest: string): Promise<Uint8Array | null>;
  publish(
    kind: "dividends" | "fundamentals",
    document: string,
    payloadSha: string,
  ): Promise<unknown>;
}
const MAX_BODY = 4 * 1024 * 1024;
const MAX_DOCUMENT = 2 * 1024 * 1024;
const MAX_ARCHIVE = 8 * 1024 * 1024;
const MAX_EXPANDED = 24 * 1024 * 1024;
const hex = /^[a-f0-9]{64}$/;
const namespace = /^feed_[a-f0-9]{16}$/;
const decimal = /^[0-9]+(\.[0-9]+)?$/;
const dividendRowKeys = [
  "amount",
  "c_name",
  "confirmed",
  "ex_date",
  "frequency",
  "issuer",
  "pay_date",
  "pay_date_end",
  "type",
  "year",
];
const numericFields = [
  "bpa",
  "cp",
  "dpa",
  "ebit",
  "ebitda",
  "fcf",
  "na",
  "net_cash",
  "net_debt",
  "net_profit",
  "profit_margin",
  "revenue",
  "rev_growth_5y",
  "rnpg_est",
  "rnpg_growth_5y",
  "roe",
  "tc5",
  "total_assets",
  "beta_3y",
  "beta_5y",
];
const integerFields = ["fiscal_year", "fy_est"];
const textFields = ["description", "ext_name", "sector", "shareholders"];
const fieldKeys = [...numericFields, ...integerFields, ...textFields];

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
  return Date.parse(value);
}
function day(value: unknown): number {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    throw new PublishError("INVALID_DATE");
  }
  const [year, month, date] = value.split("-").map(Number);
  const calendar = new Date(Date.UTC(year, month - 1, date));
  if (
    calendar.getUTCFullYear() !== year ||
    calendar.getUTCMonth() !== month - 1 ||
    calendar.getUTCDate() !== date
  ) throw new PublishError("INVALID_DATE");
  return calendar.getTime();
}
function longText(value: unknown, maximum: number) {
  if (
    typeof value !== "string" || value.length === 0 || value.length > maximum ||
    /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(value)
  ) throw new PublishError("INVALID_FIELD");
}
function integer(value: unknown, minimum: number, maximum: number): number {
  if (
    typeof value !== "number" || !Number.isInteger(value) || value < minimum ||
    value > maximum
  ) throw new PublishError("INVALID_FIELD");
  return value;
}
function text(value: unknown, maximum = 200, code = "INVALID_FIELD"): string {
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
  if (
    Object.keys(value).sort().join(",") !== [...keys].sort().join(",")
  ) throw new PublishError("INVALID_FIELD");
}

function dividendRows(value: unknown) {
  if (!Array.isArray(value) || value.length > 2000) {
    throw new PublishError("INVALID_DOCUMENT");
  }
  const seen = new Set<string>();
  for (const item of value) {
    const row = record(item);
    exactKeys(row, dividendRowKeys);
    const cName = text(row.c_name, 200);
    text(row.issuer, 200);
    const year = integer(row.year, 1900, 9999);
    if (row.confirmed !== true && row.confirmed !== false) {
      throw new PublishError("INVALID_ROW");
    }
    const ex = row.ex_date === null ? null : day(row.ex_date);
    const pay = row.pay_date === null ? null : day(row.pay_date);
    const end = row.pay_date_end === null ? null : day(row.pay_date_end);
    const yearOf = (moment: number) => new Date(moment).getUTCFullYear();
    if (
      (pay !== null && yearOf(pay) !== year) ||
      (end !== null && yearOf(end) !== year) ||
      (ex !== null && yearOf(ex) !== year &&
        !(pay !== null && yearOf(ex) === year - 1)) ||
      (ex !== null && pay !== null && pay < ex) ||
      (end !== null && (pay === null || end < pay)) ||
      (row.confirmed === true && ex === null)
    ) throw new PublishError("INVALID_ROW");
    if (row.amount !== null) {
      if (
        typeof row.amount !== "number" || !Number.isFinite(row.amount) ||
        row.amount <= 0 || row.amount > 1e12
      ) throw new PublishError("INVALID_ROW");
    }
    for (const field of ["type", "frequency"]) {
      if (row[field] !== null) text(row[field], 100);
    }
    const key = JSON.stringify([cName, year, row.type]);
    if (seen.has(key)) throw new PublishError("DUPLICATE_ROW");
    seen.add(key);
  }
  return value.length;
}

function fundamentalFields(value: unknown) {
  const fields = record(value);
  exactKeys(fields, fieldKeys);
  for (const name of numericFields) {
    if (fields[name] === null) continue;
    if (
      typeof fields[name] !== "number" || !Number.isFinite(fields[name]) ||
      Math.abs(fields[name] as number) > 1e15
    ) throw new PublishError("INVALID_ROW");
  }
  for (const name of integerFields) {
    if (fields[name] !== null) integer(fields[name], 1900, 2100);
  }
  for (const name of textFields) {
    if (fields[name] === null) continue;
    const maximum = name === "shareholders" ? 4000 : 3800;
    if (name === "shareholders") {
      longText(fields[name], maximum);
      let holders;
      try {
        holders = JSON.parse(fields[name] as string);
      } catch {
        throw new PublishError("INVALID_ROW");
      }
      if (
        !Array.isArray(holders) || holders.length === 0 || holders.length > 100
      ) {
        throw new PublishError("INVALID_ROW");
      }
      for (const holder of holders) {
        const item = record(holder);
        exactKeys(item, ["name", "pct"]);
        text(item.name, 200);
        if (
          typeof item.pct !== "number" || !Number.isFinite(item.pct) ||
          item.pct <= 0 || item.pct > 100
        ) throw new PublishError("INVALID_ROW");
      }
    } else if (name === "description") {
      longText(fields[name], maximum);
    } else {
      text(fields[name], maximum);
    }
  }
  return fieldKeys.length;
}

export async function verifiedArchive(
  blob: Uint8Array,
  digest: string,
  expected: { provider: string; kind: string; symbol?: string },
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
    !["private-acquisition/v2", "private-acquisition/v3"].includes(
      envelope.contract as string,
    ) ||
    (envelope.contract === "private-acquisition/v3" &&
      (expected.kind !== "fundamentals" ||
        envelope.subject_key !== "symbol:" + expected.symbol)) ||
    (envelope.contract === "private-acquisition/v2" &&
      Object.hasOwn(envelope, "subject_key")) ||
    envelope.provider_namespace !== expected.provider ||
    envelope.kind !== expected.kind ||
    envelope.execution !== "CURRENT_ACQUISITION" ||
    envelope.authority !== "UNPROMOTED" ||
    envelope.prediction_eligible !== false ||
    !["COMPLETE", "INCOMPLETE"].includes(envelope.completeness as string) ||
    (expected.symbol !== undefined && envelope.symbol !== expected.symbol) ||
    !Array.isArray(envelope.captures) || envelope.captures.length === 0 ||
    envelope.captures.length > 30
  ) throw new PublishError("INELIGIBLE_ARCHIVE", 503);
  const identities = new Set<string>();
  let rawSize = 0;
  for (const item of envelope.captures as unknown[]) {
    const capture = record(item);
    if (
      typeof capture.raw_hex !== "string" ||
      capture.raw_hex.length % 2 || !/^[a-f0-9]*$/.test(capture.raw_hex) ||
      typeof capture.sha256 !== "string" || !hex.test(capture.sha256) ||
      typeof capture.capture_id !== "string" || !hex.test(capture.capture_id) ||
      identities.has(capture.capture_id)
    ) throw new PublishError("INVALID_RAW_CAPTURE", 503);
    identities.add(capture.capture_id);
    stamp(capture.received_at);
    rawSize += capture.raw_hex.length / 2;
    if (rawSize > MAX_ARCHIVE) {
      throw new PublishError("RAW_BATCH_LIMIT", 413);
    }
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
  }
  return envelope;
}

export function validatedDocument(document: string) {
  if (document.length > MAX_DOCUMENT) {
    throw new PublishError("DOCUMENT_LIMIT", 413);
  }
  let value;
  try {
    value = JSON.parse(document);
  } catch {
    throw new PublishError("INVALID_DOCUMENT");
  }
  const doc = record(value);
  const provider = text(doc.provider_namespace, 64);
  if (!namespace.test(provider)) throw new PublishError("INVALID_DOCUMENT");
  if (
    doc.mode !== "PROJECTION_ONLY" ||
    doc.source_execution !== "CURRENT_ACQUISITION" ||
    doc.prediction_eligible !== false ||
    doc.portfolio_valuation_eligible !== false ||
    !["COMPLETE", "INCOMPLETE"].includes(doc.completeness as string) ||
    typeof doc.archive_sha256 !== "string" || !hex.test(doc.archive_sha256) ||
    typeof doc.index_sha256 !== "string" || !hex.test(doc.index_sha256)
  ) throw new PublishError("INVALID_DOCUMENT");
  if (doc.contract === "dividend-projection/v1") {
    if (
      !Array.isArray(doc.rows) || !Array.isArray(doc.excluded) ||
      !Array.isArray(doc.unmatched)
    ) throw new PublishError("INVALID_DOCUMENT");
    return {
      kind: "dividends" as const,
      provider,
      count: dividendRows(doc.rows),
      doc,
    };
  }
  if (doc.contract === "fundamental-projection/v1") {
    const symbol = text(doc.symbol, 32);
    text(doc.c_name, 200);
    const count = fundamentalFields(doc.fields);
    return {
      kind: "fundamentals" as const,
      provider,
      count,
      symbol,
      doc,
    };
  }
  throw new PublishError("UNSUPPORTED_PROJECTION");
}

// SQL013 has distinct receipts for each RPC. Validate the real contract before
// normalizing to the stable outward projection-receipt/v1 acknowledgement.
function verifyReceipt(
  checked: ReturnType<typeof validatedDocument>,
  value: unknown,
) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new PublishError("INVALID_BACKEND_RECEIPT", 503);
  }
  const receipt = value as Record<string, unknown>;
  if (checked.kind === "dividends") {
    if (
      Object.keys(receipt).sort().join(",") !== "created,rows,status,updated" ||
      receipt.status !== "PUBLISHED" || receipt.rows !== checked.count ||
      !Number.isInteger(receipt.created) ||
      !Number.isInteger(receipt.updated) ||
      (receipt.created as number) < 0 || (receipt.updated as number) < 0 ||
      (receipt.created as number) + (receipt.updated as number) > checked.count
    ) {
      throw new PublishError("INVALID_BACKEND_RECEIPT", 503);
    }
    return;
  }
  if (
    receipt.status === "MISSING" && receipt.name === checked.doc.c_name &&
    Object.keys(receipt).sort().join(",") === "name,status"
  ) {
    throw new PublishError("TARGET_COMPANY_MISSING", 409);
  }
  const fields = checked.doc.fields as Record<string, unknown>;
  const maximumChanges =
    Object.values(fields).filter((value) => value !== null).length;
  if (
    Object.keys(receipt).sort().join(",") !==
      "fields,fiscal_year,name,refreshed,status" ||
    receipt.status !== "UPDATED" || receipt.name !== checked.doc.c_name ||
    !Number.isInteger(receipt.fields) || (receipt.fields as number) < 0 ||
    (receipt.fields as number) > maximumChanges ||
    receipt.fiscal_year !== fields.fiscal_year ||
    typeof receipt.refreshed !== "boolean"
  ) {
    throw new PublishError("INVALID_BACKEND_RECEIPT", 503);
  }
}

function contextReceipt(value: unknown, provider: string, indexSha: string) {
  const context = record(value);
  const keys = [
    "contract",
    "provider_namespace",
    "index_sha256",
    "observed_at",
    "companies",
  ];
  if (context.contract === "private-enrichment-context/v2") {
    keys.push("price_companies");
  }
  exactKeys(context, keys);
  if (
    !["private-enrichment-context/v1", "private-enrichment-context/v2"]
      .includes(context.contract as string) ||
    context.provider_namespace !== provider || context.index_sha256 !== indexSha
  ) {
    throw new PublishError("INVALID_CONTEXT_RECEIPT", 503);
  }
  const observed = stamp(context.observed_at);
  if (observed > Date.now() + 30000 || observed < Date.now() - 600000) {
    throw new PublishError("INVALID_CONTEXT_RECEIPT", 503);
  }
  const companies = record(context.companies);
  if (Object.keys(companies).length > 2000) {
    throw new PublishError("INVALID_CONTEXT_RECEIPT", 503);
  }
  for (const [name, value] of Object.entries(companies)) {
    text(name);
    const row = record(value);
    exactKeys(row, ["bpa", "sector", "fiscal_year"]);
    if (
      row.bpa !== null &&
      (typeof row.bpa !== "number" || !Number.isFinite(row.bpa) ||
        Math.abs(row.bpa) > 1e15)
    ) {
      throw new PublishError("INVALID_CONTEXT_RECEIPT", 503);
    }
    if (
      row.sector !== null &&
      (typeof row.sector !== "string" || row.sector.length > 200 ||
        /[\u0000-\u001f]/.test(row.sector))
    ) {
      throw new PublishError("INVALID_CONTEXT_RECEIPT", 503);
    }
    if (row.fiscal_year !== null) integer(row.fiscal_year, 1900, 2100);
  }
  if (context.contract === "private-enrichment-context/v2") {
    const prices = record(context.price_companies);
    if (Object.keys(prices).length > 2000) {
      throw new PublishError("INVALID_CONTEXT_RECEIPT", 503);
    }
    for (const [identifier, value] of Object.entries(prices)) {
      text(identifier);
      const row = record(value);
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
      if (typeof row.name !== "string" || !Object.hasOwn(companies, row.name)) {
        throw new PublishError("INVALID_CONTEXT_RECEIPT", 503);
      }
      for (const key of ["bpa", "tc5", "roe", "na", "cp", "net_profit"]) {
        if (
          row[key] !== null &&
          (typeof row[key] !== "number" || !Number.isFinite(row[key]) ||
            Math.abs(row[key] as number) > 1e15)
        ) {
          throw new PublishError("INVALID_CONTEXT_RECEIPT", 503);
        }
      }
      for (const key of ["date", "available_at"]) {
        if (row[key] !== null && stamp(row[key]) > Date.now() + 30000) {
          throw new PublishError("INVALID_CONTEXT_RECEIPT", 503);
        }
      }
    }
  }
  return context;
}

export function createHandler(
  backend: ProjectionBackend,
  config: { tokenHash: string; enabled: boolean; contextEnabled?: boolean },
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
      if (!/^Bearer proj_publish_[a-f0-9]{64}$/.test(auth)) {
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
      } catch {
        throw new PublishError("INVALID_PAYLOAD");
      }
      const value = record(payload);
      if (value.operation === "read_enrichment_context") {
        if (!config.contextEnabled || !backend.readContext) {
          throw new PublishError("CONTEXT_DISABLED", 503);
        }
        exactKeys(value, ["operation", "provider_namespace", "index_sha256"]);
        if (
          typeof value.provider_namespace !== "string" ||
          !namespace.test(value.provider_namespace) ||
          typeof value.index_sha256 !== "string" ||
          !hex.test(value.index_sha256)
        ) throw new PublishError("INVALID_PAYLOAD");
        return json(
          contextReceipt(
            await backend.readContext(
              value.provider_namespace,
              value.index_sha256,
            ),
            value.provider_namespace,
            value.index_sha256,
          ),
        );
      }
      if (Object.keys(value).sort().join(",") !== "document,sha256") {
        throw new PublishError("INVALID_PAYLOAD");
      }
      const document = value.document;
      if (
        typeof document !== "string" || typeof value.sha256 !== "string" ||
        !hex.test(value.sha256)
      ) throw new PublishError("INVALID_PAYLOAD");
      if (await sha256(new TextEncoder().encode(document)) !== value.sha256) {
        throw new PublishError("PAYLOAD_HASH_MISMATCH");
      }
      const checked = validatedDocument(document);
      const digest = checked.doc.archive_sha256 as string;
      const archive = await backend.readArchive(digest);
      if (!archive) throw new PublishError("ARCHIVE_UNAVAILABLE", 503);
      await verifiedArchive(archive, digest, {
        provider: checked.provider,
        kind: checked.kind,
        symbol: checked.kind === "fundamentals" ? checked.symbol : undefined,
      });
      const receipt = await backend.publish(
        checked.kind,
        document,
        value.sha256,
      );
      verifyReceipt(checked, receipt);
      return json({
        contract: "projection-receipt/v1",
        status: "PUBLISHED",
        kind: checked.kind,
        sha256: value.sha256,
        records: checked.count,
      });
    } catch (error) {
      return json({
        status: "REJECTED",
        code: error instanceof PublishError ? error.code : "PUBLISH_FAILURE",
      }, error instanceof PublishError ? error.status : 503);
    }
  };
}
