#!/usr/bin/env python3
"""scripts/apply_handoff_carryover.py — 4b-7 (final): CR + committee handoff.

At submission, create_from_pipeline_deal copies the deal's CR, committee decisions,
and appeals onto the created LMS application, so Credit Analysis sees the completed
branch-originated inputs (read-only). Closes the credit-workflow loop.

Injects a carry-over block into utils/core.py's create_from_pipeline_deal, right
before self.apps.append(app).

SAFE: .pre_carryover backup on core.py. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "utils" / "core.py"
BAK = CORE.with_suffix(".py.pre_carryover")

ANCHOR = '''            "created_by":         username or "",
            "created_via":        "api_pipeline_advance",
        }
        self.apps.append(app)'''

NEW = '''            "created_by":         username or "",
            "created_via":        "api_pipeline_advance",
        }
        # 4b-7: carry the branch-originated CR + committee decisions onto the
        # application so Credit Analysis sees the completed inputs (read-only).
        try:
            deal_cr = deal.get("cr")
            if isinstance(deal_cr, dict) and deal_cr:
                app["cr"] = deal_cr                       # same shape build_cr_view reads
                app["cr_origin"] = "branch"
            deal_committees = deal.get("committee_records")
            if isinstance(deal_committees, dict) and deal_committees:
                app["committee_records"] = deal_committees
            deal_appeals = deal.get("appeals")
            if isinstance(deal_appeals, list) and deal_appeals:
                app["committee_appeals"] = deal_appeals
        except Exception:
            pass
        self.apps.append(app)'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, CORE); BAK.unlink(); print("  reverted core.py from .pre_carryover")
    else:
        print("  no .pre_carryover backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = CORE.read_text(encoding="utf-8")
    if "4b-7: carry the branch-originated CR" in s:
        print("  already applied."); return
    if ANCHOR not in s:
        print("  ERROR: create_from_pipeline_deal append anchor not found."); sys.exit(1)
    if dry:
        print("  --dry-run: would inject CR+committee carry-over. Nothing written."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    s = s.replace(ANCHOR, NEW, 1)
    CORE.write_text(s, encoding="utf-8")
    print("  applied handoff carry-over. Restart API.")

if __name__ == "__main__":
    main()
