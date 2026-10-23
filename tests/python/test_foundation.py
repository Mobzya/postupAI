import copy
import hashlib
import sqlite3
import unittest

from pipeline.audit import render
from pipeline.validate import ROOT, load, validate_all, validate_catalog, validate_distribution, validate_measurement, validate_registry


class DataTests(unittest.TestCase):
    def setUp(self):
        self.registry = load(ROOT / 'data/source_registry.json')
        self.catalog = load(ROOT / 'data/normalized/catalog.json')

    def test_repository_data(self):
        validate_all()
        self.assertEqual(len(self.registry['sources']), 10)
        self.assertEqual(self.catalog['records'], [])

    def test_invalid_sources(self):
        for field, value in [('url', 'http://example.invalid'), ('years', [True]),
                             ('completeness', -0.1), ('reliability', 'guessed')]:
            data = copy.deepcopy(self.registry)
            data['sources'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_registry(data)

    def test_missing_and_duplicate_sources(self):
        for sources in [self.registry['sources'][:-1], self.registry['sources'] + [self.registry['sources'][0]]]:
            with self.assertRaises(ValueError):
                validate_registry({'schema_version': 1, 'sources': sources})

    def test_measurement_provenance_and_conflicts(self):
        cell = dict(value=250, status='conflict', unit='competition_points', source_id='synthetic', year=2026, methodology='SYNTHETIC conflicting evidence')
        validate_measurement(cell, 2026, {'synthetic'})
        for field, value in [('value', -1), ('value', False), ('year', 2025), ('unit', 'unknown'), ('methodology', '')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_measurement({**cell, field: value}, 2026, {'synthetic'})
        with self.assertRaises(ValueError):
            validate_measurement({**cell, 'value': None, 'status': 'missing'}, 2026, {'synthetic'})
        validate_measurement({**cell, 'value': None, 'status': 'missing', 'missing_reason': 'not_published'}, 2026, {'synthetic'})

    def test_missing_values_are_not_zero_and_reports_reproduce(self):
        first = render(self.registry, self.catalog)
        second = render(self.registry, self.catalog)
        self.assertEqual(hashlib.sha256(first.encode()).hexdigest(), hashlib.sha256(second.encode()).hexdigest())
        self.assertIn('не определено', first)
        self.assertIn('Программ, допущенных к вероятностному прогнозу: 0', first)
        self.assertEqual(first, (ROOT / 'DATA_AUDIT.md').read_text())

    def test_catalog_rejects_underspecified_rows(self):
        with self.assertRaises(ValueError):
            validate_catalog({**self.catalog, 'records': [{'program_id': 'synthetic'}]}, self.registry)

    def test_bounded_distributions(self):
        validate_distribution([dict(score=99, probability=.4), dict(score=100, probability=.6)])
        for points in [[], [dict(score=101, probability=1)], [dict(score=10, probability=-1)],
                       [dict(score=10, probability=.9)], [dict(score=10, probability=True)]]:
            with self.subTest(points=points), self.assertRaises(ValueError):
                validate_distribution(points)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('PRAGMA foreign_keys = ON')
        for path in sorted((ROOT / 'migrations').glob('*.sql')):
            self.db.executescript(path.read_text())
        self.db.executescript((ROOT / 'tests/fixtures/admissions.synthetic.sql').read_text())

    def tearDown(self):
        self.db.close()

    def test_migrations_and_seed(self):
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.db.execute('SELECT count(*) FROM institutions').fetchone()[0], 10)
        self.assertEqual(self.db.execute('SELECT count(*) FROM source_records WHERE id <> ?', ('synthetic-source',)).fetchone()[0], 10)

    def test_all_required_entities_exist(self):
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {'institutions','programs','program_versions','admission_years','admission_tracks','admission_rules',
                    'historical_metrics','score_distributions','source_records','model_versions','user_profiles',
                    'user_score_history','user_achievements','saved_programs','forecast_results'}
        self.assertTrue(required <= tables)

    def test_track_categories_are_distinct(self):
        self.assertEqual(self.db.execute('SELECT count(DISTINCT category) FROM admission_tracks').fetchone()[0], 2)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO admission_tracks VALUES ('bad','synthetic-v1','all','bad')")

    def test_metrics_are_append_only_and_revision_chain_is_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE historical_metrics SET value=260 WHERE id='synthetic-cutoff'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM historical_metrics")
        self.db.execute("""INSERT INTO historical_metrics
          SELECT 'synthetic-cutoff-v2',track_id,metric,255,NULL,unit,methodology,status,source_snapshot_id,2,id
          FROM historical_metrics WHERE id='synthetic-cutoff'""")
        self.assertEqual(self.db.execute('SELECT value FROM latest_historical_metrics').fetchone()[0], 255)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("""INSERT INTO historical_metrics
              SELECT 'bad-cross-track','synthetic-paid',metric,255,NULL,unit,methodology,status,source_snapshot_id,3,id
              FROM historical_metrics WHERE id='synthetic-cutoff-v2'""")

    def test_missing_metric_cannot_silently_be_zero(self):
        sql = "INSERT INTO historical_metrics(id,track_id,metric,value,unit,methodology,status,source_snapshot_id,revision) VALUES (?,?,?,?,?,?,?,?,?)"
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(sql, ('bad','synthetic-budget','seats',None,'places','synthetic','missing','synthetic-snapshot',1))
        self.db.execute(sql, ('synthetic-zero','synthetic-budget','seats',0,'places','SYNTHETIC explicitly zero','unverified','synthetic-snapshot',1))

    def test_reimport_identity_is_unique(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO import_batches(id,dataset_sha256,adapter_version,is_synthetic) SELECT 'duplicate',dataset_sha256,adapter_version,is_synthetic FROM import_batches")

    def test_user_score_bounds_in_sql(self):
        key = 'f' * 64
        self.db.execute('INSERT INTO user_profiles(id,consent_version) VALUES (?,?)', (key, 'synthetic'))
        for score in (-1, 101):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute('INSERT INTO user_score_history VALUES (?,?,?,?,?,?,?,?,?,?)',
                                ('synthetic-score', key, 'math', score, '2026-10-23', 'synthetic', 6, 1, 90, '2027-06-01'))


if __name__ == '__main__':
    unittest.main()
