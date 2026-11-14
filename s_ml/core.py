"""Lecture-grounded regression with explicit gradients and safe JSON checkpoints."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np


def matrix(value):
    x = np.asarray(value, dtype=float)
    if x.ndim != 2 or not x.shape[0] or not x.shape[1] or not np.isfinite(x).all():
        raise ValueError("Expected a nonempty finite 2-D feature matrix")
    return x


def targets(value, n):
    y = np.asarray(value, dtype=float)
    if y.shape != (n,) or not np.isfinite(y).all():
        raise ValueError("Expected one finite target per example")
    return y


def loss_gradient(design, y, theta, regularization=0.0):
    """J = SSE/(2m) + lambda*||theta[1:]||²/(2m); intercept unpenalized."""
    if regularization < 0 or not np.isfinite(regularization):
        raise ValueError("Regularization must be finite and nonnegative")
    residual = design @ theta - y
    penalty = theta.copy()
    penalty[0] = 0
    m = len(y)
    cost = (residual @ residual + regularization * (penalty @ penalty)) / (2 * m)
    gradient = (design.T @ residual + regularization * penalty) / m
    return float(cost), gradient


class LinearGD:
    """Train-only normalization and simultaneous batch/mini-batch updates."""
    def __init__(self, learning_rate=0.05, epochs=1000, regularization=0.0,
                 batch_size=None, seed=27):
        if not np.isfinite(learning_rate) or learning_rate <= 0:
            raise ValueError("Learning rate must be positive and finite")
        if not isinstance(epochs, int) or epochs < 1:
            raise ValueError("epochs must be a positive integer")
        if batch_size is not None and (not isinstance(batch_size, int) or batch_size < 1):
            raise ValueError("batch_size must be positive")
        if not np.isfinite(regularization) or regularization < 0:
            raise ValueError("regularization must be nonnegative and finite")
        self.learning_rate, self.epochs = learning_rate, epochs
        self.regularization, self.batch_size, self.seed = regularization, batch_size, seed

    def fit(self, x, y):
        x = matrix(x)
        y = targets(y, len(x))
        self.mean = x.mean(axis=0)
        self.scale = x.std(axis=0)
        self.scale[self.scale == 0] = 1
        z = np.column_stack([np.ones(len(x)), (x - self.mean) / self.scale])
        self.theta = np.zeros(z.shape[1])
        self.history = [loss_gradient(z, y, self.theta, self.regularization)[0]]
        rng = np.random.default_rng(self.seed)
        for _ in range(self.epochs):
            order = rng.permutation(len(x)) if self.batch_size else np.arange(len(x))
            size = self.batch_size or len(x)
            for start in range(0, len(x), size):
                ids = order[start:start + size]
                # Scale penalty for mini-batches to preserve full-data objective.
                penalty = self.regularization * len(ids) / len(x)
                _, gradient = loss_gradient(z[ids], y[ids], self.theta, penalty)
                self.theta -= self.learning_rate * gradient
            cost = loss_gradient(z, y, self.theta, self.regularization)[0]
            if not np.isfinite(cost):
                raise ValueError("Optimization diverged; lower learning_rate")
            self.history.append(cost)
        return self

    def predict(self, x):
        if not hasattr(self, "theta"):
            raise ValueError("Model has not been trained")
        x = matrix(x)
        if x.shape[1] != len(self.mean):
            raise ValueError("Feature dimension differs from checkpoint")
        return np.column_stack([np.ones(len(x)), (x - self.mean) / self.scale]) @ self.theta

    def save(self, path):
        if not hasattr(self, "theta"):
            raise ValueError("Model has not been trained")
        data = dict(format="s_ml.linear.v1", mean=self.mean.tolist(), scale=self.scale.tolist(),
                    theta=self.theta.tolist(), history=self.history,
                    parameters=dict(learning_rate=self.learning_rate, epochs=self.epochs,
                                    regularization=self.regularization,
                                    batch_size=self.batch_size, seed=self.seed))
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
        temporary.replace(path)

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("format") != "s_ml.linear.v1":
            raise ValueError("Unsupported checkpoint format")
        model = cls(**data["parameters"])
        model.mean = np.asarray(data["mean"], dtype=float)
        model.scale = np.asarray(data["scale"], dtype=float)
        model.theta = np.asarray(data["theta"], dtype=float)
        if (model.mean.ndim != 1 or len(model.mean) == 0 or
            model.scale.shape != model.mean.shape or model.theta.shape != (len(model.mean) + 1,) or
            not all(np.isfinite(a).all() for a in [model.mean, model.scale, model.theta]) or
            np.any(model.scale <= 0)):
            raise ValueError("Invalid checkpoint arrays")
        model.history = data["history"]
        return model


def ordered_split(n):
    """60/20/20 ordered partitions; caller must establish ordering and label maturity."""
    if n < 15:
        raise ValueError("Need at least 15 observations for this demonstration split")
    a, b = int(n * .6), int(n * .8)
    return np.arange(a), np.arange(a, b), np.arange(b, n)


class GaussianAnomaly:
    """Lecture15 diagonal Gaussian log density; threshold requires validation labels."""
    def fit(self, x):
        x = matrix(x)
        self.mean = x.mean(axis=0)
        self.variance = np.maximum(x.var(axis=0), 1e-12)
        return self

    def score(self, x):
        x = matrix(x)
        if not hasattr(self, "mean") or x.shape[1] != len(self.mean):
            raise ValueError("Fit model first using matching features")
        return -.5 * np.sum(np.log(2 * np.pi * self.variance) +
                            (x - self.mean) ** 2 / self.variance, axis=1)
