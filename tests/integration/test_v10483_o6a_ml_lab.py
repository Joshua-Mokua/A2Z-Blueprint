"""Integration tests for v10.483 — Phase O6-A AI/ML evolution lab."""

import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def _reset_all():
    for k in list(sys.modules):
        if any(s in k for s in ("ml", "chaos", "channels",
                                  "simulation_clock", "tick_scheduler",
                                  "event_bus", "macro_")):
            del sys.modules[k]
    from utils.simulation_clock import reset_simulation_clock
    from utils.chaos import reset_chaos_injector
    from utils.macro_state import reset_macro_state
    from utils.ml import reset_model_registry
    reset_simulation_clock()
    reset_chaos_injector()
    reset_macro_state()
    reset_model_registry()
    yield
    reset_simulation_clock()
    reset_chaos_injector()
    reset_macro_state()
    reset_model_registry()


# ── Module presence ─────────────────────────────────────────────────

def test_v10483_ml_package_exists():
    pkg = REPO / "utils" / "ml"
    assert pkg.is_dir()
    for f in ["__init__.py", "dataset.py", "features.py",
                "models.py", "registry.py", "bridge.py"]:
        assert (pkg / f).exists()


# ── FeatureEngine ───────────────────────────────────────────────────

def test_v10483_feature_engine_fit_then_transform():
    from utils.ml import FeatureEngine, DatasetRow
    rows = [
        DatasetRow(correlation_id="a", channel="mpesa",
                    timestamp="2026-05-15T10:00:00+00:00",
                    features={"x": 1.0, "y": 2.0}, labels={}),
        DatasetRow(correlation_id="b", channel="mpesa",
                    timestamp="2026-05-15T11:00:00+00:00",
                    features={"x": 3.0, "y": 4.0}, labels={}),
    ]
    eng = FeatureEngine().fit(rows)
    assert eng.spec.feature_names == ["x", "y"]
    v = eng.transform_one(rows[0])
    assert len(v) == 2


def test_v10483_feature_engine_handles_missing_features():
    from utils.ml import FeatureEngine, DatasetRow
    rows = [
        DatasetRow(correlation_id="a", channel="mpesa",
                    timestamp="2026-05-15T10:00:00+00:00",
                    features={"x": 1.0}, labels={}),
        DatasetRow(correlation_id="b", channel="mpesa",
                    timestamp="2026-05-15T11:00:00+00:00",
                    features={"y": 2.0}, labels={}),
    ]
    eng = FeatureEngine().fit(rows)
    assert set(eng.spec.feature_names) == {"x", "y"}
    v = eng.transform_one(rows[0])
    assert len(v) == 2


def test_v10483_feature_engine_persistence_roundtrip():
    from utils.ml import FeatureEngine, DatasetRow
    rows = [
        DatasetRow(correlation_id="a", channel="x",
                    timestamp="2026-05-15T10:00:00+00:00",
                    features={"f1": 1.0, "f2": 2.0}, labels={}),
        DatasetRow(correlation_id="b", channel="x",
                    timestamp="2026-05-15T11:00:00+00:00",
                    features={"f1": 5.0, "f2": 7.0}, labels={}),
    ]
    eng = FeatureEngine().fit(rows)
    eng2 = FeatureEngine.from_dict(eng.to_dict())
    assert eng.transform_one(rows[0]) == eng2.transform_one(rows[0])


def test_v10483_feature_engine_transform_before_fit_raises():
    from utils.ml import FeatureEngine, DatasetRow
    eng = FeatureEngine()
    row = DatasetRow(correlation_id="a", channel="x",
                       timestamp="2026-05-15T10:00:00+00:00",
                       features={"x": 1.0}, labels={})
    with pytest.raises(RuntimeError):
        eng.transform_one(row)


# ── SimpleClassifier ────────────────────────────────────────────────

def test_v10483_classifier_learns_linearly_separable():
    from utils.ml import SimpleClassifier
    rng = random.Random(42)
    X, y = [], []
    for _ in range(200):
        a = rng.gauss(0, 1)
        b = rng.gauss(0, 1)
        X.append([a, b])
        y.append(1 if a + b > 0 else 0)
    clf = SimpleClassifier(seed=0).fit(X, y)
    m = clf.evaluate(X, y)
    assert m.accuracy > 0.85


def test_v10483_classifier_predict_proba_in_range():
    from utils.ml import SimpleClassifier
    rng = random.Random(0)
    X = [[rng.gauss(0, 1) for _ in range(3)] for _ in range(50)]
    y = [1 if x[0] > 0 else 0 for x in X]
    clf = SimpleClassifier(seed=0).fit(X, y)
    for p in clf.predict_proba(X[:10]):
        assert 0.0 <= p <= 1.0


def test_v10483_classifier_seed_deterministic():
    from utils.ml import SimpleClassifier
    rng = random.Random(0)
    X = [[rng.gauss(0, 1), rng.gauss(0, 1)] for _ in range(50)]
    y = [1 if x[0] > 0 else 0 for x in X]
    a = SimpleClassifier(seed=99).fit(X, y)
    b = SimpleClassifier(seed=99).fit(X, y)
    assert all(abs(wa - wb) < 1e-12
                for wa, wb in zip(a.weights, b.weights))
    assert abs(a.bias - b.bias) < 1e-12


def test_v10483_classifier_persistence_roundtrip():
    from utils.ml import SimpleClassifier
    rng = random.Random(0)
    X = [[rng.gauss(0, 1)] for _ in range(50)]
    y = [1 if x[0] > 0 else 0 for x in X]
    clf = SimpleClassifier(seed=7).fit(X, y)
    clf2 = SimpleClassifier.from_dict(clf.to_dict())
    assert clf2.predict(X[:5]) == clf.predict(X[:5])


def test_v10483_classifier_empty_training_raises():
    from utils.ml import SimpleClassifier
    with pytest.raises(ValueError):
        SimpleClassifier().fit([], [])


# ── SimpleRegressor ─────────────────────────────────────────────────

def test_v10483_regressor_recovers_linear_coefficients():
    from utils.ml import SimpleRegressor
    rng = random.Random(0)
    X = [[rng.gauss(0, 1)] for _ in range(200)]
    y = [2 * x[0] + 3 for x in X]
    reg = SimpleRegressor(l2=1e-6).fit(X, y)
    assert abs(reg.weights[0] - 2.0) < 0.05
    assert abs(reg.bias - 3.0) < 0.05


def test_v10483_regressor_r2_high_on_linear():
    from utils.ml import SimpleRegressor
    rng = random.Random(0)
    X = []
    y = []
    for _ in range(200):
        a = rng.gauss(0, 1)
        b = rng.gauss(0, 1)
        X.append([a, b])
        y.append(2 * a + 3 * b + 1)
    reg = SimpleRegressor(l2=1e-6).fit(X, y)
    m = reg.evaluate(X, y)
    assert m.r2 > 0.99


def test_v10483_regressor_persistence_roundtrip():
    from utils.ml import SimpleRegressor
    rng = random.Random(0)
    X = [[rng.gauss(0, 1)] for _ in range(50)]
    y = [2 * x[0] + 1 for x in X]
    reg = SimpleRegressor().fit(X, y)
    reg2 = SimpleRegressor.from_dict(reg.to_dict())
    assert reg.predict(X[:5]) == reg2.predict(X[:5])


# ── ModelRegistry ───────────────────────────────────────────────────

def test_v10483_registry_singleton():
    from utils.ml import get_model_registry
    a = get_model_registry()
    b = get_model_registry()
    assert a is b


def test_v10483_registry_register_then_get():
    from utils.ml import (
        get_model_registry, SimpleClassifier, FeatureEngine,
        ModelMeta, DatasetRow,
    )
    rng = random.Random(0)
    X = [[rng.gauss(0, 1)] for _ in range(20)]
    y = [1 if x[0] > 0 else 0 for x in X]
    clf = SimpleClassifier(seed=0).fit(X, y)
    rows = [DatasetRow(correlation_id=f"c{i}", channel="x",
                         timestamp="2026-05-15T10:00:00+00:00",
                         features={"f": xi[0]}, labels={})
             for i, xi in enumerate(X)]
    eng = FeatureEngine().fit(rows)
    reg = get_model_registry()
    reg.register(name="m1", model=clf, features=eng,
                  meta=ModelMeta(name="m1", kind="classifier"),
                  persist=False)
    assert reg.has("m1")
    assert reg.get_model("m1") is clf


def test_v10483_registry_predict_unknown_raises():
    from utils.ml import get_model_registry
    with pytest.raises(KeyError):
        get_model_registry().predict("nonexistent_model_xyz", [])


def test_v10483_registry_persistence_to_tmp(tmp_path):
    from utils.ml.registry import ModelRegistry, ModelMeta
    from utils.ml import SimpleClassifier, FeatureEngine, DatasetRow
    rng = random.Random(0)
    rows = [DatasetRow(correlation_id=f"c{i}", channel="x",
                         timestamp="2026-05-15T10:00:00+00:00",
                         features={"f": rng.gauss(0, 1)},
                         labels={"success": (i % 2 == 0)})
             for i in range(40)]
    eng = FeatureEngine().fit(rows)
    X = eng.transform(rows)
    y = [1 if r.labels["success"] else 0 for r in rows]
    clf = SimpleClassifier(seed=0).fit(X, y)
    reg = ModelRegistry(artifacts_dir=tmp_path)
    reg.register(name="rt_test", model=clf, features=eng,
                  meta=ModelMeta(name="rt_test", kind="classifier"))
    assert (tmp_path / "rt_test.json").exists()
    # Fresh registry pointed at same dir → load it
    reg2 = ModelRegistry(artifacts_dir=tmp_path)
    assert reg2.load("rt_test")
    assert reg2.has("rt_test")


# ── DatasetBuilder ──────────────────────────────────────────────────

def test_v10483_dataset_builder_returns_rows():
    from utils.ml import DatasetBuilder, DatasetSpec, DatasetRow
    from utils.channels import submit_channel
    for i in range(10):
        submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                      "msisdn": "254712345678", "amount": 1500,
                      "paybill": "174379"},
            amount=1500, reference=f"DS-{i}", actor="t", seed=i)
    rows = DatasetBuilder().build(DatasetSpec())
    assert any(isinstance(r, DatasetRow) for r in rows)


def test_v10483_dataset_row_has_features_and_labels():
    from utils.ml import DatasetBuilder, DatasetSpec
    from utils.channels import submit_channel
    submit_channel("cards",
        payload={"operation": "AUTH_CAPTURE",
                  "pan": "4111111111111111", "cvv": "123",
                  "expiry": "12/28", "card_not_present": False},
        amount=2500, reference="DS-CARDS-1", actor="t", seed=1)
    rows = DatasetBuilder().build(DatasetSpec())
    cards_rows = [r for r in rows if r.channel == "cards"]
    assert cards_rows
    r = cards_rows[-1]
    assert "amount_log" in r.features
    assert "hour_sin" in r.features
    assert "success" in r.labels


def test_v10483_dataset_fingerprint_deterministic():
    from utils.ml import DatasetBuilder, DatasetSpec
    from utils.channels import submit_channel
    submit_channel("mpesa",
        payload={"transaction_type": "CustomerPayBillOnline",
                  "msisdn": "254712345678", "amount": 1500,
                  "paybill": "174379"},
        amount=1500, reference="FP-1", actor="t", seed=1)
    b1 = DatasetBuilder()
    b2 = DatasetBuilder()
    rows1 = b1.build(DatasetSpec())
    rows2 = b2.build(DatasetSpec())
    assert b1.fingerprint(rows1) == b2.fingerprint(rows2)


def test_v10483_dataset_filter_by_channel():
    from utils.ml import DatasetBuilder, DatasetSpec
    from utils.channels import submit_channel
    submit_channel("mpesa",
        payload={"transaction_type": "CustomerPayBillOnline",
                  "msisdn": "254712345678", "amount": 1500,
                  "paybill": "174379"},
        amount=1500, reference="MIX-1", actor="t", seed=1)
    submit_channel("cards",
        payload={"operation": "AUTH_CAPTURE",
                  "pan": "4111111111111111", "cvv": "123",
                  "expiry": "12/28", "card_not_present": False},
        amount=1000, reference="MIX-2", actor="t", seed=1)
    rows = DatasetBuilder().build(DatasetSpec(channels=["cards"]))
    assert all(r.channel == "cards" for r in rows)


# ── MLBridge ────────────────────────────────────────────────────────

def test_v10483_bridge_train_classifier_emits_event():
    from utils.ml import MLBridge, DatasetBuilder, DatasetRow
    from utils.event_bus import get_event_bus
    rows = [
        DatasetRow(correlation_id=f"c{i:04d}", channel="mpesa",
                    timestamp="2026-05-15T10:00:00+00:00",
                    features={"x": float(i % 10),
                                "hour_sin": 0.1, "hour_cos": 0.1,
                                "dow_sin": 0.1, "dow_cos": 0.1,
                                "channel_mpesa": 1.0},
                    labels={"success": (i % 2 == 0)})
        for i in range(60)
    ]

    class StubBuilder(DatasetBuilder):
        def __init__(self, rs): self._rs = rs
        def build(self, spec): return list(self._rs)
        def fingerprint(self, rs): return "stub_fp"

    MLBridge().train_classifier(
        name="t_emit", target_label="success",
        builder=StubBuilder(rows), persist=False, seed=1,
    )
    events = get_event_bus().query(event_type="ml.model_trained", limit=5)
    assert any(e.entity_id == "t_emit" for e in events)


def test_v10483_bridge_split_deterministic():
    from utils.ml.bridge import _stable_split_key
    assert _stable_split_key("abc-123") == _stable_split_key("abc-123")
    assert 0.0 <= _stable_split_key("anything") <= 1.0


def test_v10483_bridge_train_classifier_records_provenance():
    from utils.ml import MLBridge, DatasetBuilder, DatasetRow
    rows = [
        DatasetRow(correlation_id=f"c{i:04d}", channel="x",
                    timestamp="2026-05-15T10:00:00+00:00",
                    features={"f": float(i)},
                    labels={"success": (i % 2 == 0)})
        for i in range(40)
    ]

    class StubBuilder(DatasetBuilder):
        def __init__(self, rs): self._rs = rs
        def build(self, spec): return list(self._rs)
        def fingerprint(self, rs): return "prov_fp_xyz"

    meta, metrics = MLBridge().train_classifier(
        name="prov_test", target_label="success",
        builder=StubBuilder(rows), persist=False, seed=5,
        notes="for provenance test",
    )
    assert meta.dataset_fingerprint == "prov_fp_xyz"
    assert meta.target_label == "success"
    assert meta.seed == 5
    assert meta.notes == "for provenance test"
    assert meta.sample_count > 0
    assert "accuracy" in meta.metrics


def test_v10483_bridge_train_regressor_for_latency():
    from utils.ml import MLBridge, DatasetBuilder, DatasetRow
    rng = random.Random(0)
    rows = []
    for i in range(80):
        a = rng.gauss(0, 1)
        rows.append(DatasetRow(
            correlation_id=f"r{i:04d}", channel="x",
            timestamp="2026-05-15T10:00:00+00:00",
            features={"a": a},
            labels={"latency_ms": 100.0 + 50 * a},
        ))

    class StubBuilder(DatasetBuilder):
        def __init__(self, rs): self._rs = rs
        def build(self, spec): return list(self._rs)
        def fingerprint(self, rs): return "lat_fp"

    meta, metrics = MLBridge().train_regressor(
        name="lat_test", target_label="latency_ms",
        builder=StubBuilder(rows), persist=False,
    )
    assert meta.kind == "regressor"
    assert metrics.r2 > 0.5


def test_v10483_bridge_raises_on_empty_dataset():
    from utils.ml import MLBridge, DatasetBuilder
    class EmptyBuilder(DatasetBuilder):
        def build(self, spec): return []
        def fingerprint(self, rs): return "empty"
    with pytest.raises(ValueError):
        MLBridge().train_classifier(
            name="empty", target_label="success",
            builder=EmptyBuilder(), persist=False,
        )


def test_v10483_bridge_schedule_recurring_train():
    """MLBridge can schedule retraining via TickScheduler."""
    from utils.ml import MLBridge
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.tick_scheduler import TickScheduler
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 9, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    bridge = MLBridge()
    called = []
    cb_id = bridge.schedule_recurring_train(
        scheduler=sched,
        start_at=datetime(2026, 5, 15, 10, 0, tzinfo=NAIROBI_TZ),
        interval=timedelta(hours=1),
        train_fn=lambda: called.append(1),
    )
    assert cb_id  # got an ID back
    sched.tick(advance_by=timedelta(hours=3))
    assert len(called) >= 3


# ── End-to-end ───────────────────────────────────────────────────────

def test_v10483_e2e_real_traffic_then_train():
    """Generate channel traffic, train classifier on outcomes."""
    from utils.channels import submit_channel
    from utils.ml import MLBridge
    for i in range(30):
        submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                      "msisdn": "254712345678", "amount": 1500,
                      "paybill": "174379"},
            amount=1500, reference=f"E2E-{i}", actor="t", seed=i)
    meta, metrics = MLBridge().train_classifier(
        name="e2e_test", target_label="success",
        persist=False, seed=42,
    )
    assert meta.sample_count > 0
    assert "accuracy" in meta.metrics


def test_v10483_e2e_chaos_aware_features():
    """Dataset features include chaos features at call time."""
    from utils.channels import submit_channel
    from utils.chaos import get_chaos_injector, get_chaos_event
    from utils.ml import DatasetBuilder, DatasetSpec
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    # Submit during outage
    get_chaos_injector().activate(get_chaos_event(
        "safaricom_mpesa_outage_30min", when=clock.now()))
    for i in range(10):
        submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                      "msisdn": "254712345678", "amount": 1500,
                      "paybill": "174379"},
            amount=1500, reference=f"CH-{i}", actor="t", seed=i)
    rows = DatasetBuilder().build(DatasetSpec())
    mpesa_during_outage = [r for r in rows
                             if r.channel == "mpesa"
                             and r.labels.get("error_code") == "CHAOS_OUTAGE"]
    assert mpesa_during_outage
    # At least one such row should have chaos_outage_active=1.0
    assert any(r.features.get("chaos_outage_active", 0) == 1.0
                for r in mpesa_during_outage)


# ── G369 + cumulative regression ────────────────────────────────────

def test_v10483_g369_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10483_o6a_ml_evolution_lab
    r = gate_v10483_o6a_ml_evolution_lab()
    assert r["passed"], r.get("violations")


def test_v10483_prior_phase_gates_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10482_o5_chaos_engineering,
        gate_v10481_o4b_macro_economic_state,
        gate_v10480_o4a_simulation_clock_tick_scheduler,
        gate_v10479_o3c_scenario_library,
        gate_v10478_o3b_kic_cards_complete_7_channels,
        gate_v10477_o3a_channel_simulators,
    )
    for gate in (gate_v10482_o5_chaos_engineering,
                  gate_v10481_o4b_macro_economic_state,
                  gate_v10480_o4a_simulation_clock_tick_scheduler,
                  gate_v10479_o3c_scenario_library,
                  gate_v10478_o3b_kic_cards_complete_7_channels,
                  gate_v10477_o3a_channel_simulators):
        assert gate()["passed"], f"{gate.__name__} regressed"


def test_v10483_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9
