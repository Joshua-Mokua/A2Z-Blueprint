#!/usr/bin/env python3
"""
p4a_diag.py — read-only diagnostic for the P4a advance-stage failure.

Prints what the LIVE pipeline_settings.json actually contains for the advance
allowlist, so we stop guessing. Run from project root with the venv active.

    python scripts\\p4a_diag.py
"""
import json
from pathlib import Path

CFG = Path(__file__).resolve().parent.parent / "data" / "pipeline_settings.json"


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))

    print(f"config: {CFG}")
    print(f"top-level keys: {sorted(cfg.keys())}\n")

    pf = cfg.get("product_flows", {})
    print(f"product_flows present: {'product_flows' in cfg} | count: {len(pf)}")
    if pf:
        for name, entry in list(pf.items())[:3]:
            stages = [s.get('stage') if isinstance(s, dict) else s
                      for s in entry.get('stages', [])]
            print(f"  {name}: {stages}")
        print()

    sf = cfg.get("stage_flows", {})
    print(f"stage_flows keys: {list(sf.keys())}")
    for k, v in sf.items():
        print(f"  {k}: {v}")
    print()

    dc = cfg.get("deal_categories", [])
    print(f"deal_categories: {len(dc)} categories")
    for cat in dc[:12]:
        nm = cat.get("name") or cat.get("category") or "?"
        print(f"  {nm}: {cat.get('stages', [])}")
    print()

    # Reproduce get_all_pipeline_stage_names exactly
    names = set()
    for st in cfg.get("stages", []):
        n = str(st.get("stage", "")).strip() if isinstance(st, dict) else str(st).strip()
        if n:
            names.add(n)
    for cat in cfg.get("deal_categories", []):
        for st in cat.get("stages", []):
            if str(st).strip():
                names.add(str(st).strip())
    for flow in cfg.get("stage_flows", {}).values():
        if isinstance(flow, list):
            for st in flow:
                if str(st).strip():
                    names.add(str(st).strip())
    for entry in cfg.get("product_flows", {}).values():
        if isinstance(entry, dict):
            for st in entry.get("stages", []):
                n = (str(st.get("stage", "")).strip() if isinstance(st, dict)
                     else str(st).strip())
                if n:
                    names.add(n)

    print("=== COMPUTED ADVANCE ALLOWLIST ===")
    print(f"total: {len(names)}")
    for probe in ("Application", "Credit Assessment", "Qualified", "Contacted"):
        print(f"  '{probe}' in allowlist? {probe in names}")
    print(f"\nfull sorted allowlist:\n{sorted(names)}")


if __name__ == "__main__":
    main()
