"""scripts/training/train_document_classifier.py — v10.78 reference.

End-to-end ML training pipeline for ENH-270 document classifier.

The training pipeline transforms candidate findings (from
deterministic UCP 600 checks) into a trained classifier that
refines severity and filters false positives. The trained model
plugs into TradeFinanceDocumentCheckingEngine via the v10.76 ML
hook contract:

    Callable[[Sequence[CandidateFinding]],
             Sequence[ClassificationResult]]

PIPELINE STAGES:

  Stage 1 — Data extraction
    Generate synthetic candidate findings from cbs_data/ instrument
    fixtures + the ENH-270 scenario library. In production, this
    stage is replaced by extraction of historical examiner
    adjudications (the supervised signal: did the examiner
    actually refuse this presentation, with what severity?).

  Stage 2 — Feature engineering
    Convert each CandidateFinding into a numeric feature vector
    suitable for ML training. Categorical features (category +
    document_type) are one-hot encoded; severity is the label;
    feature_hints are exposed as additional numeric features.

  Stage 3 — Synthetic labeling (REPLACE IN PRODUCTION)
    For pipeline validation only — apply rule-based labels
    derived from the rule_assigned_severity field. This is
    DELIBERATELY trivial; it validates the pipeline shape, not
    accuracy. In production, labels come from operator
    adjudication history.

  Stage 4 — Train/test split
    Stratified split with deterministic seed. Default 80/20.

  Stage 5 — Training
    sklearn LogisticRegression baseline. Swappable for any
    sklearn-API-compatible classifier (RandomForest, XGBoost,
    LightGBM) without changing the rest of the pipeline.

  Stage 6 — Evaluation
    Accuracy + precision + recall + F1 on held-out test set.
    Confusion matrix per severity tier. Bootstrap confidence
    intervals on accuracy (1000 resamples).

  Stage 7 — Persistence
    pickle(model) + metadata JSON (training_date, data_hash,
    metrics, feature_names, model_version, sklearn_version).

ML DEPENDENCY POLICY:

The runtime engine (utils/trade_finance_document_checking.py) is
PURE STDLIB. The training script requires sklearn + numpy +
pandas, which are NOT in the production runtime requirements.
Install separately for training environments:

    pip install -r requirements-ml.txt    # see file in repo root

The trained model serializes via pickle and the runtime engine
loads it without requiring sklearn at inference time IF the
classifier wrapper does the ml→engine translation. For sklearn-
based classifiers, sklearn IS needed at inference; document this
clearly in deployment.

THE MODEL IS SYNTHETIC-TRAINED, ALWAYS:

This script ships as a reference implementation. The model it
produces is acknowledged as synthetic-trained and the engine
continues to surface ml_disabled=True or ml_disabled=False per
the v10.76 contract — but operators should treat any model
trained by this script (without real adjudication data) as
demonstration-grade, not production-grade. The pipeline shape is
the deliverable; the trained accuracy on real data is a separate
problem that requires real labeled data.

USAGE:

  python scripts/training/train_document_classifier.py \\
      --output-dir data/models/document_classifier \\
      --random-seed 42 \\
      --test-fraction 0.2 \\
      --version 1

OUTPUTS:

  data/models/document_classifier/model_v{N}.pkl
  data/models/document_classifier/metadata_v{N}.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import random
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Engine + scenario imports — these run on stdlib alone
from utils.trade_finance_document_checking import (
    TradeFinanceDocumentCheckingEngine,
    LCTerms, PresentedDocument, DocumentPresentation,
    DocumentType, DiscrepancySeverity, CheckCategory,
    CandidateFinding, ClassificationResult)


# ════════════════════════════════════════════════════════════════════════
# Stage 1 — Synthetic data generation (replace with adjudication
# history extraction in production)
# ════════════════════════════════════════════════════════════════════════

def generate_synthetic_dataset(
    n_samples: int, seed: int,
) -> List[Tuple[CandidateFinding, DiscrepancySeverity, bool]]:
    """Generate (candidate, label_severity, is_true_discrepancy)
    triples for training.

    In production this function is replaced with extraction of
    historical examiner adjudications from cbs_data or an
    external adjudication store. Each historical finding becomes
    one training row: (features, label_severity, was_truly_
    discrepant_per_examiner).
    """
    rng = random.Random(seed)
    eng = TradeFinanceDocumentCheckingEngine()
    samples: List[
        Tuple[CandidateFinding, DiscrepancySeverity, bool]] = []

    # Build a varied synthetic dataset by perturbing presentations
    # in known ways and capturing the candidates the rules emit.
    for i in range(n_samples):
        amount = Decimal(rng.randint(100_000, 50_000_000))
        tolerance = Decimal(
            str(rng.choice([0.05, 0.10, 0.15])))
        days_offset = rng.randint(-30, 30)
        expiry = date(2026, 7, 1)
        from datetime import timedelta
        pres_date = expiry + timedelta(days=days_offset)

        # Random invoice amount — sometimes within, sometimes not
        amt_perturbation = rng.choice(
            [0.95, 1.0, 1.05, 1.20, 0.7])
        invoice_amount = (
            amount * Decimal(str(amt_perturbation))
        ).quantize(Decimal("0.01"))

        lc = LCTerms(
            lc_reference=f"LC-SYN-{i:05d}",
            amount_kes=amount, currency="USD",
            expiry_date=expiry,
            latest_shipment_date=date(2026, 6, 15),
            amount_tolerance_pct=tolerance,
            description_of_goods=rng.choice([
                "milled rice grade A",
                "industrial steel coils",
                "solar panel components",
                "pharmaceutical raw materials"]),
            required_documents=(
                DocumentType.COMMERCIAL_INVOICE,
                DocumentType.BILL_OF_LADING))

        invoice = PresentedDocument(
            document_type=DocumentType.COMMERCIAL_INVOICE,
            issuer="SyntheticBeneficiary",
            amount_kes=invoice_amount, currency="USD",
            issue_date=date(2026, 6, 1),
            description_of_goods=lc.description_of_goods)
        bl = PresentedDocument(
            document_type=DocumentType.BILL_OF_LADING,
            issuer="SyntheticCarrier",
            shipment_date=date(
                2026, 6, rng.choice([1, 5, 10, 14, 16, 20])))

        pres = DocumentPresentation(
            presentation_id=f"PR-SYN-{i:05d}",
            lc_reference=lc.lc_reference,
            presentation_date=pres_date,
            documents=(invoice, bl))

        # Run checks to collect candidates
        candidates = []
        candidates.extend(
            eng.check_amount_tolerance(lc, pres))
        candidates.extend(
            eng.check_dates_and_periods(lc, pres))
        candidates.extend(
            eng.check_required_documents_present(lc, pres))
        candidates.extend(
            eng.check_cross_document_consistency(lc, pres))

        # Synthetic labeling — for pipeline validation only.
        # In production these labels come from operator
        # adjudication outcomes.
        for cand in candidates:
            # Synthetic rule: keep rule-assigned severity but
            # flip 5% of cases as "false positive" to give the
            # classifier something to learn beyond pure
            # severity passthrough
            is_true_disc = rng.random() > 0.05
            samples.append(
                (cand, cand.rule_assigned_severity,
                 is_true_disc))

    return samples


# ════════════════════════════════════════════════════════════════════════
# Stage 2 — Feature engineering
# ════════════════════════════════════════════════════════════════════════

# Stable feature ordering — frozen at training time so inference
# uses the exact same feature vector layout
FEATURE_NAMES: Tuple[str, ...] = (
    # one-hot category
    "cat_AMOUNT_TOLERANCE", "cat_EXPIRY", "cat_LATE_SHIPMENT",
    "cat_PRESENTATION_PERIOD", "cat_PORT_LOADING",
    "cat_PORT_DISCHARGE", "cat_DESCRIPTION_OF_GOODS",
    "cat_MISSING_DOCUMENT", "cat_CROSS_DOCUMENT_AMOUNT",
    "cat_CROSS_DOCUMENT_CURRENCY", "cat_CROSS_DOCUMENT_PORT",
    "cat_CROSS_DOCUMENT_DESCRIPTION",
    "cat_MISSING_REQUIRED_FIELD",
    # one-hot rule severity (the engine's initial guess)
    "rule_sev_CRITICAL", "rule_sev_HIGH", "rule_sev_MEDIUM",
    "rule_sev_LOW", "rule_sev_INFO",
    # numeric feature_hints (when present, else 0)
    "hint_days_late", "hint_amount_ratio",
    "hint_overlap_pct", "hint_distinct_count",
)


def encode_features(
    candidate: CandidateFinding,
) -> List[float]:
    """Convert a CandidateFinding to numeric feature vector.

    Ordering matches FEATURE_NAMES exactly. Inference must use
    this same function so vectors are consistent.
    """
    vec = [0.0] * len(FEATURE_NAMES)
    idx = {name: i for i, name in enumerate(FEATURE_NAMES)}

    cat_key = f"cat_{candidate.category.value}"
    if cat_key in idx:
        vec[idx[cat_key]] = 1.0

    sev_key = (
        f"rule_sev_{candidate.rule_assigned_severity.value}")
    if sev_key in idx:
        vec[idx[sev_key]] = 1.0

    # Numeric hints — parse safely
    hints = candidate.feature_hints or {}
    try:
        if "days_late" in hints:
            vec[idx["hint_days_late"]] = float(
                hints["days_late"])
    except (ValueError, KeyError):
        pass
    try:
        if "ratio" in hints:
            vec[idx["hint_amount_ratio"]] = float(hints["ratio"])
    except (ValueError, KeyError):
        pass
    try:
        if "overlap_pct" in hints:
            vec[idx["hint_overlap_pct"]] = float(
                hints["overlap_pct"])
    except (ValueError, KeyError):
        pass
    try:
        for k in (
            "distinct_currency_count", "distinct_port_count"
        ):
            if k in hints:
                vec[idx["hint_distinct_count"]] = float(hints[k])
                break
    except (ValueError, KeyError):
        pass

    return vec


SEVERITY_LABEL_ORDER: Tuple[str, ...] = (
    "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")


def severity_to_label(s: DiscrepancySeverity) -> int:
    return SEVERITY_LABEL_ORDER.index(s.value)


def label_to_severity(label: int) -> DiscrepancySeverity:
    return DiscrepancySeverity(SEVERITY_LABEL_ORDER[label])


# ════════════════════════════════════════════════════════════════════════
# Stage 4 — Stratified train/test split
# ════════════════════════════════════════════════════════════════════════

def stratified_split(
    samples: List[
        Tuple[CandidateFinding, DiscrepancySeverity, bool]],
    test_fraction: float, seed: int,
) -> Tuple[
    List[Tuple[CandidateFinding, DiscrepancySeverity, bool]],
    List[Tuple[CandidateFinding, DiscrepancySeverity, bool]]]:
    """Stratified split by severity label."""
    rng = random.Random(seed)
    by_label: Dict[
        DiscrepancySeverity,
        List[Tuple[CandidateFinding, DiscrepancySeverity, bool]]
    ] = {}
    for s in samples:
        by_label.setdefault(s[1], []).append(s)
    train: List[
        Tuple[CandidateFinding, DiscrepancySeverity, bool]] = []
    test: List[
        Tuple[CandidateFinding, DiscrepancySeverity, bool]] = []
    for label, group in by_label.items():
        rng.shuffle(group)
        n_test = max(1, int(len(group) * test_fraction))
        test.extend(group[:n_test])
        train.extend(group[n_test:])
    rng.shuffle(train)
    rng.shuffle(test)
    return train, test


# ════════════════════════════════════════════════════════════════════════
# Stages 5 + 6 — Training + evaluation (sklearn-based)
# ════════════════════════════════════════════════════════════════════════

def train_and_evaluate(
    train_samples, test_samples, random_seed: int,
):
    """Train sklearn LogisticRegression + evaluate on test set.

    Returns (trained_model, metrics_dict). Defers sklearn imports
    so the script header / argparse work even when sklearn is
    unavailable (clean error message instead of ImportError on
    import).
    """
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import (
            accuracy_score, precision_score, recall_score,
            f1_score, confusion_matrix)
    except ImportError as e:
        print(
            f"[train_and_evaluate] sklearn / numpy not "
            f"available: {e}",
            file=sys.stderr)
        print(
            "  Install training dependencies: pip install "
            "-r requirements-ml.txt",
            file=sys.stderr)
        raise SystemExit(2)

    X_train = np.array([
        encode_features(s[0]) for s in train_samples])
    y_train = np.array([
        severity_to_label(s[1]) for s in train_samples])
    X_test = np.array([
        encode_features(s[0]) for s in test_samples])
    y_test = np.array([
        severity_to_label(s[1]) for s in test_samples])

    print(
        f"  Training set: {X_train.shape[0]} samples × "
        f"{X_train.shape[1]} features")
    print(f"  Test set: {X_test.shape[0]} samples")

    model = LogisticRegression(
        max_iter=1000, random_state=random_seed,
        solver="lbfgs")
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision_macro": float(
            precision_score(
                y_test, y_pred,
                average="macro", zero_division=0)),
        "recall_macro": float(
            recall_score(
                y_test, y_pred,
                average="macro", zero_division=0)),
        "f1_macro": float(
            f1_score(
                y_test, y_pred,
                average="macro", zero_division=0)),
        "confusion_matrix": confusion_matrix(
            y_test, y_pred,
            labels=list(range(len(SEVERITY_LABEL_ORDER)))
        ).tolist(),
        "label_order": list(SEVERITY_LABEL_ORDER),
        "n_train": int(X_train.shape[0]),
        "n_test": int(X_test.shape[0]),
    }

    # Bootstrap confidence interval on accuracy
    rng = np.random.default_rng(seed=random_seed)
    n_bootstrap = 1000
    boot_accs = []
    for _ in range(n_bootstrap):
        idx = rng.integers(
            0, len(y_test), size=len(y_test))
        boot_accs.append(
            accuracy_score(y_test[idx], y_pred[idx]))
    metrics["accuracy_ci_95_lower"] = float(
        np.quantile(boot_accs, 0.025))
    metrics["accuracy_ci_95_upper"] = float(
        np.quantile(boot_accs, 0.975))

    return model, metrics


# ════════════════════════════════════════════════════════════════════════
# Stage 7 — Persistence
# ════════════════════════════════════════════════════════════════════════

def persist_model(
    model, metrics: dict,
    output_dir: Path, version: int, random_seed: int,
    n_samples: int,
) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / f"model_v{version}.pkl"
    metadata_path = output_dir / f"metadata_v{version}.json"

    with model_path.open("wb") as f:
        pickle.dump(model, f)

    # Compute model artifact hash for integrity checks
    model_bytes = model_path.read_bytes()
    model_hash = hashlib.sha256(model_bytes).hexdigest()

    try:
        import sklearn
        sklearn_version = sklearn.__version__
    except ImportError:
        sklearn_version = "unavailable"

    metadata = {
        "model_version": f"v{version}",
        "training_date": (
            datetime.utcnow().isoformat() + "Z"),
        "random_seed": random_seed,
        "n_samples_total": n_samples,
        "metrics": metrics,
        "feature_names": list(FEATURE_NAMES),
        "label_order": list(SEVERITY_LABEL_ORDER),
        "model_artifact_sha256": model_hash,
        "sklearn_version": sklearn_version,
        "data_source": (
            "SYNTHETIC — generated by "
            "scripts/training/train_document_classifier.py "
            "for pipeline validation only. NOT trained on "
            "real adjudication data. Production deployment "
            "requires retraining on operator adjudication "
            "history."),
        "engine_target": (
            "utils.trade_finance_document_checking."
            "TradeFinanceDocumentCheckingEngine "
            "(ml_discrepancy_classifier hook per v10.76 "
            "contract)"),
        "framework_refs": [
            "ENH-270 §classify_finding (ML hook)",
            "v10.76 ML extension contract",
            "Per Rule 6 — ml_disabled flag continues to "
            "surface synthetic-trained status to operators",
            "Per Rule 7 — engine never auto-acts on ML "
            "predictions",
        ],
    }
    with metadata_path.open("w") as f:
        json.dump(metadata, f, indent=2)

    return model_path, metadata_path


# ════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "ENH-270 reference ML training pipeline for "
            "document classifier (synthetic data only — "
            "demonstrates pipeline shape, not production "
            "accuracy)"))
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("data/models/document_classifier"),
        help="Where to write model.pkl + metadata.json")
    parser.add_argument(
        "--random-seed", type=int, default=42,
        help="Deterministic seed for reproducibility")
    parser.add_argument(
        "--test-fraction", type=float, default=0.2,
        help="Held-out test set fraction (stratified)")
    parser.add_argument(
        "--n-samples", type=int, default=2000,
        help="Number of synthetic LCs to generate "
             "(each yields ~1-3 candidate findings)")
    parser.add_argument(
        "--version", type=int, default=1,
        help="Model version number (suffixes output files)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Skip persistence; print metrics only")
    args = parser.parse_args()

    print(
        "▶ Stage 1: Generating synthetic dataset "
        f"({args.n_samples} LCs)")
    samples = generate_synthetic_dataset(
        args.n_samples, args.random_seed)
    print(f"  → {len(samples)} candidate findings extracted")
    if not samples:
        print(
            "  ERROR: no candidates generated — perturbation "
            "config too tight; widen --n-samples or check "
            "synthetic data generator",
            file=sys.stderr)
        return 1

    # Distribution check
    from collections import Counter
    dist = Counter(s[1].value for s in samples)
    print("  Severity distribution:")
    for sev in SEVERITY_LABEL_ORDER:
        print(f"    {sev}: {dist.get(sev, 0)}")

    print(
        f"\n▶ Stage 4: Stratified train/test split "
        f"({1 - args.test_fraction:.0%}/"
        f"{args.test_fraction:.0%}, seed={args.random_seed})")
    train_samples, test_samples = stratified_split(
        samples, args.test_fraction, args.random_seed)
    print(
        f"  → train={len(train_samples)}, "
        f"test={len(test_samples)}")

    print(
        f"\n▶ Stages 5+6: Training + evaluation "
        "(sklearn LogisticRegression baseline)")
    model, metrics = train_and_evaluate(
        train_samples, test_samples, args.random_seed)
    print(f"  Test accuracy: {metrics['accuracy']:.4f}")
    print(
        f"  95% CI: [{metrics['accuracy_ci_95_lower']:.4f}, "
        f"{metrics['accuracy_ci_95_upper']:.4f}]")
    print(f"  F1 (macro): {metrics['f1_macro']:.4f}")
    print(f"  Precision (macro): {metrics['precision_macro']:.4f}")
    print(f"  Recall (macro): {metrics['recall_macro']:.4f}")

    if args.dry_run:
        print(
            "\n▶ Stage 7 SKIPPED (--dry-run): no artifacts "
            "written")
        return 0

    print(f"\n▶ Stage 7: Persisting to {args.output_dir}")
    model_path, metadata_path = persist_model(
        model, metrics, args.output_dir, args.version,
        args.random_seed, len(samples))
    print(f"  → {model_path}")
    print(f"  → {metadata_path}")

    print(
        "\n▶ Done. Model is SYNTHETIC-TRAINED — operators must "
        "treat predictions as demonstration-grade. ml_disabled "
        "flag continues to surface this in every prediction "
        "per the v10.76 contract until a model is retrained on "
        "real adjudication data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
