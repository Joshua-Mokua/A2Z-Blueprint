"""utils/ml/models.py — baseline ML models in pure Python.

Deterministic, dependency-free baselines (no sklearn, no numpy required).
Honest starting points future work can build on or replace.

  - SimpleClassifier: L2-regularised logistic regression by batch GD
  - SimpleRegressor: L2-regularised linear regression (ridge) via
    closed-form normal equations with Gauss-Jordan elimination

Both are seed-deterministic and produce ModelMetrics on evaluation.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Sequence


@dataclass
class ModelMetrics:
    """Evaluation metrics for a fit model."""
    samples: int = 0
    # Classification
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    confusion: Dict[str, int] = field(default_factory=dict)
    # Regression
    mse: float = 0.0
    rmse: float = 0.0
    mae: float = 0.0
    r2: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "samples": self.samples,
            "accuracy": round(self.accuracy, 5),
            "precision": round(self.precision, 5),
            "recall": round(self.recall, 5),
            "f1": round(self.f1, 5),
            "confusion": dict(self.confusion),
            "mse": round(self.mse, 5),
            "rmse": round(self.rmse, 5),
            "mae": round(self.mae, 5),
            "r2": round(self.r2, 5),
        }


class SimpleClassifier:
    """L2-regularised logistic regression by batch GD."""

    def __init__(self, *, lr: float = 0.1, epochs: int = 200,
                  l2: float = 1e-3, seed: int = 0):
        self.lr = lr
        self.epochs = epochs
        self.l2 = l2
        self.seed = seed
        self.weights: List[float] = []
        self.bias: float = 0.0
        self.n_features: int = 0

    def fit(self, X: Sequence[Sequence[float]],
            y: Sequence[int]) -> "SimpleClassifier":
        if not X:
            raise ValueError("empty training set")
        self.n_features = len(X[0])
        rng = random.Random(self.seed)
        self.weights = [rng.gauss(0, 0.01) for _ in range(self.n_features)]
        self.bias = 0.0
        n = len(X)
        for _ in range(self.epochs):
            grad_w = [0.0] * self.n_features
            grad_b = 0.0
            for xi, yi in zip(X, y):
                p = self._sigmoid(self._linear(xi))
                err = p - yi
                grad_b += err
                for j in range(self.n_features):
                    grad_w[j] += err * xi[j]
            for j in range(self.n_features):
                grad_w[j] = grad_w[j] / n + self.l2 * self.weights[j]
            grad_b = grad_b / n
            for j in range(self.n_features):
                self.weights[j] -= self.lr * grad_w[j]
            self.bias -= self.lr * grad_b
        return self

    def predict_proba(self, X: Sequence[Sequence[float]]) -> List[float]:
        return [self._sigmoid(self._linear(xi)) for xi in X]

    def predict(self, X: Sequence[Sequence[float]],
                 *, threshold: float = 0.5) -> List[int]:
        return [1 if p >= threshold else 0
                 for p in self.predict_proba(X)]

    def evaluate(self, X: Sequence[Sequence[float]],
                  y_true: Sequence[int]) -> ModelMetrics:
        y_pred = self.predict(X)
        return _classification_metrics(y_true, y_pred)

    def to_dict(self) -> Dict:
        return {
            "kind": "SimpleClassifier",
            "lr": self.lr, "epochs": self.epochs, "l2": self.l2,
            "seed": self.seed,
            "weights": list(self.weights), "bias": self.bias,
            "n_features": self.n_features,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "SimpleClassifier":
        m = cls(lr=d["lr"], epochs=d["epochs"], l2=d["l2"], seed=d["seed"])
        m.weights = list(d["weights"])
        m.bias = float(d["bias"])
        m.n_features = int(d["n_features"])
        return m

    def _linear(self, x: Sequence[float]) -> float:
        s = self.bias
        for j, xj in enumerate(x):
            s += self.weights[j] * xj
        return s

    @staticmethod
    def _sigmoid(z: float) -> float:
        if z >= 0:
            ez = math.exp(-z)
            return 1.0 / (1.0 + ez)
        ez = math.exp(z)
        return ez / (1.0 + ez)


class SimpleRegressor:
    """L2-regularised linear regression solved in closed form."""

    def __init__(self, *, l2: float = 1e-3):
        self.l2 = l2
        self.weights: List[float] = []
        self.bias: float = 0.0
        self.n_features: int = 0

    def fit(self, X: Sequence[Sequence[float]],
            y: Sequence[float]) -> "SimpleRegressor":
        if not X:
            raise ValueError("empty training set")
        self.n_features = len(X[0])
        n = len(X)
        d = self.n_features
        Xa = [list(row) + [1.0] for row in X]
        Y = [float(yi) for yi in y]
        D = d + 1
        XtX = [[0.0] * D for _ in range(D)]
        XtY = [0.0] * D
        for row, yi in zip(Xa, Y):
            for i in range(D):
                XtY[i] += row[i] * yi
                for j in range(D):
                    XtX[i][j] += row[i] * row[j]
        for i in range(d):
            XtX[i][i] += self.l2 * n
        w = _solve_linear(XtX, XtY)
        self.weights = w[:d]
        self.bias = w[d]
        return self

    def predict(self, X: Sequence[Sequence[float]]) -> List[float]:
        out = []
        for xi in X:
            s = self.bias
            for j, xj in enumerate(xi):
                s += self.weights[j] * xj
            out.append(s)
        return out

    def evaluate(self, X: Sequence[Sequence[float]],
                  y_true: Sequence[float]) -> ModelMetrics:
        y_pred = self.predict(X)
        return _regression_metrics(y_true, y_pred)

    def to_dict(self) -> Dict:
        return {
            "kind": "SimpleRegressor",
            "l2": self.l2,
            "weights": list(self.weights), "bias": self.bias,
            "n_features": self.n_features,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "SimpleRegressor":
        m = cls(l2=d["l2"])
        m.weights = list(d["weights"])
        m.bias = float(d["bias"])
        m.n_features = int(d["n_features"])
        return m


# ─── Metric helpers ──────────────────────────────────────────────────


def _classification_metrics(y_true, y_pred) -> ModelMetrics:
    y_true = list(y_true)
    y_pred = list(y_pred)
    n = max(1, len(y_true))
    tp = fp = tn = fn = 0
    for yt, yp in zip(y_true, y_pred):
        if yp == 1 and yt == 1: tp += 1
        elif yp == 1 and yt == 0: fp += 1
        elif yp == 0 and yt == 0: tn += 1
        elif yp == 0 and yt == 1: fn += 1
    acc = (tp + tn) / n
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
    return ModelMetrics(
        samples=n, accuracy=acc, precision=prec,
        recall=rec, f1=f1,
        confusion={"tp": tp, "fp": fp, "tn": tn, "fn": fn},
    )


def _regression_metrics(y_true, y_pred) -> ModelMetrics:
    y_true = [float(v) for v in y_true]
    y_pred = [float(v) for v in y_pred]
    n = max(1, len(y_true))
    se = sum((yt - yp) ** 2 for yt, yp in zip(y_true, y_pred))
    ae = sum(abs(yt - yp) for yt, yp in zip(y_true, y_pred))
    mse = se / n
    mae = ae / n
    rmse = math.sqrt(mse)
    mean_y = sum(y_true) / n
    ss_tot = sum((yt - mean_y) ** 2 for yt in y_true)
    r2 = 1.0 - (se / ss_tot) if ss_tot > 1e-12 else 0.0
    return ModelMetrics(samples=n, mse=mse, rmse=rmse, mae=mae, r2=r2)


def _solve_linear(A: List[List[float]],
                    b: List[float]) -> List[float]:
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(n):
        piv = i
        for k in range(i + 1, n):
            if abs(M[k][i]) > abs(M[piv][i]):
                piv = k
        if abs(M[piv][i]) < 1e-12:
            return [0.0] * n
        if piv != i:
            M[i], M[piv] = M[piv], M[i]
        d = M[i][i]
        M[i] = [v / d for v in M[i]]
        for k in range(n):
            if k != i and abs(M[k][i]) > 1e-15:
                f = M[k][i]
                M[k] = [M[k][j] - f * M[i][j] for j in range(n + 1)]
    return [M[i][n] for i in range(n)]


__all__ = [
    "SimpleClassifier", "SimpleRegressor", "ModelMetrics",
]
