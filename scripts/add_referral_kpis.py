#!/usr/bin/env python3
"""
add_referral_kpis.py  —  adds the two referral SHADOW KPIs to kpi_library.json.

Backup-first, idempotent (skips if K238/K239 already present). These are the
referrer-recognition KPIs on the Financial pillar; flagged shadow:true so they
credit the referrer's own scorecard WITHOUT feeding the consolidated P&L (the
owner's scorecard carries the P&L figure — no double count).

Run:
    python scripts\\add_referral_kpis.py            (apply)
    python scripts\\add_referral_kpis.py --dry-run
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.core import DATA_DIR  # noqa: E402

NEW_KPIS = [
    {
        "id": "K238", "name": "Asset Referral", "pillar": "Financial",
        "weight": 0.0, "unit": "KES", "direction": "higher", "cbk_ref": "",
        "active": True, "shadow": True,
        "description": ("Value of asset (lending) deals the staff referred that "
                        "materialized. Shadow / recognition only — credited to the "
                        "referrer; does NOT feed consolidated P&L."),
        "source": "referral_shadow", "_origin": "v10.5xx_referral_shadow_credit",
    },
    {
        "id": "K239", "name": "Liabilities/Deposit Referral", "pillar": "Financial",
        "weight": 0.0, "unit": "KES", "direction": "higher", "cbk_ref": "",
        "active": True, "shadow": True,
        "description": ("Value of liability (deposit) deals the staff referred that "
                        "materialized. Shadow / recognition only — credited to the "
                        "referrer; does NOT feed consolidated P&L."),
        "source": "referral_shadow", "_origin": "v10.5xx_referral_shadow_credit",
    },
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    f = DATA_DIR / "kpi_library.json"
    lib = json.loads(f.read_text())
    kpis = lib.get("kpis")
    if not isinstance(kpis, list):
        raise SystemExit("kpi_library.json has no 'kpis' list — aborting.")

    existing = {k.get("id") for k in kpis if isinstance(k, dict)}
    to_add = [k for k in NEW_KPIS if k["id"] not in existing]

    print(f"existing KPIs: {len(kpis)}")
    print(f"to add: {[k['id'] + ' (' + k['name'] + ')' for k in to_add] or 'none — already present'}")
    if not to_add:
        print("Nothing to do.")
        return
    if args.dry_run:
        print("\n--dry-run: would append:")
        print(json.dumps(to_add, indent=2))
        return

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    (DATA_DIR / f"kpi_library.json.pre-referralkpis-{ts}").write_text(f.read_text())
    print(f"backup -> kpi_library.json.pre-referralkpis-{ts}")

    kpis.extend(to_add)
    lib["kpis"] = kpis
    f.write_text(json.dumps(lib, indent=2))
    print(f"\nDone. KPIs now: {len(kpis)}. Restart the API to pick up the library.")


if __name__ == "__main__":
    main()
