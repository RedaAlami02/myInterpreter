# Website publication and owner-only portfolio recovery

The owner explicitly requested publication after seeing an empty live portfolio.
A fresh encrypted-FTP inspection confirmed that the host still contained the old
retired-backend implementation, while the replacement existed only locally.
Fresh SQL inspection found no Supabase Auth accounts, two disabled owner-approved
recovery bindings, and all 55 original private records intact in staging.

## Completed

- Published a bounded 67-file PHP website snapshot over encrypted FTP. Forty-four
  files changed and 23 were already identical. Every selected file was compared
  against the host; transferred files were read back byte for byte. A subsequent
  three-file confirmation-flow fix was also uploaded and verified.
- Installed the existing Supabase authentication, private portfolio, market-data
  readers, recovered-history readers, navigation and reference-price display on
  the website. The retired adapter now fails closed rather than contacting the
  old service. Old browser authentication state is discarded on session restore.
- Enabled only the two existing approved recovery bindings and recovery control
  in one transaction, after locking the controls, checking the exact previously
  approved plans, and rechecking all original source hashes and staged payloads.
  A fresh read-only connection verified the committed flags and original data.
- Larger saved portfolio: 13 buys, 3 sells, 8 holdings and 22 P&L snapshots
  (46 records). Other saved portfolio: 3 buys, 1 sell, 4 holdings and one P&L
  snapshot (9 records). Approved owner identities remain in private configuration.
- Recovery uses installed SQL019: confirmed email plus genuine password
  authentication, exact source pins, empty destination, owner serialization,
  one durable claim and preserved original payload/provenance. No accounts,
  passwords, JWTs or authenticated claims were fabricated. Activation itself
  imported zero financial rows; real users must claim through their login.
- Signup confirmation now ends signed out, revokes its provisional session on a
  best-effort basis, clears local tokens/cookies/PKCE, rotates session and CSRF,
  and displays a one-use instruction to sign in with the chosen password.
  Password-reset sessions remain isolated from normal authentication.
- Added an explicit environment-only `MYINTERPRETER_DIRECT_SOURCE_REQUESTS`
  gate, default false. Legacy dashboard status requests and enrichment requests
  cannot start a capture while disabled. Session status displays unavailable
  instead of guessing from the clock. The direct proxy uses no-store and requires
  authentication when separately enabled. The existing private upstream config
  was excluded from this upload; the disabled website does not require it.

## Verified

- All selected PHP files passed syntax checks.
- Fifteen existing Python deployment/configuration/portfolio-display cases and
  three new no-network source-gate cases pass.
- PHP Auth/portfolio adapter, PKCE, email-intent/recovery isolation, session
  lifecycle, portfolio claim and 17 reference-price cases pass. Confirmation
  coverage includes failed provisional logout without retaining local access.
- A separate authorized reviewer checked the source gate, confirmation flow
  and exact-plan activation script; no remaining concrete blocker was found in
  this bounded delta. This was not real-user or email-delivery acceptance.
- An isolated browser loaded the real new login/signup interface, with zero
  JavaScript errors; anonymous Portfolio requests redirected to login. No
  credential submission, email send or upstream request was made by this check.
- Both saved Supabase API keys are accepted (HTTP 200 settings checks).
  Read-only database connectivity and TLS pass; observed database size was
  333,846,195 bytes. Anonymous application-table privileges remain zero.
- Fresh full SQL/API privacy checks pass: all 15 anonymous application REST
  requests are denied, all four portfolio owner policies and RLS remain intact,
  no user relation is anonymously readable, no private internal schema is exposed,
  and there are zero public Storage buckets.

Private publication snapshots, hashes, rollback copies, before/after recovery
receipts, browser evidence and verification reports are preserved under
`private/portfolio-publish-20261101/`. They must never be published or pushed.
The initial upload was automatically rejected because it selected private source
configuration; that file was removed from the revised manifest before any upload.

## Remaining acceptance

**Subsequent genuine-user acceptance:** after the owner reported signing in,
a fresh read-only connection verified a confirmed larger-owner account and its
successful claim. The application has exactly 13 buys, 3 sells, 8 holdings and
22 P&L snapshots. All 46 provenance payloads match staging and the approved plan.
The second owner has not registered. All 55 original records remain intact;
anonymous application privileges remain zero. Observed size: 334,026,419 bytes.
The first owner's signup/login/recovery portions below are now complete;
reset/logout, device acceptance and the remaining owner are still outstanding.
The earlier zero-account/zero-claim statements document the activation baseline.

1. The actual owners must create fresh Supabase accounts with their approved
   emails and their own new passwords, confirm their emails in the same browser,
   and explicitly sign in with those passwords. The old service's browser login
   and password export cannot supply this authentication.
2. Verify real confirmation delivery and redirect allowlists. Custom SMTP status
   remains unverified. The owner has been asked to try the published signup;
   no email verification or password requirement was disabled to bypass this.
3. Verify genuine recovery receipts and the expected 8/4 holdings, transactions
   and original P&L after those real logins. At activation verification, there
   were zero genuine claims. Do not claim that private data is already attached
   to a new account merely because bindings are enabled.
4. Assign the owner-only admin UUID after the real, confirmed account exists;
   never grant admin solely from a client-supplied email. The rare maintenance
   navigation is last and restricted; its UUID is currently unset.
5. Mobile implementation remains local; no root Git push, release APK or mobile
   deployment occurred in this continuation.

Market preview and saved portfolio valuation flags remain OFF. Other collection,
projection and schedule controls were not activated. SQL020/021 remain staged,
not installed. Saved daily P&L still requires verified official closing prices,
per the owner's decision. This publication does not certify a new market source
or make prediction/model execution production-ready. Prediction work is excluded.
