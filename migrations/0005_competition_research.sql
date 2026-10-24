-- Stage 1B: append-only review ledgers. Legacy candidate rows remain unchanged.
-- Allocation candidates are unresolved identities, never inferred competitions.
CREATE TABLE competition_group_assessments (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL REFERENCES competition_groups(id),
  status TEXT NOT NULL CHECK(status IN ('confirmed','inferred','unresolved')),
  basis TEXT NOT NULL,
  evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json) AND json_array_length(evidence_json) > 0),
  source_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id),
  supersedes_id TEXT UNIQUE REFERENCES competition_group_assessments(id),
  assessment_version TEXT NOT NULL,
  payload_json TEXT NOT NULL CHECK(json_valid(payload_json))
);
CREATE TRIGGER assessment_confirmed_group BEFORE INSERT ON competition_group_assessments
WHEN NEW.status='confirmed' AND NOT EXISTS (
 SELECT 1 FROM competition_groups WHERE id=NEW.group_id AND resolution_status='confirmed'
   AND length(trim(official_key))>0
) BEGIN SELECT RAISE(ABORT,'confirmed_assessment_requires_official_group'); END;
CREATE TRIGGER assessment_allocation_not_inference BEFORE INSERT ON competition_group_assessments
WHEN NEW.basis='allocation_scope_only' AND NEW.status<>'unresolved'
BEGIN SELECT RAISE(ABORT,'allocation_does_not_establish_group'); END;
CREATE TRIGGER assessment_revision_scope BEFORE INSERT ON competition_group_assessments
WHEN NEW.supersedes_id IS NOT NULL AND NOT EXISTS (
 SELECT 1 FROM competition_group_assessments a WHERE a.id=NEW.supersedes_id AND a.group_id=NEW.group_id
) BEGIN SELECT RAISE(ABORT,'assessment_revision_group_mismatch'); END;

CREATE TABLE historical_group_assessments (
  id TEXT PRIMARY KEY,
  observation_id TEXT NOT NULL REFERENCES admission_observations(id),
  group_id TEXT REFERENCES competition_groups(id),
  status TEXT NOT NULL CHECK(status IN ('confirmed','inferred','unresolved')),
  reason TEXT NOT NULL,
  evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json) AND json_array_length(evidence_json) > 0),
  assessment_version TEXT NOT NULL,
  payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
  CHECK((status='unresolved' AND group_id IS NULL) OR (status IN ('inferred','confirmed') AND group_id IS NOT NULL)),
  UNIQUE(observation_id, assessment_version)
);
CREATE TRIGGER historical_assessment_scope BEFORE INSERT ON historical_group_assessments
WHEN NEW.group_id IS NOT NULL AND NOT EXISTS (
 SELECT 1 FROM competition_groups g JOIN admission_observations o ON o.id=NEW.observation_id
 WHERE g.id=NEW.group_id AND g.campaign_id=o.campaign_id
   AND (NEW.status<>'confirmed' OR g.resolution_status='confirmed')
) BEGIN SELECT RAISE(ABORT,'historical_group_unconfirmed_or_cross_campaign'); END;

CREATE TRIGGER group_assessments_no_update BEFORE UPDATE ON competition_group_assessments
BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER group_assessments_no_delete BEFORE DELETE ON competition_group_assessments
BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER history_assessments_no_update BEFORE UPDATE ON historical_group_assessments
BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER history_assessments_no_delete BEFORE DELETE ON historical_group_assessments
BEGIN SELECT RAISE(ABORT,'append_only'); END;
