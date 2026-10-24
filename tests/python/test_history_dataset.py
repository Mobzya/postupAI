import copy,json,sqlite3,unittest
from pipeline.history_dataset import (OUT,build,parse_hse,parse_nsu,parse_bmstu,parse_innopolis,observation)
from pipeline.import_history import import_dataset
from pipeline.validate import ROOT


def source(ident,year=2025):
    return dict(source_id=ident+'-history-'+str(year),institution_id=ident,url='https://example.invalid/history',sha256='a'*64,representation_sha256='b'*64)


class HistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.data=json.loads((OUT/'dataset.json').read_text())

    def test_complete_dataset_replays_and_all_ten_universities_are_reported(self):
        self.assertEqual(build(write=False),self.data)
        self.assertEqual(len(self.data['coverage']),10);self.assertEqual(self.data['parse_errors'],[])
        self.assertEqual(len({r['id'] for r in self.data['records']}),len(self.data['records']))

    def test_priority_footnote_is_not_bvi_only_or_zero(self):
        s='<title>Проходные баллы 2025</title><table><tr><th>Программа</th><th>Проходной балл</th></tr><tr><td>Программа</td><td>-*</td></tr></table><p data-footnote="true">*Все места заняты в приоритетном порядке: квоты и олимпиады.</p>'
        row=parse_hse(source('hse'),s)[0]
        self.assertEqual(row['status'],'priority_only');self.assertIsNone(row['value'])
        with self.assertRaises(ValueError):parse_hse(source('hse',2024),s)

    def test_lower_bounds_and_missing_values_have_different_statuses(self):
        a=observation(source('hse'),2016,'Synthetic','cutoff','competition_points','budget','282 и более','synthetic')
        b=observation(source('hse'),2016,'Synthetic','cutoff','competition_points','budget','—','synthetic')
        self.assertEqual((a['status'],a['value']),('lower_bound',282))
        self.assertEqual((b['status'],b['value']),('not_published',None))

    def test_serial_header_and_above_300_are_preserved(self):
        s='<title>Проходные 2017</title><table><tr><th>№</th><th>Конкурс</th><th>Проходной балл</th></tr><tr><td>1</td><td>Synthetic</td><td>372</td></tr></table>'
        row=parse_hse(source('hse',2017),s)[0]
        self.assertEqual(row['name'],'Synthetic');self.assertEqual(row['value'],372)
        self.assertIsNone(row['official_code'])

    def test_nsu_years_remain_separate_after_source_linebreak_normalization(self):
        actual=[r for r in self.data['records'] if r['institution_id']=='nsu']
        self.assertEqual([(r['year'],r['value']) for r in actual],[(2021,234),(2022,177),(2023,225),(2024,232),(2025,223)])
        self.assertTrue(all(r['unit']=='unspecified_points' for r in actual))

    def test_bmstu_decimal_minimum_and_mean_are_not_mean_ege(self):
        text='2025 О/К Средний\n35.03.02  Synthetic program  Бакалавр  163,5  —  179,3  —\n'
        rows=parse_bmstu(source('bmstu'),text)
        self.assertEqual(rows[0]['value'],163.5)
        self.assertEqual(rows[2]['metric'],'mean_entrance_total')
        self.assertEqual(rows[2]['unit'],'exam_total_points')
        self.assertIsNone(rows[1]['value'])

    def test_innopolis_feature_year_and_metric_unit_are_retained(self):
        s='<a class="subject-card"><h3>Synthetic</h3><div class="subject-card__features-card"><h4 class="features-card-title">280</h4><div class="features-card-text">Проходной балл ЕГЭ на бюджет</div><span>на 2025</span></div></a>'
        row=parse_innopolis(source('innopolis'),s)[0]
        self.assertEqual((row['year'],row['value'],row['unit']),(2025,280,'exam_total_points'))

    def test_legacy_divisions_and_parent_ids_are_not_lost(self):
        rows=[r for r in self.data['records'] if r['institution_id']=='mephi' and r['year']==2023 and r['official_code']=='03.03.01' and r['metric']=='cutoff']
        self.assertEqual({r['division'] for r in rows},{'ИНТЭЛ','ЛАПЛАЗ'})
        self.assertTrue(all(r['parent_observation_id'] for r in rows))

    def test_append_only_full_import_is_idempotent(self):
        db=sqlite3.connect(':memory:');db.execute('PRAGMA foreign_keys=ON')
        for p in sorted((ROOT/'migrations').glob('*.sql')):db.executescript(p.read_text())
        self.assertGreater(import_dataset(db,self.data),0);self.assertEqual(import_dataset(db,self.data),0)
        self.assertEqual(db.execute('SELECT count(*) FROM historical_source_observations').fetchone()[0],len(self.data['records']))
        self.assertEqual(db.execute('SELECT count(*) FROM catalog_observations').fetchone()[0],458)
        self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        with self.assertRaises(sqlite3.IntegrityError):db.execute('UPDATE historical_source_observations SET value=0')
        db.rollback()
        changed=copy.deepcopy(self.data);changed['records'][0]['value']=999
        with self.assertRaises(ValueError):import_dataset(db,changed)
        db.close()


if __name__=='__main__':unittest.main()
