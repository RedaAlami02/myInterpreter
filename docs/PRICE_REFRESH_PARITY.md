# Original price job parity — October 30

**Later checkpoint:** read [APPLICATION_PRICE_PUBLICATION.md](APPLICATION_PRICE_PUBLICATION.md).
The port now has a tested private full-row publish/read path. SQL016 and publisher
v8 are installed and verified disabled, with original-data fingerprints unchanged.
PHP/Flutter v3 readers pass the actual SQL fixture. Main-screen cutover, real-user
acceptance and recurring jobs remain; the older "writer not added" notes below
refer to the preceding local-only port. Historical/valuation tables remain intact.

The existing price job's calculations now run on the verified archive without
its retired SDK, database or network. The real saved capture produces **82 full
rows matching the original job exactly: 81 stocks and MASI**. This is a local
historical derivation, not a new capture, application-table update or prediction.

## Implemented and connected locally

- `fundamental_frame.price_document()` retains the original stock row fields,
  ratios, ratings, chart trimming and missing-versus-zero behavior.
- `index_document()` retains the original index row without stock ratios or an
  invented stock symbol. Both require an explicit aware observation date and a
  positive finite price.
- `price_jobs.enrichment_jobs()` ports the original initial-enrichment cap of
  five, completed-sector marker and separate five-company hourly refresh. It
  preserves original company order, including fiscal-year ties. UTC minutes
  0–14 select the refresh, as before; tests do not consult the wall clock.
- `price_jobs.new_listings()` proposes missing mappings and bare company rows,
  reuses existing companies and explicitly flags conflicting identities. It
  performs no inserts or enrichment requests. Existing mappings are never changed.
- `price_refresh.build()` connects archive verification, the existing display
  fallback, exact raw-row field extraction, full row calculations and enrichment
  choices. Private field bindings cannot override price, date or identity.
  Conflicting observations/fields and wrong companies are excluded explicitly.
  Fundamentals must have a known availability time, taking the later of their
  explicit date and preserved update metadata, no later than the actual price
  record/capture time or evaluation cutoff. Later evaluation cannot attach newer
  fundamentals to an old price row. Trade quantities remain exact integers.
- The existing `tools/prepare_app_feed.py` accepts `--include-price-refresh` and
  optional `--application-bindings`. Its output remains confined to a new file
  under ignored `private/`; the original default output is unchanged. There is
  no table-write or source-request option.

The original job had two different field calculations: quotes derived absolute
change from the reference close; instrument references derived reference close
from the supplied change. These rules require explicit
`calculation_rules: legacy_getprice/v1` in the private field profile. They are not
silently imposed on other providers. The real-capture comparison initially caught
these two omissions; they were corrected before the final successful comparison.

## Provenance and limits

Each derived row has a separate provenance object containing its original
observation/reference IDs, capture date, reported date, source event when known,
price basis, fundamental availability time and eligibility flags. Saved-price fallback retains its original
record date and never receives today's market cap, volume or chart.

The result is labeled `SAVED_ARCHIVE_DERIVATION` / `SHADOW_ONLY`, with the actual
archive capture time, original source execution metadata and field-profile hash.
All prediction and automatic-valuation eligibility remains false. Reference
capture time is not represented as a trade timestamp. No original archive,
published v1 candidate, recovery record, genuine ledger or frozen model is changed.

## Verified evidence

- **230 managed-worker tests pass**, including focused old-AST row/ratio/chart,
  index and enrichment comparisons plus archive-to-full-row integration cases.
- The existing preparation CLI was run offline on the genuine saved capture.
  All **82 full rows** equal the original job's actual normalization/calculation
  AST using the verified preserved company artifact. Enrichment decisions match.
- Coverage remains **65 observed quote values** (64 stocks + index), plus
  **17 instrument references**. Original acquisition remains INCOMPLETE; the
  reference values do not certify missing quote rows or fresh trade timestamps.
- The original saved archive SHA-256 was verified before and after. Zero source
  requests and zero remote writes occurred in this parity continuation.

Focused independent review found two further edge cases after the first passing
suite: later evaluations could mix newer fundamentals into earlier price rows,
and the generic text parser rejected charts longer than 500 characters before
legacy trimming. Both were corrected. New cases cover capture/saved-price date
bounds, preserved update metadata, unknown availability, and a real extraction
path with a 691-character chart. Chart extraction is bounded to 64 KiB and suffix
trimming is linear in input size; ordinary identifier/text limits are unchanged.
The independent reviewer then reran all **36 focused price tests**, confirmed
both fixes closed and found no further blocker in this local-only change. That
review does not approve hosted publication, scheduling or production cutover.

Private receipts, derived outputs and logs:
`private/price-refresh-20261030/`. Source paths/bindings stay private. Failed initial
comparison artifacts are retained separately; use `saved-capture-receipt.json`
to identify the final verified output by filename and SHA-256.

The earlier backend-only upgrade is already installed: SQL015 + app publisher v7,
all three endpoints and controls disabled. See
[DISPLAY_FALLBACK_INTEGRATION.md](DISPLAY_FALLBACK_INTEGRATION.md). This newer local
price port is **not in that immutable deployed package**.

## Exact remaining work

1. Connect reviewed row publication to application persistence and latest-price
   display behavior, retaining price basis and dates. Current `latest_prices`
   consumers lack these reference distinctions; do not copy reference-only values
   there as fresh valuation inputs. No application-table writer was added here.
2. Persist approved new-listing additions and dispatch the enrichment choices
   through the existing fundamental collector. The decision code is implemented;
   its hosted side effects are not yet integrated.
3. Verify the existing fundamental/dividend publication path with real accepted
   inputs, finish daily P&L and safe operational retention, then recurring jobs.
4. Complete real user signup/email, authenticated preview, website and Android
   acceptance. Mock tests do not establish inbox delivery or device behavior.

No new schedule, production execution, app-screen switch, release APK, Git commit
or push was performed. The main application migration is not yet complete.
