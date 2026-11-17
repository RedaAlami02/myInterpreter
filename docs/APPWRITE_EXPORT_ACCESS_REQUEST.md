# Request for temporary Appwrite export access

Updated 2026-10-24 for the user to send through Appwrite's official support channel. Not sent. The [Education FAQ](https://appwrite.io/education) identifies an Education support channel in the [Appwrite Discord](https://appwrite.io/discord). Do not post credentials, account exports, or private trade records in a public channel.

Subject: Education read limit blocks data export before graduation

Hello,

My Appwrite Education membership expires around November 10, 2026, according to the remaining-days notice shown on October 22. My current billing cycle is October 6–November 5, 2026.

The Console reports approximately 1.8M/1.8M database reads and project access is suspended. Read-only database export requests return HTTP 402, `limit_databases_reads_exceeded`.

I am preparing a backup before Education ends. A fresh read-only API test on October 24 still returns the same database quota error. Could you provide a temporary read allowance solely for export, or assist with a complete export including database schemas, documents and permissions, and user authentication data? If available, please include original user IDs, verification/status metadata, preferences, password hashes, algorithm/options and linked authentication identities. Please confirm any authentication data that cannot be exported.

Current private portfolio transactions and user accounts are essential and cannot be reconstructed from public sources. Please prioritize access to those resources if a full export cannot be provided immediately. My available project keys also lack users.read/teams.read; the suspended project screen may prevent creating an appropriate read-only export key in the Console. Please confirm how I can create that key while the database read limit is exhausted.

Please also confirm the exact quota reset time and the safest way to retain my projects and data through Education graduation while completing the migration. I have two projects in the organization.

Storage files and active function sources have already been backed up separately. I have not changed plans or authorized any paid add-ons.

Thank you.

## Recovery order once access is available

1. Save a temporary project key locally as `.appwrite-export-key`, with Auth read scopes (`users.read`, `teams.read`) and read-only database/schema/document scopes. For the legacy API these are `databases.read`, `collections.read`, `attributes.read`, `indexes.read`, `documents.read`; if Console labels have changed, select the equivalent database/table/column/row read permissions. Do not enable write or key-management scopes.
2. Run the prepared exporter. It captures users and teams before any database work. It preserves all returned user fields, including password/hash fields if present; actual password portability must be tested rather than assumed.
3. When database reads are available, the exporter prioritizes `achats`, `ventes`, `portefeuille`, and `benefits` before public market history. Source counts, payloads, original ownership, page hashes and checkpoints are preserved.
4. A complete export still requires reconciliation and restoration testing. Freeze writes or capture a final consistent delta at cutover; a paginated online export is not an atomic snapshot.

```bash
# New directory: capture current accounts/private data before large market history.
python3 tools/export_appwrite.py --output backup_live_database_NEW_TIMESTAMP

# Resume only that same snapshot after an interrupted attempt.
python3 tools/export_appwrite.py --output backup_live_database_NEW_TIMESTAMP --resume
```

A new key addresses authorization, not the billing quota. If Appwrite cannot provide an allowance or assisted export, compare a temporary paid bridge with waiting for the confirmed cycle reset. The screenshots suggest a reset around November 6, but Appwrite must confirm the exact time and expiry overlap. A paid change requires review of the checkout and explicit authorization; no billing changes have been made.
