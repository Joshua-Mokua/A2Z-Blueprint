#!/usr/bin/env python3
"""scripts/apply_committee_climb_react.py — C1b React: climb-aware banner + MCC toggle.

- api.ts: CommitteeRouting gains entry/final/require_mcc/must_climb; + setRequireMcc.
- LmsApplicationDetail.tsx: refer banner shows the climb path (enters at MCC, climbs
  to Board/Group) + pre-selects the ENTRY tier.
- CommitteeAdmin.tsx: "Require MCC before Board/Group" toggle.

Layers on C1 (committee_routing). SAFE: .pre_climb_ui backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
DETAIL = ROOT / "frontend" / "web" / "src" / "pages" / "LmsApplicationDetail.tsx"
ADMIN = ROOT / "frontend" / "web" / "src" / "pages" / "CommitteeAdmin.tsx"

def patch_api(s):
    ch = False
    if "entry_tier" not in s.split("CommitteeRouting")[1].split("}")[0]:
        s = s.replace(
            '''export interface CommitteeRouting {
  tiers: CommitteeTier[];
  amount: number;
  suggested_tier: number | null;
  suggested_name: string | null;''',
            '''export interface CommitteeRouting {
  tiers: CommitteeTier[];
  amount: number;
  suggested_tier: number | null;
  suggested_name: string | null;
  entry_tier?: number | null;
  entry_name?: string | null;
  final_tier?: number | null;
  final_name?: string | null;
  require_mcc?: boolean;
  must_climb?: boolean;''', 1)
        ch = True
    if "setRequireMcc" not in s:
        block = '''
// C1b: require-MCC-before-higher admin toggle
export async function setRequireMcc(enabled: boolean): Promise<{ status: string; require_mcc_before_higher: boolean }> {
  return postJson<{ status: string; require_mcc_before_higher: boolean }, { enabled: boolean }>(
    '/lms/committee/require-mcc', { enabled });
}
'''
        s = s.rstrip() + "\n" + block + "\n"
        ch = True
    return s, ch

def patch_detail(s):
    if "and climbs to" in s: return s, False
    s = s.replace(
        "  const [suggested, setSuggested] = useState<{ tier: number | null; name: string | null; amount: number } | null>(null);",
        "  const [suggested, setSuggested] = useState<{ tier: number | null; name: string | null; amount: number; finalName?: string | null; mustClimb?: boolean } | null>(null);", 1)
    s = s.replace(
        '''      setSuggested({ tier: r.suggested_tier, name: r.suggested_name, amount: r.amount });
      if (r.suggested_tier != null) setEntryTier(r.suggested_tier);''',
        '''      setSuggested({ tier: r.entry_tier ?? r.suggested_tier, name: r.entry_name ?? r.suggested_name, amount: r.amount, finalName: r.final_name, mustClimb: r.must_climb });
      const preselect = r.entry_tier ?? r.suggested_tier;
      if (preselect != null) setEntryTier(preselect);''', 1)
    s = s.replace(
        '''        {suggested?.name && (
          <div className="mb-3 rounded bg-blue-50 px-3 py-2 text-xs text-blue-800">
            By limit, KES {suggested.amount.toLocaleString()} routes to <span className="font-semibold">{suggested.name}</span> (pre-selected). You can override below.
          </div>
        )}''',
        '''        {suggested?.name && (
          <div className="mb-3 rounded bg-blue-50 px-3 py-2 text-xs text-blue-800">
            {suggested.mustClimb ? (
              <>By limit, KES {suggested.amount.toLocaleString()} enters at <span className="font-semibold">{suggested.name}</span> and climbs to <span className="font-semibold">{suggested.finalName}</span> — each committee's verdict is captured before the next.</>
            ) : (
              <>By limit, KES {suggested.amount.toLocaleString()} is decided by <span className="font-semibold">{suggested.name}</span> (pre-selected). You can override below.</>
            )}
          </div>
        )}''', 1)
    return s, True

def patch_admin(s):
    if "Require MCC before Board" in s: return s, False
    s = s.replace("  seedCommitteePalette,\n  type CommitteeDef,",
                  "  seedCommitteePalette,\n  setRequireMcc,\n  type CommitteeDef,", 1)
    s = s.replace("  const [draft, setDraft] = useState<CommitteeDef | null>(null);",
                  "  const [draft, setDraft] = useState<CommitteeDef | null>(null);\n"
                  "  const [requireMcc, setRequireMccState] = useState(true);\n"
                  "  const [savingMcc, setSavingMcc] = useState(false);", 1)
    s = s.replace(
        '''      <Card><Card.Body>
        <div className="mb-3 flex justify-between">
          <p className="text-sm text-gray-600">{committees.length} committee(s)</p>''',
        '''      {/* C1b: ladder policy toggle */}
      <Card stripe="accent"><Card.Body>
        <label className="flex items-start gap-3 cursor-pointer">
          <input type="checkbox" checked={requireMcc} className="mt-1"
            onChange={async (e) => {
              const v = e.target.checked; setRequireMccState(v); setSavingMcc(true);
              try { await setRequireMcc(v); toast({ tone: 'success', message: 'Ladder policy saved.' }); }
              catch { toast({ tone: 'danger', message: 'Could not save.' }); setRequireMccState(!v); }
              finally { setSavingMcc(false); }
            }} disabled={savingMcc} />
          <div>
            <div className="text-sm font-medium text-gray-900">Require MCC before Board / Group</div>
            <div className="text-xs text-gray-500">When on (recommended), any case whose limit needs the Board or Group committee must first pass through the Management Credit Committee, whose verdict is captured before it climbs. When off, cases route directly to the committee their limit requires.</div>
          </div>
        </label>
      </Card.Body></Card>

      <Card><Card.Body>
        <div className="mb-3 flex justify-between">
          <p className="text-sm text-gray-600">{committees.length} committee(s)</p>''', 1)
    return s, True

def revert():
    for f in (API, DETAIL, ADMIN):
        b = f.with_suffix(f.suffix + ".pre_climb_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    files = []
    for f, fn in ((API, patch_api), (DETAIL, patch_detail), (ADMIN, patch_admin)):
        new, ch = fn(f.read_text(encoding="utf-8"))
        files.append((f, new, ch)); print(f"  {f.name}: {'change' if ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in files:
        if ch:
            b = f.with_suffix(f.suffix + ".pre_climb_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
