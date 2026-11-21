# Hosting decision, 18 November 2026

Follow-up: the first optimization is now deployed. See
[implementation and validation](OPTIMIZATION_DEPLOYMENT_20261118.md). The measurements
and candidate discussion below describe the original decision baseline.

Keep the existing Supabase database in Ireland for now. Optimize the company's
history-loading path before migrating infrastructure. Paris is the leading
geographic candidate from the limited Morocco network measurements, but a full
project migration is not yet justified by an application comparison.

## Measured evidence

| Measurement | Result | Scope |
| --- | --- | --- |
| Current database region | eu-west-1, Ireland | Validated project-bound pooler configuration; supersedes historical Frankfurt notes |
| Morocco → Paris TCP connection | Median 32 ms; range 32–35 ms | Three public regional EC2 endpoint probes from the available Fes probe |
| Morocco → Ireland TCP connection | Median 47 ms; range 47–54 ms | Same method and probe city |
| Morocco → Frankfurt TCP connection | Median 40 ms; range 40–41 ms | Same method and probe city |
| Local machine → database round trip | Median 59.5 ms | Five SELECT 1 samples on a reused SQL connection; machine location unverified |
| Basic market-table SQL execution | 0.024–0.576 ms | One EXPLAIN ANALYZE per representative read; excludes HTTP and networking |
| Application feed SQL function | 49–54 ms execution | Two runs; feed returned AVAILABLE |
| Recent sessions SQL function | 44–52 ms execution | Two runs |
| Current ADDOHA history loading | Medians 399.2 ms and 340.8 ms | Two sets of five samples; five sequential SQL page requests; 2,154 records |
| Daily-history query candidate | Medians 76.7 ms and 74.9 ms | Two sets of five samples; one SQL request; 866 daily records |
| Daily-history equivalence | Passed | Exact record identities and order compared with current deduplication under a read-only repeatable-read snapshot |

The history-stage reduction is approximately 78–81% in these SQL experiments.
This is **not** a measured full-page improvement, and the SQL candidate is not
implemented as an application endpoint. Returning 866 daily observations through
an ordinary bounded table reader would still require pagination; a single-request
application design needs an appropriately bounded RPC/response contract.

The 15 ms Paris/Ireland difference is a TCP connection metric to public regional
EC2 APIs, not a measured improvement from moving this website or Supabase. All
nine region tests received the expected unauthenticated HTTP 400 responses from
those APIs. Only transport timings are compared. Three samples from one Morocco
probe cannot represent all Moroccan ISPs, users, or times of day. DNS, TLS and
first-byte timings are recorded separately in the evidence.

## Website measurement limits

The execution machine could establish TLS to the current site, but HTTP reads
were closed without a valid response. Neither HTTPS with HTTP/1.1/TLS 1.2 nor
plain HTTP produced a usable page. This does not prove a general website outage.

Seven external HTTPS probes succeeded: one from Fes, two from France, two from
Ireland and two from Germany. All seven received the host's JavaScript browser
challenge, and none received the rendered company page. The Fes challenge
response took 499 ms including 311 ms DNS; this is not an authenticated page-load
measurement. The requested second Morocco probe was unavailable.

The direct anonymous database REST checks returned HTTP 401. Those numbers are
retained as diagnostics and **excluded** from successful query-performance
conclusions. Authenticated SQL benchmarks used the authenticated role inside
read-only transactions. Shared market RPC checks used a synthetic, non-user,
transaction-local claim. No real users were impersonated, no HTTP sessions were
created, and no market, portfolio, authentication or configuration data changed.

We do not yet have an authenticated production browser waterfall, LCP, p95 page
response time, or PHP-host → database measurements. We have not benchmarked a
staged application in France or Ireland. Do not claim either region wins an
application comparison without that evidence.

## Why optimize before moving

The local company controller makes a series of backend calls before delivering
HTML: session validation, the market feed, two directory queries, five history
pages for ADDOHA, recent sessions, latest price, the order book and dividends.
The current local implementation therefore has up to 13 sequential backend
requests on that path. This is a code-derived count, not a production trace.
Financial-profile enrichment then requires a separate browser request.

Each backend round trip adds delay even when database execution is fast. The
history test demonstrates a material avoidable cost without changing geography.
The feed/session RPC costs also warrant inspection before assuming a slow database
server. Moving PHP to France while leaving the database in Ireland adds a
France/Ireland hop to each uncached backend request; moving both would avoid that
hop but requires a wider migration.

## Recommended sequence

1. Replace fetching all raw intraday history before rendering with a verified daily
   history read. Load the chart after the essential company/price/book information.
   Preserve the exact daily observation selection demonstrated by the equivalence check.
2. Batch independent shared-market reads and reuse safe reference data. Preserve
   per-user authorization and freshness labels; do not remove session validation
   to improve benchmarks.
3. Measure the resulting authenticated page from Morocco. Separate initial HTML,
   history/chart, financial enrichment and static assets.
4. If hosting is still the limiting factor, trial PHP hosting in Ireland near the
   existing database and in Paris using the same application and data contract.
   Compare end-to-end timings and variability before changing DNS or moving data.
5. Migrate the database to Paris only if the staged app comparison demonstrates a
   worthwhile additional gain for both PHP and Flutter. Include auth, storage,
   scheduled jobs, secrets, rollback and client configuration in that decision.

France is a sensible trial destination, not the first change to production.
This measurement task does not deploy page changes or repair order-book collection.
The previously identified stale order book remains a separate freshness issue.

## Evidence and reproduction

- `hosting_measurement_20261118.json`: basic table reads, connection diagnostics.
- `detail_measurement_20261118.json`: first history/RPC benchmark.
- `detail_repeat_measurement_20261118.json`: repeat benchmark and equivalence check.
- `regional_measurement_20261118.json`: current website, seven external probes.
- `region_candidates_20261118.json`: three Morocco samples for each region.

The JSON files contain timings, row counts and public probe measurement IDs;
no credentials, session cookies, private endpoint addresses or response bodies.

Run from the project root with the existing private database configuration:

```bash
python3 tools/measure_web_latency.py --samples 5 --output /tmp/web-latency.json
python3 tools/measure_company_history.py --output /tmp/history-latency.json
```

SQL timings use persistent direct SQL connections and therefore do not include
PostgREST overhead, PHP connection setup, HTTP auth validation or browser work.
The regional tests use Globalping's public HTTPS probes; measurement IDs in the
JSON identify the individual runs. Those tests sent only public website/regional
service targets and no application or database credentials.

## Primary documentation checked

- [Supabase regions](https://supabase.com/docs/guides/platform/regions): Ireland
  and Paris are distinct supported regions.
- [Supabase region changes](https://supabase.com/kb/troubleshooting/change-project-region-eWJo5Z):
  moving region requires a new project and migration, rather than a simple switch.
- [AWS regional codes](https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-region-billing-codes.html).
- [InfinityFree browser security](https://forum.infinityfree.com/t/browser-security-system-features-and-limitations/49353):
  hosting requires JavaScript and cookies.
- [Globalping API schema](https://github.com/jsdelivr/globalping/blob/master/public/v1/spec.yaml).
