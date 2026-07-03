#!/usr/bin/env python3
"""scripts/apply_app_sla2_react.py — C-SLA2 React: two-level SLA (My stage + Case).

Layers on C-SLA (app_sla). Each row shows TWO lines: "My: Xd left" (current stage
clock) + "Case: on track/Xd over" (overall customer promise). Detail header shows
both an overall banner and a My-stage line.

Requires C-SLA (app_sla.zip) already applied/committed.

- types/lms.ts: AppSla -> nested overall/stage (AppSlaClock)
- Lms.tsx: two-line SLA cell
- LmsApplicationDetail.tsx: My-stage line

SAFE: .pre_appsla2_ui backups. Idempotent. --revert. TSC-gated.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = ROOT / "frontend" / "web" / "src" / "types" / "lms.ts"
LMS = ROOT / "frontend" / "web" / "src" / "pages" / "Lms.tsx"
DETAIL = ROOT / "frontend" / "web" / "src" / "pages" / "LmsApplicationDetail.tsx"

def patch_types(s):
    if "AppSlaClock" in s: return s, False
    old = '''export interface AppSla {
  state: 'on_track' | 'due_soon' | 'breached';
  elapsed_business_days: number;
  target_days: number;
  remaining_business_days: number;
  overdue_business_days: number;
  breached: boolean;
}'''
    if old not in s: return s, False
    new = '''export interface AppSlaClock {
  state: 'on_track' | 'due_soon' | 'breached';
  step_key?: string;
  elapsed_business_days: number;
  target_days: number;
  remaining_business_days: number;
  overdue_business_days: number;
  breached: boolean;
}
export interface AppSla extends AppSlaClock {
  // C-SLA2: two-level — overall (customer promise) + stage ("My SLA").
  overall?: AppSlaClock;
  stage?: AppSlaClock | null;
}'''
    return s.replace(old, new, 1), True

def patch_lms(s):
    old_cell = '''                        <td className="px-4 py-3 text-xs">
                          {app.sla ? (
                            <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium ${
                              app.sla.state === 'breached' ? 'bg-red-100 text-red-700'
                              : app.sla.state === 'due_soon' ? 'bg-amber-100 text-amber-700'
                              : 'bg-green-100 text-green-700'}`}>
                              {app.sla.state === 'breached'
                                ? `${app.sla.overdue_business_days}d over`
                                : app.sla.state === 'due_soon'
                                ? `${app.sla.remaining_business_days}d left`
                                : 'On track'}
                            </span>
                          ) : <span className="text-gray-300">—</span>}
                        </td>'''
    if old_cell not in s: return s, False
    new_cell = '''                        <td className="px-4 py-3 text-xs">
                          {app.sla ? (
                            <div className="flex flex-col gap-0.5">
                              {app.sla.stage && (
                                <span className={`inline-flex w-fit items-center gap-1 rounded px-1.5 py-0.5 font-medium ${
                                  app.sla.stage.state === 'breached' ? 'bg-red-100 text-red-700'
                                  : app.sla.stage.state === 'due_soon' ? 'bg-amber-100 text-amber-700'
                                  : 'bg-green-100 text-green-700'}`}>
                                  My: {app.sla.stage.state === 'breached'
                                    ? `${app.sla.stage.overdue_business_days}d over`
                                    : `${app.sla.stage.remaining_business_days}d left`}
                                </span>
                              )}
                              <span className={`inline-flex w-fit items-center gap-1 rounded px-1.5 py-0.5 ${
                                app.sla.state === 'breached' ? 'text-red-600'
                                : app.sla.state === 'due_soon' ? 'text-amber-600'
                                : 'text-green-600'}`}>
                                Case: {app.sla.state === 'breached'
                                  ? `${app.sla.overdue_business_days}d over`
                                  : app.sla.state === 'due_soon'
                                  ? `${app.sla.remaining_business_days}d left`
                                  : 'on track'}
                              </span>
                            </div>
                          ) : <span className="text-gray-300">—</span>}
                        </td>'''
    return s.replace(old_cell, new_cell, 1), True

def patch_detail(s):
    if "My stage — " in s: return s, False
    anchor = '''              {application.sla && (
                <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium ${
                  application.sla.state === 'breached' ? 'bg-red-500/90 text-white'
                  : application.sla.state === 'due_soon' ? 'bg-amber-400/90 text-amber-950'
                  : 'bg-green-500/90 text-white'}`}>
                  {application.sla.state === 'breached'
                    ? `SLA breached — ${application.sla.overdue_business_days}d over promise`
                    : application.sla.state === 'due_soon'
                    ? `SLA due soon — ${application.sla.remaining_business_days}d left`
                    : `SLA on track — ${application.sla.remaining_business_days}d left`}
                </span>
              )}'''
    if anchor not in s: return s, False
    new = anchor + '''
              {application.sla?.stage && (
                <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium ${
                  application.sla.stage.state === 'breached' ? 'bg-red-500/90 text-white'
                  : application.sla.stage.state === 'due_soon' ? 'bg-amber-400/90 text-amber-950'
                  : 'bg-green-500/90 text-white'}`}>
                  {application.sla.stage.state === 'breached'
                    ? `My stage — ${application.sla.stage.overdue_business_days}d over`
                    : `My stage — ${application.sla.stage.remaining_business_days}d left of ${application.sla.stage.target_days}`}
                </span>
              )}'''
    return s.replace(anchor, new, 1), True

def revert():
    for f in (TYPES, LMS, DETAIL):
        b = f.with_suffix(f.suffix + ".pre_appsla2_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    files = []
    for f, fn in ((TYPES, patch_types), (LMS, patch_lms), (DETAIL, patch_detail)):
        new, ch = fn(f.read_text(encoding="utf-8"))
        files.append((f, new, ch)); print(f"  {f.name}: {'change' if ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in files:
        if ch:
            b = f.with_suffix(f.suffix + ".pre_appsla2_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
