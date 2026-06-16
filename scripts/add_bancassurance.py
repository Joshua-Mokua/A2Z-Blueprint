"""Add 'Bancassurance' to product_catalogue.Insurance in pipeline_settings.json.
Idempotent + backs up first. Non-destructive — preserves all other config.

Usage (project root, venv active):  python scripts\add_bancassurance.py
"""
import json, shutil
from datetime import datetime
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "data" / "pipeline_settings.json"
s = json.loads(p.read_text(encoding="utf-8"))
ins = s.setdefault("product_catalogue", {}).setdefault("Insurance", [])
if "Bancassurance" in ins:
    print("Already present — no change.")
else:
    shutil.copy2(p, p.with_suffix(
        f".json.bak-{datetime.now():%Y%m%d-%H%M%S}"))
    ins.insert(0, "Bancassurance")
    p.write_text(json.dumps(s, indent=2), encoding="utf-8")
    print(f"Added 'Bancassurance' to Insurance -> {ins}")
