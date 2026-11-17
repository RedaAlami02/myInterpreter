# Website portfolio prices — November 4

The website displayed SGTM580 from the recovered October21 reference table.
Scheduling was activated after market close, so there had been no new quote run;
expired live quotes also fell back to that old table. The earlier automation status
should not have implied prices were already refreshed.

The website now reads a separate authenticated, read-only reference projection:
verified recovered closing reports and future approved closing batches take
precedence over older saved references. Fresh intraday quotes still take precedence
while valid. SGTM's verified November3 closing reference is524.00.75company closes
are available from that report. The missing official-close holding remains unknown.

Original observations, timestamps, portfolio trades and saved P&L were preserved.
The original price table intentionally remains unchanged. Raw report bytes and
provenance stay in an owner-only RLS table; anonymous RPC reads are denied.

SQL029 and two PHP files were installed/published with exact readback and private
rollback.7isolated SQL tests, PHP adapter tests and independent review passed.
Database size after insertion:335,328,947bytes. Evidence is private under
`private/website-price-check-20261104/`.

This updates dated portfolio and company-directory references. It does not rewrite
historical charts or claim past reference prices are live quotes. A real signed-in
browser refresh remains the final user-visible acceptance check. Mobile fallback
reads need corresponding RPC integration in a future APK.
