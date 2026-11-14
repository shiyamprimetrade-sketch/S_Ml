import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from s_ml.core import LinearGD, GaussianAnomaly, loss_gradient, ordered_split
from s_ml.training import benchmark


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.x = np.random.default_rng(27).normal(size=(100, 3))
        self.y = 5 + self.x @ np.array([2., -3., .4])

    def test_gradient_finite_difference(self):
        z = np.column_stack([np.ones(100), self.x])
        theta = np.array([1., 2., 3., 4.])
        for penalty in (0., 10.):
            _, analytic = loss_gradient(z, self.y, theta, penalty)
            for i in range(4):
                delta = np.eye(4)[i] * 1e-5
                numeric = (loss_gradient(z, self.y, theta + delta, penalty)[0] - loss_gradient(z, self.y, theta - delta, penalty)[0]) / 2e-5
                self.assertAlmostEqual(analytic[i], numeric, places=6)

    def test_training_checkpoint(self):
        model = LinearGD().fit(self.x, self.y)
        self.assertLess(model.history[-1], model.history[0] * 1e-10)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'checkpoint.json'
            model.save(path)
            np.testing.assert_array_equal(model.predict(self.x), LinearGD.load(path).predict(self.x))

    def test_minibatch(self):
        model = LinearGD(batch_size=13, epochs=200).fit(self.x, self.y)
        np.testing.assert_allclose(model.predict(self.x), self.y, atol=1e-7)

    def test_train_only_scaling(self):
        model = LinearGD().fit(self.x[:60], self.y[:60])
        mean = model.mean.copy()
        model.predict(self.x[60:] * 10000)
        np.testing.assert_array_equal(mean, self.x[:60].mean(axis=0))
        np.testing.assert_array_equal(model.mean, mean)

    def test_library_ridge_parity(self):
        ours = LinearGD(regularization=10).fit(self.x, self.y)
        reference = make_pipeline(StandardScaler(), Ridge(alpha=10)).fit(self.x, self.y)
        np.testing.assert_allclose(ours.predict(self.x), reference.predict(self.x), atol=1e-7)

    def test_regularization(self):
        weak = LinearGD().fit(self.x, self.y)
        strong = LinearGD(regularization=1000).fit(self.x, self.y)
        self.assertLess(np.linalg.norm(strong.theta[1:]), np.linalg.norm(weak.theta[1:]))
        self.assertAlmostEqual(strong.theta[0], self.y.mean(), places=7)

    def test_constant_feature(self):
        model = LinearGD().fit(np.ones((30, 1)), np.ones(30) * 7)
        np.testing.assert_allclose(model.predict([[1]]), [7], atol=1e-7)

    def test_ordered_split(self):
        a, b, c = ordered_split(100)
        self.assertLess(max(a), min(b))
        self.assertLess(max(b), min(c))
        self.assertEqual(len(set(a) | set(b) | set(c)), 100)

    def test_bad_inputs(self):
        for kwargs in ({'epochs': 0}, {'learning_rate': float('nan')}, {'regularization': -1}, {'batch_size': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                LinearGD(**kwargs)
        for x in ([], [[float('nan')]], [1, 2]):
            with self.subTest(x=x), self.assertRaises(ValueError):
                LinearGD().fit(x, [1])
        with self.assertRaises(ValueError):
            LinearGD().predict([[1]])

    def test_corrupt_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'model.json'
            LinearGD().fit(self.x, self.y).save(p)
            data = json.loads(p.read_text())
            data['scale'][0] = 0
            p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                LinearGD.load(p)

    def test_gaussian(self):
        model = GaussianAnomaly().fit(self.x)
        self.assertLess(model.score([[100, 100, 100]])[0], model.score([[0, 0, 0]])[0])
        self.assertTrue(np.isfinite(GaussianAnomaly().fit([[1], [1]]).score([[1]])).all())

    def test_benchmark(self):
        with tempfile.TemporaryDirectory() as d:
            first = benchmark(Path(d) / 'a')
            self.assertEqual(first, benchmark(Path(d) / 'b'))
            self.assertEqual(first['checkpoint_reload_max_abs_delta'], 0)
            self.assertLess(first['sklearn_ridge_max_prediction_delta'], .01)
            self.assertTrue(first['candidate_promoted_in_benchmark_only'])
            self.assertLess(first['test']['mae'], first['baseline_test']['mae'])
