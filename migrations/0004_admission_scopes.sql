-- Additive migration: legacy stage-0 rows and APIs remain intact.
CREATE TABLE campuses (
  id TEXT PRIMARY KEY,
  institution_id TEXT NOT NULL REFERENCES institutions(id),
  name TEXT NOT NULL,
  city TEXT NOT NULL,
  UNIQUE(institution_id, name)
);
CREATE TABLE study_fields (
  id TEXT PRIMARY KEY,
  official_code TEXT NOT NULL UNIQUE,
  degree TEXT NOT NULL CHECK(degree IN ('bachelor','specialist','basic_higher'))
);
CREATE TABLE admission_campaigns (
  id TEXT PRIMARY KEY,
  institution_id TEXT NOT NULL REFERENCES institutions(id),
  campus_id TEXT NOT NULL REFERENCES campuses(id),
  year INTEGER NOT NULL REFERENCES admission_years(year),
  UNIQUE(institution_id, campus_id, year)
);
ALTER TABLE program_versions ADD COLUMN campus_id TEXT REFERENCES campuses(id);
ALTER TABLE program_versions ADD COLUMN field_id TEXT REFERENCES study_fields(id);
ALTER TABLE program_versions ADD COLUMN catalog_metadata_json TEXT CHECK(catalog_metadata_json IS NULL OR json_valid(catalog_metadata_json));

CREATE TABLE competition_groups (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES admission_campaigns(id),
  official_key TEXT,
  label TEXT NOT NULL,
  resolution_status TEXT NOT NULL CHECK(resolution_status IN ('candidate','confirmed')),
  source_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id),
  CHECK(resolution_status = 'candidate' OR official_key IS NOT NULL)
);
CREATE TABLE campaign_field_offerings (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES admission_campaigns(id),
  field_id TEXT NOT NULL REFERENCES study_fields(id),
  official_name TEXT NOT NULL,
  study_form TEXT NOT NULL,
  adapter_version TEXT NOT NULL,
  source_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id),
  evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),
  UNIQUE(campaign_id, field_id, study_form, source_snapshot_id, adapter_version)
);
CREATE TABLE competition_group_members (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL REFERENCES competition_groups(id),
  field_id TEXT NOT NULL REFERENCES study_fields(id),
  program_version_id TEXT REFERENCES program_versions(id),
  evidence_status TEXT NOT NULL CHECK(evidence_status IN ('allocation_scope_only','confirmed'))
);
CREATE UNIQUE INDEX group_member_identity ON competition_group_members(group_id, field_id, coalesce(program_version_id,''));
CREATE TABLE competition_conditions (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL REFERENCES competition_groups(id),
  category TEXT NOT NULL CHECK(category IN ('budget_total','general_budget','special_quota','separate_quota','targeted','bvi','paid','grant','unknown')),
  study_form TEXT NOT NULL,
  applicant_basis TEXT NOT NULL,
  rules_json TEXT NOT NULL CHECK(json_valid(rules_json)),
  source_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id)
);
CREATE TABLE seat_allocations (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES admission_campaigns(id),
  condition_id TEXT REFERENCES competition_conditions(id),
  source_row_key TEXT NOT NULL,
  funding TEXT NOT NULL CHECK(funding IN ('federal_budget_total','paid')),
  places INTEGER NOT NULL CHECK(places >= 0),
  scope_label TEXT NOT NULL,
  adapter_version TEXT NOT NULL,
  source_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id),
  evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),
  UNIQUE(source_snapshot_id, source_row_key, adapter_version)
);
CREATE TABLE seat_allocation_members (
  allocation_id TEXT NOT NULL REFERENCES seat_allocations(id),
  field_id TEXT NOT NULL REFERENCES study_fields(id),
  PRIMARY KEY(allocation_id, field_id)
);
CREATE TABLE admission_observations (
  id TEXT PRIMARY KEY,
  row_key TEXT NOT NULL,
  campaign_id TEXT NOT NULL REFERENCES admission_campaigns(id),
  field_id TEXT REFERENCES study_fields(id),
  group_id TEXT REFERENCES competition_groups(id),
  group_mapping_status TEXT NOT NULL CHECK(group_mapping_status IN ('unresolved','confirmed')),
  official_code_raw TEXT,
  official_name TEXT NOT NULL,
  division TEXT,
  competition_category TEXT NOT NULL,
  threshold_status TEXT NOT NULL CHECK(threshold_status IN ('numeric','bvi_only','not_published','not_offered','parse_error','manual_review')),
  cutoff REAL CHECK(cutoff >= 0),
  mean_ege_score REAL CHECK(mean_ege_score BETWEEN 0 AND 100),
  mean_entrance_total REAL CHECK(mean_entrance_total >= 0),
  adapter_version TEXT NOT NULL,
  source_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id),
  payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
  CHECK((threshold_status = 'numeric' AND cutoff IS NOT NULL) OR (threshold_status <> 'numeric' AND cutoff IS NULL)),
  CHECK((group_mapping_status = 'unresolved' AND group_id IS NULL) OR (group_mapping_status = 'confirmed' AND group_id IS NOT NULL)),
  UNIQUE(source_snapshot_id, row_key, adapter_version)
);
CREATE INDEX observation_campaign ON admission_observations(campaign_id, official_code_raw);
CREATE INDEX allocation_campaign ON seat_allocations(campaign_id, funding);

CREATE TRIGGER observation_group_scope BEFORE INSERT ON admission_observations
WHEN NEW.group_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM competition_groups g WHERE g.id = NEW.group_id
    AND g.campaign_id = NEW.campaign_id AND g.resolution_status = 'confirmed'
) BEGIN SELECT RAISE(ABORT,'unconfirmed_or_cross_campaign_group'); END;

CREATE TRIGGER member_program_scope BEFORE INSERT ON competition_group_members
WHEN NEW.program_version_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM program_versions p JOIN competition_groups g ON g.id=NEW.group_id
  JOIN admission_campaigns c ON c.id=g.campaign_id
  WHERE p.id=NEW.program_version_id AND p.field_id=NEW.field_id
    AND p.campus_id=c.campus_id AND p.admission_year=c.year
) BEGIN SELECT RAISE(ABORT,'program_group_scope_mismatch'); END;

CREATE TRIGGER campaign_campus_scope BEFORE INSERT ON admission_campaigns
WHEN NOT EXISTS (SELECT 1 FROM campuses c WHERE c.id = NEW.campus_id AND c.institution_id = NEW.institution_id)
BEGIN SELECT RAISE(ABORT,'campus_institution_mismatch'); END;

CREATE TRIGGER allocation_scope BEFORE INSERT ON seat_allocations
WHEN NEW.condition_id IS NOT NULL AND NOT EXISTS (
 SELECT 1 FROM competition_conditions c JOIN competition_groups g ON g.id=c.group_id
 WHERE c.id=NEW.condition_id AND g.campaign_id=NEW.campaign_id
) BEGIN SELECT RAISE(ABORT,'allocation_campaign_mismatch'); END;

CREATE TRIGGER observations_no_update BEFORE UPDATE ON admission_observations BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER observations_no_delete BEFORE DELETE ON admission_observations BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER allocations_no_update BEFORE UPDATE ON seat_allocations BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER allocations_no_delete BEFORE DELETE ON seat_allocations BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER groups_no_update BEFORE UPDATE ON competition_groups BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER groups_no_delete BEFORE DELETE ON competition_groups BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER conditions_no_update BEFORE UPDATE ON competition_conditions BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER conditions_no_delete BEFORE DELETE ON competition_conditions BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER offerings_no_update BEFORE UPDATE ON campaign_field_offerings BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER offerings_no_delete BEFORE DELETE ON campaign_field_offerings BEGIN SELECT RAISE(ABORT,'append_only'); END;
