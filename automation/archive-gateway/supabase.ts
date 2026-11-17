import { Backend, bounded, GatewayError, Reservation } from "./gateway.ts";

// The privileged key lives only inside the managed function, never in CI.
export class SupabaseArchiveBackend implements Backend {
  constructor(
    private url: string,
    private key: string,
    private fetcher = fetch,
    private recurring = false,
  ) {
    if (
      !/^https:\/\/[a-z0-9]{10,40}\.supabase\.co$/.test(url) ||
      !/^sb_secret_[A-Za-z0-9_-]+$/.test(key)
    ) throw new GatewayError("INVALID_SERVER_CONFIGURATION", 503);
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
      throw new GatewayError("ARCHIVE_BACKEND_UNAVAILABLE", 503);
    }
  }
  private async rpc(name: string, body: unknown) {
    const response = await this.call("/rest/v1/rpc/" + name + (this.recurring ? "_recurring_v1" : ""), {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    });
    if (!response.ok) {
      await response.body?.cancel();
      throw new GatewayError("ARCHIVE_POLICY_REJECTED", 503);
    }
    try {
      return JSON.parse(
        new TextDecoder().decode(await bounded(response.body, 4096)),
      );
    } catch {
      throw new GatewayError("INVALID_BACKEND_RECEIPT", 503);
    }
  }
  async officialComplete(provider: string, digest: string, documentSha: string) {
    if (!this.recurring) throw new GatewayError("RECURRING_MODE_REQUIRED",503);
    const value = await this.rpc("official_close_status",{p_provider:provider,p_digest:digest,p_document_sha256:documentSha});
    if(typeof value!=="boolean")throw new GatewayError("INVALID_BACKEND_RECEIPT",503);
    return value;
  }
  async reserve(metadata: Record<string, unknown>): Promise<Reservation> {
    const value = await this.rpc(
      metadata.p_subject_key === undefined
        ? "reserve_market_archive"
        : "reserve_subject_market_archive",
      metadata,
    );
    if (
      !value || !["RESERVED", "STORED"].includes(value.state) ||
      value.bucket !== "private-market-evidence" ||
      value.object_path !==
        "sha256/" + String(metadata.p_digest).slice(0, 2) + "/" +
          metadata.p_digest + ".json.gz"
    ) {
      throw new GatewayError("INVALID_BACKEND_RECEIPT", 503);
    }
    return value;
  }
  private path(location: Reservation) {
    if (
      location.bucket !== "private-market-evidence" ||
      !/^sha256\/[a-f0-9]{2}\/[a-f0-9]{64}\.json\.gz$/.test(
        location.object_path,
      )
    ) {
      throw new GatewayError("INVALID_BACKEND_RECEIPT", 503);
    }
    return "/storage/v1/object/" + location.bucket + "/" + location.object_path;
  }
  async read(location: Reservation) {
    const response = await this.call(this.path(location), { method: "GET" });
    if (!response.ok) {
      // Some Storage versions send the semantic status in a bounded JSON body.
      // A missing bucket/access failure is never treated as a missing object.
      let error;
      try {
        error = JSON.parse(
          new TextDecoder().decode(await bounded(response.body, 4096)),
        );
      } catch {
        throw new GatewayError("ARCHIVE_READ_FAILED", 503);
      }
      if (
        (response.status === 404 || response.status === 400) &&
        (error.code === "NoSuchKey" ||
          (error.error === "not_found" && !error.code)) &&
        (response.status === 404 || String(error.statusCode) === "404")
      ) return null;
      throw new GatewayError("ARCHIVE_READ_FAILED", 503);
    }
    return await bounded(response.body, 8 * 1024 * 1024);
  }
  async put(location: Reservation, body: Uint8Array) {
    const response = await this.call(this.path(location), {
      method: "POST",
      body: body as BodyInit,
      headers: { "Content-Type": "application/gzip", "x-upsert": "false" },
    });
    // Concurrent same-digest uploads are resolved by exact read-back, never overwrite.
    if (![200, 201, 409].includes(response.status)) {
      let error;
      try {
        error = JSON.parse(
          new TextDecoder().decode(await bounded(response.body, 4096)),
        );
      } catch {
        throw new GatewayError("ARCHIVE_UPLOAD_FAILED", 503);
      }
      if (
        !(response.status === 400 && String(error.statusCode) === "409" &&
          ["KeyAlreadyExists", "ResourceAlreadyExists"].includes(error.code))
      ) {
        throw new GatewayError("ARCHIVE_UPLOAD_FAILED", 503);
      }
      return;
    }
    await response.body?.cancel();
  }
  async finalize(digest: string) {
    if (
      await this.rpc("finalize_market_archive", { p_digest: digest }) !== digest
    ) {
      throw new GatewayError("INVALID_BACKEND_RECEIPT", 503);
    }
  }
  async complete(provider: string, kind: string, slot: string) {
    const value = await this.rpc("market_archive_slot_complete", {
      p_provider: provider,
      p_kind: kind,
      p_slot: slot,
    });
    if (typeof value !== "boolean") {
      throw new GatewayError("INVALID_BACKEND_RECEIPT", 503);
    }
    return value;
  }
  async finalizeSubject(digest: string, subject: string) {
    if (
      await this.rpc("finalize_subject_market_archive", {
        p_digest: digest,
        p_subject_key: subject,
      }) !== digest
    ) {
      throw new GatewayError("INVALID_BACKEND_RECEIPT", 503);
    }
  }
  async completeSubject(
    provider: string,
    kind: string,
    slot: string,
    subject: string,
  ) {
    const value = await this.rpc("market_archive_subject_complete", {
      p_provider: provider,
      p_kind: kind,
      p_slot: slot,
      p_subject_key: subject,
    });
    if (typeof value !== "boolean") {
      throw new GatewayError("INVALID_BACKEND_RECEIPT", 503);
    }
    return value;
  }
  async admitSubject(provider: string, subject: string, projection: boolean) {
    const value = await this.rpc("market_archive_subject_admission", {
      p_provider: provider,
      p_subject_key: subject,
      p_projection: projection,
    });
    if (typeof value !== "boolean") {
      throw new GatewayError("INVALID_BACKEND_RECEIPT", 503);
    }
    return value;
  }
  async admit(
    provider: string,
    kind: string,
    slot: string,
    shadow: boolean,
    projection: boolean,
  ) {
    const value = await this.rpc("market_archive_acquisition_admission", {
      p_provider: provider,
      p_kind: kind,
      p_slot: slot,
      p_shadow: shadow,
      p_projection: projection,
    });
    if (typeof value !== "boolean") {
      throw new GatewayError("INVALID_BACKEND_RECEIPT", 503);
    }
    return value;
  }
}
