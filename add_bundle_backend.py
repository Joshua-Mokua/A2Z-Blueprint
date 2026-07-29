#!/usr/bin/env python3
"""Step 2 — backend bundle_lines. Mirrors the is_top_up pattern.

  1. api_pipeline_models.py: add BundleLine model + bundle_lines field to PipelineDealCreate
  2. api.py handler: when bundle_lines present -> deal_value = sum(amounts),
     product_type = 'Bundled Loan Product', persist the lines. Placed right beside the
     existing is_top_up block.

    python add_bundle_backend.py            # dry run
    python add_bundle_backend.py --apply
"""
import sys, shutil, time, re
from pathlib import Path

MODELS = Path("utils/api_pipeline_models.py")
API    = Path("utils/api.py")
m = MODELS.read_text(encoding="utf-8")
a = API.read_text(encoding="utf-8")

# ---- 1. model ----
if "class BundleLine" not in m:
    # add BundleLine just before PipelineDealCreate
    anchor = "class PipelineDealCreate(BaseModel):"
    if anchor not in m:
        print("REFUSING — PipelineDealCreate not found"); sys.exit(1)
    bl = (
        "class BundleLine(BaseModel):\n"
        "    \"\"\"One component of a Bundled Loan Product: a loan product + its amount.\"\"\"\n"
        "    product_type: str = Field(description=\"A catalogued loan product name.\")\n"
        "    amount: float = Field(description=\"Amount for this line; must be > 0.\")\n\n\n"
    )
    m = m.replace(anchor, bl + anchor, 1)

if "bundle_lines" not in m:
    # add the field after product_type in PipelineDealCreate
    # anchor on the product_type Field(...) closing in that class
    idx = m.find("class PipelineDealCreate(BaseModel):")
    seg = m[idx:]
    pm = re.search(r'product_type:\s*str\s*=\s*Field\([^)]*\)\n', seg)
    if not pm:
        print("REFUSING — product_type field not found in PipelineDealCreate"); sys.exit(1)
    insert_at = idx + pm.end()
    field = ("    bundle_lines: Optional[list[BundleLine]] = Field(\n"
             "        default=None,\n"
             "        description=\"For a Bundled Loan Product: component loan products with \"\n"
             "        \"amounts. When present, deal_value is set to their sum server-side.\",\n"
             "    )\n")
    m = m[:insert_at] + field + m[insert_at:]

# ensure Optional imported
if "from typing import" in m and "Optional" not in m.split("from typing import",1)[1][:80]:
    m = m.replace("from typing import", "from typing import Optional,", 1)

# ---- 2. handler ----
if "bundle_lines" not in a or "sum(float" not in a:
    # find the is_top_up block to anchor beside
    anchor = 'if deal_dict.get("is_top_up"):'
    if anchor not in a:
        print("REFUSING — is_top_up handler block not found to anchor beside"); sys.exit(1)
    block = (
        'if deal_dict.get("bundle_lines"):\n'
        '            _lines = [l for l in (deal_dict.get("bundle_lines") or [])\n'
        '                      if float((l or {}).get("amount") or 0) > 0]\n'
        '            if not _lines:\n'
        '                raise HTTPException(status_code=400,\n'
        '                    detail="A bundled loan needs at least one product line with an amount.")\n'
        '            deal_dict["bundle_lines"] = _lines\n'
        '            deal_dict["deal_value"]   = round(sum(float(l["amount"]) for l in _lines), 2)\n'
        '            deal_dict["product_type"] = "Bundled Loan Product"\n'
        '        '
    )
    a = a.replace(anchor, block + anchor, 1)

print("=== planned ===")
print(f"   BundleLine model added:        {'class BundleLine' in m}")
print(f"   bundle_lines field added:      {'bundle_lines' in m}")
print(f"   handler sum block added:       {'sum(float(l' in a}")

if "--apply" not in sys.argv:
    print("\n[DRY-RUN] re-run with --apply"); sys.exit(0)

ts = int(time.time())
shutil.copy2(MODELS, MODELS.with_suffix(f".py.pre_bundle_{ts}"))
shutil.copy2(API, API.with_suffix(f".py.pre_bundle_{ts}"))
MODELS.write_text(m, encoding="utf-8")
API.write_text(a, encoding="utf-8")
import ast
ast.parse(MODELS.read_text(encoding="utf-8"))
ast.parse(API.read_text(encoding="utf-8"))
print("\napplied, both parse clean. Restart the API and curl-test a bundle create.")
