-- Staging observations keep unknown campus/year/code nullable. They are not
-- automatically promoted to fully verified program_versions or competitions.
CREATE TABLE catalog_observations (
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 name TEXT NOT NULL CHECK(length(trim(name))>0),
 campus TEXT,
 degree TEXT CHECK(degree IS NULL OR degree IN ('bachelor','specialist','basic_higher')),
 official_code TEXT,
 campaign_year INTEGER REFERENCES admission_years(year),
 kind TEXT NOT NULL CHECK(kind IN ('program_profile','marketing_track','direction')),
 program_url TEXT,
 legacy_program_id TEXT REFERENCES programs(id),
 source_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id),
 adapter_version TEXT NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json))
);
CREATE INDEX catalog_observation_institution ON catalog_observations(institution_id,kind);
CREATE TRIGGER catalog_observations_no_update BEFORE UPDATE ON catalog_observations
BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER catalog_observations_no_delete BEFORE DELETE ON catalog_observations
BEGIN SELECT RAISE(ABORT,'append_only'); END;
