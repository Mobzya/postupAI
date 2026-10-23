import copy
import json
from pathlib import Path
import sqlite3
import unittest

from lxml import html

from pipeline.import_mephi import import_dataset, import_plan
from pipeline.mephi import ParseError, parse_catalog, parse_history, parse_seats, threshold
from pipeline.mephi_pipeline import validate_dataset
from pipeline.sources import SnapshotStore, digest
from pipeline.validate import ROOT

FIXTURES = ROOT / 'tests/fixtures/mephi'


def fixture(name):
    path = FIXTURES / name
    data = path.read_bytes()
    meta = json.loads(path.with_suffix('.json').read_text())
    if digest(data) != meta['excerpt_sha256']:
        raise AssertionError('official excerpt changed without provenance update')
    return data, dict(source_id='official-excerpt', url=meta['source_url'], sha256=meta['parent_sha256'], path=str(path.relative_to(ROOT)))


class ParserTests(unittest.TestCase):
    def test_control_a_above_300_is_preserved(self):
        rows = parse_history(*fixture('history-2025.official-excerpt.html'))['records']
        row = next(r for r in rows if r['official_code']=='01.03.02')
        self.assertEqual(row['cutoff'],305)
        self.assertEqual(row['mean_ege_score'],97.41)
        self.assertEqual(row['threshold_status'],'numeric')

    def test_control_b_bvi_is_not_zero_or_300(self):
        rows = parse_history(*fixture('history-2025.official-excerpt.html'))['records']
        row = next(r for r in rows if r['official_code']=='09.03.04')
        self.assertEqual(row['threshold_status'],'bvi_only')
        self.assertIsNone(row['cutoff'])
        self.assertEqual(row['mean_ege_score'],98.42)

    def test_control_c_rowspan_places_are_one_allocation(self):
        result = parse_seats(*fixture('seats-it-2026.official-excerpt.html'))
        self.assertEqual(len(result['records']),1)
        row = result['records'][0]
        self.assertEqual(row['places'],120)
        self.assertEqual(row['codes'],['09.03.01','09.03.02','09.03.03','09.03.04'])
        self.assertEqual(result['sum_budget'],120)
        self.assertIn('not_confirmed',row['competition_group_status'])

    def test_control_d_same_code_stays_separate(self):
        rows = parse_history(*fixture('history-2025.official-excerpt.html'))['records']
        repeated = [r for r in rows if r['official_code']=='03.03.01']
        self.assertEqual([r['cutoff'] for r in repeated],[282,281])
        self.assertEqual(len({r['id'] for r in repeated}),2)
        self.assertTrue(all(r['competition_group_id'] is None for r in repeated))

    def test_division_and_mean_sum_are_retained(self):
        rows = parse_history(*fixture('history-2023.official-excerpt.html'))['records']
        self.assertEqual({r['division'] for r in rows},{'ИНТЭЛ','ЛАПЛАЗ'})
        self.assertTrue(all(r['mean_ege_score'] is None for r in rows))
        self.assertTrue(all(r['mean_entrance_total']==291.04 for r in rows))

    def test_header_order_combined_code_and_missing_code(self):
        for year in [2015,2016,2022]:
            with self.subTest(year=year):
                rows = parse_history(*fixture(f'history-{year}.official-excerpt.html'))['records']
                self.assertTrue(all(r['year']==year for r in rows))
                self.assertTrue(all(r['official_code'] is None for r in rows) if year==2015 else all(r['official_code'] for r in rows))

    def test_years_do_not_leak_between_blocks(self):
        chunks = [fixture(f'history-{year}.official-excerpt.html')[0] for year in [2025,2023,2022,2016,2015]]
        snapshot = fixture('history-2025.official-excerpt.html')[1]
        rows = parse_history(b'<html><body>'+b''.join(chunks)+b'</body></html>',snapshot)['records']
        self.assertEqual(set(r['year'] for r in rows),{2015,2016,2022,2023,2025})
        self.assertTrue(all(r['cutoff']==305 for r in rows if r['year']==2025 and r['official_code']=='01.03.02'))

    def test_harmless_html_changes_are_supported(self):
        data,snapshot = fixture('history-2025.official-excerpt.html')
        doc = html.fromstring(data.decode('utf-8'))
        for node in doc.iter():
            node.attrib.clear()
        modified = html.tostring(doc,encoding='utf-8')
        expected=parse_history(data,snapshot)['records'];actual=parse_history(modified,snapshot)['records']
        self.assertEqual([(r['year'],r['official_code'],r['cutoff']) for r in actual],[(r['year'],r['official_code'],r['cutoff']) for r in expected])

    def test_conflicting_or_missing_year_and_broken_schema_fail_closed(self):
        data,snapshot=fixture('history-2025.official-excerpt.html')
        for modified in [data.replace(b'id="2025"',b'id="2024"'),data.replace('Проходной балл'.encode(),'Unknown column'.encode())]:
            with self.assertRaises(ParseError):
                parse_history(modified,snapshot)

    def test_six_threshold_states_and_zero(self):
        self.assertEqual(threshold('0'),('numeric',0))
        self.assertEqual(threshold('Нет','Только БВИ'),('bvi_only',None))
        self.assertEqual(threshold('—'),('not_published',None))
        self.assertEqual(threshold('Конкурс не проводился'),('not_offered',None))
        self.assertEqual(threshold('305','Только БВИ'),('manual_review',None))
        self.assertEqual(threshold('250 / 260'),('manual_review',None))
        # Structural extraction failures are returned as parse_error, not invented numeric rows.
        data,snapshot=fixture('history-2025.official-excerpt.html')
        with self.assertRaises(ParseError):parse_history(data.replace(b'<table',b'<article').replace(b'</table>',b'</article>'),snapshot)

    def test_scripts_are_data_and_are_never_executed(self):
        data,snapshot=fixture('history-2025.official-excerpt.html')
        self.assertEqual(len(parse_history(b'<html><script>throw new Error("untrusted")</script>'+data+b'</html>',snapshot)['records']),4)


class ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset=json.loads((ROOT/'data/normalized/mephi/dataset.json').read_text())
        cls.store=SnapshotStore()

    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.execute('PRAGMA foreign_keys=ON')
        for p in sorted((ROOT/'migrations').glob('*.sql')):self.db.executescript(p.read_text())

    def tearDown(self):self.db.close()

    def test_repeated_import_has_no_new_rows(self):
        self.assertGreater(import_dataset(self.db,self.dataset,self.store),0)
        counts={t:self.db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['programs','program_versions','seat_allocations','admission_observations']}
        self.assertEqual(import_dataset(self.db,self.dataset,self.store),0)
        self.assertEqual(counts,{t:self.db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in counts})
        self.assertEqual(counts['admission_observations'],286)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_exported_sql_is_idempotent_and_preserves_control_cases(self):
        sql='\n'.join(import_plan(self.dataset,self.store))
        self.db.executescript(sql);self.db.executescript(sql)
        self.assertEqual(self.db.execute("SELECT cutoff FROM admission_observations o JOIN admission_campaigns c ON c.id=o.campaign_id WHERE c.year=2025 AND official_code_raw='01.03.02'").fetchone()[0],305)
        self.assertEqual(self.db.execute("SELECT cutoff,threshold_status FROM admission_observations o JOIN admission_campaigns c ON c.id=o.campaign_id WHERE c.year=2025 AND official_code_raw='09.03.04'").fetchone(),(None,'bvi_only'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM seat_allocations WHERE places=120').fetchone()[0],1)

    def test_missing_source_and_tampered_normalized_facts_rejected(self):
        for change in ['url','cutoff','year','snapshot_sha256']:
            d=copy.deepcopy(self.dataset)
            if change=='url':d['history']['records'][0]['provenance']['url']=''
            elif change=='snapshot_sha256':d['history']['records'][0]['provenance'][change]='0'*64
            elif change=='cutoff':d['history']['records'][0]['cutoff']=306
            else:d['history']['records'][0]['year']=2024
            with self.subTest(change=change),self.assertRaises(ValueError):validate_dataset(d,self.store)

    def test_duplicate_observation_is_rejected(self):
        d=copy.deepcopy(self.dataset);d['history']['records'].append(d['history']['records'][0])
        with self.assertRaises(ValueError):validate_dataset(d,self.store)

    def test_unknown_groups_are_explicit_and_unconfirmed_match_is_blocked(self):
        import_dataset(self.db,self.dataset,self.store)
        self.assertEqual(self.db.execute('SELECT count(*) FROM admission_observations WHERE group_id IS NULL AND group_mapping_status="unresolved"').fetchone()[0],286)
        row=self.db.execute('SELECT * FROM admission_observations LIMIT 1').fetchone()
        columns=[c[1] for c in self.db.execute('PRAGMA table_info(admission_observations)')]
        values=dict(zip(columns,row));values['id']='synthetic-invalid-group';values['row_key']='synthetic';values['group_mapping_status']='confirmed';values['group_id']=self.db.execute('SELECT id FROM competition_groups LIMIT 1').fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('INSERT INTO admission_observations('+','.join(values)+') VALUES ('+','.join('?' for _ in values)+')',tuple(values.values()))

    def test_import_failure_rolls_back_entire_batch(self):
        self.db.executescript("CREATE TRIGGER synthetic_import_failure BEFORE INSERT ON admission_observations BEGIN SELECT RAISE(ABORT,'synthetic failure'); END;")
        with self.assertRaises(sqlite3.IntegrityError):import_dataset(self.db,self.dataset,self.store)
        self.assertEqual(self.db.execute('SELECT count(*) FROM programs').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM source_snapshots').fetchone()[0],0)

    def test_adapter_revision_preserves_prior_observations(self):
        import_dataset(self.db,self.dataset,self.store)
        row=self.db.execute('SELECT * FROM admission_observations WHERE cutoff=305').fetchone()
        columns=[c[1] for c in self.db.execute('PRAGMA table_info(admission_observations)')]
        values=dict(zip(columns,row));values['id']='synthetic-new-adapter-test';values['adapter_version']='synthetic-test-v2'
        self.db.execute('INSERT INTO admission_observations('+','.join(values)+') VALUES ('+','.join('?' for _ in values)+')',tuple(values.values()))
        self.assertEqual(self.db.execute('SELECT count(*) FROM admission_observations WHERE row_key=?',(values['row_key'],)).fetchone()[0],2)
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute('UPDATE admission_observations SET cutoff=306')

    def test_program_group_membership_must_match_field_and_campaign(self):
        import_dataset(self.db,self.dataset,self.store)
        group=self.db.execute('SELECT id FROM competition_groups LIMIT 1').fetchone()[0]
        p=self.db.execute('SELECT id,field_id FROM program_versions LIMIT 1').fetchone()
        other=self.db.execute('SELECT id FROM study_fields WHERE id<>? LIMIT 1',(p[1],)).fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('INSERT INTO competition_group_members VALUES (?,?,?,?,?)',('synthetic-cross-field',group,other,p[0],'confirmed'))

    def test_conflicting_existing_payload_is_not_silently_ignored(self):
        import_dataset(self.db,self.dataset,self.store)
        # Simulate an independently corrupted database; no source fixture is altered.
        self.db.executescript("DROP TRIGGER observations_no_update; UPDATE admission_observations SET payload_json='{}' WHERE cutoff=305; CREATE TRIGGER observations_no_update BEFORE UPDATE ON admission_observations BEGIN SELECT RAISE(ABORT,'append_only'); END;")
        with self.assertRaises(sqlite3.IntegrityError):import_dataset(self.db,self.dataset,self.store)


if __name__=='__main__':unittest.main()
