"""Auditable benchmark; never treats synthetic or unrelated data as TikTok evidence."""
from __future__ import annotations
import hashlib
import json
import platform
from pathlib import Path
import numpy as np
import sklearn
from sklearn.datasets import load_diabetes
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error
from .core import LinearGD, ordered_split


def errors(y, p):
    return {"mae": float(mean_absolute_error(y, p)),
            "rmse": float(np.sqrt(mean_squared_error(y, p)))}


def benchmark(output):
    """Real public regression dataset; index order is NOT a temporal forecast."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    x, y = load_diabetes(return_X_y=True)
    train, validation, test = ordered_split(len(y))
    baseline = DummyRegressor(strategy="mean").fit(x[train], y[train])
    trials, fitted = [], {}
    for penalty in (0., 1., 10., 100.):
        name = f"linear_gd_lambda_{penalty:g}"
        model = LinearGD(epochs=3000, regularization=penalty).fit(x[train], y[train])
        score = errors(y[validation], model.predict(x[validation]))
        trials.append({"model": name, "validation": score})
        fitted[name] = model
    best = min(trials, key=lambda item: item["validation"]["mae"])
    baseline_validation = errors(y[validation], baseline.predict(x[validation]))
    promote = best["validation"]["mae"] < baseline_validation["mae"] * .95
    selected = fitted[best["model"]] if promote else baseline
    # Test data is evaluated only after validation selection.
    prediction = selected.predict(x[test])
    residual = np.abs(y[validation] - selected.predict(x[validation]))
    radius = float(np.quantile(residual, .9, method="higher"))
    checkpoint = output / "linear.json"
    candidate = fitted[best["model"]]
    candidate.save(checkpoint)
    restored = LinearGD.load(checkpoint)
    reference = make_pipeline(StandardScaler(), Ridge(alpha=candidate.regularization))
    reference.fit(x[train], y[train])
    curves = []
    for size in (40, 80, 160, len(train)):
        model = LinearGD(epochs=3000, regularization=candidate.regularization)
        model.fit(x[train[:size]], y[train[:size]])
        curves.append({"n": size, "train": errors(y[train[:size]], model.predict(x[train[:size]])),
                       "validation": errors(y[validation], model.predict(x[validation]))})
    report = {
        "schema": "s_ml.benchmark.v1", "dataset": "sklearn.load_diabetes (public real data)",
        "dataset_sha256": hashlib.sha256(x.tobytes() + y.tobytes()).hexdigest(),
        "scope": "General regression engineering benchmark; not TikTok, not a time-series claim",
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "sklearn": sklearn.__version__},
        "split": {"method": "fixed index order 60/20/20", "train": len(train),
                  "validation": len(validation), "test": len(test)},
        "trials": trials, "baseline_validation": baseline_validation,
        "selected": best["model"] if promote else "historical_mean",
        "promotion_rule": "validation MAE at least 5% lower than mean baseline",
        "candidate_promoted_in_benchmark_only": promote,
        "test": errors(y[test], prediction),
        "baseline_test": errors(y[test], baseline.predict(x[test])),
        "initial_train_loss": candidate.history[0], "final_train_loss": candidate.history[-1],
        "checkpoint_reload_max_abs_delta": float(np.max(np.abs(restored.predict(x[test]) - candidate.predict(x[test])))),
        "sklearn_ridge_max_prediction_delta": float(np.max(np.abs(reference.predict(x[test]) - candidate.predict(x[test])))),
        "interval": {"method": "validation absolute-residual 90th percentile heuristic",
                     "radius": radius, "test_coverage": float(np.mean(np.abs(y[test] - prediction) <= radius)),
                     "limitation": "No guaranteed coverage under drift or adaptive model selection"},
        "learning_curve": curves,
        "limitations": ["No production model promoted", "Single fixed holdout; no clinical use",
                        "TikTok needs repeated, horizon-aligned observations before forecasting"]}
    (output / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
