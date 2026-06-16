"""Seed the admin sector config so the deal-create sector source is
config-driven, not hardcoded.

- business_sectors : the CBK economic-sector classification (seeded from the
  existing utils.core.CBK_SECTORS — the "confirm what we defined" source).
- allow_other_sector / allow_other_mou : enable the "Other…" free-text fallback.

Idempotent and NON-DESTRUCTIVE: existing keys are never overwritten (admin edits
win); only missing keys are added. Backup-before-mutation per OPERATIONAL_PROTOCOL.
Individual MOUs are NOT duplicated here — they are read live from
data/partnerships_mous.json (the real register) by the config endpoint.
"""
import json
import os
import shutil
from datetime import datetime

SETTINGS = os.path.join("data", "pipeline_settings.json")


def main() -> None:
    from utils.core import CBK_SECTORS

    with open(SETTINGS, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    changed = []
    if not cfg.get("business_sectors"):
        cfg["business_sectors"] = list(CBK_SECTORS)
        changed.append(f"business_sectors ({len(CBK_SECTORS)} CBK classes)")
    if "allow_other_sector" not in cfg:
        cfg["allow_other_sector"] = True
        changed.append("allow_other_sector=true")
    if "allow_other_mou" not in cfg:
        cfg["allow_other_mou"] = True
        changed.append("allow_other_mou=true")

    if not changed:
        print("sector config already present — no changes (idempotent).")
        return

    backup = f"{SETTINGS}.bak_{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(SETTINGS, backup)
    with open(SETTINGS, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f"backup: {backup}")
    print("added:", "; ".join(changed))
    print(f"business_sectors[0..2] = {cfg['business_sectors'][:3]}")


if __name__ == "__main__":
    main()
