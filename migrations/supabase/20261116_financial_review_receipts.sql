-- Private audit trail for explicitly reviewed primary-document corrections.
CREATE TABLE market_admin.financial_review_receipts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 company_id text NOT NULL,
 fiscal_year integer NOT NULL CHECK(fiscal_year BETWEEN 1900 AND 2200),
 evidence_sha256 text NOT NULL CHECK(evidence_sha256 ~ '^[a-f0-9]{64}$'),
 before_values jsonb NOT NULL,
 applied_values jsonb NOT NULL,
 evidence_metadata jsonb NOT NULL,
 review_method text NOT NULL,
 reviewed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE market_admin.financial_review_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON market_admin.financial_review_receipts FROM PUBLIC,anon,authenticated,service_role;
