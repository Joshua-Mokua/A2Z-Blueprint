"""utils/ml/registry.py — ModelRegistry singleton.

Holds fit models with full provenance: dataset fingerprint, sim time of
training, feature spec, evaluation metrics, seed. Persists to
data/ml_artifacts/ as JSON for cross-process durability.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from utils.ml.features import FeatureEngine
from utils.ml.models import (
    SimpleClassifier, SimpleRegressor, ModelMetrics,
)


_ARTIFACTS_DIR = Path("data/ml_artifacts")


@dataclass
class ModelMeta:
    """Metadata about a registered model."""
    name: str
    kind: str = ""                      # "classifier" | "regressor"
    dataset_fingerprint: str = ""
    trained_at: str = ""                # ISO timestamp (sim time)
    target_label: str = ""              # which label was being predicted
    metrics: Dict[str, Any] = field(default_factory=dict)
    seed: int = 0
    sample_count: int = 0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ModelRegistry:
    """Thread-safe registry of fit models with provenance."""

    def __init__(self, *, artifacts_dir: Optional[Path] = None):
        self._models: Dict[str, Any] = {}
        self._features: Dict[str, FeatureEngine] = {}
        self._meta: Dict[str, ModelMeta] = {}
        self._lock = threading.RLock()
        self.artifacts_dir = Path(artifacts_dir or _ARTIFACTS_DIR)
        try:
            self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def register(self, *, name: str,
                  model: Union[SimpleClassifier, SimpleRegressor],
                  features: FeatureEngine,
                  meta: ModelMeta,
                  persist: bool = True) -> ModelMeta:
        kind = "classifier" if isinstance(model, SimpleClassifier) \
                else "regressor"
        if not meta.kind:
            meta.kind = kind
        if not meta.trained_at:
            try:
                from utils.simulation_clock import sim_now
                meta.trained_at = sim_now().isoformat()
            except Exception:
                meta.trained_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._models[name] = model
            self._features[name] = features
            self._meta[name] = meta
        if persist:
            self._save(name)
        return meta

    def get_model(self, name: str):
        with self._lock:
            return self._models.get(name)

    def get_features(self, name: str) -> Optional[FeatureEngine]:
        with self._lock:
            return self._features.get(name)

    def get_meta(self, name: str) -> Optional[ModelMeta]:
        with self._lock:
            return self._meta.get(name)

    def list_models(self) -> List[str]:
        with self._lock:
            return sorted(self._models.keys())

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._models

    def predict(self, name: str, rows) -> List:
        with self._lock:
            model = self._models.get(name)
            features = self._features.get(name)
        if model is None or features is None:
            raise KeyError(f"unknown model {name!r}")
        X = features.transform(rows)
        return model.predict(X)

    def delete(self, name: str) -> bool:
        with self._lock:
            existed = name in self._models
            self._models.pop(name, None)
            self._features.pop(name, None)
            self._meta.pop(name, None)
        if existed:
            try:
                (self.artifacts_dir / f"{name}.json").unlink(
                    missing_ok=True)
            except Exception:
                pass
        return existed

    def clear(self) -> int:
        with self._lock:
            n = len(self._models)
            self._models.clear()
            self._features.clear()
            self._meta.clear()
        return n

    def _save(self, name: str) -> None:
        try:
            model = self._models[name]
            features = self._features[name]
            meta = self._meta[name]
            blob = {
                "name": name,
                "model": model.to_dict(),
                "features": features.to_dict(),
                "meta": meta.to_dict(),
            }
            path = self.artifacts_dir / f"{name}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(blob, f, indent=2)
        except Exception:
            pass

    def load(self, name: str) -> bool:
        path = self.artifacts_dir / f"{name}.json"
        if not path.exists():
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                blob = json.load(f)
            model_blob = blob["model"]
            kind = model_blob.get("kind")
            if kind == "SimpleClassifier":
                model = SimpleClassifier.from_dict(model_blob)
            elif kind == "SimpleRegressor":
                model = SimpleRegressor.from_dict(model_blob)
            else:
                return False
            features = FeatureEngine.from_dict(blob["features"])
            meta = ModelMeta(**blob["meta"])
            with self._lock:
                self._models[name] = model
                self._features[name] = features
                self._meta[name] = meta
            return True
        except Exception:
            return False


_GLOBAL_REGISTRY: Optional[ModelRegistry] = None
_REGISTRY_LOCK = threading.Lock()


def get_model_registry() -> ModelRegistry:
    global _GLOBAL_REGISTRY
    with _REGISTRY_LOCK:
        if _GLOBAL_REGISTRY is None:
            _GLOBAL_REGISTRY = ModelRegistry()
        return _GLOBAL_REGISTRY


def reset_model_registry() -> None:
    """For test isolation. Does not touch artifacts on disk."""
    global _GLOBAL_REGISTRY
    with _REGISTRY_LOCK:
        if _GLOBAL_REGISTRY is not None:
            _GLOBAL_REGISTRY.clear()
        _GLOBAL_REGISTRY = None


__all__ = [
    "ModelMeta", "ModelRegistry",
    "get_model_registry", "reset_model_registry",
]
