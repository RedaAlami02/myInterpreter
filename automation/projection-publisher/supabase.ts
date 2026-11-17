import { bounded, ProjectionBackend, PublishError } from "./publisher.ts";

// The privileged key lives only inside the managed function, never in CI.
export class SupabaseProjectionBackend implements ProjectionBackend {
  constructor(
    private url: string,
    private key: string,
    private fetcher = fetch,
    private recurring = false,
  ) {
    if (
      !/^https:\/\/[a-z0-9]{10,40}\.supabase\.co$/.test(url) ||
      !/^sb_secret_[A-Za-z0-9_-]+$/.test(key)
    ) throw new PublishError("INVALID_SERVER_CONFIGURATION", 503);
  }
  private async call(path: string, init: RequestInit) {
    try {
      return await this.fetcher(this.url + path, {
        ...init,
        redirect: "error",
        signal: AbortSignal.timeout(20000),
        headers: { apikey: this.key, ...init.headers },
      });
    } catch {
      throw new PublishError("PUBLISH_BACKEND_UNAVAILABLE", 503);
    }
  }
  async readArchive(digest: string) {
    if (!/^[a-f0-9]{64}$/.test(digest)) {
      throw new PublishError("INVALID_ARCHIVE_DIGEST");
    }
    const path = "/storage/v1/object/private-market-evidence/sha256/" +
      digest.slice(0, 2) + "/" + digest + ".json.gz";
    const response = await this.call(path, { method: "GET" });
    if (!response.ok) {
      let error;
      try {
        error = JSON.parse(
          new TextDecoder().decode(await bounded(response.body, 4096)),
        );
      } catch {
        throw new PublishError("ARCHIVE_READ_FAILED", 503);
      }
      if (
        response.status === 404 &&
        (error?.code === "NoSuchKey" ||
          (error?.error === "not_found" && !error?.code))
      ) return null;
      throw new PublishError("ARCHIVE_READ_FAILED", 503);
    }
    return await bounded(response.body, 8 * 1024 * 1024);
  }
  async readContext(provider: string, indexSha: string) {
    const response = await this.call("/rest/v1/rpc/read_enrichment_context" + (this.recurring ? "_recurring_v1" : ""), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ p_provider: provider, p_index_sha256: indexSha }),
    });
    if (!response.ok) {
      await response.body?.cancel();
      throw new PublishError("CONTEXT_POLICY_REJECTED", 503);
    }
    try {
      return JSON.parse(
        new TextDecoder("utf-8", { fatal: true }).decode(
          await bounded(response.body, 524288),
        ),
      );
    } catch {
      throw new PublishError("INVALID_CONTEXT_RECEIPT", 503);
    }
  }
  async publish(
    kind: "dividends" | "fundamentals",
    document: string,
    payloadSha: string,
  ) {
    const rpc = kind === "dividends"
      ? "publish_dividend_projection"
      : "publish_fundamental_projection";
    const response = await this.call("/rest/v1/rpc/" + rpc + (this.recurring ? "_recurring_v1" : ""), {
      method: "POST",
      body: JSON.stringify({
        p_document: document,
        p_payload_sha256: payloadSha,
      }),
      headers: { "Content-Type": "application/json" },
    });
    if (!response.ok) {
      await response.body?.cancel();
      throw new PublishError("PROJECTION_POLICY_REJECTED", 503);
    }
    let value;
    try {
      value = JSON.parse(
        new TextDecoder().decode(await bounded(response.body, 4096)),
      );
    } catch {
      throw new PublishError("INVALID_BACKEND_RECEIPT", 503);
    }
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new PublishError("INVALID_BACKEND_RECEIPT", 503);
    }
    return value;
  }
}
