"""
map_dsa_regions.py — set each branch's `region` in data/org_config.json to the
4-region DSA structure, so BRANCH_REGION / REGIONS (core.py) and every
region-scoped view (Regional DSA Head, rollups) resolve correctly.

This is PRODUCTION hierarchy data, so the script is strict:
  - Matches branches by NORMALIZED name (case/space-insensitive) so minor
    spelling differences still resolve.
  - DRY-RUN by default; --apply required to write.
  - Backs up org_config.json (.pre_regionmap) before writing.
  - HARD-FAILS (non-zero exit, no write) if:
      * any of the 16 mapped branches is NOT found in org_config, OR
      * any ACTIVE branch in org_config is left UNMAPPED.
    Either case means the region picture would be incomplete — better to stop
    and reconcile than to push a half-mapped hierarchy to production.

USAGE:
  python scripts/map_dsa_regions.py            # dry-run: shows every change + any gaps
  python scripts/map_dsa_regions.py --apply     # back up + write (only if no gaps)
"""
import sys
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORG = ROOT / "data" / "org_config.json"
APPLY = "--apply" in sys.argv

# The 4-region DSA structure -> branches (exact business names).
REGION_BRANCHES = {
    "Western":   ["Eldoret", "Kisii", "Kisumu", "Nakuru"],
    "Mt. Kenya": ["Mombasa Moi Avenue", "Thika", "Nyeri", "Karatina"],
    "Nairobi 1": ["Plaza", "Towers", "Industrial Area", "Upper Hill"],
    "Nairobi 2": ["Westlands", "Karen", "Valley Arcade", "Fortis Office Park"],
}


def norm(s: str) -> str:
    """Case/space-insensitive key so 'Upper hill' == 'Upper Hill' == 'upperhill'."""
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def main():
    if not ORG.exists():
        print(f"!! {ORG} not found")
        sys.exit(2)
    cfg = json.loads(ORG.read_text(encoding="utf-8"))
    branches = cfg.get("branches", [])
    if not branches:
        print("!! org_config.json has no 'branches' list")
        sys.exit(2)

    # Build: normalized branch name -> intended region.
    want = {}
    for region, names in REGION_BRANCHES.items():
        for n in names:
            want[norm(n)] = region

    # Index live branches by normalized name.
    live_by_norm = {}
    for b in branches:
        live_by_norm.setdefault(norm(b.get("name")), []).append(b)

    print(f"org_config: {len(branches)} branches; target mapping covers "
          f"{sum(len(v) for v in REGION_BRANCHES.values())} branches "
          f"across {len(REGION_BRANCHES)} regions.\n")

    # 1) Every one of the 16 must exist in org_config.
    missing = [name for region, names in REGION_BRANCHES.items()
               for name in names if norm(name) not in live_by_norm]
    # 2) Apply the mapping + record changes.
    changes = []
    mapped_norms = set()
    for b in branches:
        nk = norm(b.get("name"))
        if nk in want:
            mapped_norms.add(nk)
            new_region = want[nk]
            old_region = b.get("region", "")
            if old_region != new_region:
                changes.append((b.get("name"), old_region, new_region))
            b["region"] = new_region  # staged in-memory; only written on --apply

    # 3) Any ACTIVE live branch not in the 16 is an unmapped gap.
    unmapped = [b.get("name") for b in branches
                if b.get("active", True) and norm(b.get("name")) not in want]

    print("=== CHANGES (branch: old region -> new region) ===")
    if changes:
        for name, old, new in changes:
            print(f"  {name}: {old or '(none)'} -> {new}")
    else:
        print("  (no region changes needed — already aligned)")
    print()

    if missing:
        print("!! MISSING — these mapped branches are NOT in org_config.json:")
        for m in missing:
            print(f"     - {m}")
        print()
    if unmapped:
        print("!! UNMAPPED — these ACTIVE org_config branches are not in the 4-region map:")
        for u in unmapped:
            print(f"     - {u}")
        print()

    if missing or unmapped:
        print("ABORT: region picture is incomplete. Reconcile the names above "
              "(or confirm extra branches should be inactive) before --apply.")
        sys.exit(1)

    # Summary by region (post-map).
    print("=== RESULT BY REGION ===")
    by_region = {}
    for b in branches:
        by_region.setdefault(b.get("region", "?"), []).append(b.get("name"))
    for region in REGION_BRANCHES:
        print(f"  {region}: {sorted(by_region.get(region, []))}")
    print()

    if not APPLY:
        print("[DRY-RUN] No file written. Re-run with --apply to back up + write.")
        return

    bak = ORG.with_name(f"org_config.json.pre_regionmap-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(ORG, bak)
    print(f"[backup] {bak.name}")
    # Atomic write.
    import os, tempfile
    fd, tmp = tempfile.mkstemp(dir=str(ORG.parent), prefix=".orgcfg_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, str(ORG))
    print(f"[apply] wrote {len(changes)} region change(s) to org_config.json.")
    print("Restart the API so BRANCH_REGION / REGIONS rebuild from the new config.")


if __name__ == "__main__":
    main()
