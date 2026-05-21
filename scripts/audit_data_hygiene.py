"""scripts/audit_data_hygiene.py — v10.320 data hygiene audit.

Comprehensive report on weight + bank-target health across the
system. Run anytime: it doesn't modify any data, only reports.

Usage:
    python scripts/audit_data_hygiene.py
    python scripts/audit_data_hygiene.py --role Teller
    python scripts/audit_data_hygiene.py --bank-targets-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.bsc_score_computation import (
    resolve_role_kpis,
    validate_role_weights,
)
from utils.db import db


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def audit_all_role_weights() -> dict:
    """Audit weight sums across every role in users.json +
    role_kpis."""
    users = db.load_json(DATA_DIR / "users.json", default={}) or {}
    lib = db.load_json(DATA_DIR / "kpi_library.json",
                        default={}) or {}
    user_roles = {
        u.get("role") for u in users.values()
        if isinstance(u, dict) and u.get("role")
    }
    library_roles = set(lib.get("role_kpis", {}).keys())
    all_roles = sorted(user_roles | library_roles)

    bucket: dict = {
        "underweighted": [],     # sum < 0.95
        "balanced": [],           # 0.95 ≤ sum ≤ 1.05
        "overweighted": [],       # sum > 1.05
        "empty": [],              # sum = 0 (no defined KPIs)
    }

    for role in all_roles:
        val = validate_role_weights(role)
        tw = val["total_weight"]
        if tw == 0:
            bucket["empty"].append((role, val))
        elif tw < 0.95:
            bucket["underweighted"].append((role, val))
        elif tw > 1.05:
            bucket["overweighted"].append((role, val))
        else:
            bucket["balanced"].append((role, val))

    return {
        "all_roles": all_roles,
        "buckets": bucket,
        "stats": {
            "total_roles": len(all_roles),
            "empty_count": len(bucket["empty"]),
            "underweighted_count": len(bucket["underweighted"]),
            "balanced_count": len(bucket["balanced"]),
            "overweighted_count": len(bucket["overweighted"]),
        },
    }


def audit_bank_targets() -> dict:
    """Audit bank_targets.json for scale plausibility against
    kpi_library + actuals data when available.

    The heuristic compares the bank target against the actual
    value range observed in bsc_actuals files. If actuals exist
    and the target is in a different scale range, that's a
    high-confidence finding.
    """
    bt = db.load_json(DATA_DIR / "bank_targets.json",
                       default={}) or {}
    lib = db.load_json(DATA_DIR / "kpi_library.json",
                        default={}) or {}
    kpis_by_id = {
        k.get("id"): k for k in lib.get("kpis", [])
        if isinstance(k, dict) and k.get("id")
    }

    # Collect actuals ranges per KPI (across all v10.317-shipped
    # periods) for cross-checking against bank targets
    actuals_by_kpi: dict = {}
    for actuals_file in DATA_DIR.glob("bsc_actuals_*.json"):
        try:
            records = db.load_json(actuals_file,
                                     default=[]) or []
            if not isinstance(records, list):
                continue
            for rec in records:
                kpi = rec.get("kpi_id") or rec.get("kpi")
                val = rec.get("value") or rec.get("actual")
                if kpi and val is not None:
                    try:
                        v = float(val)
                        actuals_by_kpi.setdefault(
                            kpi, []).append(v)
                    except (ValueError, TypeError):
                        pass
        except Exception:  # noqa: BLE001
            pass

    findings: list = []
    for key, entry in bt.items():
        if "|" not in key:
            continue
        kpi_id = key.rsplit("|", 1)[0]
        target = (
            entry.get("target") if isinstance(entry, dict)
            else entry
        )
        if not isinstance(target, (int, float)):
            continue

        kpi_def = kpis_by_id.get(kpi_id, {})
        unit = kpi_def.get("unit", "")

        # Cross-check against actuals if we have any
        if kpi_id in actuals_by_kpi:
            actuals = actuals_by_kpi[kpi_id]
            actuals_max = max(actuals)
            actuals_min = min(actuals)
            # If actuals are 0-100 range but target is <10,
            # that's a clear mismatch
            if (actuals_max > 20 and target < 10 and
                    target > 0):
                findings.append({
                    "kpi": kpi_id,
                    "key": key,
                    "target": target,
                    "unit": unit,
                    "severity": "high",
                    "reason": (
                        f"actuals range {actuals_min:.1f}-"
                        f"{actuals_max:.1f} but target={target} "
                        f"— scale mismatch"
                    ),
                    "actuals_range": (
                        actuals_min, actuals_max),
                })
            # If target is on 1-5 scale but actuals are 0-100
            elif (actuals_max > 20 and 1 <= target <= 5):
                findings.append({
                    "kpi": kpi_id,
                    "key": key,
                    "target": target,
                    "unit": unit,
                    "severity": "high",
                    "reason": (
                        f"target={target} looks like 1-5 scale "
                        f"but actuals max={actuals_max:.1f}"
                    ),
                    "actuals_range": (
                        actuals_min, actuals_max),
                })

    return {
        "total_targets": len(bt),
        "findings": findings,
        "high_severity_count": sum(
            1 for f in findings if f["severity"] == "high"),
        "actuals_kpis_coverage": len(actuals_by_kpi),
    }


def print_report() -> int:
    """Print full report and return non-zero exit code if
    critical issues exist."""
    print("═" * 70)
    print(" A2Z MIS 360 — Data Hygiene Audit (v10.320)")
    print("═" * 70)

    # Role weights
    rw = audit_all_role_weights()
    s = rw["stats"]
    print(f"\n■ Role weight audit ({s['total_roles']} roles)")
    print(f"   ✓ Balanced (95-105%):  {s['balanced_count']}")
    print(f"   ⬇ Underweighted (<95%):{s['underweighted_count']}")
    print(f"   ⬆ Overweighted (>105%):{s['overweighted_count']}")
    print(f"   ∅ Empty (0%):          {s['empty_count']}")

    if rw["buckets"]["overweighted"]:
        print(f"\n   Top 5 overweighted:")
        for role, val in sorted(
            rw["buckets"]["overweighted"],
            key=lambda r: -abs(r[1]["deviation_from_100"]),
        )[:5]:
            print(
                f"     {role:<42s} "
                f"sum={val['total_weight']:.2f} "
                f"({val['deviation_from_100']:+.0f}pp)"
            )

    if rw["buckets"]["empty"]:
        print(f"\n   Top 5 with empty weights (KPIs assigned but "
               f"none defined):")
        for role, val in rw["buckets"]["empty"][:5]:
            print(
                f"     {role:<42s} "
                f"KPIs={val['kpi_count']}, "
                f"undefined={val['undefined_count']}"
            )

    # Bank targets
    bt = audit_bank_targets()
    print(
        f"\n■ Bank target sanity ({bt['total_targets']} entries)"
    )
    print(f"   Findings: {len(bt['findings'])} "
           f"({bt['high_severity_count']} high severity)")
    for f in bt["findings"]:
        sev = "🔴" if f["severity"] == "high" else "🟡"
        print(
            f"   {sev} {f['kpi']:<35s} "
            f"target={f['target']:<15} "
            f"unit={f['unit']:<8s} ← {f['reason']}"
        )

    # Exit code
    critical = bt["high_severity_count"]
    if critical > 0:
        print(
            f"\n✗ {critical} HIGH-severity bank target issues "
            f"detected"
        )
    else:
        print(f"\n✓ No HIGH-severity bank target issues")

    print("═" * 70)
    return 0 if critical == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role")
    parser.add_argument("--bank-targets-only", action="store_true")
    args = parser.parse_args()

    if args.role:
        val = validate_role_weights(args.role)
        print(f"Role: {val['role']}")
        for k, v in val.items():
            if k != "normalized_weights":
                print(f"  {k}: {v}")
        return 0

    if args.bank_targets_only:
        bt = audit_bank_targets()
        for f in bt["findings"]:
            print(
                f"  {f['severity']:<6s} {f['kpi']}: "
                f"{f['reason']}"
            )
        return 0 if bt["high_severity_count"] == 0 else 1

    return print_report()


if __name__ == "__main__":
    sys.exit(main())
