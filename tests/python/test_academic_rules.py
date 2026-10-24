import copy,json,sqlite3,unittest
from pipeline.academic_rules import OUT,build
from pipeline.import_rules import import_dataset
from pipeline.validate import ROOT


class AcademicRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.data=json.loads((OUT/'dataset.json').read_text())

    def test_replay_preserves_annual_scope_and_alternatives(self):
        self.assertEqual(self.data,build(write=False))
        self.assertEqual(len(self.data['rules']),59)
        self.assertEqual({r['year'] for r in self.data['rules']},{2026})
        r=next(r for r in self.data['rules'] if r['official_code']=='09.03.04' and r['category']=='general_budget')
        self.assertEqual([s[0]['minimum'] for s in r['slots']],[75,75,70])
        self.assertEqual({s['key'] for s in r['slots'][1]},{'physics','informatics'})
        self.assertTrue(all(r['evidence']['annual_pdf']['sha256'] for r in self.data['rules']))

    def test_missing_paid_minimums_and_foreign_scope_are_not_invented(self):
        self.assertFalse(any(r['official_code']=='31.05.01' for r in self.data['rules']))
        self.assertFalse(any(r['official_code']=='38.03.01' and r['category']=='paid' for r in self.data['rules']))
        self.assertEqual(self.data['bvi_and_quotas'],'manual_review_required')

    def test_achievement_age_conditions_and_unused_diplomas_survive_extraction(self):
        rules=self.data['supported_achievements']
        self.assertEqual(rules['gto_gold']['points'],4)
        self.assertIn('age_group_eligible_for_campaign',rules['gto_gold']['requires'])
        self.assertIn('not_used_for_special_rights',rules['rsosh_prize_unused']['requires'])
        self.assertEqual(rules['rsosh_prize_unused']['points'],8)

    def test_full_import_is_idempotent_and_immutable(self):
        db=sqlite3.connect(':memory:');db.execute('PRAGMA foreign_keys=ON')
        for p in sorted((ROOT/'migrations').glob('*.sql')):db.executescript(p.read_text())
        self.assertGreater(import_dataset(db,self.data),0);self.assertEqual(import_dataset(db,self.data),0)
        self.assertEqual(db.execute('SELECT count(*) FROM academic_rule_versions').fetchone()[0],59)
        self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        with self.assertRaises(sqlite3.IntegrityError):db.execute('UPDATE academic_rule_versions SET year=2027')
        db.rollback();changed=copy.deepcopy(self.data);changed['rules'][0]['achievementCap']=50
        with self.assertRaises(ValueError):import_dataset(db,changed)
        db.close()


if __name__=='__main__':unittest.main()
