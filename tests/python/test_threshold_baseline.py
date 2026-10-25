import copy,json,unittest
from pipeline.threshold_baseline import ROOT,OUT,CONFIG,build,evaluate,predict_series,select_series


def row(year,value=280,**kw):
    return dict(id='synthetic-'+str(year),institution_id='synthetic',program_url='https://example.invalid/program',
        name='Synthetic',official_code='01.03.02',category='budget_unspecified',unit='competition_points',
        metric='cutoff',status='numeric',year=year,value=value,provenance={'url':'https://example.invalid/history'},**kw)


class ThresholdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.config=json.loads(CONFIG.read_text())

    def test_frozen_artifact_replays_and_is_not_an_admission_model(self):
        d=build(write=False);self.assertEqual(d,json.loads((OUT/'evaluation.json').read_text()))
        self.assertFalse(d['probability_enabled']);self.assertGreater(len(d['evaluation']),0)
        self.assertTrue(all(y<r['year'] for r in d['evaluation'] for y in r['training_years']))

    def test_gap_duplicate_or_only_one_year_prevents_extrapolation(self):
        for rows in [[row(2025)],[row(2025),row(2023)],[row(2025),row(2025),row(2024)]]:
            self.assertIsNone(predict_series(rows,2026,self.config))

    def test_baselines_are_simple_and_only_use_prior_years(self):
        p=predict_series([row(2023,250),row(2024,270),row(2025,290),row(2026,500)],2026,self.config)
        self.assertEqual((p['last_year'],p['median_last_three']),(290,270))
        self.assertEqual(p['training_years'],[2025,2024,2023])

    def test_future_data_perturbation_does_not_change_past_predictions(self):
        rows=[row(y,250+y%5) for y in range(2019,2026)];a=evaluate(rows,self.config)
        changed=copy.deepcopy(rows);changed[-1]['value']=999;b=evaluate(changed,self.config)
        for year in (2023,2024):
            self.assertEqual([r for r in a['evaluation'] if r['year']==year],[r for r in b['evaluation'] if r['year']==year])

    def test_categories_names_codes_and_urls_cannot_merge(self):
        base=row(2025);rows=[base]
        for key in ['category','name','official_code','program_url']:rows.append({**base,key:'other'})
        s,_=select_series(rows);self.assertEqual(len(s),5)

    def test_means_censored_unknown_units_and_missing_identity_are_excluded(self):
        base=row(2025)
        rows=[{**base,**patch} for patch in [{'metric':'mean_ege_score'},{'status':'bvi_only','value':None},
            {'status':'lower_bound'},{'unit':'unspecified_points'},{'program_url':None},{'official_code':None}]]
        s,_=select_series(rows);self.assertEqual(len(s),0)


if __name__=='__main__':unittest.main()
