# Mobile portfolio refresh — November 2, 2026

Main migration work continues; prediction work is excluded. The earlier price
input repair remains installed/verified, collection and schedules stay off, and
the hosted email routing permission remains pending.

## Fixed

The phone keeps its tabs mounted in an IndexedStack. A successful trade previously
reloaded only its calling screen, leaving another tab's holdings/statistics stale.
An acknowledged trade now invalidates portfolio, statistics and personal dividends,
including a hidden tab, while preserving their existing navigation/state.

TradeSubmission emits the invalidation once per submission instance, after the
backend acknowledges success. Failed/uncertain responses emit no false success;
retry preserves the original request ID/payload. A repeated acknowledgement does
not cause another refresh. The signal contains no user IDs, records or tokens.
Screens unsubscribe on disposal, so an old account screen receives no callbacks.
The current portfolio's extra local reload was removed to avoid duplicate reads.

Reload state callbacks are synchronous; fetching starts outside setState. The
initial widget test exposed a Future-returning callback assertion, and analysis
flagged a protected notifier call. Both were corrected before publication. The
intermediate logs remain private. Trade calculations, ownership/RLS and recorded
price semantics are unchanged; this does not turn old market prices into live data.

## Verification and release

- Flutter analysis: no issues.
- Full Flutter suite: **105 tests passed** (102 existing plus three regressions).
- Regressions exercise visible updated holdings plus hidden statistics/dividend reads,
  exactly-once invalidation, uncertain-response retry identity and disposed
  account-screen cleanup. Fictional local data only; no financial writes/emails.
- Initial five-file branch: `fix/mobile-portfolio-refresh-20261102`, commit
  `482db80c25a7f260301f2735d85873432d25c53d`; build41512642657 succeeded and
  its installer is preserved. Final review caught the personal-dividend dependency.
- Final two-file follow-up branch: `fix/mobile-refresh-complete-20261102`,
  commit `a317845ead3fc5c1a6d24e7b4e1deebbaa158c06`, adds the dividend refresh
  and extends the regression. Full105tests and clean analysis were rerun afterward.
- Based on the corrected email-callback release; callbacks remain enabled.
- Final GitHub Actions build: `41514053430`: **succeeded**.
- Final installer: `private/mobile-refresh-complete-20261102/mobile-apk/app-release.apk`;
  the matching size/hash/readback receipt is `apk-receipt.json` in that directory.
- No default-branch merge, unrelated root-worktree commit or local release build.

Evidence and build receipts: `private/main-fixes-20261102/` under the mobile
filenames/logs, plus `private/mobile-refresh-complete-20261102/` for the final
release. Device installation/acceptance remains a separate owner check.
No source collection, cloud schedule, database policy or prediction assets changed.
