#!/usr/bin/env python3
"""scripts/apply_committee_routing_react.py — C1 React: routing-aware refer panel.

The Chief's "Refer to credit committee" panel now shows the tier SUGGESTED by the
case amount (from GET committee-routing) and pre-selects it, while keeping override.

- api.ts: fetchCommitteeRouting + CommitteeRouting
- LmsApplicationDetail.tsx: WfReferCommittee loads routing, shows banner, pre-selects.

SAFE: .pre_crouting_ui backups. Idempotent. --revert. TSC-gated.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "LmsApplicationDetail.tsx"

def patch_api(s):
    if "fetchCommitteeRouting" in s: return s, False
    block = '''
// C1: committee routing suggestion (Chief routes by limit)
export interface CommitteeRouting {
  tiers: CommitteeTier[];
  amount: number;
  suggested_tier: number | null;
  suggested_name: string | null;
  can_refer: boolean;
  current_status: string;
}
export async function fetchCommitteeRouting(appId: string): Promise<CommitteeRouting> {
  return getJson<CommitteeRouting>(`/lms/applications/${encodeURIComponent(appId)}/committee-routing`);
}
'''
    return s.rstrip() + "\n" + block + "\n", True

def patch_page(s):
    if "fetchCommitteeRouting" in s: return s, False
    s = s.replace("getLmsCr, saveLmsCr, getCommitteeCharter, getCommitteeTiers,",
                  "getLmsCr, saveLmsCr, getCommitteeCharter, getCommitteeTiers, fetchCommitteeRouting,", 1)
    anchor = '''  const [tiers, setTiers] = useState<CommitteeTier[]>([]);
  const [entryTier, setEntryTier] = useState<number | ''>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getCommitteeTiers().then((r) => { if (live) setTiers(r.tiers || []); }).catch(() => {});
    return () => { live = false; };
  }, []);'''
    new = '''  const [tiers, setTiers] = useState<CommitteeTier[]>([]);
  const [entryTier, setEntryTier] = useState<number | ''>('');
  const [error, setError] = useState<string | null>(null);
  const [suggested, setSuggested] = useState<{ tier: number | null; name: string | null; amount: number } | null>(null);

  useEffect(() => {
    let live = true;
    getCommitteeTiers().then((r) => { if (live) setTiers(r.tiers || []); }).catch(() => {});
    fetchCommitteeRouting(appId).then((r) => {
      if (!live) return;
      setSuggested({ tier: r.suggested_tier, name: r.suggested_name, amount: r.amount });
      if (r.suggested_tier != null) setEntryTier(r.suggested_tier);
    }).catch(() => {});
    return () => { live = false; };
  }, [appId]);'''
    s = s.replace(anchor, new, 1)
    anchor_banner = '''        <p className="text-xs text-gray-500 mb-3">
          This facility is committee-tier under the bank's policy. Most cases enter at the Branch
          Credit Committee; CIB / head-office cases may enter a higher tier directly.
        </p>'''
    new_banner = anchor_banner + '''
        {suggested?.name && (
          <div className="mb-3 rounded bg-blue-50 px-3 py-2 text-xs text-blue-800">
            By limit, KES {suggested.amount.toLocaleString()} routes to <span className="font-semibold">{suggested.name}</span> (pre-selected). You can override below.
          </div>
        )}'''
    s = s.replace(anchor_banner, new_banner, 1)
    return s, True

def revert():
    for f in (API, PAGE):
        b = f.with_suffix(f.suffix + ".pre_crouting_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    files = []
    for f, fn in ((API, patch_api), (PAGE, patch_page)):
        new, ch = fn(f.read_text(encoding="utf-8"))
        files.append((f, new, ch))
        print(f"  {f.name}: {'change' if ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in files:
        if ch:
            b = f.with_suffix(f.suffix + ".pre_crouting_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
