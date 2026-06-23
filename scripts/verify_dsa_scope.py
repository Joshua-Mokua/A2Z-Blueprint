"""
verify_dsa_scope.py — prove the DSA-hierarchy scope fix (A3).

Feeds DSA-role user_data into get_visible_staff and checks the returned subtree:
  - Regional DSA Head sees ONLY their region's DSA spine (region-scoped).
  - Branch DSA Team Lead sees ONLY their branch's DSAs (unit-scoped).
  - A DSA sees ~self.
  - Regional DSA Head's set is a strict SUBSET of DSA Head's (bank-wide spine).

Run after the core.py / core_audit.py scope fix + an org_config region map.
  python scripts/verify_dsa_scope.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.core_audit import get_visible_staff  # noqa: E402
from utils.api_pipeline_scope import get_staff_roster  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond, note=""):
    global PASS, FAIL
    ok = bool(cond)
    PASS += ok
    FAIL += (not ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  :: {note}" if note else ""))


def first_staff(roster, role, region=None, unit=None):
    df = roster[roster["Role"].astype(str).str.strip().str.lower() == role.lower()]
    if region is not None and "Region" in df.columns:
        df = df[df["Region"].astype(str).str.strip().str.lower() == region.lower()]
    if unit is not None and "Unit" in df.columns:
        df = df[df["Unit"].astype(str).str.strip().str.lower() == unit.lower()]
    if len(df) == 0:
        return None
    r = df.iloc[0]
    return {
        "staff_code": str(r.get("Staff Code", "")),
        "full_name": str(r.get("Staff Name", "")),
        "name": str(r.get("Staff Name", "")),
        "role": str(r.get("Role", "")),
        "unit": str(r.get("Unit", "")),
        "region": str(r.get("Region", "")),
    }


def main():
    roster = get_staff_roster()
    if roster is None or len(roster) == 0:
        print("!! no roster available — run on the live machine")
        sys.exit(2)

    print(f"roster: {len(roster)} staff\n")

    # Pick a Regional DSA Head and resolve their region.
    rdh = first_staff(roster, "Regional DSA Head")
    if not rdh:
        print("!! no Regional DSA Head in roster"); sys.exit(1)
    region = rdh["region"]
    print(f"Regional DSA Head: {rdh['full_name']} ({rdh['staff_code']}) region={region!r}\n")

    # 1) Regional DSA Head visibility is region-scoped.
    vis_rdh = get_visible_staff(rdh, roster)
    rdh_regions = set(vis_rdh["Region"].astype(str).str.strip()) if len(vis_rdh) else set()
    check("Regional DSA Head sees only their region",
          rdh_regions <= {region} and len(vis_rdh) > 0,
          note=f"{len(vis_rdh)} staff; regions={rdh_regions}")
    rdh_roles = set(vis_rdh["Role"].astype(str).str.strip()) if len(vis_rdh) else set()
    check("Regional DSA Head sees only DSA-spine roles",
          rdh_roles <= {"Regional DSA Head", "Branch DSA Team Lead", "Direct Sales Agent"},
          note=f"roles={rdh_roles}")

    # 2) DSA Head (bank-wide spine) — Regional DSA Head must be a strict subset.
    dsah = first_staff(roster, "DSA Head")
    if dsah:
        vis_dsah = get_visible_staff(dsah, roster)
        rdh_codes = set(vis_rdh["Staff Code"].astype(str))
        dsah_codes = set(vis_dsah["Staff Code"].astype(str))
        check("Regional DSA Head subtree ⊆ DSA Head subtree",
              rdh_codes <= dsah_codes and len(rdh_codes) < len(dsah_codes),
              note=f"RDH={len(rdh_codes)} <= DSAHead={len(dsah_codes)}")

    # 3) Branch DSA Team Lead is unit-scoped.
    btl = first_staff(roster, "Branch DSA Team Lead")
    if btl:
        vis_btl = get_visible_staff(btl, roster)
        btl_units = set(vis_btl["Unit"].astype(str).str.strip()) if len(vis_btl) else set()
        check("Branch DSA Team Lead sees only their branch",
              btl_units <= {btl["unit"]} and len(vis_btl) > 0,
              note=f"{len(vis_btl)} staff; units={btl_units}")

    # 4) A DSA sees ~self.
    dsa = first_staff(roster, "Direct Sales Agent")
    if dsa:
        vis_dsa = get_visible_staff(dsa, roster)
        check("Direct Sales Agent sees a minimal set (self-ish)",
              len(vis_dsa) <= 2,
              note=f"{len(vis_dsa)} staff")

    print(f"\n{'='*48}\nSUMMARY: {PASS} passed, {FAIL} failed\n{'='*48}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
