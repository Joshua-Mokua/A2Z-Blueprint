"""
seed_pool_visibility.py — add the `pool_visibility` section to lms_config.json.

The credit work-pool visibility feature reads lms_config.json -> pool_visibility,
falling back to code defaults if absent. This script writes the defaults into the
file so the policy is VISIBLE and editable (via the admin endpoint or by hand)
rather than implicit. Idempotent: if the section already exists it is left as-is
unless --force is passed.

  python scripts/seed_pool_visibility.py            # dry-run
  python scripts/seed_pool_visibility.py --apply    # backup + write
  python scripts/seed_pool_visibility.py --apply --force   # overwrite existing
"""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

DEFAULTS = {
    "roles": [
        "credit analyst",
        "credit administrator",
        "chief credit officer",
        "branch credit manager",
        "head of credit",
        "credit manager",
    ],
    "statuses": [
        "submitted", "assigned", "info_requested",
        "referred_to_committee", "approved", "offer_issued",
        "offer_signed", "offer_validated", "analyst_confirmed",
    ],
}


def main():
    apply = "--apply" in sys.argv
    force = "--force" in sys.argv
    p = Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
    if not p.exists():
        print(f"!! {p} not found"); sys.exit(1)

    cfg = json.loads(p.read_text(encoding="utf-8"))
    has = isinstance(cfg.get("pool_visibility"), dict)
    print(f"lms_config.json: pool_visibility present = {has}")

    if has and not force:
        print("Section already present. Use --force to overwrite. Nothing to do.")
        sys.exit(0)

    cfg["pool_visibility"] = dict(DEFAULTS)
    print("=== would write pool_visibility ===")
    print(json.dumps(cfg["pool_visibility"], indent=2))

    if not apply:
        print("\n[DRY-RUN] Re-run with --apply to back up + write.")
        sys.exit(0)

    backup = p.with_suffix(f".pre_poolvis_{datetime.now():%Y%m%d-%H%M%S}.json")
    backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[backup] {backup.name}")
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, str(p))
    print(f"[apply] wrote pool_visibility to {p.name}")


if __name__ == "__main__":
    main()
