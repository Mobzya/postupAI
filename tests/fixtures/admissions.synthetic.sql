-- SYNTHETIC ONLY. Invented programs, rules, scores, snapshots; never import into production.
INSERT INTO admission_years VALUES (2026);
INSERT INTO import_batches(id,dataset_sha256,adapter_version,is_synthetic)
VALUES ('synthetic-batch',printf('%064d',0),'synthetic-v1',1);
INSERT INTO source_records(id,institution_id,url,document_type,years_json,extraction_method,parsing_status,reliability,original_url)
VALUES ('synthetic-source','hse','https://example.invalid/synthetic','synthetic_fixture','[2026]','synthetic','success','unassessed','https://example.invalid/synthetic');
INSERT INTO source_snapshots(id,source_record_id,import_batch_id,captured_at,sha256,artifact_path)
VALUES ('synthetic-snapshot','synthetic-source','synthetic-batch','2026-01-01T00:00:00Z',printf('%064d',1),'tests/fixtures/admissions.synthetic.sql');
INSERT INTO programs(id,institution_id,classification,classification_reason,is_synthetic)
VALUES ('synthetic-program','hse','computer_science','SYNTHETIC fixture',1);
INSERT INTO program_versions(id,program_id,admission_year,revision,name,official_code,campus,degree,study_form,verification_status,source_snapshot_id)
VALUES ('synthetic-v1','synthetic-program',2026,1,'Synthetic program','00.00.00','Synthetic campus','bachelor','full_time','unverified','synthetic-snapshot');
INSERT INTO admission_tracks(id,program_version_id,category,competition_group_key) VALUES
('synthetic-budget','synthetic-v1','general_budget','synthetic-budget-group'),
('synthetic-paid','synthetic-v1','paid','synthetic-paid-group');
INSERT INTO admission_rules(id,track_id,revision,rules_json,verification_status,source_snapshot_id)
VALUES ('synthetic-rules','synthetic-budget',1,'{}','unverified','synthetic-snapshot');
INSERT INTO historical_metrics(id,track_id,metric,value,unit,methodology,status,source_snapshot_id,revision)
VALUES ('synthetic-cutoff','synthetic-budget','cutoff',250,'competition_points','SYNTHETIC example; includes achievement points','unverified','synthetic-snapshot',1);
