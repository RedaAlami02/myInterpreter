-- Recovery staging only. Application tables and auth mapping come after review.
-- Keep original payloads private, including legacy ownership and permissions.
CREATE SCHEMA IF NOT EXISTS migration_stage;

REVOKE ALL ON SCHEMA migration_stage
    FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS migration_stage.datasets (
    dataset_id text PRIMARY KEY CHECK (dataset_id ~ '^[0-9a-f]{64}$'),
    dataset_name text NOT NULL,
    source_kind text NOT NULL,
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    source_bytes bigint NOT NULL CHECK (source_bytes >= 0),
    row_count bigint NOT NULL CHECK (row_count >= 0),
    source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    imported_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS migration_stage.documents (
    dataset_id text NOT NULL
        REFERENCES migration_stage.datasets(dataset_id),
    document_id text NOT NULL CHECK (length(document_id) > 0),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    PRIMARY KEY (dataset_id, document_id),
    CHECK (NOT (payload ? '$id') OR payload ->> '$id' = document_id)
);

ALTER TABLE migration_stage.datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE migration_stage.documents ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON ALL TABLES IN SCHEMA migration_stage
    FROM PUBLIC, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA migration_stage
    REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated, service_role;
