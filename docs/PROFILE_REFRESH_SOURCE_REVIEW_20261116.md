# Fresh profile source review — 2026-11-16

## What was checked

- Fresh fundamental API captures for ADH, ATW, IAM, LES and T2S: 96 network requests, with one registry response reused within this batch (four avoided duplicate requests). Each annual/profile response was fetched again. Raw bodies, hashes and capture timestamps remain in the owner-only vault.
- A second fresh run through the new reusable command checked ATW and T2S: 39 requests and one registry reuse. T2S consistently returns HTTP 404 for the optional per-share financial endpoint, while 19 other responses are available. This is partial coverage, not an all-company save failure.
- The configured separate market API responded successfully. Its payload supplies quotes, quote dates and capitalization; this is not independent annual financial-statement evidence.
- Three fresh configured issuer records parsed successfully. Their shareholder disclosure dates were 2025-06-23, 2015-05-21 and 2021-06-30. Capture time cannot replace those dates. An initial private audit helper passed bytearray rather than bytes to the HTML parser; that local helper error was corrected and the same captured pages re-parsed, without claiming an upstream failure.

Source identities, endpoints, raw evidence and original inspection errors remain private. No additional unreviewed provider was added.

## Findings

The website's current fetch function reads database profiles under the migrated backend; the administrator button still cannot initiate a fresh acquisition.

The configured corporate annual tables do not cover the sampled bank. Its secondary per-share endpoint contains EPS through 2023, with the 2024 slot null. Those are dated candidate facts, not current bank financials. The evidence extractor previously omitted this endpoint and now retains its seven recognized annual sections, raw JSON paths, exact decimals and missing-value issues.

Several source annual series contain 2025 figures, but reported net profit remains 2024 while later profit is marked forecast. The coherent derived source fiscal year therefore remains 2024. T2S already has a primary-reviewed 2025 record, which these older API candidates must not replace. Reported EPS, normalized EPS and current share counts require separate provenance.

## Implemented source layer

`automation/managed/profile_refresh.py` performs new acquisition, archive integrity verification and comparison with a supplied company baseline. It distinguishes missing and changed fields, older/same/newer fiscal years, unavailable values, individual source HTTP failures, primary-review protection, and source annual years by metric. No proposed financial value is automatically certified or published. Even a candidate-validation failure retains the raw captured archive for inspection.

`tools/refresh_company_profiles.py` runs at most five companies, preserves each company's results and hashed manifest before continuing, uses owner-only newly created output directories and never overwrites earlier captures. One failed company does not erase other results. Only the source registry is reused within one invocation; a new invocation re-fetches it, and financial/biographical calls are not cached.

The expanded `financial_evidence.py` records the secondary annual sections, keeps forecasts separate and rejects duplicate year keys. Units, consolidation scope and publication date stay unknown until evidenced. Source-year bounds exclude junk labels. Existing recurring publication behavior and production data were not modified in this phase.

## Validation and remaining connection

42 focused tests passed across collection, source frames, projection integrity, financial facts, primary extraction and the new refresh comparison/batch logic. Python compilation passed. The reusable command was exercised against two real companies, preserving private manifests and HTTP 404 detail without production writes.

The next implementation is the administrator request/status queue and collector connection: a click must initiate background fresh acquisition, report company-level progress, and apply only validated changes through protected publication. The currently deployed saved-biography button is unchanged by this source phase. No mobile code was changed.
