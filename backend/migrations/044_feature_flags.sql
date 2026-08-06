-- Runtime feature-flag control plane. Lets a platform admin toggle features from
-- the admin UI without a redeploy. A row here is an OVERRIDE of the env-var default
-- (services/feature_flags.FLAGS registry names the env default per key); absence of
-- a row means "use the env default". Read at request time (short per-worker cache).
CREATE TABLE IF NOT EXISTS feature_flags (
    key         text PRIMARY KEY,
    enabled     boolean NOT NULL,
    updated_by  uuid REFERENCES users(id) ON DELETE SET NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
