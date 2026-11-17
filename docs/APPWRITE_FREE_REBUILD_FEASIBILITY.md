# Rebuild feasibility without further Appwrite access

Assessed 2026-10-24. The assessment was completed before implementation. The user
subsequently clarified that **the purpose is to build**, authorizing continued
implementation with a new account and fresh personal information/portfolio.
Read [MIGRATION_HANDOFF.md](MIGRATION_HANDOFF.md) for the authorized next steps.
The temporary assessment-only restriction is superseded. No paid subscription
change or destructive retirement is implied by this authorization.

## Verdict

A working replacement for myInterpreter is feasible without obtaining another
Appwrite export. This is an engineering conclusion from source inspection,
read-only live source probes, existing Supabase pilot evidence, and reverified
local recovery files. It is not a claim that every old Appwrite record can be
recreated exactly, that all future collectors already run in another cloud, or
that operation is guaranteed to cost $0/month.

Keep the existing PHP/Flutter application source and recovered public history.
Recreate authentication and private portfolio tables with fresh identities and
empty personal records. This removes legacy account/hash/owner-ID transfer from
the critical path. Do not discard the private backups or delete Appwrite data;
starting fresh does not authorize destructive cleanup.

## Evidence and limits

| Area | Verified evidence | Remaining work or limit |
| --- | --- | --- |
| Web and mobile features | PHP pages, Flutter source and calculation logic are available locally; backend calls have been located | Replace auth/database integrations and test the clients; do not rewrite the whole UI to escape the backend |
| Fresh accounts and portfolios | Supabase provides password authentication and user-scoped database authorization; its existing project connection and public pilot previously passed | Implement new auth, owner isolation, transactions, admin identity and email delivery; no new account was created during this assessment |
| Company directory and quote feed | Live feed returned all **81/81 saved symbols**, all with positive price values, plus **60 stock-detail rows** and the market index | Source quote timestamps must remain distinct from retrieval time; suspended/untraded instruments are not current trades |
| Fundamental inputs | Saved company baseline has **81 companies**, with BPA/ROE/share count/equity populated for all 81; growth for 80 and dividend-per-share for 59 | Saved values are dated observations, not a promise of current financial statements |
| Fresh fundamentals | Four samples returned data without request failures; three had 17–23 populated computed fields | The sampled bank had only 3/23 populated fields; its fiscal year, share count and core financials were missing. HTTP success does not prove financial completeness |
| Fundamentals identity coverage | Live fundamentals registry matched **76/81** saved symbols; direct fallback lookup failed for the remaining five | Full fresh-universe automation is not established. Preserve the baseline and use alternative/official issuer statements where necessary |
| Price/index history already retained | Hash-verified **110,067 original market observations**, all with prices, across **65,659 series-days**, May 29, 2023–October 21, 2026; **842 MASI days** | This is a recovered observation set, not the exact current database; includes intraday rows whose later deletion is unknown |
| Independent daily history retained | Hash-verified **56,756 daily rows for 81 symbols** with OHLC and partial additional fields | Keep distinct until corporate-action adjustments, timestamps and source disagreements are reconciled |
| Fresh daily-history feasibility | Three live tests succeeded: two established stocks each returned **737 rows**, October 25, 2023–October 23, 2026; a newer listing returned **312 rows**, July 15, 2025–October 23, 2026 | Only three symbols were retested today. The earliest returned dates moved forward relative to the older saved history, so do not assume unlimited retrospective availability |
| Dividend calendars | Live parsing returned **296 rows across 2022–2026** | 2027 failed validation and was not treated as empty or nonexistent; issuer mapping, estimates/confirmation and fiscal-vs-payment-year rules need reconciliation |
| Order books going forward | Live discovery returned **81 symbols**; one sample returned a summary and **five bid/five ask levels** | Weekend source responses do not establish in-session collection or availability from the future cloud host |
| Archived order books and function source | All **1,713 saved export artifacts** still match hashes and sizes, including the known **1,686 storage objects** and **8 active function source archives**; all eight source archives were read successfully | This verifies the saved October 22 bundle, not objects generated later or unknown buckets |
| Background jobs and monitoring | Collector, dividends, cleanup and valuation source is available; cloud scheduling is supported by the proposed managed runtime | Backend/storage adaptation, source access from the selected cloud region, secrets, schedules, retries, backups and observation remain untested there |

The current fundamentals adapter explicitly documents that its corporate
statement feed omits banks. Its refresh path preserves existing values when
incoming fields are missing. This explains the bank probe and shows why dropping
the saved baseline would lose useful inputs. Official issuer financial statements
provide an alternative: the sampled bank publishes annual reports and its market
regulator hosts the 2025 financial report. Retrieving such documents is feasible;
extracting and validating all required metrics is additional work, not completed
by this assessment.

## What cannot be promised from scratch

- An exact copy of the latest cloud database, its corrections/deletions, IDs,
  user accounts, sessions, manual edits, or operational logs.
- Historical intraday ticks and full bid/ask depth that were never captured or
  saved. A fresh daily-history endpoint cannot recreate those snapshots.
- Every historical ratio or point-in-time fundamental snapshot by recalculating
  it with today's financial statements. Preserve original observations instead.
- Complete official corporate-action/tradability history or an untouched future
  research dataset. Existing research documents already record these gaps.
- Complete live fundamentals for all companies through the current adapter,
  published 2027 dividends, or perpetual free operation.

These limits do not prevent a working new account, market views, charts,
dividends, screener, new trades/holdings and future scheduled collection. They do
prevent claiming a perfect restoration of every historical Appwrite record.

## Before a later authorized cutover

1. Choose the fresh-start account/portfolio approach already accepted by the user;
   preserve historical recovery artifacts rather than wait on Appwrite account
   export as a hard dependency.
2. Reconcile public data, retain source/observation dates, and establish explicit
   handling of incomplete bank/company fundamentals and corporate actions.
3. Implement new auth/private ownership and test user isolation, then integrate
   PHP and Flutter against the same backend and verify actual web-host access.
4. Prove source retrieval and scheduling from the selected cloud region, email
   delivery, runtime/cost estimates and backup restoration before cutover.
5. Test the complete user journey and an Android update before retiring the old
   backend. No implementation or retirement was performed in this assessment.

## Primary references

- [Supabase authentication](https://supabase.com/docs/guides/auth): password auth
  and JWT/RLS integration support fresh identities.
- [Supabase SMTP requirements](https://supabase.com/docs/guides/auth/auth-smtp):
  default email delivery is restricted; production delivery needs configuration.
- [Cloud Run scheduled jobs](https://docs.cloud.google.com/run/docs/execute/jobs-on-schedule):
  managed scheduling can keep collectors independent of the user's PC.
- [Issuer annual financial reports](https://ir.attijariwafabank.com/financial-information/annual-reports)
  and the [regulator's 2025 report page](https://www.ammc.ma/fr/espace-emetteurs/etats-financiers/attijariwafa-bank-rfa-2025)
  establish an official alternative for the sampled bank's missing feed data.

Live probes used existing retrieval functions only. Responses stayed in memory;
no raw responses were saved, no Appwrite requests were made, no accounts were
created, and no application/backend code, database data or deployment changed.
Only this assessment and continuity guidance were documented locally.
