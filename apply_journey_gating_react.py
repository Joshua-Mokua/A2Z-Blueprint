#!/usr/bin/env python3
"""scripts/apply_journey_gating_react.py — 4b-5 React: show CR/committee gate reasons.

- CreditChecklistResponse gains cr_ok/cr_required/committee_ok/committee_pending/
  committee_rejected.
- The submit panel, when blocked, explains outstanding CR / pending committees /
  rejected committees (in addition to the stage gate).

SAFE: .pre_jgate_ui backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = ROOT / "frontend" / "web" / "src" / "types" / "pipeline.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "PipelineDealDetail.tsx"

def patch_types():
    s = TYPES.read_text(encoding="utf-8")
    if "committee_ok" in s:
        return s, False
    anchor = "  stage_ok?:           boolean;\n}"
    if anchor not in s:
        return s, False
    new = '''  stage_ok?:           boolean;
  cr_required?:        boolean;
  cr_ok?:              boolean;
  committee_ok?:       boolean;
  committee_pending?:  string[];
  committee_rejected?: string[];
}'''
    return s.replace(anchor, new, 1), True

def patch_page():
    s = PAGE.read_text(encoding="utf-8")
    if "committee decision(s) outstanding" in s or "gateReasons" in s:
        return s, False
    # Replace the stage-only blocked block with a richer multi-reason block.
    anchor = '''  if (!checklist.can_submit) {
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
    new = '''  if (!checklist.can_submit) {
    const gateReasons: string[] = [];
    if (checklist.stage_ok === false && checklist.stage_required) {
      gateReasons.push(`Deal must be at stage "${checklist.stage_required}"${checklist.current_stage ? ` (currently "${checklist.current_stage}")` : ''}.`);
    }
    if ((checklist.committee_rejected ?? []).length > 0) {
      gateReasons.push(`Committee rejected: ${(checklist.committee_rejected ?? []).join(', ')}. The deal returns to the owner (appeal or close).`);
    }
    if ((checklist.committee_pending ?? []).length > 0) {
      gateReasons.push(`Committee decision outstanding: ${(checklist.committee_pending ?? []).join(', ')}.`);
    }
    if (checklist.cr_required && checklist.cr_ok === false) {
      gateReasons.push('The Credit Report (CR) must be completed first.');
    }
    if (gateReasons.length > 0) {
      const rejected = (checklist.committee_rejected ?? []).length > 0;
      return (
        <Card className="mt-6" stripe="accent">
          <Card.Header>
            <h3 className="text-sm font-semibold text-gray-900">Submit to Credit Analysis</h3>
            <Badge tone={rejected ? 'danger' : 'warning'} size="sm">{rejected ? 'committee gate' : 'prerequisites'}</Badge>
          </Card.Header>
          <Card.Body>
            <p className="mb-2 text-sm text-gray-700">Before this deal can be submitted to credit analysis:</p>
            <ul className="list-disc pl-5 text-sm text-amber-700">
              {gateReasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </Card.Body>
        </Card>
      );
    }
    return null;
  }'''
    if anchor not in s:
        return s, False
    return s.replace(anchor, new, 1), True

def revert():
    for f in (TYPES, PAGE):
        b = f.with_suffix(f.suffix + ".pre_jgate_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    t, tc = patch_types()
    p, pc = patch_page()
    print(f"  types: {'change' if tc else 'skip'}")
    print(f"  PipelineDealDetail.tsx: {'change' if pc else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in ((TYPES, t, tc), (PAGE, p, pc)):
        if ch:
            b = f.with_suffix(f.suffix + ".pre_jgate_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
