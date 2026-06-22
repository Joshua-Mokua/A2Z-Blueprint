#!/usr/bin/env python3
"""
seed_product_flows.py — P4a: seed pipeline_settings.json's new `product_flows`
map from the existing 4 class-flows (stage_flows), so every catalogued product
inherits its CLASS's stage sequence on day one. Zero behavior change: the
resolver falls back to class anyway, but seeding makes each product an explicit,
divergeable entry an admin can later customise.

Model written:
    product_flows: {
      "<Product Name>": {
        "client_types": [],                 # empty = offered to ALL client types
        "stages": [
          {"stage": "<Stage>", "target_days": <int>},  # SLA rides inside the flow
          ...
        ]
      },
      ...
    }

Per-stage target_days seed: taken from the global sla_config default where a
flow-stage maps to a known SLA step; otherwise a sane per-stage default. (SLA is
not yet WIRED to the clock — that's P4b — but the targets are authored here so
there's one surface.)

SAFE: dry-run unless --apply. Backs up pipeline_settings.json first.

    python scripts\\seed_product_flows.py            # dry-run
    python scripts\\seed_product_flows.py --apply    # backup + write
"""
import sys
import json
from pathlib import Path
from datetime import datetime

DATA = Path(__file__).resolve().parent.parent / "data"
CFG = DATA / "pipeline_settings.json"

# Catalogue-class -> flow-class, mirroring api._classify_product exactly.
CLASS_TO_FLOW = {
    "Assets": "asset",
    "Liabilities": "liability",
    "Insurance": "insurance",
    "Transactional": "other",
    "Investments": "other",
}

# Default per-stage target_days. Stage names are the flow vocabulary
# (Title Case), not the SLA step keys. These seed the authoring surface; an admin
# tunes them per product. Chosen to roughly mirror the global sla_config ladder.
STAGE_TARGET_DEFAULTS = {
    "Lead": 2,
    "Contacted": 2,
    "Qualified": 3,
    "Application": 3,
    "Credit Assessment": 5,
    "Offer / Proposal": 3,
    "Proposal": 3,
    "Negotiation": 3,
    "Documentation": 4,
    "Compliance": 4,
    "Closed Won": 1,
    "Closed Lost": 1,
}
_DEFAULT_TARGET = 3


def main():
    apply = "--apply" in sys.argv
    cfg = json.loads(CFG.read_text(encoding="utf-8"))

    stage_flows = cfg.get("stage_flows", {})
    catalogue = cfg.get("product_catalogue", {})
    if not stage_flows or not catalogue:
        print("ERROR: stage_flows or product_catalogue missing from config.")
        sys.exit(1)

    existing = cfg.get("product_flows", {})
    product_flows = dict(existing)  # preserve any already-authored entries
    seeded, skipped = 0, 0

    for cls, prods in catalogue.items():
        flow_cls = CLASS_TO_FLOW.get(cls, "other")
        stages = stage_flows.get(flow_cls, [])
        if not isinstance(stages, list) or not stages:
            continue
        for product in prods:
            if product in product_flows:
                skipped += 1     # don't clobber an admin-authored flow
                continue
            product_flows[product] = {
                "client_types": [],   # empty = all (admin narrows later)
                "stages": [
                    {"stage": str(s),
                     "target_days": STAGE_TARGET_DEFAULTS.get(str(s), _DEFAULT_TARGET)}
                    for s in stages
                ],
            }
            seeded += 1

    print(f"product_flows: {len(existing)} existing -> {len(product_flows)} total "
          f"({seeded} seeded, {skipped} preserved)")
    # sample
    sample = next(iter(product_flows.items())) if product_flows else None
    if sample:
        name, entry = sample
        print(f"\nsample: {name}")
        print(f"  client_types: {entry['client_types']} (empty = all)")
        for st in entry["stages"][:4]:
            print(f"  {st['stage']:<20} target_days={st['target_days']}")
        print(f"  ... ({len(entry['stages'])} stages)")

    if not apply:
        print("\n[DRY-RUN] No file written. Re-run with --apply to back up + write.")
        return

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = CFG.with_name(f"pipeline_settings.json.pre_p4a_{ts}")
    backup.write_text(CFG.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"\n[backup] {backup.name}")

    cfg["product_flows"] = product_flows
    CFG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[apply] wrote product_flows for {len(product_flows)} products. "
          "Resolver honours per-product first; class fallback unchanged.")


if __name__ == "__main__":
    main()
