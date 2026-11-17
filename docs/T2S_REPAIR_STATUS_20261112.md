# T2S repair status

The November 12 PDF contains T2S (verified ISIN MA0000012858). It was absent from both the approved 78-company identity configuration and the parser output. Its primary table row has six fields before the ISIN because a trade price and date are separated by one space. The parser required seven fields.

Local fix expands only that exact merged price/date shape, retaining table boundaries and close/reference consistency checks. Ten parser tests and nineteen official-close tests pass. Portfolio UI now lists dates when aggregate estimates are incomplete; Flutter analysis passes.

Mobile explanation alone published from isolated baseline 57ab8e1 to commit c7feb21c51c7a670d72b6f8221015ad93308d86a on fix/mobile-price-coverage-explanation-20261112. APK build 43286855700 started; last observed in progress. No completed new APK claimed.

Backend publication did not happen. Collector 43285107945 remained in dependency installation for over ten minutes. Ordinary and force cancellation requests were accepted, but GitHub continued reporting in_progress. A checked precondition confirmed state restoration and collection had not started before cancellation. Maintenance was stopped before publication and both execution gates restored. No identity secrets, policy pins, report rows or parser production files were changed.

Resume: verify hung job has ended; prepare a fresh deployment receipt directory (preserve the unpublished attempt evidence), deploy parser and synchronize parser/identity policy pins together using private scripts under private/identity-repair-20261112. Independently validate returned T2S row and price before publication. Existing repair.py selects only verified T2S, leaving SGTM unresolved; do not infer SGTM identity from a fuzzy name match. Publish current-day recovered display evidence only with truthful capture timestamps. Refresh the private profile consumers after pin changes; preserve original profile evidence.

Outstanding: backend parser/mapping deployment, live T2S same-date totals, fresh market quotes/screener, successful APK completion/download, historical-close ingestion and final monitoring acceptance.

## Live repair completed later November 12

- Hung job 43285107945 ended cancelled. Parser deployed commit f4c4b0e8ae02bd07d44ee9589cd097b348a7e1e2.
- T2S ISIN and approved company/symbol binding installed in both private collector and protected review configurations. Database source policy, parser and identity pins synchronized. Current profile: owner vault identity-repair-20261112/config.private.json; original profile preserved as historical evidence.
- Independent repeated download matched exact report bytes. Published current-day display evidence with truthful capture/verification timestamps; 76 available mapped prices. Existing financial batches were not rewritten.
- Authenticated reference function verified IAM 90.05, MUTANDIS 231.50, T2S Group Holding 216.00, VICENNE 327.20, all November 12. This resolves mixed-date totals for the four observed holdings.
- Maintenance transaction first rejected missing required statement timeout before any database write. Reconciled using the required bounded timeout; both execution gates restored.
- Narrow checkpoint exception for reviewed cancelled-before-state job deployed commit 6a4d15a2e9a670eb4c8971441c642626dee88ec7; 14 checkpoint tests pass. Remote readback and official-review trust pin verified.
- APK build 43286855700 succeeded; downloaded private/identity-repair-20261112/apk/app-release/app-release.apk. Contains only date-coverage explanation relative to previous mobile baseline.
- Screener still returns DISABLED with zero rows when called under authenticated scope with required 20-second timeout. Controls enabled, recurring policies unexpired. Existing market archive is beyond its recovery eligibility; fresh in-window collection and live coverage verification remain required. Do not describe this as a disabled control or a verified current-price feed. No stale data expiry was extended.
