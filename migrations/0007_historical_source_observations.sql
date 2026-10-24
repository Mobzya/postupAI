CREATE TABLE historical_source_observations (
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 year INTEGER NOT NULL REFERENCES admission_years(year),
 name TEXT NOT NULL,
 official_code TEXT,
 metric TEXT NOT NULL CHECK(metric IN ('cutoff','mean_ege_score','mean_entrance_total','minimum_entrance_total')),
 unit TEXT NOT NULL CHECK(unit IN ('competition_points','exam_total_points','exam_points','unspecified_points')),
 category TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('numeric','lower_bound','not_published','bvi_only','priority_only','manual_review','not_offered','parse_error')),
 value REAL CHECK(value IS NULL OR value>=0),
 source_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id),
 parent_observation_id TEXT REFERENCES admission_observations(id),
 adapter_version TEXT NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 CHECK((status IN ('numeric','lower_bound') AND value IS NOT NULL) OR
       (status NOT IN ('numeric','lower_bound') AND value IS NULL)),
 CHECK(unit<>'exam_points' OR value IS NULL OR value<=100)
);
CREATE INDEX historical_source_scope ON historical_source_observations(institution_id,year,metric,category,unit);
CREATE TRIGGER historical_sources_no_update BEFORE UPDATE ON historical_source_observations
BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER historical_sources_no_delete BEFORE DELETE ON historical_source_observations
BEGIN SELECT RAISE(ABORT,'append_only'); END;
