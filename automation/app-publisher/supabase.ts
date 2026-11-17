import { bounded, PublishBackend, PublishError } from "./publisher.ts";

// The privileged key lives only inside the managed function, never in CI.
export class SupabasePublishBackend implements PublishBackend {
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
      // A missing bucket or denied read must never look like absent evidence.
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
  async readPriceContext(
    provider: string,
    mappingDocument: string,
    mappingSha: string,
    recipeSha: string,
    fieldsSha: string,
  ) {
    const response = await this.call(
      "/rest/v1/rpc/read_price_company_context" + (this.recurring ? "_recurring_v1" : ""),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          p_provider: provider,
          p_mapping_document: mappingDocument,
          p_mapping_sha256: mappingSha,
          p_recipe_sha256: recipeSha,
          p_fields_sha256: fieldsSha,
        }),
      },
    );
    if (!response.ok) {
      await response.body?.cancel();
      throw new PublishError("PRICE_CONTEXT_POLICY_REJECTED", 503);
    }
    try {
      return JSON.parse(
        new TextDecoder().decode(await bounded(response.body, 524288)),
      );
    } catch {
      throw new PublishError("INVALID_PRICE_CONTEXT", 503);
    }
  }
  async publish(document: string, payloadSha: string) {
    return await this.publishRpc(
      "publish_shadow_market_candidate",
      document,
      payloadSha,
    );
  }
  async publishApplicationRows(document: string, payloadSha: string) {
    return await this.publishRpc(
      "publish_shadow_application_rows",
      document,
      payloadSha,
    );
  }
  private async publishRpc(rpc: string, document: string, payloadSha: string) {
    const response = await this.call(
      "/rest/v1/rpc/" + rpc + (this.recurring ? "_recurring_v1" : ""),
      {
        method: "POST",
        body: JSON.stringify({
          p_document: document,
          p_payload_sha256: payloadSha,
        }),
        headers: { "Content-Type": "application/json" },
      },
    );
    if (!response.ok) {
      await response.body?.cancel();
      throw new PublishError("PUBLISH_POLICY_REJECTED", 503);
    }
    let value;
    try {
      value = JSON.parse(
        new TextDecoder().decode(await bounded(response.body, 4096)),
      );
    } catch {
      throw new PublishError("INVALID_BACKEND_RECEIPT", 503);
    }
    if (typeof value !== "string") {
      throw new PublishError("INVALID_BACKEND_RECEIPT", 503);
    }
    return value;
  }
}
