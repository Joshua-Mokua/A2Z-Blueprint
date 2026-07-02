#!/usr/bin/env python3
"""scripts/apply_stagegate_react.py — Batch 4a frontend: show the stage-gate reason.

- CreditChecklistResponse gains current_stage / stage_required / stage_ok.
- The submit panel, instead of silently hiding when blocked ONLY by the stage
  gate, shows a short explanation ("requires stage X, currently Y").

SAFE: .pre_stagegate_ui backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = ROOT / "frontend" / "web" / "src" / "types" / "pipeline.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "PipelineDealDetail.tsx"

def patch_types():
    s = TYPES.read_text(encoding="utf-8")
    if "stage_required" in s:
        return s, False
    old = '''export interface CreditChecklistResponse {
  required:            string[];
  provided:            string[];
  missing:             string[];
  already_submitted:   boolean;
  lms_application_id:   string | null;
  can_submit:          boolean;
}'''
    new = '''export interface CreditChecklistResponse {
  required:            string[];
  provided:            string[];
  missing:             string[];
  already_submitted:   boolean;
  lms_application_id:   string | null;
  can_submit:          boolean;
  current_stage?:      string;
  stage_required?:     string;
  stage_ok?:           boolean;
}'''
    if old not in s:
        return s, False
    return s.replace(old, new, 1), True

def patch_page():
    s = PAGE.read_text(encoding="utf-8")
    if "requires this deal to be at stage" in s:
        return s, False
    # Replace the blunt "if (!checklist.can_submit) return null;" so that a
    # stage-only block shows an explanation instead of hiding.
    old = "  // Only the owner / admin sees the submission form.\n  if (!checklist.can_submit) return null;"
    new = '''  // Only the owner / admin sees the submission form. If the ONLY thing blocking
  // submission is the stage gate, show an explanation instead of hiding.
  if (!checklist.can_submit) {
    if (checklist.stage_ok === false && checklist.stage_required) {
      return (
        <Card className="mt-6" stripe="accent">
          <Card.Header>
            <h3 className="text-sm font-semibold text-gray-900">Submit to Credit Analysis</h3>
            <Badge tone="warning" size="sm">stage gate</Badge>
          </Card.Header>
          <Card.Body>
            <p className="text-sm text-amber-700">
              This product requires this deal to be at stage
              {' '}<span className="font-medium">"{checklist.stage_required}"</span>
              {' '}before it can be submitted to credit analysis
              {checklist.current_stage ? <> (currently "{checklist.current_stage}")</> : null}.
            </p>
          </Card.Body>
        </Card>
      );
    }
    return null;
  }'''
    if old not in s:
        return s, False
    return s.replace(old, new, 1), True

def revert():
    for f in (TYPES, PAGE):
        b = f.with_suffix(f.suffix + ".pre_stagegate_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    t, tc = patch_types()
    p, pc = patch_page()
    print(f"  types/pipeline.ts: {'change' if tc else 'skip'}")
    print(f"  PipelineDealDetail.tsx: {'change' if pc else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in ((TYPES, t, tc), (PAGE, p, pc)):
        if ch:
            b = f.with_suffix(f.suffix + ".pre_stagegate_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
