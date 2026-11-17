# Production health review — 2026-11-12

Read-only checks at approximately 07:57 UTC.

- Independent timer enabled; repeated cron executions succeeded and dispatch returned 202. Latest completed collection run inspected: 43082580512, failed.
- User screenshot confirms delivery of both collection and health failure emails.
- Health run 43093460353 reported OFFICIAL_CLOSE_UNVERIFIED and COLLECTION_RUN_FAILED.
- Latest collection failure code: CLOUD_STATE_LATEST_CHECKPOINT_MISSING.
- Last successful run before the sustained failure chain: 42670340622, November 9 at 18:02 UTC. It uploaded and verified a checkpoint. Following runs 42671126097 and 42671914337 have no artifacts and returned no jobs through the jobs API. Their original failure cause remains unverified; do not infer billing or runner failure.
- Checkpoint selection requires the immediately preceding non-skipped run to have a checkpoint. A missing artifact therefore blocks subsequent runs. Recovery must preserve state integrity and use a verified checkpoint; do not bootstrap empty or blindly skip failed acquisitions.
- Latest archived depth age approximately 226,712 seconds; quotes age approximately 227,395 seconds. Latest depth complete; latest quotes incomplete. These are archive timestamps, not direct proof of every displayed website value.
- Accepted official sessions: November 5 and November 9. No November 10/11 accepted close found.
- Database 224,245,427 bytes; approximately 125.8 MB below 350 MB guard. Storage cleanup headroom persists.
- Both website and mobile auth redirect destinations matched expectations using invalid-token redirect probes. This does not repeat actual email acceptance.
- Public website DNS and TLS handshake succeeded, but HTTP requests from this environment ended unexpectedly during SSL reads. Website availability and signed-in behavior could not be verified. Browser connector unavailable (localhost:9222 refused connection). Do not report the website as either healthy or definitively down from these observations.

Raw run logs and metadata are retained in the owner-only host vault. No production data, deployments or scheduler settings were changed during this review.

## Recovery deployment and browser verification

- Deployed worker commit f0deaebcb8a062ad0e8d72632c0efb6fd73cd605; remote file readback, publisher trust pin and restored execution gates verified.
- Fourteen checkpoint regression tests passed. Recovery bypasses selector-only failures with skipped state operations, plus exactly two reviewed incident run IDs with no jobs or artifacts.
- Recovery run 43272100900 succeeded, restored checkpoint from run 42670340622, completed collection and verified its uploaded checkpoint.
- Production now has a November 12 accepted official-close batch and one valuation receipt. November 10–11 remain absent.
- Browser verification succeeded for dashboard and screener. Screener explicitly reports recent prices unavailable. Raw HTTP failures did not establish a website outage.
- Follow-up quote run 43272804141 returned OUTSIDE_WINDOW: it did not collect fresh quotes after the authorized market window. It uploaded a checkpoint, but GitHub artifact readback failed (download error); verification then failed with CLOUD_STATE_DOWNLOAD_INVALID. Raw logs retained privately.
- Independent review run 43272656848 failed with OFFICIAL_REVIEW_FAILED even though a November 12 batch/valuation now exists. This discrepancy needs investigation; do not equate the database receipt with an entirely successful review workflow.
- Timer remains enabled. At 17:47 UTC it correctly suppressed a recent overlapping dispatch.
- Outstanding: fresh in-window quote/depth collection and coverage investigation, repeat checkpoint verification after artifact download failure, review failure diagnosis, historical-close recovery through a separately validated historical path, and final healthy monitoring result.

## Account investigation and report recovery

- Investigated requested account privately: email confirmed, no ban/deletion, existing auth session refreshed November 12. No account-block evidence; exact mobile error and installed APK requested from owner. No account credentials or state changed.
- Three latest automatic collector runs (43279951543, 43280820174, 43281701249) succeeded after recovery. This verifies continuing checkpoint operation; it does not prove fresh in-window market coverage.
- Found raw official-review HTTP receipt read bypassed content decoding. Corrected bounded read to decode HTTP content encoding before JSON parsing; three independent verifier tests passed. Deployed commit bcf832ebe2965a9d458c447e908af2ff31d2f1e2 with readback/trust pin/gates verified. Live successful review after this correction remains to be verified; compression is a plausible cause, not a proven reconstruction of the earlier masked exception.
- Retrieved authentic November 10 and November 11 report PDFs through approved private configuration. Both returned 200 and independently parsed 80 rows with matching session dates. Raw PDFs and parsed results retained in owner-only vault. Historical batches and valuations have not been published; a validated historical ingestion path remains necessary.
- No fresh quote data was claimed after an OUTSIDE_WINDOW response.
