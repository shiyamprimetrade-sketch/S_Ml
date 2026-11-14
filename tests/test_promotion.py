from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import numpy as np
from fixtures import sample
from s_ml.core import LinearGD
from s_ml.storage import Store
from s_ml.promotion import (GatePolicy, register_checkpoint, evaluate_and_promote,
                            active_model, rollback, train_and_gate)


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'db.sqlite3'
        self.store = Store(self.path)
        self.train_x = np.linspace(-1, 1, 80).reshape(-1, 1)
        self.train_ids = [f'train-{i}' for i in range(80)]

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def register(self, version, slope, mission='lab', mode='iid', account_id=None, cutoff=None,
                 offset=3, train_x=None, names=None):
        x = self.train_x if train_x is None else train_x
        y = slope * x[:, 0] + offset
        model = LinearGD(epochs=1000).fit(x, y)
        path = self.root / (version + '.json')
        model.save(path)
        register_checkpoint(self.store, mission, version, path, self.train_ids, y,
                            names or ['x'], cutoff, mode, account_id)
        return path

    def evaluation(self, generation=1, n=40, target_slope=2):
        rng = np.random.default_rng(generation)
        x = rng.uniform(-1, 1, size=(n, 1))
        y = 3 + target_slope * x[:, 0]
        ids = [f'heldout-{generation}-{i}' for i in range(n)]
        return x, y, ids

    def evaluate(self, version, generation=1, **kwargs):
        if 'label_available_at' in kwargs and 'prediction_at' not in kwargs:
            kwargs['prediction_at'] = ['2020-01-01T12:00:00+00:00'] * len(kwargs['label_available_at'])
        return evaluate_and_promote(self.store, 'lab', version, *self.evaluation(generation), **kwargs)

    def test_first_candidate_must_beat_mean_baseline(self):
        self.register('constant', 0)
        result = self.evaluate('constant')
        self.assertFalse(result['accepted'])
        self.assertIn('baseline', result['reason'])
        self.assertIsNone(active_model(self.store, 'lab'))
        self.register('working', 1.4)
        self.assertTrue(self.evaluate('working', 2)['accepted'])
        self.assertEqual(active_model(self.store, 'lab')[0], 'working')

    def test_better_candidate_replaces_incumbent_and_worse_does_not(self):
        self.register('v1', 1.4)
        self.assertTrue(self.evaluate('v1')['accepted'])
        self.register('v2', 1.9)
        result = self.evaluate('v2', 2)
        self.assertTrue(result['accepted'])
        self.assertIn('incumbent', result['reference_scores'])
        self.register('worse', 1.2)
        result = self.evaluate('worse', 3)
        self.assertFalse(result['accepted'])
        self.assertIn('incumbent', result['reason'])
        self.assertEqual(active_model(self.store, 'lab')[0], 'v2')

    def test_rejection_records_evidence_and_consumes_scored_holdout(self):
        self.register('bad', 0)
        self.assertFalse(self.evaluate('bad')['accepted'])
        self.register('good', 2)
        result = self.evaluate('good')
        self.assertEqual(result['reason'], 'holdout_already_scored')
        self.assertTrue(self.evaluate('good', 2)['accepted'])
        rows = self.store.connection.execute('SELECT * FROM model_decisions').fetchall()
        self.assertEqual(len(rows), 3)
        self.assertIn('candidate_scores', json.loads(rows[0]['report']))

    def test_small_holdout_never_activates(self):
        self.register('v1', 2)
        x,y,ids = self.evaluation(n=10)
        result = evaluate_and_promote(self.store, 'lab', 'v1', x,y,ids)
        self.assertEqual(result['reason'], 'insufficient_heldout_examples')
        self.assertIsNone(active_model(self.store, 'lab'))

    def test_training_overlap_rejected(self):
        self.register('v1', 2)
        x,y,ids = self.evaluation()
        ids[0] = 'train-0'
        result = evaluate_and_promote(self.store, 'lab', 'v1', x,y,ids)
        self.assertEqual(result['reason'], 'candidate_training_overlap')
        self.assertNotIn('candidate_scores', result)

    def test_timestamp_leakage_chronology_and_future_labels(self):
        self.register('v1', 2, mode='temporal', cutoff='2020-01-02T00:00:00+00:00')
        x,y,ids = self.evaluation()
        self.assertEqual(evaluate_and_promote(self.store, 'lab', 'v1', x,y,ids)['reason'], 'label_availability_required')
        times = ['2020-01-01T00:00:00+00:00'] * 40
        self.assertEqual(evaluate_and_promote(self.store, 'lab', 'v1', x,y,ids,times)['reason'], 'training_label_time_overlap')
        times = ['2020-01-05T00:00:00+00:00'] * 40
        origins = ['2020-01-04T00:00:00+00:00'] * 20 + ['2020-01-03T00:00:00+00:00'] * 20
        self.assertEqual(evaluate_and_promote(self.store, 'lab', 'v1', x,y,ids,times,prediction_at=origins)['reason'], 'heldout_not_chronological')
        times = ['2999-01-01T00:00:00+00:00'] * 40
        self.assertEqual(evaluate_and_promote(self.store, 'lab', 'v1', x,y,ids,times)['reason'], 'labels_not_yet_available')
        times = ['2020-01-03T00:00:00+00:00'] * 40
        self.assertEqual(evaluate_and_promote(self.store,'lab','v1',x,y,ids,times)['reason'],'prediction_origins_required')
        self.assertEqual(evaluate_and_promote(self.store,'lab','v1',x,y,ids,times,prediction_at=['2020-01-01T00:00:00+00:00']*40)['reason'],'forecast_origin_before_training_cutoff')
        self.assertEqual(evaluate_and_promote(self.store,'lab','v1',x,y,ids,times,prediction_at=['2020-01-04T00:00:00+00:00']*40)['reason'],'label_before_forecast_origin')
        origins = ['2020-01-02T12:00:00+00:00'] * 40
        self.assertTrue(evaluate_and_promote(self.store, 'lab', 'v1', x,y,ids,times,prediction_at=origins)['accepted'])

    def test_rmse_guard_even_when_mae_improves(self):
        train_x = np.linspace(0,2,80).reshape(-1,1)
        self.register('incumbent', 1, offset=1, train_x=train_x)
        x,y,ids = self.evaluation()
        self.assertTrue(evaluate_and_promote(self.store,'lab','incumbent',x,1+x[:,0],ids)['accepted'])
        self.register('candidate', 2, offset=0, train_x=train_x)
        x = np.zeros((40,1)); y = np.zeros(40);y[-1] = 30
        ids = [f'tail-{i}' for i in range(40)]
        result = evaluate_and_promote(self.store,'lab','candidate',x,y,ids)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['reason'], 'rmse_regression_against_incumbent')
        self.assertLess(result['candidate_scores']['mae'],result['reference_scores']['incumbent']['mae'])

    def test_explicit_rollback_only_to_approved_model(self):
        self.register('v1',1.4);self.evaluate('v1')
        self.register('v2',1.9);self.evaluate('v2',2)
        self.register('untested',2)
        with self.assertRaises(ValueError):
            rollback(self.store,'lab','untested')
        result=rollback(self.store,'lab','v1')
        self.assertEqual(result['previous_version'],'v2')
        self.assertEqual(active_model(self.store,'lab')[0],'v1')

    def test_active_checkpoint_immutable_and_survives_restart(self):
        path=self.register('v1',1.4)
        self.evaluate('v1')
        x,_,_=self.evaluation(2)
        before=active_model(self.store,'lab')[1].predict(x)
        self.register('v1',1.4)  # Identical registration remains idempotent.
        path.write_text('{}')
        self.store.close();self.store=Store(self.path)
        np.testing.assert_array_equal(before,active_model(self.store,'lab')[1].predict(x))

    def test_changed_checkpoint_version_rejected(self):
        path=self.register('v1',1.4)
        LinearGD().fit(self.train_x, self.train_x[:,0]*2+3).save(path)
        with self.assertRaises(ValueError):
            register_checkpoint(self.store,'lab','v1',path,self.train_ids,self.train_x[:,0]*2+3,['x'],validation_mode='iid')

    def test_atomic_decision_and_pointer(self):
        self.register('v1',2)
        self.store.connection.execute("CREATE TRIGGER deny_pointer BEFORE INSERT ON model_active BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.evaluate('v1')
        self.assertEqual(self.store.connection.execute('SELECT COUNT(*) FROM model_decisions').fetchone()[0],0)
        self.assertEqual(self.store.connection.execute('SELECT COUNT(*) FROM model_holdouts').fetchone()[0],0)

    def test_account_forecast_cannot_use_iid_validation(self):
        self.store.ingest(sample())
        with self.assertRaises(ValueError):
            self.register('v1',2,account_id=1)

    def test_account_deletion_clears_linked_models_and_evidence(self):
        self.store.ingest(sample())
        self.register('v1',2,account_id=1,mode='temporal',cutoff='2020-01-01T00:00:00+00:00')
        self.evaluate('v1',label_available_at=['2020-01-02T00:00:00+00:00']*40)
        self.assertTrue(self.store.export()['model_versions'])
        self.store.delete_account(1)
        self.assertIsNone(active_model(self.store,'lab'))
        self.assertEqual(self.store.export()['model_versions'],[])
        self.assertEqual(self.store.export()['model_decisions'],[])

    def test_invalid_policy_and_inputs(self):
        for kwargs in [{'min_examples':1},{'min_relative_improvement':0},{'max_rmse_ratio':1.1}]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                GatePolicy(**kwargs)
        self.register('v1',2)
        x,y,ids=self.evaluation();y[0]=float('nan')
        with self.assertRaises(ValueError):
            evaluate_and_promote(self.store,'lab','v1',x,y,ids)
        self.assertIsNone(active_model(self.store,'lab'))

    def test_train_save_evaluate_activate_pipeline(self):
        x,y,ids=self.evaluation()
        manifest={'schema':'s_ml.training-gate.v1','mission':'prepared-lab','version':'v1',
                  'validation_mode':'iid',
                  'training':{'x':self.train_x.tolist(),'y':(3+2*self.train_x[:,0]).tolist(),
                              'ids':self.train_ids,'feature_schema':['x']},
                  'evaluation':{'x':x.tolist(),'y':y.tolist(),'ids':ids}}
        result=train_and_gate(self.store,manifest,self.root/'artifacts')
        self.assertTrue(result['promotion']['accepted'])
        self.assertLess(result['final_training_loss'],result['initial_training_loss'])
        self.assertEqual(active_model(self.store,'prepared-lab')[0],'v1')
        self.assertTrue(Path(result['checkpoint']).is_file())
        with self.assertRaises(ValueError):
            train_and_gate(self.store,manifest,self.root/'artifacts')

    def test_feature_layout_must_match_incumbent(self):
        self.register('v1',1.4)
        self.evaluate('v1')
        self.register('different-feature',1.9,names=['another_feature'])
        result=self.evaluate('different-feature',2)
        self.assertEqual(result['reason'],'feature_schema_mismatch')
        self.assertEqual(active_model(self.store,'lab')[0],'v1')
