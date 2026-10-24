-- Annual score constraints; deliberately separate from unresolved competition groups.
CREATE TABLE academic_rule_versions (
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 campus_id TEXT NOT NULL REFERENCES campuses(id),
 year INTEGER NOT NULL REFERENCES admission_years(year),
 field_id TEXT NOT NULL REFERENCES study_fields(id),
 category TEXT NOT NULL CHECK(category IN ('general_budget','paid')),
 applicant_basis TEXT NOT NULL CHECK(applicant_basis='school_ege'),
 source_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id),
 adapter_version TEXT NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json))
);
CREATE INDEX academic_rule_scope ON academic_rule_versions(institution_id,campus_id,year,field_id,category,applicant_basis);
CREATE TRIGGER academic_rule_no_update BEFORE UPDATE ON academic_rule_versions
BEGIN SELECT RAISE(ABORT,'append_only'); END;
CREATE TRIGGER academic_rule_no_delete BEFORE DELETE ON academic_rule_versions
BEGIN SELECT RAISE(ABORT,'append_only'); END;
