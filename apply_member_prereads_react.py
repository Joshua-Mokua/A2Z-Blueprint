#!/usr/bin/env python3
"""scripts/apply_member_prereads_react.py — C3b React: committee pre-read panel.

On a referred case, a CommitteePreReadPanel lets members record a non-binding view
(leaning approve/decline/questions + note); everyone sees the tally + individual
leanings. Layers on C3a. SAFE: .pre_mprq_ui backups. Idempotent. --revert. TSC-gated.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
DETAIL = ROOT / "frontend" / "web" / "src" / "pages" / "LmsApplicationDetail.tsx"

def patch_api(s):
    if "recordCommitteePreRead" in s: return s, False
    block = '''
// C3b: committee pre-read (member non-binding view)
export interface CommitteePreRead {
  by_code: string; by_name: string; view: 'leaning_approve' | 'leaning_decline' | 'questions';
  note?: string; at: string; tier?: number | null;
}
export interface CommitteePreReadsResponse {
  pre_reads: CommitteePreRead[]; all: CommitteePreRead[];
  tally: Record<string, number>; current_tier: number | null;
}
export async function recordCommitteePreRead(
  appId: string, view: 'leaning_approve' | 'leaning_decline' | 'questions', note?: string,
): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, { view: string; note?: string }>(
    `/lms/applications/${encodeURIComponent(appId)}/committee/pre-read`, { view, note });
}
export async function fetchCommitteePreReads(appId: string): Promise<CommitteePreReadsResponse> {
  return getJson<CommitteePreReadsResponse>(
    `/lms/applications/${encodeURIComponent(appId)}/committee/pre-reads`);
}
'''
    return s.rstrip() + "\n" + block + "\n", True

def patch_detail(s):
    if "CommitteePreReadPanel" in s: return s, False
    s = s.replace(
        "  getLmsCr, saveLmsCr, getCommitteeCharter, getCommitteeTiers, fetchCommitteeRouting, getLmsCommitteeRecords, fetchMyAnalysts, setCommitteeReadiness, type LmsCommitteeRecordsResponse, type AssignableAnalyst,",
        "  getLmsCr, saveLmsCr, getCommitteeCharter, getCommitteeTiers, fetchCommitteeRouting, getLmsCommitteeRecords, fetchMyAnalysts, setCommitteeReadiness, recordCommitteePreRead, fetchCommitteePreReads, type CommitteePreReadsResponse, type LmsCommitteeRecordsResponse, type AssignableAnalyst,", 1)
    s = s.replace(
        "        <BranchCommitteeDecisionsCard appId={application.id} />",
        '''        <BranchCommitteeDecisionsCard appId={application.id} />
        {application.status === 'referred_to_committee' && (
          <CommitteePreReadPanel appId={application.id} toast={toast} />
        )}''', 1)
    comp = '''

// C3b: committee pre-read — members record a non-binding view; everyone sees leanings.
function CommitteePreReadPanel({ appId, toast }: {
  appId: string; toast: (t: { tone: 'success' | 'danger'; message: string }) => void;
}) {
  const [data, setData] = useState<CommitteePreReadsResponse | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const load = async () => {
    try { setData(await fetchCommitteePreReads(appId)); } catch { /* non-fatal */ }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, [appId]);
  const record = async (view: 'leaning_approve' | 'leaning_decline' | 'questions') => {
    setBusy(true);
    try {
      await recordCommitteePreRead(appId, view, note.trim() || undefined);
      toast({ tone: 'success', message: 'Pre-read recorded.' });
      setNote(''); await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not record' });
    } finally { setBusy(false); }
  };
  const label: Record<string, string> = {
    leaning_approve: 'Leaning approve', leaning_decline: 'Leaning decline', questions: 'Questions',
  };
  return (
    <Card className="mt-4" stripe="accent">
      <Card.Header><h3 className="text-sm font-semibold text-gray-900">Committee pre-read (non-binding)</h3></Card.Header>
      <Card.Body>
        <p className="mb-2 text-xs text-gray-500">Members review independently ahead of the convened meeting. This is a non-binding leaning, not the vote.</p>
        {data && (
          <div className="mb-3 flex gap-3 text-xs">
            <span className="rounded bg-green-50 px-2 py-1 text-green-700">Approve: {data.tally.leaning_approve ?? 0}</span>
            <span className="rounded bg-red-50 px-2 py-1 text-red-700">Decline: {data.tally.leaning_decline ?? 0}</span>
            <span className="rounded bg-amber-50 px-2 py-1 text-amber-700">Questions: {data.tally.questions ?? 0}</span>
          </div>
        )}
        <textarea value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="Optional note with your leaning…"
          className="mb-2 w-full rounded border border-gray-300 px-3 py-2 text-sm" rows={2} />
        <div className="flex gap-2">
          <Button variant="primary" size="sm" onClick={() => void record('leaning_approve')} disabled={busy}>Leaning approve</Button>
          <Button variant="ghost" size="sm" onClick={() => void record('leaning_decline')} disabled={busy}>Leaning decline</Button>
          <Button variant="ghost" size="sm" onClick={() => void record('questions')} disabled={busy}>Questions</Button>
        </div>
        {data && data.pre_reads.length > 0 && (
          <div className="mt-3 space-y-1">
            {data.pre_reads.map((r) => (
              <div key={r.by_code} className="rounded bg-gray-50 px-2 py-1 text-xs">
                <span className="font-medium">{r.by_name}</span>: {label[r.view] ?? r.view}
                {r.note && <span className="text-gray-500"> — {r.note}</span>}
              </div>
            ))}
          </div>
        )}
      </Card.Body>
    </Card>
  );
}'''
    s = s.rstrip() + "\n" + comp + "\n"
    return s, True

def revert():
    for f in (API, DETAIL):
        b = f.with_suffix(f.suffix + ".pre_mprq_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    files = []
    for f, fn in ((API, patch_api), (DETAIL, patch_detail)):
        new, ch = fn(f.read_text(encoding="utf-8"))
        files.append((f, new, ch)); print(f"  {f.name}: {'change' if ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in files:
        if ch:
            b = f.with_suffix(f.suffix + ".pre_mprq_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
