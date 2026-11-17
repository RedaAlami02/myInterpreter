# Saved-profile sync safety — November 15

Replaced the old immediate-write GET with an admin-only preview and explicit CSRF-protected POST. The Update page now labels it “Vérifier les fiches sauvegardées”. Opening the page does not write company data.

Current captured profiles have no field-level verified fiscal periods or units for computed financial values. The new tool therefore does not apply financial values. Financial authority must come from the separately verified statement/projection pipeline; this change does not claim to refresh or certify financial data.

Allowed changes are exact saved-profile values for empty ext_name, sector, description and shareholders fields. Preview shows capture dates and proposed values. It protects existing values, rejects mismatched/ambiguous company-symbol mappings, future/unknown captures and captures older than 30 days. Thirty days is a conservative gap-fill limit, not a certification of factual accuracy. Candidate profiles must still be reviewed by the administrator.

Apply uses an administrator-checked database RPC, bounded at 25 companies/512 KiB per transaction. The database rechecks exact identity, snapshot timestamp, stored source value and expected current field under a row lock. Source changes or concurrent edits return STALE/PROTECTED. Financial/unsupported fields and non-admin callers are rejected. Repeats of already applied values return UNCHANGED. A private audit receipt records source hash, capture time, before/applied values and actor. Direct receipt access is revoked.

The web handler reads companies, formats and profiles in three bounded reads instead of one profile request and write per company. Preview tokens expire after 15 minutes, are session/owner-bound, and are consumed on use. Responses are no-store. Large previews show which proposals belong to the next bounded batch.

Verification:
- Tested gap filling, idempotency, concurrent-value protection, changed-source rejection, financial-field rejection and non-admin rejection in rolled-back SQL transactions. All test data rolled back before installing schema; no company data changed.
- All 81 actual profiles passed the planner audit: zero missing biography fields, zero financial proposals. Zero proposed updates is expected after the owner's previous successful sync.
- All applicable PHP fast suites pass; legacy live-backend suite skipped. Planner tests cover identity, stale/future/invalid dates, microsecond preservation, existing values and financial exclusion.
- Four runtime files deployed with backups and exact remote-byte readback: Update.php, handlers/sync_companies.php, core/company_sync_plan.php, core/SupabaseAdmin.php.
- Ordinary-account access remains forbidden. Actual administrator browser POST was not executed; database enforcement was tested through the existing administrator identity in rollback.

Schema: migrations/supabase/20261115_safe_profile_sync.sql. Private installation and publication receipts remain under the safe-profile-sync-20261115 task folders.
