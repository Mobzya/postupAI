import copy,json,sqlite3,unittest
from pathlib import Path
from pipeline.catalog_adapters import parse_html,parse_msu,parse_spbu
from pipeline.catalog_pipeline import build,validate,OUT
from pipeline.import_catalog import import_dataset
from pipeline.validate import ROOT


def source(ident,name='programs'):
    return dict(institution_id=ident,source_id=ident+'-catalog-'+name,url='https://example.invalid/catalog',
                sha256='a'*64,representation_sha256='b'*64)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.data=json.loads((OUT/'dataset.json').read_text())

    def test_all_ten_coverage_rows_and_unknown_denominator(self):
        validate(self.data)
        self.assertEqual(len(self.data['coverage']),10)
        self.assertTrue(all(r['target_program_denominator'] is None for r in self.data['coverage']))
        self.assertFalse(self.data['complete_for_ten_universities'])

    def test_catalog_replays_from_versioned_structural_excerpts(self):
        self.assertEqual(build(write=False),self.data)

    def test_hse_campus_and_no_implicit_degree(self):
        s='<div class="nn events"><p class="text"><a href="https://nnov.hse.ru/ba/math/">Synthetic math</a></p></div>'
        rows=parse_html(source('hse'),s)
        self.assertEqual(rows[0]['campus'],'Нижний Новгород');self.assertIsNone(rows[0]['degree'])
        self.assertIsNone(rows[0]['campaign_year'])
        with self.assertRaises(ValueError):parse_html(source('hse'),s.replace('nn events','events'))

    def test_hse_totals_not_programs_and_dash_not_zero(self):
        header='<tr><td colspan="8">Направление 01.03.01</td></tr>'
        row='<tr><td>Synthetic</td><td></td><td>-</td><td>0</td><td>-</td><td>1</td><td>0</td><td>-</td></tr>'
        total=row.replace('Synthetic','Всего:')
        rows=parse_html(source('hse','seats'),'<h1>2026</h1><table><tbody>'+header+row+total+'</tbody></table>')
        self.assertEqual(len(rows),1);self.assertIsNone(rows[0]['places']['budget_total'])
        self.assertEqual(rows[0]['places']['paid'],0)

    def test_nsu_numbered_text_fields_keep_all_program_lines(self):
        rows=parse_html(source('nsu'),'<a href="https://example.invalid/faculty"><div field="text2">One<br>Two</div></a>')
        self.assertEqual([r['name'] for r in rows],['One','Two'])
        self.assertTrue(all(r['program_url'] is None for r in rows))

    def test_marketing_tracks_remain_separate_from_program_profiles(self):
        rows=parse_html(source('cu'),'<h3>Искусственный интеллект</h3><h3>Дизайн</h3>')
        self.assertTrue(all(r['kind']=='marketing_track' for r in rows))
        actual=[r for r in self.data['display_index'] if r['institution_id']=='cu']
        self.assertEqual(len(actual),4)

    def test_pdf_titles_and_missing_codes_not_inferred(self):
        rows=parse_msu(source('msu','seats'),'образовательная программа "Synthetic\nprogram"')
        self.assertEqual(rows[0]['name'],'Synthetic program');self.assertIsNone(rows[0]['official_code'])
        blocks=[dict(x0='270',x1='430',y0='10',y1='20',text='Synthetic',locator='program'),
                dict(x0='450',x1='480',y0='14',y1='16',text='очная',locator='form')]
        rows=parse_spbu(source('spbu'),blocks)
        self.assertIsNone(rows[0]['official_code'])
        with self.assertRaises(ValueError):parse_spbu(source('spbu'),blocks[:-1])

    def test_aggregate_hse_rows_absent_and_no_profiles_disappear_by_shared_pdf_url(self):
        for r in self.data['display_index']:
            self.assertFalse(r['name'].casefold().startswith(('итого','всего:')))
        self.assertEqual(len([r for r in self.data['display_index'] if r['institution_id']=='spbu']),119)
        self.assertGreater(len([r for r in self.data['display_index'] if r['institution_id']=='nsu']),25)

    def test_import_atomic_idempotent_and_preserves_legacy(self):
        db=sqlite3.connect(':memory:');db.execute('PRAGMA foreign_keys=ON')
        for p in sorted((ROOT/'migrations').glob('*.sql')):db.executescript(p.read_text())
        self.assertGreater(import_dataset(db,self.data),0);self.assertEqual(import_dataset(db,self.data),0)
        self.assertEqual(db.execute('SELECT count(*) FROM admission_observations').fetchone()[0],286)
        self.assertEqual(db.execute('SELECT count(*) FROM catalog_observations').fetchone()[0],len(self.data['records']))
        self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        with self.assertRaises(sqlite3.IntegrityError):db.execute('UPDATE catalog_observations SET name="changed"')
        db.rollback()
        modified=copy.deepcopy(self.data);modified['records'][0]['name']='changed'
        with self.assertRaises(ValueError):import_dataset(db,modified)
        db.close()


if __name__=='__main__':unittest.main()
