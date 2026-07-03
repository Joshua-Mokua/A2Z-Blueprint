#!/usr/bin/env python3
"""scripts/apply_case_assign_react.py — C-ASSIGN: Chief's per-case Assign button.

Adds an "Assign" column to the Credit Analysis list (manager-only). On a submitted,
unassigned case the Chief clicks "Assign ▾" -> popover: pick an analyst (assigns
immediately) OR "Route to committee →" (opens the case's routing panel). Lets the
Chief act as traffic-controller from the LIST, not case-by-case. Reuses B2's
doAssign + analystPool.

Frontend-only. SAFE: .pre_cassign backup. Idempotent. --revert. TSC-gated.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LMS = ROOT / "frontend" / "web" / "src" / "pages" / "Lms.tsx"
BAK = LMS.with_suffix(".tsx.pre_cassign")

EDITS = [
    ("  const [assignBusy, setAssignBusy] = useState<string | null>(null);",
     "  const [assignBusy, setAssignBusy] = useState<string | null>(null);\n"
     "  const [assignMenuFor, setAssignMenuFor] = useState<string | null>(null);",
     "assign menu state"),
    ('                      <th className="px-4 py-3">SLA</th>\n'
     '                      <th className="px-4 py-3">Applied</th>',
     '                      <th className="px-4 py-3">SLA</th>\n'
     '                      <th className="px-4 py-3">Applied</th>\n'
     '                      {isManagerRole && <th className="px-4 py-3">Assign</th>}',
     "assign column header"),
    ('''                        <td className="px-4 py-3 text-gray-600 text-xs">
                          {formatDate(app.application_date)}
                        </td>
                      </tr>''',
     '''                        <td className="px-4 py-3 text-gray-600 text-xs">
                          {formatDate(app.application_date)}
                        </td>
                        {isManagerRole && (
                          <td className="px-4 py-3 text-xs relative" onClick={(e) => e.stopPropagation()}>
                            {!app.analyst?.code && (app.status || '').toLowerCase() === 'submitted' ? (
                              <>
                                <button
                                  onClick={() => setAssignMenuFor(assignMenuFor === app.id ? null : app.id)}
                                  className="rounded border border-brand-primary px-2 py-0.5 text-xs text-brand-primary hover:bg-brand-primary/5"
                                >
                                  Assign ▾
                                </button>
                                {assignMenuFor === app.id && (
                                  <div className="absolute right-0 z-10 mt-1 w-56 rounded-md border border-gray-200 bg-white p-2 shadow-lg">
                                    <div className="mb-1 text-xs font-medium text-gray-500">To an analyst</div>
                                    <select
                                      className="mb-2 w-full rounded border px-2 py-1 text-xs"
                                      defaultValue=""
                                      onChange={(e) => {
                                        const a = analystPool.find((x) => x.staff_code === e.target.value);
                                        if (a) { void doAssign(app.id, a.staff_code, a.name); setAssignMenuFor(null); }
                                      }}
                                    >
                                      <option value="">— pick analyst —</option>
                                      {analystPool.map((a) => (
                                        <option key={a.staff_code} value={a.staff_code}>{a.name}</option>
                                      ))}
                                    </select>
                                    <div className="border-t border-gray-100 pt-2">
                                      <button
                                        onClick={() => { setAssignMenuFor(null); navigate(`/lms/${encodeURIComponent(app.id)}`); }}
                                        className="w-full rounded bg-gray-50 px-2 py-1 text-left text-xs text-gray-700 hover:bg-gray-100"
                                      >
                                        Route to committee →
                                      </button>
                                    </div>
                                  </div>
                                )}
                              </>
                            ) : (
                              <span className="text-gray-300">—</span>
                            )}
                          </td>
                        )}
                      </tr>''',
     "assign cell"),
]

def revert():
    if BAK.exists():
        shutil.copy2(BAK, LMS); BAK.unlink(); print("  reverted Lms.tsx from .pre_cassign")
    else:
        print("  no .pre_cassign backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = LMS.read_text(encoding="utf-8")
    if "assignMenuFor" in s:
        print("  already applied."); return
    missing = [label for anchor, _, label in EDITS if anchor not in s]
    if missing:
        print(f"  ERROR: anchors not found: {missing}"); sys.exit(1)
    print(f"  all {len(EDITS)} anchors matched")
    if dry:
        print("  --dry-run: nothing written."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    for anchor, repl, _ in EDITS:
        s = s.replace(anchor, repl, 1)
    LMS.write_text(s, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
