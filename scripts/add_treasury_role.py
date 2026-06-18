#!/usr/bin/env python3
"""
add_treasury_role.py — register "Treasury Back Office" (Troops) as a first-class
role in the registry, and grant it the disbursement capability.

Backup-first, idempotent. Two additive edits:
  1. kpi_library.json -> role_kpis["Treasury Back Office"] = <starter ops KPIs>
     (only if absent). Starter set is intentionally small; KPI/weight tuning is a
     later pass once the mixed-identifier refs are reconciled.
  2. pipeline_settings.json -> disbursement_roles includes "Treasury Back Office"
     (so the role registry + _is_troops read it explicitly rather than relying on
     the in-code default).

Run:
    python scripts\\add_treasury_role.py            (apply)
    python scripts\\add_treasury_role.py --dry-run
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.core import DATA_DIR  # noqa: E402

ROLE = "Treasury Back Office"
# Operational starter set (best-effort refs that exist in the library/soup).
STARTER_KPIS = ["COMPLIANCE", "DILIGENCE", "SLA_SCORE"]


def _ts():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    ts = _ts()

    # 1) role_kpis in kpi_library.json
    klf = DATA_DIR / "kpi_library.json"
    lib = json.loads(klf.read_text())
    role_kpis = lib.setdefault("role_kpis", {})
    role_present = ROLE in role_kpis
    print(f"kpi_library role_kpis: {len(role_kpis)} roles | '{ROLE}' present: {role_present}")

    # 2) disbursement_roles in pipeline_settings.json
    psf = DATA_DIR / "pipeline_settings.json"
    settings = json.loads(psf.read_text()) if psf.exists() else {}
    disb = settings.get("disbursement_roles")
    if not isinstance(disb, list):
        disb = []
    disb_present = any(str(r).strip().lower() == ROLE.lower() for r in disb)
    print(f"pipeline_settings disbursement_roles: {disb or '(default)'} | '{ROLE}' present: {disb_present}")

    if role_present and disb_present:
        print("Nothing to do — already registered.")
        return
    if args.dry_run:
        print("\n--dry-run: would")
        if not role_present:
            print(f"  + add role_kpis['{ROLE}'] = {STARTER_KPIS}")
        if not disb_present:
            print(f"  + add '{ROLE}' to disbursement_roles")
        return

    if not role_present:
        (DATA_DIR / f"kpi_library.json.pre-treasuryrole-{ts}").write_text(klf.read_text())
        role_kpis[ROLE] = list(STARTER_KPIS)
        lib["role_kpis"] = role_kpis
        klf.write_text(json.dumps(lib, indent=2))
        print(f"role_kpis['{ROLE}'] added (backup .pre-treasuryrole-{ts})")

    if not disb_present:
        if psf.exists():
            (DATA_DIR / f"pipeline_settings.json.pre-treasuryrole-{ts}").write_text(psf.read_text())
        disb.append(ROLE)
        settings["disbursement_roles"] = disb
        psf.write_text(json.dumps(settings, indent=2))
        print(f"disbursement_roles now: {disb}")

    print("\nDone. Restart the API to pick up the registry change.")


if __name__ == "__main__":
    main()
