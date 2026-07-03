#!/usr/bin/env python3
"""scripts/apply_analyst_dropdown_react.py — assign-analyst dropdown.

Replaces the two free-text inputs (code + name) in the assign panel with a
dropdown of the manager's analysts (GET /api/lms/my-analysts). Selecting one
sets both code and name. Falls back to manual entry if no analysts are returned.

- api.ts: fetchMyAnalysts + type
- LmsApplicationDetail.tsx: load analysts, dropdown in ActionPanelAssign.

SAFE: .pre_analystdd_ui backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_TS = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "LmsApplicationDetail.tsx"

API_BLOCK = '''
// assignable analysts for the current manager (assign-analyst dropdown)
export interface AssignableAnalyst { staff_code: string; name: string; role: string; unit: string; }
export async function fetchMyAnalysts(): Promise<{ analysts: AssignableAnalyst[]; count: number }> {
  return getJson<{ analysts: AssignableAnalyst[]; count: number }>('/lms/my-analysts');
}
'''

# import the fetcher + type
IMPORT_OLD = "  getLmsCr, saveLmsCr, getCommitteeCharter, getCommitteeTiers, getLmsCommitteeRecords, type LmsCommitteeRecordsResponse,"
IMPORT_NEW = "  getLmsCr, saveLmsCr, getCommitteeCharter, getCommitteeTiers, getLmsCommitteeRecords, fetchMyAnalysts, type LmsCommitteeRecordsResponse, type AssignableAnalyst,"

# add state + load in ActionPanelAssign (after the analystName state)
STATE_OLD = '''function ActionPanelAssign({ appId, open, setOpen, mutations, onSuccess, toast }: ActionPanelProps) {
  const [analystCode, setAnalystCode] = useState('');
  const [analystName, setAnalystName] = useState('');
  const [error, setError] = useState<string | null>(null);'''
STATE_NEW = '''function ActionPanelAssign({ appId, open, setOpen, mutations, onSuccess, toast }: ActionPanelProps) {
  const [analystCode, setAnalystCode] = useState('');
  const [analystName, setAnalystName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [analysts, setAnalysts] = useState<AssignableAnalyst[]>([]);
  useEffect(() => {
    fetchMyAnalysts().then((r) => setAnalysts(r.analysts)).catch(() => setAnalysts([]));
  }, []);'''

# replace the two Input fields with a dropdown (+ manual fallback)
FORM_OLD = '''        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Input
            label="Analyst staff code *"
            placeholder="e.g. 300080"
            value={analystCode}
            onChange={(e) => setAnalystCode(e.target.value)}
            disabled={mutations.loading}
          />
          <Input
            label="Analyst name *"
            placeholder="e.g. Zainab Okello"
            value={analystName}
            onChange={(e) => setAnalystName(e.target.value)}
            disabled={mutations.loading}
          />
        </div>'''
FORM_NEW = '''        {analysts.length > 0 ? (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Credit analyst *</label>
            <select
              className="w-full px-3 py-1.5 rounded-md border border-gray-300 text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              value={analystCode}
              disabled={mutations.loading}
              onChange={(e) => {
                const a = analysts.find((x) => x.staff_code === e.target.value);
                setAnalystCode(a?.staff_code ?? '');
                setAnalystName(a?.name ?? '');
              }}
            >
              <option value="">— select an analyst —</option>
              {analysts.map((a) => (
                <option key={a.staff_code} value={a.staff_code}>
                  {a.name} ({a.staff_code}){a.unit ? ` — ${a.unit}` : ''}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-gray-400">{analysts.length} analyst(s) in your team.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Input
              label="Analyst staff code *"
              placeholder="e.g. 300080"
              value={analystCode}
              onChange={(e) => setAnalystCode(e.target.value)}
              disabled={mutations.loading}
            />
            <Input
              label="Analyst name *"
              placeholder="e.g. Zainab Okello"
              value={analystName}
              onChange={(e) => setAnalystName(e.target.value)}
              disabled={mutations.loading}
            />
          </div>
        )}'''

def revert():
    for f in (API_TS, PAGE):
        b = f.with_suffix(f.suffix + ".pre_analystdd_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    a = API_TS.read_text(encoding="utf-8")
    a_ch = "fetchMyAnalysts" not in a
    p = PAGE.read_text(encoding="utf-8")
    checks = {
        "import": IMPORT_OLD in p,
        "state": STATE_OLD in p and "fetchMyAnalysts().then" not in p,
        "form": FORM_OLD in p,
    }
    print("  api.ts:", "change" if a_ch else "skip")
    print("  page checks:", {k: ("ok" if v else "MISS") for k, v in checks.items()})
    if not any(checks.values()) and not a_ch:
        print("  nothing to do."); return
    if dry:
        print("  --dry-run: nothing written."); return
    if a_ch:
        b = API_TS.with_suffix(API_TS.suffix + ".pre_analystdd_ui")
        if not b.exists(): b.write_text(a, encoding="utf-8")
        API_TS.write_text(a.rstrip() + "\n" + API_BLOCK + "\n", encoding="utf-8")
    p2 = p
    if checks["import"]:
        p2 = p2.replace(IMPORT_OLD, IMPORT_NEW, 1)
    if checks["state"]:
        p2 = p2.replace(STATE_OLD, STATE_NEW, 1)
    if checks["form"]:
        p2 = p2.replace(FORM_OLD, FORM_NEW, 1)
    if p2 != p:
        b = PAGE.with_suffix(PAGE.suffix + ".pre_analystdd_ui")
        if not b.exists(): b.write_text(p, encoding="utf-8")
        PAGE.write_text(p2, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
