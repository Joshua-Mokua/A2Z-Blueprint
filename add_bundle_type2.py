#!/usr/bin/env python3
"""Add bundle_lines to CreateDealRequest in types/pipeline.ts, after top_up_amount."""
import sys, shutil, time
from pathlib import Path
F = Path("frontend/web/src/types/pipeline.ts")
s = F.read_text(encoding="utf-8")
if "bundle_lines" in s:
    print("already present."); sys.exit(0)
anchor = "  top_up_amount?:        number;    // the increment (becomes pipeline value)\n"
if anchor not in s:
    # tolerant: match the top_up_amount line whatever the comment
    import re
    m = re.search(r'\n(\s*)top_up_amount\?:[^\n]*\n', s)
    if not m:
        print("REFUSING — top_up_amount line not found"); sys.exit(1)
    ins = "  bundle_lines?:         { product_type: string; amount: number }[]; // Bundled Loan Product lines\n"
    s = s[:m.end()] + ins + s[m.end():]
else:
    s = s.replace(anchor, anchor +
        "  bundle_lines?:         { product_type: string; amount: number }[]; // Bundled Loan Product lines\n", 1)
if "--apply" not in sys.argv:
    print("[DRY-RUN] would add bundle_lines after top_up_amount"); sys.exit(0)
shutil.copy2(F, F.with_suffix(f".ts.pre_bundletype_{int(time.time())}"))
F.write_text(s, encoding="utf-8")
print("applied. Run tsc.")
