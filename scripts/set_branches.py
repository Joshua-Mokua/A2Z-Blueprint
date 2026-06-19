#!/usr/bin/env python3
"""
set_branches.py — restructure org_config.json to the 16 live branches + HO shell.

Backup-first, idempotent (always writes the canonical set, so re-running is safe).
Geographic `region` / `region_group` drive CBS realism + analytics drills; the
two area-manager regions (Region 1 led from Towers, Region 2 led from Kisumu) are
held in the new `area` / `area_name` / `is_area_lead` fields — additive, so nothing
that reads region/region_group today breaks. P50 Head Office is flagged a shell
(is_head_office, no area) and carries no sales structure.

Run:
    python scripts\\set_branches.py --dry-run
    python scripts\\set_branches.py
"""
import argparse, datetime, json, sys
from pathlib import Path

# DATA_DIR mirrors utils.core (project_root/data) without importing core,
# which pulls in streamlit + side effects.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

R1, R2 = "Region 1", "Region 2"
R1_NAME, R2_NAME = "Nairobi Region", "Upcountry Region"

# (branch_code, name, geo_region, area, is_area_lead)
SPEC = [
    ("P01", "Towers",              "Nairobi",     R1, True),
    ("P03", "Plaza",               "Nairobi",     R1, False),
    ("P11", "Industrial Area",     "Nairobi",     R1, False),
    ("P13", "Westlands",           "Nairobi",     R1, False),
    ("P22", "Upper Hill",          "Nairobi",     R1, False),
    ("P23", "Valley Arcade",       "Nairobi",     R1, False),
    ("P24", "Karen",               "Nairobi",     R1, False),
    ("P30", "Fortis Office Park",  "Nairobi",     R1, False),
    ("P02", "Mombasa Moi Avenue",  "Coastal",     R2, False),
    ("P06", "Thika",               "Central",     R2, False),
    ("P07", "Eldoret",             "Rift Valley", R2, False),
    ("P08", "Kisumu",              "Nyanza",      R2, True),
    ("P09", "Kisii",               "Nyanza",      R2, False),
    ("P12", "Karatina",            "Central",     R2, False),
    ("P15", "Nakuru",              "Rift Valley", R2, False),
    ("P17", "Nyeri",               "Central",     R2, False),
]
AREA_NAME = {R1: R1_NAME, R2: R2_NAME}
AREA_LEAD_BRANCH = {R1: "P01", R2: "P08"}


def build_branches():
    out = []
    for code, name, region, area, lead in SPEC:
        out.append({
            "id": code, "name": name, "region": region, "region_group": region,
            "active": True, "branch_code": code, "dept_id": "retail",
            "opened_date": "2010-01-01",
            "area": area, "area_name": AREA_NAME[area],
            "area_lead_branch": AREA_LEAD_BRANCH[area],
            "is_area_lead": lead,
        })
    # Head Office shell — defined, flagged, no area / no sales structure
    out.append({
        "id": "P50", "name": "Head Office", "region": "Nairobi",
        "region_group": "Nairobi", "active": True, "branch_code": "P50",
        "dept_id": "head_office", "opened_date": "2010-01-01",
        "area": None, "area_name": None, "area_lead_branch": None,
        "is_area_lead": False, "is_head_office": True, "is_shell": True,
    })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    f = DATA_DIR / "org_config.json"
    cfg = json.loads(f.read_text(encoding="utf-8"))
    old_n = len(cfg.get("branches", []))
    new_branches = build_branches()

    print(f"org_config branches: {old_n} -> {len(new_branches)} "
          f"(16 live + Head Office shell)")
    if args.dry_run:
        print("[dry-run] no write. Region 1 (Towers-led):",
              [b["branch_code"] for b in new_branches if b.get("area") == R1])
        print("[dry-run] Region 2 (Kisumu-led):",
              [b["branch_code"] for b in new_branches if b.get("area") == R2])
        return

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f.with_suffix(f".json.pre_branch16_{stamp}")
    backup.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[backup] {backup}")

    cfg["branches"] = new_branches
    # keep the geographic region list coherent with the surviving branches
    cfg["regions"] = sorted({b["region"] for b in new_branches})
    f.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"[ok] org_config.json now carries {len(new_branches)} branches.")


if __name__ == "__main__":
    main()
