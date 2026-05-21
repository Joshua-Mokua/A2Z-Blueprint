"""utils/ml/features.py — feature normalisation for ML models.

FeatureEngine turns variable-key feature dicts (as emitted by
DatasetBuilder) into ordered float vectors that the SimpleClassifier /
SimpleRegressor can consume.

Two stages:
  1. fit(rows)     — discover the full feature vocabulary and compute
                      per-feature mean + std for standardisation
  2. transform(row) — produce a fixed-length float vector

The engine is deterministic given the same rows. It writes its state
into a FeatureSpec which can be persisted alongside a model so that
inference uses the same feature space + normalisation as training.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


@dataclass
class FeatureSpec:
    """Fitted feature engineering state."""
    feature_names: List[str] = field(default_factory=list)
    means: Dict[str, float] = field(default_factory=dict)
    stds: Dict[str, float] = field(default_factory=dict)

    def is_fit(self) -> bool:
        return bool(self.feature_names)


class FeatureEngine:
    """Fit a feature vocabulary and standardise vectors."""

    def __init__(self):
        self.spec = FeatureSpec()

    def fit(self, rows) -> "FeatureEngine":
        """Discover feature names + compute means/stds."""
        # Collect all feature keys across rows
        all_keys = set()
        for r in rows:
            all_keys.update(r.features.keys())
        feature_names = sorted(all_keys)

        # Compute mean + std per feature
        means: Dict[str, float] = {}
        stds: Dict[str, float] = {}
        for name in feature_names:
            vals = [r.features.get(name, 0.0) for r in rows]
            n = max(1, len(vals))
            m = sum(vals) / n
            var = sum((v - m) ** 2 for v in vals) / n
            s = math.sqrt(var)
            means[name] = m
            stds[name] = s if s > 1e-9 else 1.0   # avoid div-by-zero

        self.spec = FeatureSpec(
            feature_names=feature_names, means=means, stds=stds,
        )
        return self

    def transform_one(self, row) -> List[float]:
        """Transform one row into an ordered float vector."""
        if not self.spec.is_fit():
            raise RuntimeError("FeatureEngine: fit() before transform()")
        out = []
        for name in self.spec.feature_names:
            raw = row.features.get(name, 0.0)
            m = self.spec.means[name]
            s = self.spec.stds[name]
            out.append((raw - m) / s)
        return out

    def transform(self, rows: Sequence) -> List[List[float]]:
        return [self.transform_one(r) for r in rows]

    def fit_transform(self, rows) -> List[List[float]]:
        self.fit(rows)
        return self.transform(rows)

    # ── Persistence ─────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "feature_names": list(self.spec.feature_names),
            "means": dict(self.spec.means),
            "stds": dict(self.spec.stds),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "FeatureEngine":
        eng = cls()
        eng.spec = FeatureSpec(
            feature_names=list(d.get("feature_names", [])),
            means=dict(d.get("means", {})),
            stds=dict(d.get("stds", {})),
        )
        return eng


__all__ = ["FeatureEngine", "FeatureSpec"]
