#!/usr/bin/env python3
"""scripts/apply_app_sla_react.py — C-SLA React: SLA badges on apps (list + detail).

Every LMS application row shows an SLA badge (green On track / amber Xd left /
red Xd over); the case detail header shows a fuller SLA banner. The SLA spine
travels with the case up the committee ladder so every player sees urgency.

- types/lms.ts: AppSla + app.sla
- Lms.tsx: SLA column (header + badge cell)
- LmsApplicationDetail.tsx: SLA badge in the header

SAFE: .pre_appsla_ui backups. Idempotent. --revert. TSC-gated.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = ROOT / "frontend" / "web" / "src" / "types" / "lms.ts"
LMS = ROOT / "frontend" / "web" / "src" / "pages" / "Lms.tsx"
DETAIL = ROOT / "frontend" / "web" / "src" / "pages" / "LmsApplicationDetail.tsx"

def patch_types(s):
    if "AppSla" in s: return s, False
    s = s.replace("  sla_target_days?:       number;",
                  "  sla_target_days?:       number;\n  sla?:                   AppSla | null;", 1)
    s = s.replace("export interface LoanApplication {",
                  "export interface AppSla {\n"
                  "  state: 'on_track' | 'due_soon' | 'breached';\n"
                  "  elapsed_business_days: number;\n"
                  "  target_days: number;\n"
                  "  remaining_business_days: number;\n"
                  "  overdue_business_days: number;\n"
                  "  breached: boolean;\n"
                  "}\n\n"
                  "export interface LoanApplication {", 1)
    return s, True

def patch_lms(s):
    if '<th className="px-4 py-3">SLA</th>' in s: return s, False
    s = s.replace(
        '                      <th className="px-4 py-3">Analyst</th>\n'
        '                      <th className="px-4 py-3">Applied</th>',
        '                      <th className="px-4 py-3">Analyst</th>\n'
        '                      <th className="px-4 py-3">SLA</th>\n'
        '                      <th className="px-4 py-3">Applied</th>', 1)
    old_date_cell = '''                        <td className="px-4 py-3 text-gray-600 text-xs">
                          {formatDate(app.application_date)}
                        </td>'''
    new_cells = '''                        <td className="px-4 py-3 text-xs">
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
                        </td>
                        <td className="px-4 py-3 text-gray-600 text-xs">
                          {formatDate(app.application_date)}
                        </td>'''
    s = s.replace(old_date_cell, new_cells, 1)
    return s, True

def patch_detail(s):
    if "SLA breached — " in s: return s, False
    anchor = '''              <Badge tone={statusTone(application.status)} size="md">
                {application.status}
              </Badge>
              {application.swim_lane && (
                <span className="text-xs text-white/70">{application.swim_lane}</span>
              )}'''
    new = '''              <Badge tone={statusTone(application.status)} size="md">
                {application.status}
              </Badge>
              {application.sla && (
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
              )}
              {application.swim_lane && (
                <span className="text-xs text-white/70">{application.swim_lane}</span>
              )}'''
    s = s.replace(anchor, new, 1)
    return s, True

def revert():
    for f in (TYPES, LMS, DETAIL):
        b = f.with_suffix(f.suffix + ".pre_appsla_ui")
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
            b = f.with_suffix(f.suffix + ".pre_appsla_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
