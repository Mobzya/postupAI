CREATE TRIGGER program_revision BEFORE INSERT ON program_versions
WHEN (NEW.revision = 1 AND NEW.supersedes_id IS NOT NULL)
  OR (NEW.revision > 1 AND NOT EXISTS (
    SELECT 1 FROM program_versions old WHERE old.id = NEW.supersedes_id
      AND old.program_id = NEW.program_id AND old.admission_year = NEW.admission_year
      AND old.revision = NEW.revision - 1
  )) BEGIN SELECT RAISE(ABORT,'invalid_revision_chain'); END;

CREATE TRIGGER rule_revision BEFORE INSERT ON admission_rules
WHEN (NEW.revision = 1 AND NEW.supersedes_id IS NOT NULL)
  OR (NEW.revision > 1 AND NOT EXISTS (
    SELECT 1 FROM admission_rules old WHERE old.id = NEW.supersedes_id
      AND old.track_id = NEW.track_id AND old.revision = NEW.revision - 1
  )) BEGIN SELECT RAISE(ABORT,'invalid_revision_chain'); END;

CREATE TRIGGER metric_revision BEFORE INSERT ON historical_metrics
WHEN (NEW.revision = 1 AND NEW.supersedes_id IS NOT NULL)
  OR (NEW.revision > 1 AND NOT EXISTS (
    SELECT 1 FROM historical_metrics old WHERE old.id = NEW.supersedes_id
      AND old.track_id = NEW.track_id AND old.metric = NEW.metric AND old.revision = NEW.revision - 1
  )) BEGIN SELECT RAISE(ABORT,'invalid_revision_chain'); END;

CREATE TRIGGER distribution_revision BEFORE INSERT ON score_distributions
WHEN (NEW.revision = 1 AND NEW.supersedes_id IS NOT NULL)
  OR (NEW.revision > 1 AND NOT EXISTS (
    SELECT 1 FROM score_distributions old WHERE old.id = NEW.supersedes_id
      AND old.track_id = NEW.track_id AND old.revision = NEW.revision - 1
  )) BEGIN SELECT RAISE(ABORT,'invalid_revision_chain'); END;

CREATE TRIGGER curve_scope BEFORE INSERT ON admission_curves
WHEN NOT EXISTS (SELECT 1 FROM admission_rules WHERE id = NEW.rule_id AND track_id = NEW.track_id)
  OR NOT EXISTS (SELECT 1 FROM model_versions WHERE id = NEW.model_version_id AND kind = 'admission_curve')
BEGIN SELECT RAISE(ABORT,'curve_scope_mismatch'); END;
