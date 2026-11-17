// Write-only archive boundary. No provider bindings, user data APIs or logging.
export class GatewayError extends Error {
  constructor(public code: string, public status = 400) {
    super(code);
  }
}
export type Reservation = {
  state: "RESERVED" | "STORED";
  bucket: string;
  object_path: string;
};
export interface Backend {
  officialComplete?(provider: string, digest: string, documentSha: string): Promise<boolean>;
  reserve(metadata: Record<string, unknown>): Promise<Reservation>;
  read(location: Reservation): Promise<Uint8Array | null>;
  put(location: Reservation, body: Uint8Array): Promise<void>;
  finalize(digest: string): Promise<void>;
  complete(provider: string, kind: string, slot: string): Promise<boolean>;
  completeSubject?(
    provider: string,
    kind: string,
    slot: string,
    subject: string,
  ): Promise<boolean>;
  finalizeSubject?(digest: string, subject: string): Promise<void>;
  admitSubject?(
    provider: string,
    subject: string,
    projection: boolean,
  ): Promise<boolean>;
  admit?(
    provider: string,
    kind: string,
    slot: string,
    shadow: boolean,
    projection: boolean,
  ): Promise<boolean>;
}
const MAX_GZIP = 8 * 1024 * 1024, MAX_JSON = 24 * 1024 * 1024;
const kinds = ["quotes", "depth", "fundamentals", "dividends"];
const hex = /^[a-f0-9]{64}$/;
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
  if (!stream) throw new GatewayError("EMPTY_BODY");
  const reader = stream.getReader(), chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > limit) {
        await reader.cancel();
        throw new GatewayError("BODY_LIMIT", 413);
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
  ) throw new GatewayError("INVALID_TIMESTAMP");
  const [year, month, day, hour, minute, second] = value.slice(0, 19).split(
    /[-T:]/,
  ).map(Number);
  const calendar = new Date(Date.UTC(year, month - 1, day));
  if (
    calendar.getUTCFullYear() !== year ||
    calendar.getUTCMonth() !== month - 1 ||
    calendar.getUTCDate() !== day || hour > 23 || minute > 59 || second > 59
  ) {
    throw new GatewayError("INVALID_TIMESTAMP");
  }
  return Date.parse(value);
}
function logical(value: Record<string, unknown>) {
  if (
    typeof value.provider_namespace !== "string" ||
    !/^feed_[a-f0-9]{16}$/.test(value.provider_namespace) ||
    !kinds.includes(value.kind as string)
  ) throw new GatewayError("INVALID_NAMESPACE_OR_KIND");
  stamp(value.slot);
}
async function metadata(body: Uint8Array, now: number) {
  let value;
  try {
    const stream = new Blob([body as BlobPart]).stream().pipeThrough(
      new DecompressionStream("gzip"),
    );
    value = JSON.parse(
      new TextDecoder("utf-8", { fatal: true }).decode(
        await bounded(stream, MAX_JSON),
      ),
    );
  } catch (error) {
    if (error instanceof GatewayError) throw error;
    throw new GatewayError("INVALID_GZIP_ENVELOPE");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new GatewayError("INVALID_ENVELOPE");
  }
  logical(value);
  if (
    !["private-acquisition/v2", "private-acquisition/v3"].includes(
      value.contract,
    ) ||
    value.execution !== "CURRENT_ACQUISITION" ||
    value.authority !== "UNPROMOTED" || value.prediction_eligible !== false ||
    !["COMPLETE", "INCOMPLETE"].includes(value.completeness) ||
    !Array.isArray(value.captures) ||
    value.captures.length > 2000 ||
    (value.completeness === "COMPLETE" && value.captures.length === 0)
  ) {
    throw new GatewayError("INELIGIBLE_ENVELOPE");
  }
  if (value.contract === "private-acquisition/v3") {
    if (
      value.kind !== "fundamentals" || typeof value.symbol !== "string" ||
      !/^[A-Z0-9][A-Z0-9._-]{0,31}$/.test(value.symbol) ||
      value.subject_key !== "symbol:" + value.symbol
    ) {
      throw new GatewayError("INVALID_ARCHIVE_SUBJECT");
    }
  } else if (Object.hasOwn(value, "subject_key")) {
    throw new GatewayError("INVALID_ARCHIVE_SUBJECT");
  }
  const completed = stamp(value.completed_at), slot = stamp(value.slot);
  if (completed < slot || completed > now + 30000) {
    throw new GatewayError("INVALID_CAPTURE_WINDOW");
  }
  let rawSize = 0;
  const captureIds = new Set();
  for (const capture of value.captures) {
    if (
      !capture || typeof capture !== "object" ||
      typeof capture.raw_hex !== "string" ||
      capture.raw_hex.length > 8 * 1024 * 1024 || capture.raw_hex.length % 2 ||
      !/^[a-f0-9]*$/.test(capture.raw_hex) ||
      !hex.test(capture.sha256) ||
      !hex.test(capture.capture_id) || captureIds.has(capture.capture_id)
    ) {
      throw new GatewayError("INVALID_RAW_CAPTURE");
    }
    captureIds.add(capture.capture_id);
    const received = stamp(capture.received_at);
    if (received < slot || received > completed) {
      throw new GatewayError("INVALID_CAPTURE_WINDOW");
    }
    rawSize += capture.raw_hex.length / 2;
    if (rawSize > MAX_GZIP) throw new GatewayError("RAW_BATCH_LIMIT", 413);
    // Avoid millions of temporary two-character strings near the body limit.
    const raw = new Uint8Array(capture.raw_hex.length / 2);
    const digit = (code: number) => code < 58 ? code - 48 : code - 87;
    for (let i = 0; i < raw.length; i++) {
      raw[i] = (digit(capture.raw_hex.charCodeAt(i * 2)) << 4) |
        digit(capture.raw_hex.charCodeAt(i * 2 + 1));
    }
    if (await sha256(raw) !== capture.sha256) {
      throw new GatewayError("RAW_HASH_MISMATCH");
    }
    const identity = await sha256(new TextEncoder().encode(JSON.stringify([
      value.provider_namespace,
      capture.sha256,
      capture.received_at,
    ])));
    if (identity !== capture.capture_id) {
      throw new GatewayError("CAPTURE_ID_MISMATCH");
    }
  }
  return {
    p_digest: await sha256(body),
    p_provider: value.provider_namespace,
    p_kind: value.kind,
    p_slot: value.slot,
    p_completed_at: value.completed_at,
    p_completeness: value.completeness,
    p_bytes: body.length,
    ...(value.contract === "private-acquisition/v3"
      ? { p_subject_key: value.subject_key }
      : {}),
  };
}
export function createHandler(
  backend: Backend,
  config: { tokenHash: string; enabled: boolean; subjectEnabled?: boolean },
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
        throw new GatewayError("ARCHIVE_DISABLED", 503);
      }
      const auth = request.headers.get("Authorization") ?? "";
      if (!/^Bearer arc_write_[a-f0-9]{64}$/.test(auth)) {
        throw new GatewayError("UNAUTHORIZED", 401);
      }
      const actual = await sha256(new TextEncoder().encode(auth.slice(7)));
      let mismatch = 0;
      for (let i = 0; i < 64; i++) {
        mismatch |= actual.charCodeAt(i) ^ config.tokenHash.charCodeAt(i);
      }
      if (mismatch) throw new GatewayError("UNAUTHORIZED", 401);
      if (request.method !== "POST" || new URL(request.url).search) {
        throw new GatewayError("INVALID_REQUEST");
      }
      const type = request.headers.get("Content-Type");
      if (type === "application/json") {
        let value;
        try {
          value = JSON.parse(
            new TextDecoder().decode(await bounded(request.body, 1024)),
          );
        } catch {
          throw new GatewayError("INVALID_STATUS_REQUEST");
        }
        if (value?.operation === "official_close_status") {
          if (!backend.officialComplete || Object.keys(value).sort().join(",") !== "archive_sha256,document_sha256,operation,provider_namespace"
              || !/^feed_[a-f0-9]{16}$/.test(value.provider_namespace) || !hex.test(value.archive_sha256) || !hex.test(value.document_sha256)) throw new GatewayError("INVALID_STATUS_REQUEST");
          return json({contract:"private-archive-receipt/v1",complete:await backend.officialComplete(value.provider_namespace,value.archive_sha256,value.document_sha256)});
        }
        if (value?.operation === "acquisition_admission") {
          if (!backend.admit) {
            throw new GatewayError("ACQUISITION_ADMISSION_UNAVAILABLE", 503);
          }
          if (
            Object.keys(value).sort().join(",") !==
              "kind,operation,projection,provider_namespace,shadow,slot" ||
            !["quotes", "depth", "dividends"].includes(value.kind) ||
            typeof value.shadow !== "boolean" ||
            typeof value.projection !== "boolean" ||
            (value.shadow && value.kind !== "quotes") ||
            (value.projection && !["quotes", "dividends"].includes(value.kind))
          ) {
            throw new GatewayError("INVALID_STATUS_REQUEST");
          }
          logical(value);
          return json({
            contract: "private-archive-receipt/v1",
            admitted: await backend.admit(
              value.provider_namespace,
              value.kind,
              value.slot,
              value.shadow,
              value.projection,
            ),
          });
        }
        if (value?.operation === "subject_acquisition_admission") {
          if (!config.subjectEnabled || !backend.admitSubject) {
            throw new GatewayError("SUBJECT_ARCHIVE_DISABLED", 503);
          }
          if (
            Object.keys(value).sort().join(",") !==
              "operation,projection,provider_namespace,subject_key" ||
            typeof value.provider_namespace !== "string" ||
            !/^feed_[a-f0-9]{16}$/.test(value.provider_namespace) ||
            typeof value.subject_key !== "string" ||
            !/^symbol:[A-Z0-9][A-Z0-9._-]{0,31}$/.test(value.subject_key) ||
            typeof value.projection !== "boolean"
          ) throw new GatewayError("INVALID_STATUS_REQUEST");
          return json({
            contract: "private-archive-receipt/v1",
            admitted: await backend.admitSubject(
              value.provider_namespace,
              value.subject_key,
              value.projection,
            ),
          });
        }
        if (
          !value ||
          !["slot_complete", "subject_slot_complete"].includes(
            value.operation,
          ) ||
          Object.keys(value).sort().join(",") !==
            (value.operation === "subject_slot_complete"
              ? "kind,operation,provider_namespace,slot,subject_key"
              : "kind,operation,provider_namespace,slot")
        ) throw new GatewayError("INVALID_STATUS_REQUEST");
        logical(value);
        if (value.operation === "subject_slot_complete") {
          if (
            !config.subjectEnabled || !backend.completeSubject ||
            !backend.finalizeSubject
          ) {
            throw new GatewayError("SUBJECT_ARCHIVE_DISABLED", 503);
          }
          if (
            value.kind !== "fundamentals" ||
            typeof value.subject_key !== "string" ||
            !/^symbol:[A-Z0-9][A-Z0-9._-]{0,31}$/.test(value.subject_key) ||
            !backend.completeSubject
          ) {
            throw new GatewayError("INVALID_ARCHIVE_SUBJECT");
          }
          return json({
            contract: "private-archive-receipt/v1",
            complete: await backend.completeSubject(
              value.provider_namespace,
              value.kind,
              value.slot,
              value.subject_key,
            ),
          });
        }
        return json({
          contract: "private-archive-receipt/v1",
          complete: await backend.complete(
            value.provider_namespace,
            value.kind,
            value.slot,
          ),
        });
      }
      if (type !== "application/gzip") {
        throw new GatewayError("INVALID_CONTENT_TYPE", 415);
      }
      const body = await bounded(request.body, MAX_GZIP);
      const meta = await metadata(body, clock());
      if (
        meta.p_subject_key !== undefined &&
        (!config.subjectEnabled || !backend.completeSubject ||
          !backend.finalizeSubject)
      ) {
        throw new GatewayError("SUBJECT_ARCHIVE_DISABLED", 503);
      }
      const reserved = await backend.reserve(meta);
      let saved = await backend.read(reserved);
      if (!saved) {
        if (reserved.state === "STORED") {
          throw new GatewayError("STORED_OBJECT_MISSING", 503);
        }
        await backend.put(reserved, body);
        saved = await backend.read(reserved);
      }
      if (
        !saved || saved.length !== body.length ||
        await sha256(saved) !== meta.p_digest
      ) {
        throw new GatewayError("ARCHIVE_READBACK_MISMATCH", 503);
      }
      if (meta.p_subject_key !== undefined) {
        if (!backend.finalizeSubject) {
          throw new GatewayError("SUBJECT_ARCHIVE_NOT_CONFIGURED", 503);
        }
        await backend.finalizeSubject(
          meta.p_digest as string,
          meta.p_subject_key as string,
        );
      } else await backend.finalize(meta.p_digest as string);
      return json({
        contract: "private-archive-receipt/v1",
        status: "STORED",
        sha256: meta.p_digest,
        bytes: body.length,
        prediction_eligible: false,
      });
    } catch (error) {
      return json({
        status: "REJECTED",
        code: error instanceof GatewayError ? error.code : "ARCHIVE_FAILURE",
      }, error instanceof GatewayError ? error.status : 503);
    }
  };
}
