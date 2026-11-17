// STAGED ONLY. No deployment/activation is performed by this repository.
import { createHandler } from "./publisher.ts";
import { SupabaseProjectionBackend } from "./supabase.ts";

Deno.serve(async (request) => {
  try {
    if (Deno.env.get("APP_PROJECTION_ENABLED") !== "true") {
      return Response.json({ status: "REJECTED", code: "PUBLISHER_DISABLED" }, {
        status: 503,
      });
    }
    // Supabase provisions named server keys; no privileged key is sent by callers.
    const keys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}");
    const backend = new SupabaseProjectionBackend(
      Deno.env.get("SUPABASE_URL") ?? "",
      keys.default ?? "",
      undefined,
      Deno.env.get("APP_RECURRING_ENABLED") === "true",
    );
    return await createHandler(backend, {
      enabled: true,
      contextEnabled: Deno.env.get("APP_ENRICHMENT_CONTEXT_ENABLED") === "true",
      tokenHash: Deno.env.get("APP_PROJECTION_TOKEN_SHA256") ?? "",
    })(request);
  } catch {
    return Response.json({
      status: "REJECTED",
      code: "INVALID_SERVER_CONFIGURATION",
    }, { status: 503 });
  }
});
