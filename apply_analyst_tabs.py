#!/usr/bin/env python3
"""scripts/apply_analyst_tabs.py — B1: analyst workload tabs (My cases | Pool | All).

Lms.tsx gains a tab row: analysts default to "My cases" (their assigned apps),
everyone can view "Pool" (unassigned submitted apps, read-only) and "All". Managers
default to All. This is the foundation for B2 (request assignment) + B3 (reassign).

SAFE: .pre_tabs backup. Idempotent. --revert. TSC-gated.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "Lms.tsx"
BAK = PAGE.with_suffix(".tsx.pre_tabs")

EDITS = [
    # (anchor, replacement, label)
    ("import { useState, useMemo } from 'react';",
     "import { useState, useMemo, useEffect } from 'react';",
     "react import"),
    ("  const { user } = useRole();",
     "  const { user, isAdmin } = useRole();",
     "useRole destructure"),
    ("""  const [statusFilter, setStatusFilter] = useState<string | 'all'>('all');
  const [searchTerm,   setSearchTerm]   = useState<string>('');""",
     """  const [statusFilter, setStatusFilter] = useState<string | 'all'>('all');
  const [searchTerm,   setSearchTerm]   = useState<string>('');
  // B1: workload tabs. Analysts default to their own cases; managers to All.
  const myCode = String(user?.staff_code ?? '');
  const roleLc = String(user?.role ?? '').toLowerCase();
  const isPureAnalyst = roleLc.includes('analyst') && !isAdmin
    && !/chief|head|manager|officer|director|managing/.test(roleLc);
  const [tab, setTab] = useState<'mine' | 'pool' | 'all'>('all');
  useEffect(() => { setTab(isPureAnalyst ? 'mine' : 'all'); }, [isPureAnalyst]);""",
     "tab state"),
    ("""    return result;
  }, [applications, statusFilter, searchTerm]);""",
     """    // B1: workload tab filter.
    if (tab === 'mine') {
      result = result.filter((a) => String(a.analyst?.code ?? '') === myCode);
    } else if (tab === 'pool') {
      result = result.filter((a) => !a.analyst?.code
        && ['submitted'].includes((a.status || '').toLowerCase()));
    }
    return result;
  }, [applications, statusFilter, searchTerm, tab, myCode]);""",
     "tab filter"),
    ("  const currencySymbol = branding?.currency_symbol ?? 'KES';",
     """  const tabCounts = useMemo(() => ({
    mine: applications.filter((a) => String(a.analyst?.code ?? '') === myCode).length,
    pool: applications.filter((a) => !a.analyst?.code && (a.status || '').toLowerCase() === 'submitted').length,
    all: applications.length,
  }), [applications, myCode]);

  const currencySymbol = branding?.currency_symbol ?? 'KES';""",
     "tab counts"),
    ('''          <Card.Body>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <button
                onClick={() => setStatusFilter('all')}''',
     '''          <Card.Body>
            {/* B1: workload tabs */}
            <div className="flex items-center gap-2 mb-3 border-b border-gray-100 pb-3">
              {([['mine', 'My cases'], ['pool', 'Pool'], ['all', 'All']] as const).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition ${
                    tab === key ? 'bg-brand-primary text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  {label} ({tabCounts[key]})
                </button>
              ))}
              {tab === 'pool' && (
                <span className="ml-2 text-xs text-gray-400">Read-only — request assignment from a case to work it.</span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <button
                onClick={() => setStatusFilter('all')}''',
     "tab UI"),
]

def revert():
    if BAK.exists():
        shutil.copy2(BAK, PAGE); BAK.unlink(); print("  reverted Lms.tsx from .pre_tabs")
    else:
        print("  no .pre_tabs backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = PAGE.read_text(encoding="utf-8")
    if "B1: workload tabs" in s:
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
    PAGE.write_text(s, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
