PRAGMA foreign_keys = ON;

CREATE TABLE institutions (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  official_url TEXT NOT NULL CHECK(official_url LIKE 'https://%')
);

CREATE TABLE admission_years (
  year INTEGER PRIMARY KEY CHECK(year BETWEEN 2000 AND 2100)
);

CREATE TABLE import_batches (
  id TEXT PRIMARY KEY,
  dataset_sha256 TEXT NOT NULL CHECK(length(dataset_sha256) = 64),
  adapter_version TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  is_synthetic INTEGER NOT NULL CHECK(is_synthetic IN (0,1)),
  UNIQUE(dataset_sha256, adapter_version)
);

CREATE TABLE source_records (
  id TEXT PRIMARY KEY,
  institution_id TEXT NOT NULL REFERENCES institutions(id),
  url TEXT NOT NULL CHECK(url LIKE 'https://%'),
  document_type TEXT NOT NULL,
  years_json TEXT NOT NULL CHECK(json_valid(years_json) AND json_type(years_json) = 'array'),
  last_checked_at TEXT,
  extraction_method TEXT NOT NULL,
  parsing_status TEXT NOT NULL CHECK(parsing_status IN ('not_started','success','partial','blocked','error','manual_review')),
  reliability TEXT NOT NULL CHECK(reliability IN ('unassessed','official_unverified','verified','conflict')),
  completeness REAL CHECK(completeness BETWEEN 0 AND 1),
  original_url TEXT NOT NULL CHECK(original_url LIKE 'https://%'),
  notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX source_institution ON source_records(institution_id, parsing_status);

CREATE TABLE source_snapshots (
  id TEXT PRIMARY KEY,
  source_record_id TEXT NOT NULL REFERENCES source_records(id),
  import_batch_id TEXT NOT NULL REFERENCES import_batches(id),
  captured_at TEXT NOT NULL,
  sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
  artifact_path TEXT NOT NULL,
  UNIQUE(source_record_id, sha256),
  UNIQUE(id, source_record_id)
);

CREATE TABLE programs (
  id TEXT PRIMARY KEY,
  institution_id TEXT NOT NULL REFERENCES institutions(id),
  classification TEXT NOT NULL CHECK(classification IN ('mathematics','computer_science','engineering','data_ai','adjacent','unreviewed')),
  classification_reason TEXT NOT NULL,
  is_synthetic INTEGER NOT NULL DEFAULT 0 CHECK(is_synthetic IN (0,1))
);
CREATE INDEX program_institution ON programs(institution_id);

CREATE TABLE program_versions (
  id TEXT PRIMARY KEY,
  program_id TEXT NOT NULL REFERENCES programs(id),
  admission_year INTEGER NOT NULL REFERENCES admission_years(year),
  revision INTEGER NOT NULL CHECK(revision >= 1),
  name TEXT NOT NULL,
  official_code TEXT NOT NULL,
  campus TEXT NOT NULL,
  degree TEXT NOT NULL CHECK(degree IN ('bachelor','specialist','basic_higher')),
  study_form TEXT NOT NULL CHECK(study_form IN ('full_time','part_time','extramural','online')),
  verification_status TEXT NOT NULL CHECK(verification_status IN ('unverified','verified','conflict')),
  source_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id),
  supersedes_id TEXT UNIQUE REFERENCES program_versions(id),
  CHECK(supersedes_id IS NULL OR supersedes_id <> id),
  UNIQUE(program_id, admission_year, revision)
);
CREATE INDEX version_program_year ON program_versions(program_id, admission_year);

CREATE TABLE admission_tracks (
  id TEXT PRIMARY KEY,
  program_version_id TEXT NOT NULL REFERENCES program_versions(id),
  category TEXT NOT NULL CHECK(category IN (
    'general_budget','special_quota','separate_quota','targeted','bvi','paid','grant','special_selection'
  )),
  competition_group_key TEXT NOT NULL,
  -- Shared key identifies one competition across several educational programs.
  UNIQUE(program_version_id, category, competition_group_key)
);

CREATE TABLE admission_rules (
  id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL REFERENCES admission_tracks(id),
  revision INTEGER NOT NULL CHECK(revision >= 1),
  rules_json TEXT NOT NULL CHECK(json_valid(rules_json) AND json_type(rules_json) = 'object'),
  verification_status TEXT NOT NULL CHECK(verification_status IN ('unverified','verified','conflict')),
  source_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id),
  supersedes_id TEXT UNIQUE REFERENCES admission_rules(id),
  CHECK(supersedes_id IS NULL OR supersedes_id <> id),
  UNIQUE(track_id, revision)
);

CREATE TABLE historical_metrics (
  id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL REFERENCES admission_tracks(id),
  metric TEXT NOT NULL CHECK(metric IN ('seats','cutoff','mean_score','applications','enrolled','bvi_enrolled','quota_enrolled')),
  value REAL CHECK(value >= 0),
  missing_reason TEXT,
  unit TEXT NOT NULL CHECK(unit IN ('exam_points','competition_points','people','applications','places')),
  methodology TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('unverified','verified','conflict','missing')),
  source_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id),
  revision INTEGER NOT NULL CHECK(revision >= 1),
  supersedes_id TEXT UNIQUE REFERENCES historical_metrics(id),
  CHECK(supersedes_id IS NULL OR supersedes_id <> id),
  CHECK((value IS NULL AND missing_reason IS NOT NULL AND status = 'missing') OR
        (value IS NOT NULL AND missing_reason IS NULL AND status <> 'missing')),
  UNIQUE(track_id, metric, revision)
);
CREATE INDEX metric_track ON historical_metrics(track_id, metric, revision);

CREATE TABLE score_distributions (
  id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL REFERENCES admission_tracks(id),
  source_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id),
  distribution_json TEXT NOT NULL CHECK(json_valid(distribution_json) AND json_type(distribution_json) = 'array'),
  score_unit TEXT NOT NULL CHECK(score_unit IN ('exam_points','competition_points')),
  population_definition TEXT NOT NULL,
  methodology TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision >= 1),
  supersedes_id TEXT UNIQUE REFERENCES score_distributions(id),
  CHECK(supersedes_id IS NULL OR supersedes_id <> id),
  UNIQUE(track_id, revision)
);

CREATE TABLE model_versions (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('ege_progress','admission_curve')),
  artifact_path TEXT NOT NULL,
  artifact_sha256 TEXT NOT NULL CHECK(length(artifact_sha256) = 64),
  dataset_sha256 TEXT NOT NULL CHECK(length(dataset_sha256) = 64),
  config_sha256 TEXT NOT NULL CHECK(length(config_sha256) = 64),
  code_revision TEXT NOT NULL,
  assumptions_json TEXT NOT NULL CHECK(json_valid(assumptions_json)),
  validated_at TEXT,
  is_synthetic INTEGER NOT NULL CHECK(is_synthetic IN (0,1)),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE admission_curves (
  id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL REFERENCES admission_tracks(id),
  rule_id TEXT NOT NULL REFERENCES admission_rules(id),
  model_version_id TEXT NOT NULL REFERENCES model_versions(id),
  scenario TEXT NOT NULL CHECK(scenario IN ('baseline','optimistic','pessimistic')),
  points_json TEXT NOT NULL CHECK(json_valid(points_json) AND json_type(points_json) = 'array'),
  assumptions_json TEXT NOT NULL CHECK(json_valid(assumptions_json)),
  UNIQUE(track_id, rule_id, model_version_id, scenario)
);

CREATE TABLE user_profiles (
  id TEXT PRIMARY KEY CHECK(length(id) = 64),
  consent_version TEXT NOT NULL,
  settings_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(settings_json)),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE TABLE user_score_history (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  subject TEXT NOT NULL,
  score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),
  mock_date TEXT NOT NULL,
  mock_type TEXT NOT NULL,
  hours_per_week REAL NOT NULL CHECK(hours_per_week BETWEEN 0 AND 168),
  regularity REAL NOT NULL CHECK(regularity BETWEEN 0 AND 1),
  target INTEGER CHECK(target BETWEEN 0 AND 100),
  expected_exam_date TEXT NOT NULL
);
CREATE INDEX scores_user ON user_score_history(user_id, subject, mock_date);
CREATE TABLE user_achievements (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  details_json TEXT NOT NULL CHECK(json_valid(details_json)),
  verification_status TEXT NOT NULL DEFAULT 'self_reported' CHECK(verification_status IN ('self_reported','verified','rejected'))
);
CREATE INDEX achievements_user ON user_achievements(user_id);
CREATE TABLE saved_programs (
  user_id TEXT NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  program_id TEXT NOT NULL REFERENCES programs(id),
  PRIMARY KEY(user_id, program_id)
);
CREATE TABLE forecast_results (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  track_id TEXT REFERENCES admission_tracks(id),
  rule_id TEXT REFERENCES admission_rules(id),
  ege_model_id TEXT REFERENCES model_versions(id),
  admission_model_id TEXT REFERENCES model_versions(id),
  input_json TEXT NOT NULL CHECK(json_valid(input_json)),
  result_json TEXT NOT NULL CHECK(json_valid(result_json)),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX forecasts_user ON forecast_results(user_id, created_at);

CREATE TABLE telegram_updates (
  update_id INTEGER PRIMARY KEY CHECK(update_id >= 0),
  expires_at INTEGER NOT NULL
);
CREATE INDEX update_expiry ON telegram_updates(expires_at);

CREATE VIEW latest_historical_metrics AS
SELECT m.* FROM historical_metrics m
WHERE NOT EXISTS (
  SELECT 1 FROM historical_metrics newer
  WHERE newer.track_id = m.track_id AND newer.metric = m.metric AND newer.revision > m.revision
);

-- Numeric aggregates and their provenance are append-only; corrections add a revision.
CREATE TRIGGER metrics_no_update BEFORE UPDATE ON historical_metrics BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER metrics_no_delete BEFORE DELETE ON historical_metrics BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER snapshots_no_update BEFORE UPDATE ON source_snapshots BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER snapshots_no_delete BEFORE DELETE ON source_snapshots BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER versions_no_update BEFORE UPDATE ON program_versions BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER versions_no_delete BEFORE DELETE ON program_versions BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER rules_no_update BEFORE UPDATE ON admission_rules BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER rules_no_delete BEFORE DELETE ON admission_rules BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER distributions_no_update BEFORE UPDATE ON score_distributions BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER distributions_no_delete BEFORE DELETE ON score_distributions BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER curves_no_update BEFORE UPDATE ON admission_curves BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER curves_no_delete BEFORE DELETE ON admission_curves BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER models_no_update BEFORE UPDATE ON model_versions BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER models_no_delete BEFORE DELETE ON model_versions BEGIN SELECT RAISE(ABORT,'append_only'); END;
