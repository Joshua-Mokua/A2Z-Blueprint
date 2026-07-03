#!/usr/bin/env python3
"""scripts/apply_att_ui_fix.py — ATT: fix the required-attachments / committee-journey
admin panel layout.

The "Required documents (this product)" + "Credit committee journey (this product)"
panels were wrongly nested inside a `flex items-center gap-2` container meant for the
Save buttons — squishing the two full-width panels into a cramped horizontal row
(unusable, so admin saves came back empty). Fix: make the panels a vertical stack and
give the Save/Reset buttons their own row. Layout-only; the save payload was already
correct.

SAFE: .pre_attui backup on AdminConfig.tsx. Idempotent. --revert. TSC-gated.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADMIN = ROOT / "frontend" / "web" / "src" / "pages" / "AdminConfig.tsx"
BAK = ADMIN.with_suffix(".tsx.pre_attui")

def patch(s):
    if 'className="space-y-3 pt-1"' in s:
        return s, False
    s = s.replace(
        '''                    <div className="flex items-center gap-2 pt-1">
                      <div className="mb-3 rounded border p-3">
                <p className="mb-1 text-sm font-medium">Required documents (this product)</p>''',
        '''                    <div className="space-y-3 pt-1">
                      <div className="rounded border p-3">
                <p className="mb-1 text-sm font-medium">Required documents (this product)</p>''', 1)
    s = s.replace(
        '''              </div>
<div className="mb-3 rounded border p-3">
                <p className="mb-1 text-sm font-medium">Credit committee journey (this product)</p>''',
        '''              </div>
              <div className="rounded border p-3">
                <p className="mb-1 text-sm font-medium">Credit committee journey (this product)</p>''', 1)
    s = s.replace(
        '''              </div>
                            <Button size="sm" onClick={saveFlow} disabled={flowBusy}>
                        Save flow
                      </Button>
                      {productFlows[flowProduct] && (
                        <Button variant="secondary" size="sm" onClick={resetFlowToClass} disabled={flowBusy}>
                          Reset to class flow
                        </Button>
                      )}
                    </div>''',
        '''              </div>
                      <div className="flex items-center gap-2">
                        <Button size="sm" onClick={saveFlow} disabled={flowBusy}>
                          Save flow
                        </Button>
                        {productFlows[flowProduct] && (
                          <Button variant="secondary" size="sm" onClick={resetFlowToClass} disabled={flowBusy}>
                            Reset to class flow
                          </Button>
                        )}
                      </div>
                    </div>''', 1)
    return s, True

def revert():
    if BAK.exists():
        shutil.copy2(BAK, ADMIN); BAK.unlink(); print("  reverted AdminConfig.tsx")
    else:
        print("  no .pre_attui backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = ADMIN.read_text(encoding="utf-8")
    new, ch = patch(s)
    print(f"  AdminConfig.tsx (panel layout): {'change' if ch else 'skip (already applied?)'}")
    if dry:
        print("  --dry-run: nothing written."); return
    if ch:
        if not BAK.exists(): BAK.write_text(s, encoding="utf-8")
        ADMIN.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
