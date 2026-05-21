"""utils/ml/bridge.py — MLBridge orchestration layer.

Wires the full pipeline together (mirrors MacroBridge / ChaosScheduler):

  1. Extract a dataset from the event bus over a sim time window
  2. Fit a FeatureEngine on the rows
  3. Split into train/holdout (deterministic by correlation_id hash)
  4. Train a SimpleClassifier or SimpleRegressor on a chosen label
  5. Evaluate on the holdout
  6. Register the model with provenance into the global ModelRegistry
  7. Emit ml.model_trained event to the bus

Can also be scheduled into a TickScheduler so retraining happens at
specific sim moments (e.g. "retrain channel-success model every Sunday
at 9pm sim time" or "retrain after each MPC meeting").
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.ml.dataset import DatasetBuilder, DatasetRow, DatasetSpec
from utils.ml.features import FeatureEngine
from utils.ml.models import (
    SimpleClassifier, SimpleRegressor, ModelMetrics,
)
from utils.ml.registry import (
    ModelMeta, ModelRegistry, get_model_registry,
)


def _stable_split_key(corr_id: str) -> float:
    """Deterministic 0.0-1.0 hash for train/holdout split."""
    h = hashlib.sha256(corr_id.encode("utf-8")).digest()
    # Use first 8 bytes
    n = int.from_bytes(h[:8], "big")
    return n / float(2 ** 64)


class MLBridge:
    """Orchestrate train-evaluate-register cycles."""

    def __init__(self, *, registry: Optional[ModelRegistry] = None):
        self.registry = registry or get_model_registry()
        self._train_count = 0
        self._last_dataset_size = 0
        self._last_fingerprint = ""

    # ── Training ─────────────────────────────────────────────────

    def train_classifier(self, *, name: str, target_label: str,
                          spec: Optional[DatasetSpec] = None,
                          holdout_fraction: float = 0.2,
                          seed: int = 0,
                          lr: float = 0.1, epochs: int = 200,
                          l2: float = 1e-3,
                          notes: str = "",
                          builder: Optional[DatasetBuilder] = None,
                          persist: bool = True
                          ) -> Tuple[ModelMeta, ModelMetrics]:
        """Build a dataset, train a SimpleClassifier, evaluate, register."""
        rows = self._build_dataset(spec=spec, builder=builder)
        if not rows:
            raise ValueError(
                "train_classifier: no rows in dataset — nothing to learn"
            )
        train_rows, holdout_rows = self._split(rows, holdout_fraction)
        # Filter rows that have the target label
        train_rows = [r for r in train_rows if target_label in r.labels]
        holdout_rows = [r for r in holdout_rows
                         if target_label in r.labels]
        if not train_rows:
            raise ValueError(
                f"train_classifier: no rows carry label {target_label!r}"
            )

        engine = FeatureEngine().fit(train_rows)
        X_train = engine.transform(train_rows)
        y_train = [1 if bool(r.labels[target_label]) else 0
                    for r in train_rows]

        clf = SimpleClassifier(lr=lr, epochs=epochs, l2=l2, seed=seed)
        clf.fit(X_train, y_train)

        # Holdout evaluation
        if holdout_rows:
            X_h = engine.transform(holdout_rows)
            y_h = [1 if bool(r.labels[target_label]) else 0
                    for r in holdout_rows]
            metrics = clf.evaluate(X_h, y_h)
        else:
            metrics = clf.evaluate(X_train, y_train)

        # Register
        fp = self._last_fingerprint
        meta = ModelMeta(
            name=name, kind="classifier",
            dataset_fingerprint=fp,
            target_label=target_label,
            metrics=metrics.to_dict(),
            seed=seed,
            sample_count=len(train_rows),
            notes=notes,
        )
        self.registry.register(
            name=name, model=clf, features=engine, meta=meta,
            persist=persist,
        )
        self._emit_trained(name, meta)
        self._train_count += 1
        return meta, metrics

    def train_regressor(self, *, name: str, target_label: str,
                         spec: Optional[DatasetSpec] = None,
                         holdout_fraction: float = 0.2,
                         l2: float = 1e-3,
                         notes: str = "",
                         builder: Optional[DatasetBuilder] = None,
                         persist: bool = True
                         ) -> Tuple[ModelMeta, ModelMetrics]:
        """Build a dataset, train a SimpleRegressor, evaluate, register."""
        rows = self._build_dataset(spec=spec, builder=builder)
        if not rows:
            raise ValueError(
                "train_regressor: no rows in dataset — nothing to learn"
            )
        train_rows, holdout_rows = self._split(rows, holdout_fraction)
        train_rows = [r for r in train_rows if target_label in r.labels]
        holdout_rows = [r for r in holdout_rows
                         if target_label in r.labels]
        if not train_rows:
            raise ValueError(
                f"train_regressor: no rows carry label {target_label!r}"
            )

        engine = FeatureEngine().fit(train_rows)
        X_train = engine.transform(train_rows)
        y_train = [float(r.labels[target_label]) for r in train_rows]

        reg = SimpleRegressor(l2=l2)
        reg.fit(X_train, y_train)

        if holdout_rows:
            X_h = engine.transform(holdout_rows)
            y_h = [float(r.labels[target_label]) for r in holdout_rows]
            metrics = reg.evaluate(X_h, y_h)
        else:
            metrics = reg.evaluate(X_train, y_train)

        fp = self._last_fingerprint
        meta = ModelMeta(
            name=name, kind="regressor",
            dataset_fingerprint=fp,
            target_label=target_label,
            metrics=metrics.to_dict(),
            seed=0,
            sample_count=len(train_rows),
            notes=notes,
        )
        self.registry.register(
            name=name, model=reg, features=engine, meta=meta,
            persist=persist,
        )
        self._emit_trained(name, meta)
        self._train_count += 1
        return meta, metrics

    # ── Scheduling ───────────────────────────────────────────────

    def schedule_recurring_train(self, *, scheduler, start_at: datetime,
                                    interval: timedelta,
                                    train_fn: Callable[[], Any],
                                    label: str = "ml_retrain") -> str:
        """Schedule a recurring retraining job on a TickScheduler."""
        return scheduler.schedule_recurring(
            start_at=start_at, interval=interval,
            callback=train_fn, label=label, priority=-5,
        )

    # ── Internals ────────────────────────────────────────────────

    def _build_dataset(self, *,
                         spec: Optional[DatasetSpec],
                         builder: Optional[DatasetBuilder]
                         ) -> List[DatasetRow]:
        if spec is None:
            spec = DatasetSpec()
        if builder is None:
            builder = DatasetBuilder()
        rows = builder.build(spec)
        self._last_dataset_size = len(rows)
        self._last_fingerprint = builder.fingerprint(rows)
        return rows

    @staticmethod
    def _split(rows: List[DatasetRow], holdout_fraction: float
                ) -> Tuple[List[DatasetRow], List[DatasetRow]]:
        train, holdout = [], []
        for r in rows:
            if _stable_split_key(r.correlation_id) < holdout_fraction:
                holdout.append(r)
            else:
                train.append(r)
        return train, holdout

    def _emit_trained(self, name: str, meta: ModelMeta) -> None:
        try:
            from utils.event_bus import get_event_bus
            bus = get_event_bus()
            bus.emit(
                event_type="ml.model_trained",
                actor="ml_bridge",
                entity_id=name,
                module="ml",
                payload={
                    "name": name,
                    "kind": meta.kind,
                    "target_label": meta.target_label,
                    "sample_count": meta.sample_count,
                    "metrics": meta.metrics,
                    "fingerprint": meta.dataset_fingerprint,
                },
            )
        except Exception:
            pass

    # ── Introspection ────────────────────────────────────────────

    def train_count(self) -> int:
        return self._train_count

    def last_dataset_size(self) -> int:
        return self._last_dataset_size

    def last_fingerprint(self) -> str:
        return self._last_fingerprint


__all__ = ["MLBridge"]
