#!/usr/bin/env python3
"""scripts/apply_committee_capture_react.py — 4b-4 React: committee decision capture.

A "Credit Committee Journey" card on the deal detail page showing each gate in the
deal's journey with its recorded decision, or a form to record one:
  - voting mode: per-member votes (name/role/YES-NO-ABSTAIN); outcome derived server-side
  - single mode: an outcome dropdown (APPROVED/REJECTED/DEFERRED)

- api.ts: getDealCommitteeRecords / recordDealCommitteeDecision + types
- PipelineDealDetail.tsx: CommitteeJourneyCard component + injection.

SAFE: .pre_cmtecap_ui backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_TS = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "PipelineDealDetail.tsx"

API_BLOCK = '''
// committee decision capture on the deal (4b-4)
export interface CommitteeVote { name: string; role: string; vote: string; }
export interface CommitteeRecord {
  outcome: string; mode: string; votes: CommitteeVote[];
  note?: string; recorded_by?: string; recorded_at?: string;
}
export interface CommitteeGate {
  code: string; name: string; recording_mode: string; voting_rule: string;
  members: { name: string; role: string }[];
  record: CommitteeRecord | null;
}
export interface CommitteeRecordsResponse { gates: CommitteeGate[]; cr_only: boolean; }
export async function getDealCommitteeRecords(dealId: string): Promise<CommitteeRecordsResponse> {
  return getJson<CommitteeRecordsResponse>(`/pipeline/deals/${encodeURIComponent(dealId)}/committee-records`);
}
export async function recordDealCommitteeDecision(
  dealId: string,
  body: { code: string; outcome?: string; votes?: CommitteeVote[]; note?: string },
): Promise<{ status: string; code: string; record: CommitteeRecord }> {
  return postJson<{ status: string; code: string; record: CommitteeRecord }, typeof body>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/committee-records`, body);
}
'''

CARD = '''
// ── Committee Journey capture (4b-4): record each gate's decision on the deal ──
function CommitteeJourneyCard({ dealId, canEdit }: { dealId: string; canEdit: boolean }) {
  const { toast } = useToast();
  const [data, setData] = useState<CommitteeRecordsResponse | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [voteDraft, setVoteDraft] = useState<Record<string, CommitteeVote[]>>({});
  const [outcomeDraft, setOutcomeDraft] = useState<Record<string, string>>({});

  const load = async () => {
    try { setData(await getDealCommitteeRecords(dealId)); } catch { /* non-fatal */ }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, [dealId]);

  if (!data || data.cr_only) return null;

  const setVote = (code: string, i: number, field: keyof CommitteeVote, value: string) => {
    setVoteDraft((p) => {
      const gate = data.gates.find((g) => g.code === code);
      const base = p[code] ?? (gate?.members ?? []).map((m) => ({ name: m.name, role: m.role, vote: '' }));
      const arr = base.map((v, j) => (j === i ? { ...v, [field]: value } : v));
      return { ...p, [code]: arr };
    });
  };

  const votesFor = (gate: CommitteeGate): CommitteeVote[] =>
    voteDraft[gate.code] ?? (gate.members ?? []).map((m) => ({ name: m.name, role: m.role, vote: '' }));

  const recordVoting = async (gate: CommitteeGate) => {
    const votes = votesFor(gate).filter((v) => v.vote);
    if (votes.length === 0) { toast({ tone: 'danger', message: 'Record at least one vote.' }); return; }
    setBusy(gate.code);
    try {
      await recordDealCommitteeDecision(dealId, { code: gate.code, votes });
      toast({ tone: 'success', message: `${gate.code} decision recorded.` });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Failed' });
    } finally { setBusy(null); }
  };

  const recordSingle = async (gate: CommitteeGate) => {
    const outcome = outcomeDraft[gate.code];
    if (!outcome) { toast({ tone: 'danger', message: 'Pick an outcome.' }); return; }
    setBusy(gate.code);
    try {
      await recordDealCommitteeDecision(dealId, { code: gate.code, outcome });
      toast({ tone: 'success', message: `${gate.code} decision recorded.` });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Failed' });
    } finally { setBusy(null); }
  };

  const outcomeTone = (o: string) => (o === 'APPROVED' ? 'success' : o === 'REJECTED' ? 'danger' : 'warning');

  return (
    <Card className="mt-6">
      <Card.Header>
        <h2 className="text-base font-semibold text-gray-900">Credit Committee Journey</h2>
        <Badge tone="info" size="sm">{data.gates.length} gate{data.gates.length === 1 ? '' : 's'}</Badge>
      </Card.Header>
      <Card.Body>
        <div className="space-y-4">
          {data.gates.map((gate) => (
            <div key={gate.code} className="rounded border p-3">
              <div className="mb-2 flex items-center justify-between">
                <div>
                  <span className="text-sm font-semibold">{gate.code} — {gate.name}</span>
                  <span className="ml-2 text-xs text-gray-400">
                    {gate.recording_mode === 'voting' ? `voting · ${gate.voting_rule}` : 'single record'}
                  </span>
                </div>
                {gate.record && <Badge tone={outcomeTone(gate.record.outcome)} size="sm">{gate.record.outcome}</Badge>}
              </div>

              {gate.record ? (
                <div className="text-xs text-gray-600">
                  Recorded by {gate.record.recorded_by} on {gate.record.recorded_at}.
                  {gate.record.mode === 'voting' && gate.record.votes.length > 0 && (
                    <ul className="mt-1 list-disc pl-5">
                      {gate.record.votes.map((v, i) => (
                        <li key={i}>{v.name} ({v.role}): {v.vote}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ) : canEdit ? (
                gate.recording_mode === 'voting' ? (
                  <div>
                    {(gate.members ?? []).length === 0 && (
                      <p className="mb-2 text-xs text-amber-600">No members configured for this committee — add them in Credit Committees admin.</p>
                    )}
                    <div className="space-y-1">
                      {votesFor(gate).map((v, i) => (
                        <div key={i} className="flex items-center gap-2 text-sm">
                          <input className="w-1/3 rounded border px-2 py-1 text-xs" placeholder="Name" value={v.name}
                            onChange={(e) => setVote(gate.code, i, 'name', e.target.value)} />
                          <input className="w-1/3 rounded border px-2 py-1 text-xs" placeholder="Role" value={v.role}
                            onChange={(e) => setVote(gate.code, i, 'role', e.target.value)} />
                          <select className="w-1/3 rounded border px-2 py-1 text-xs" value={v.vote}
                            onChange={(e) => setVote(gate.code, i, 'vote', e.target.value)}>
                            <option value="">— vote —</option>
                            <option value="YES">YES</option>
                            <option value="NO">NO</option>
                            <option value="ABSTAIN">ABSTAIN</option>
                            <option value="RECUSED">RECUSED</option>
                          </select>
                        </div>
                      ))}
                    </div>
                    <div className="mt-2 flex justify-end">
                      <Button size="sm" onClick={() => void recordVoting(gate)} disabled={busy === gate.code}>
                        {busy === gate.code ? 'Recording…' : 'Record votes'}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <select className="rounded border px-2 py-1.5 text-sm"
                      value={outcomeDraft[gate.code] ?? ''}
                      onChange={(e) => setOutcomeDraft((p) => ({ ...p, [gate.code]: e.target.value }))}>
                      <option value="">— outcome —</option>
                      <option value="APPROVED">APPROVED</option>
                      <option value="REJECTED">REJECTED</option>
                      <option value="DEFERRED">DEFERRED</option>
                    </select>
                    <Button size="sm" onClick={() => void recordSingle(gate)} disabled={busy === gate.code}>
                      {busy === gate.code ? 'Recording…' : 'Record decision'}
                    </Button>
                  </div>
                )
              ) : (
                <p className="text-xs text-gray-400">Not yet decided.</p>
              )}
            </div>
          ))}
        </div>
      </Card.Body>
    </Card>
  );
}
'''

def patch_api():
    s = API_TS.read_text(encoding="utf-8")
    if "getDealCommitteeRecords" in s:
        return s, False
    return s.rstrip() + "\n" + API_BLOCK + "\n", True

def patch_page():
    s = PAGE.read_text(encoding="utf-8")
    ch = False
    if "getDealCommitteeRecords" not in s:
        s = s.replace("import { fetchPipelineDealDetail, fetchCreditChecklist, getDealCr, saveDealCr,",
                      "import { fetchPipelineDealDetail, fetchCreditChecklist, getDealCr, saveDealCr, getDealCommitteeRecords, recordDealCommitteeDecision, type CommitteeGate, type CommitteeVote, type CommitteeRecordsResponse,", 1)
        ch = True
    if "<CommitteeJourneyCard" not in s:
        anchor = "      <DealCreditReportCard dealId={deal.id} canEdit={true} />"
        if anchor in s:
            s = s.replace(anchor, anchor + "\n      <CommitteeJourneyCard dealId={deal.id} canEdit={true} />", 1)
            ch = True
    if "function CommitteeJourneyCard" not in s:
        s = s.rstrip() + "\n" + CARD + "\n"
        ch = True
    return s, ch

def revert():
    for f in (API_TS, PAGE):
        b = f.with_suffix(f.suffix + ".pre_cmtecap_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    a, ac = patch_api()
    p, pc = patch_page()
    print(f"  api.ts: {'change' if ac else 'skip'}")
    print(f"  PipelineDealDetail.tsx: {'change' if pc else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in ((API_TS, a, ac), (PAGE, p, pc)):
        if ch:
            b = f.with_suffix(f.suffix + ".pre_cmtecap_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
