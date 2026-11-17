-- Additive private source history. No existing market or portfolio table changes.
-- Names and raw evidence remain private; application exposure is a separate step.
CREATE SCHEMA market_history_v1;
REVOKE ALL ON SCHEMA market_history_v1 FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE market_history_v1.batches (
    batch_id text PRIMARY KEY CHECK (batch_id ~ '^[a-f0-9]{64}$'),
    manifest jsonb NOT NULL CHECK (jsonb_typeof(manifest) = 'object'),
    imported_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE market_history_v1.captures (
    batch_id text NOT NULL REFERENCES market_history_v1.batches,
    symbol text NOT NULL,
    completed_at timestamptz NOT NULL,
    raw_sha256 text NOT NULL CHECK (raw_sha256 ~ '^[a-f0-9]{64}$'),
    request_sha256 text NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
    receipt_sha256 text NOT NULL CHECK (receipt_sha256 ~ '^[a-f0-9]{64}$'),
    raw_gzip bytea NOT NULL,
    request_gzip bytea NOT NULL,
    receipt_gzip bytea NOT NULL,
    PRIMARY KEY (batch_id, symbol)
);
CREATE TABLE market_history_v1.observations (
    batch_id text NOT NULL,
    symbol text NOT NULL,
    source_ordinal integer NOT NULL CHECK (source_ordinal >= 0),
    observation_id text NOT NULL CHECK (observation_id ~ '^[a-f0-9]{64}$'),
    period_day date NOT NULL,
    source_daily_label text NOT NULL,
    close_text text NOT NULL,
    bar jsonb NOT NULL CHECK (jsonb_typeof(bar) = 'object'),
    quality_warnings text[] NOT NULL,
    observed_at timestamptz CHECK (observed_at IS NULL),
    observation_time_status text NOT NULL DEFAULT 'UNKNOWN'
        CHECK (observation_time_status = 'UNKNOWN'),
    price_definition text NOT NULL DEFAULT 'PROVIDER_DAILY_CLOSE_CANDIDATE'
        CHECK (price_definition = 'PROVIDER_DAILY_CLOSE_CANDIDATE'),
    PRIMARY KEY (batch_id, symbol, source_ordinal),
    UNIQUE (batch_id, observation_id),
    FOREIGN KEY (batch_id, symbol) REFERENCES market_history_v1.captures
);
-- Economic date is deliberately NOT unique. Conflicting observations survive.
CREATE INDEX observations_economic_date
    ON market_history_v1.observations (symbol, period_day);

ALTER TABLE market_history_v1.batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_history_v1.captures ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_history_v1.observations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA market_history_v1
    FROM PUBLIC, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA market_history_v1
    REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated, service_role;
