// STAGED ONLY. No deployment/activation is performed by this repository.
import { createHandler } from "./gateway.ts";
import { SupabaseArchiveBackend } from "./supabase.ts";

Deno.serve(async (request) => {
  try {
    if (Deno.env.get("APP_ARCHIVE_ENABLED") !== "true") {
      return Response.json({ status: "REJECTED", code: "ARCHIVE_DISABLED" }, {
        status: 503,
      });
    }
    // Supabase provisions named server keys; no privileged key is sent by callers.
    const keys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}");
    const backend = new SupabaseArchiveBackend(
      Deno.env.get("SUPABASE_URL") ?? "",
      keys.default ?? "",
      undefined,
      Deno.env.get("APP_RECURRING_ENABLED") === "true",
    );
    return await createHandler(backend, {
      enabled: true,
      subjectEnabled: Deno.env.get("APP_ARCHIVE_SUBJECT_ENABLED") === "true",
      tokenHash: Deno.env.get("APP_ARCHIVE_WRITE_TOKEN_SHA256") ?? "",
    })(request);
  } catch {
    return Response.json({
      status: "REJECTED",
      code: "INVALID_SERVER_CONFIGURATION",
    }, { status: 503 });
  }
});
