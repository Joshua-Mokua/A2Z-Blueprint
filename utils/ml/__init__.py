"""utils.ml — Phase O6-A AI/ML evolution lab.

Foundational ML infrastructure for the Olympic-grade digital twin:

  - DatasetBuilder: extracts training rows from the event_bus stream
    (channel calls, scenarios run, chaos events, macro state)
  - FeatureEngine: turns raw events into numeric feature vectors
  - ModelRegistry: stores fit models with provenance (seed, dataset
    fingerprint, sim time of training, evaluation metrics)
  - SimpleClassifier / SimpleRegressor: deterministic baseline learners
    (no sklearn dep — pure NumPy via stdlib math)
  - MLBridge: ties the whole pipeline to the sim clock so models can
    be retrained at scheduled sim moments

These are foundations, not the LLM agents (v10.484 O6-B) or training
arena (v10.485-486 O7).
"""

from utils.ml.dataset import (
    DatasetRow, DatasetBuilder, DatasetSpec,
)
from utils.ml.features import (
    FeatureEngine, FeatureSpec,
)
from utils.ml.models import (
    SimpleClassifier, SimpleRegressor, ModelMetrics,
)
from utils.ml.registry import (
    ModelRegistry, ModelMeta, get_model_registry,
    reset_model_registry,
)
from utils.ml.bridge import MLBridge

__all__ = [
    "DatasetRow", "DatasetBuilder", "DatasetSpec",
    "FeatureEngine", "FeatureSpec",
    "SimpleClassifier", "SimpleRegressor", "ModelMetrics",
    "ModelRegistry", "ModelMeta",
    "get_model_registry", "reset_model_registry",
    "MLBridge",
]
