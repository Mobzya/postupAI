import copy,itertools,json,unittest
from pathlib import Path
from models.competition import Program,Entrant,deferred_acceptance,simulate
from models.calibration import calibration_metrics
from pipeline.model_readiness import build as readiness,OUT as READINESS_OUT


class CompetitionModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.config=json.loads(Path('config/competition.synthetic.v1.json').read_text())

    def test_rejected_candidate_reapplies_and_no_entrant_holds_two_seats(self):
        ps=[Program('A',1),Program('B',1)]
        es=[Entrant({'A':280,'B':270},('A','B'),0),Entrant({'A':290,'B':250},('A','B'),1)]
        self.assertEqual(deferred_acceptance(ps,es),['B','A'])

    def test_program_specific_scores_change_matching(self):
        es=[Entrant({'A':200,'B':300},('A','B'),0),Entrant({'A':300,'B':200},('B','A'),1),Entrant({'A':280,'B':280},('A','B'),2)]
        self.assertEqual(deferred_acceptance([Program('A',1),Program('B',1)],es),['B','A',None])

    def test_zero_capacity_minimum_and_supplied_tie_priority(self):
        ps=[Program('A',0),Program('B',1,250)]
        es=[Entrant({'A':300,'B':249},('A','B'),1),Entrant({'A':300,'B':280},('A','B'),2),Entrant({'A':300,'B':280},('A','B'),3)]
        self.assertEqual(deferred_acceptance(ps,es),[None,None,'B'])

    def test_small_matching_has_no_blocking_pair(self):
        ps=[Program('A',1),Program('B',1)]
        for preferences in itertools.product([('A','B'),('B','A')],repeat=3):
            es=[Entrant({'A':score,'B':score},pref,i) for i,(score,pref) in enumerate(zip([240,260,280],preferences))]
            assignments=deferred_acceptance(ps,es)
            for i,e in enumerate(es):
                for key in e.preferences:
                    if assignments[i]==key:break
                    held=[j for j,a in enumerate(assignments) if a==key]
                    self.assertTrue(held)
                    self.assertGreaterEqual(es[held[0]].scores[key],e.scores[key])

    def test_monte_carlo_replays_seed_and_outputs_normalized_synthetic_results(self):
        a=simulate(self.config,trials=30,seed=3);self.assertEqual(a,simulate(self.config,trials=30,seed=3))
        self.assertFalse(a['deployable']);self.assertTrue(a['synthetic'])
        self.assertAlmostEqual(sum(a['by_program'].values())+a['rejected_mass'],1)
        self.assertLessEqual(a['monte_carlo_interval95'][0],a['any_admission_scenario_mass'])
        self.assertGreaterEqual(a['monte_carlo_interval95'][1],a['any_admission_scenario_mass'])

    def test_candidate_score_uncertainty_is_integrated_against_minimum(self):
        c=copy.deepcopy(self.config);c['programs']=c['programs'][:1];c['programs'][0]['seats']=1;c['programs'][0]['minimum']=250
        c['rival_count_distribution']=[[0,1]];c['candidate_preferences']=['synthetic_A'];c['preference_profiles']=[{'programs':['synthetic_A'],'weight':1}]
        c['candidate_scenarios']=[{'scores':{'synthetic_A':200},'weight':0.5},{'scores':{'synthetic_A':300},'weight':0.5}]
        r=simulate(c,trials=1000,seed=17);self.assertAlmostEqual(r['any_admission_scenario_mass'],0.5,delta=0.06)

    def test_real_unvalidated_inputs_quotas_and_malformed_distributions_fail_closed(self):
        for patch in [{'synthetic':False},{'category':'special_quota'},{'rival_count_distribution':[[20,0.4]]},
            {'candidate_preferences':['unknown']},{'candidate_preferences':['synthetic_A','synthetic_A']}]:
            with self.assertRaises(ValueError):simulate({**self.config,**patch},trials=1)

    def test_readiness_replays_sources_and_does_not_treat_threshold_errors_as_calibration(self):
        d=readiness(write=False);self.assertEqual(d,json.loads(READINESS_OUT.read_text()))
        self.assertGreater(d['threshold_holdout_predictions'],0)
        self.assertFalse(d['probability_enabled']);self.assertFalse(d['real_calibration_available'])
        self.assertIsNone(d['validated_probability_artifact'])

    def test_calibration_metrics_have_known_values_and_reject_invalid_samples(self):
        r=calibration_metrics([0.2,0.8],[0,1]);self.assertAlmostEqual(r['brier'],0.04)
        self.assertAlmostEqual(r['log_loss'],-__import__('math').log(0.8));self.assertAlmostEqual(r['expected_calibration_error'],0.2)
        self.assertEqual(calibration_metrics([0,1],[0,1])['brier'],0)
        for p,y in [([],[]),([1.1],[1]),([0.5],[2]),([float('nan')],[0])]:
            with self.assertRaises(ValueError):calibration_metrics(p,y)


if __name__=='__main__':unittest.main()
