import copy
import json
import sqlite3
import unittest
from unittest.mock import patch

from pipeline.competition_research import (OUTPUT, VERSION, build_research, import_research,
                                           validate_research, reviewed_findings)
from pipeline.import_mephi import insert_sql
from pipeline.mephi_pipeline import OUT
from pipeline.sources import SnapshotStore, canonical
from pipeline.validate import ROOT


class CompetitionResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset=json.loads((OUT/'dataset.json').read_text())
        cls.store=SnapshotStore()
        cls.research=json.loads(OUTPUT.read_text())

    def setUp(self):
        self.db=sqlite3.connect(':memory:'); self.db.execute('PRAGMA foreign_keys=ON')
        for path in sorted((ROOT/'migrations').glob('*.sql')): self.db.executescript(path.read_text())

    def tearDown(self): self.db.close()

    def load(self): return import_research(self.db,self.research,self.dataset,self.store)

    def test_research_replays_without_promoting_allocations(self):
        self.assertEqual(build_research(self.dataset,self.store),self.research)
        self.assertEqual(self.research['metrics']['confirmed'],0)
        self.assertEqual(self.research['metrics']['inferred'],0)
        self.assertEqual(self.research['metrics']['unresolved_allocation_candidates'],39)
        self.assertIsNone(self.research['metrics']['actual_competition_count'])

    def test_research_import_repeated_and_legacy_data_preserved(self):
        self.assertGreater(self.load(),0); self.assertEqual(self.load(),0)
        for table,count in [('admission_observations',286),('programs',82),('seat_allocations',39),
                            ('competition_group_assessments',39),('historical_group_assessments',286)]:
            self.assertEqual(self.db.execute('SELECT count(*) FROM '+table).fetchone()[0],count)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(self.db.execute("SELECT count(*) FROM competition_groups WHERE resolution_status='confirmed'").fetchone()[0],0)

    def test_status_tampering_or_cross_year_claim_does_not_replay(self):
        for key,value in [('status','confirmed'),('status','inferred'),('campaign_year',2025)]:
            modified=copy.deepcopy(self.research); modified['group_assessments'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                validate_research(modified,self.dataset,self.store)

    def test_six_original_cases_keep_separate_evidence(self):
        findings=reviewed_findings()['discrepancies']
        self.assertEqual({r['code'] for r in findings},{'04.03.01','04.03.02','06.03.01','09.03.02','31.05.01','10.05.05'})
        self.assertTrue(all(r['status']=='unresolved' and r['evidence'] for r in findings))

    def test_excerpt_hash_tampering_is_rejected(self):
        from pathlib import Path
        original=Path.read_bytes
        def read(path):
            raw=original(path)
            return raw+b'changed' if path.name=='entrants-navigation.official-excerpt.html' else raw
        with patch.object(Path,'read_bytes',read),self.assertRaisesRegex(ValueError,'research_excerpt_hash_mismatch'):
            reviewed_findings()

    def test_database_prevents_candidate_confirmation_and_allocation_inference(self):
        self.load()
        columns=[r[1] for r in self.db.execute('PRAGMA table_info(competition_group_assessments)')]
        original=dict(zip(columns,self.db.execute('SELECT * FROM competition_group_assessments LIMIT 1').fetchone()))
        for status in ['inferred','confirmed']:
            row=dict(original,id='synthetic-'+status,status=status)
            with self.subTest(status=status),self.assertRaises(sqlite3.IntegrityError):
                self.db.execute('INSERT INTO competition_group_assessments('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))

    def test_database_blocks_cross_year_historical_match(self):
        self.load()
        columns=[r[1] for r in self.db.execute('PRAGMA table_info(historical_group_assessments)')]
        row=dict(zip(columns,self.db.execute('SELECT * FROM historical_group_assessments LIMIT 1').fetchone()))
        row.update(id='synthetic-cross-year',group_id=self.research['group_assessments'][0]['group_id'],status='inferred',assessment_version='synthetic-new-version')
        with self.assertRaisesRegex(sqlite3.IntegrityError,'cross_campaign'):
            self.db.execute('INSERT INTO historical_group_assessments('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))

    def test_ledgers_are_append_only_and_payload_collision_rejected(self):
        self.load()
        for table in ['competition_group_assessments','historical_group_assessments']:
            with self.assertRaises(sqlite3.IntegrityError): self.db.execute('UPDATE '+table+' SET status="confirmed"')
            with self.assertRaises(sqlite3.IntegrityError): self.db.execute('DELETE FROM '+table)
        columns=[r[1] for r in self.db.execute('PRAGMA table_info(competition_group_assessments)')]
        row=dict(zip(columns,self.db.execute('SELECT * FROM competition_group_assessments LIMIT 1').fetchone()))
        row['payload_json']=canonical({'synthetic':'changed-payload'})
        with self.assertRaises(sqlite3.IntegrityError): self.db.execute(insert_sql('competition_group_assessments',row))

    def test_failed_research_batch_rolls_back_base_and_new_rows(self):
        self.db.executescript("CREATE TRIGGER synthetic_failure BEFORE INSERT ON historical_group_assessments BEGIN SELECT RAISE(ABORT,'synthetic-failure'); END;")
        with self.assertRaises(sqlite3.IntegrityError): self.load()
        self.assertEqual(self.db.execute('SELECT count(*) FROM admission_observations').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM competition_group_assessments').fetchone()[0],0)

    def test_no_rosters_or_identifiers_in_metadata_artifacts(self):
        access=reviewed_findings()['external_list_access']
        self.assertEqual(access['http_status'],451)
        self.assertFalse(access['applicant_identifiers_saved'])
        self.assertFalse(access['response_body_saved'])
        for r in self.research['history_assessments']:
            self.assertEqual(r['status'],'unresolved'); self.assertIsNone(r['group_id'])


if __name__=='__main__': unittest.main()
