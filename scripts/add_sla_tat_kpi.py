#!/usr/bin/env python3
"""
add_sla_tat_kpi.py  —  adds the SLA_CREDIT_TAT SHADOW KPI to kpi_library.json.

Backup-first, idempotent (skips if SLA_CREDIT_TAT already present). This is the
SLA-clock-derived Credit TAT on the Operational Excellence pillar, flagged
shadow:true / weight 0.0 so it is VISIBLE and validatable next to K011 and the
credit_engine lane TATs WITHOUT moving any appraisal score. Promotion to a
weighted KPI (repointing K011 / the lanes at this source) is a later, deliberate
step once the SLA-derived numbers are validated.

Run:
    python scripts\\add_sla_tat_kpi.py            (apply)
    python scripts\\add_sla_tat_kpi.py --dry-run
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.core import DATA_DIR  # noqa: E402

NEW_KPI = {
    "id": "SLA_CREDIT_TAT",
    "name": "Credit TAT (SLA clock, days)",
    "pillar": "Operational Excellence",
    "weight": 0.0,
    "unit": "Days",
    "direction": "lower",
    "cbk_ref": "",
    "active": True,
    "shadow": True,
    "description": (
        "Mean business-day credit turnaround per staff, derived from the "
        "pipeline SLA clocks (credit_assessment -> disbursement/"
        "security_perfection on deal.sla_step_log). Shadow / validation only — "
        "weight 0, does not affect appraisal scores. Source for the eventual "
        "promotion of K011 / the credit lane TATs."
    ),
    "source": "sla_clock",
    "_origin": "S4a_sla_tat_shadow",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    f = DATA_DIR / "kpi_library.json"
    if not f.exists():
        raise SystemExit(f"{f} not found — aborting.")
    lib = json.loads(f.read_text(encoding="utf-8"))
    kpis = lib.get("kpis")
    if not isinstance(kpis, list):
        raise SystemExit("kpi_library.json has no 'kpis' list — aborting.")

    if any(isinstance(k, dict) and k.get("id") == NEW_KPI["id"] for k in kpis):
        print(f"[skip] {NEW_KPI['id']} already present — no change.")
        return

    if args.dry_run:
        print(f"[dry-run] would add {NEW_KPI['id']} ({NEW_KPI['name']}) "
              f"to {f} ({len(kpis)} -> {len(kpis)+1} KPIs)")
        return

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f.with_suffix(f".json.pre_sla_tat_{stamp}")
    backup.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[backup] {backup}")

    kpis.append(NEW_KPI)
    f.write_text(json.dumps(lib, indent=2), encoding="utf-8")
    print(f"[ok] added {NEW_KPI['id']} — library now {len(kpis)} KPIs.")


if __name__ == "__main__":
    main()
