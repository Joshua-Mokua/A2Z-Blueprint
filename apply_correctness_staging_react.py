#!/usr/bin/env python3
"""scripts/apply_correctness_staging_react.py — C2 React: correctness-staging UI.

- types/lms.ts: purpose on AssignAnalystRequest; assignment_purpose +
  committee_readiness (CommitteeReadiness) on the app.
- api.ts: setCommitteeReadiness.
- Lms.tsx: assign popover gains a purpose toggle (Decisioning | Correctness check);
  doAssign passes purpose.
- LmsApplicationDetail.tsx: purpose banner + readiness banner + CorrectnessPanel
  (mark ready / return for rework + opinion box) for the assigned correctness reviewer.

Layers on C-ASSIGN + B2. SAFE: .pre_correctness_ui backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = ROOT / "frontend" / "web" / "src" / "types" / "lms.ts"
API = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
LMS = ROOT / "frontend" / "web" / "src" / "pages" / "Lms.tsx"
DETAIL = ROOT / "frontend" / "web" / "src" / "pages" / "LmsApplicationDetail.tsx"

def patch_types(s):
    if "assignment_purpose" in s: return s, False
    s = s.replace(
        "  assignment_requests?:   AssignmentRequest[];",
        "  assignment_requests?:   AssignmentRequest[];\n"
        "  assignment_purpose?:    string;  // C2: 'decisioning' | 'correctness'\n"
        "  committee_readiness?:   CommitteeReadiness | null;", 1)
    s = s.replace(
        "export interface LoanApplication {",
        "export interface CommitteeReadiness {\n"
        "  state: 'ready_for_committee' | 'returned_for_rework';\n"
        "  by_code: string;\n  by_name: string;\n  at: string;\n"
        "  opinion?: string;\n  reasons?: string[];\n}\n\n"
        "export interface LoanApplication {", 1)
    s = s.replace(
        '''export interface AssignAnalystRequest {
  analyst_code:           string;
  analyst_name:           string;
}''',
        '''export interface AssignAnalystRequest {
  analyst_code:           string;
  analyst_name:           string;
  purpose?:               'decisioning' | 'correctness';  // C2
}''', 1)
    return s, True

def patch_api(s):
    if "setCommitteeReadiness" in s: return s, False
    block = '''
// C2: correctness-staging readiness (ready for committee / return for rework)
export async function setCommitteeReadiness(
  appId: string, decision: 'ready' | 'rework', opinion?: string, reasons?: string[],
): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, { decision: string; opinion?: string; reasons?: string[] }>(
    `/lms/applications/${encodeURIComponent(appId)}/committee-readiness`,
    { decision, opinion, reasons });
}
'''
    return s.rstrip() + "\n" + block + "\n", True

def patch_lms(s):
    if "assignPurpose" in s: return s, False
    s = s.replace(
        '''  const doAssign = async (appId: string, code: string, name: string) => {
    setAssignBusy(appId + code);
    try {
      await assignLmsAnalyst(appId, { analyst_code: code, analyst_name: name });
      toast({ tone: 'success', message: `Assigned to ${name}.` });''',
        '''  const doAssign = async (appId: string, code: string, name: string, purpose: 'decisioning' | 'correctness' = 'decisioning') => {
    setAssignBusy(appId + code);
    try {
      await assignLmsAnalyst(appId, { analyst_code: code, analyst_name: name, purpose });
      toast({ tone: 'success', message: purpose === 'correctness' ? `Assigned to ${name} for correctness check.` : `Assigned to ${name} for decisioning.` });''', 1)
    s = s.replace(
        "  const [assignMenuFor, setAssignMenuFor] = useState<string | null>(null);",
        "  const [assignMenuFor, setAssignMenuFor] = useState<string | null>(null);\n"
        "  const [assignPurpose, setAssignPurpose] = useState<'decisioning' | 'correctness'>('decisioning');", 1)
    s = s.replace(
        '''                                {assignMenuFor === app.id && (
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
                                    </select>''',
        '''                                {assignMenuFor === app.id && (
                                  <div className="absolute right-0 z-10 mt-1 w-64 rounded-md border border-gray-200 bg-white p-2 shadow-lg">
                                    <div className="mb-1 text-xs font-medium text-gray-500">Purpose</div>
                                    <div className="mb-2 flex gap-1">
                                      {(['decisioning', 'correctness'] as const).map((pp) => (
                                        <button key={pp}
                                          onClick={() => setAssignPurpose(pp)}
                                          className={`flex-1 rounded px-2 py-1 text-xs ${
                                            assignPurpose === pp ? 'bg-brand-primary text-white' : 'bg-gray-100 text-gray-700'}`}>
                                          {pp === 'decisioning' ? 'Decisioning' : 'Correctness check'}
                                        </button>
                                      ))}
                                    </div>
                                    <div className="mb-1 text-xs font-medium text-gray-500">To</div>
                                    <select
                                      className="mb-2 w-full rounded border px-2 py-1 text-xs"
                                      defaultValue=""
                                      onChange={(e) => {
                                        const a = analystPool.find((x) => x.staff_code === e.target.value);
                                        if (a) { void doAssign(app.id, a.staff_code, a.name, assignPurpose); setAssignMenuFor(null); }
                                      }}
                                    >
                                      <option value="">— pick person —</option>
                                      {analystPool.map((a) => (
                                        <option key={a.staff_code} value={a.staff_code}>{a.name}</option>
                                      ))}
                                    </select>''', 1)
    return s, True

def patch_detail(s):
    if "CorrectnessPanel" in s: return s, False
    if "useRole" not in s:
        s = s.replace("import { useToast } from '@/components/Toast';",
                      "import { useToast } from '@/components/Toast';\nimport { useRole } from '@/hooks/useRole';", 1)
    s = s.replace(
        "  getLmsCr, saveLmsCr, getCommitteeCharter, getCommitteeTiers, fetchCommitteeRouting, getLmsCommitteeRecords, fetchMyAnalysts, type LmsCommitteeRecordsResponse, type AssignableAnalyst,",
        "  getLmsCr, saveLmsCr, getCommitteeCharter, getCommitteeTiers, fetchCommitteeRouting, getLmsCommitteeRecords, fetchMyAnalysts, setCommitteeReadiness, type LmsCommitteeRecordsResponse, type AssignableAnalyst,", 1)
    s = s.replace(
        "  const { toast } = useToast();\n\n  const { application, permissions, loading, error, refetch } =",
        "  const { toast } = useToast();\n  const { user } = useRole();\n\n  const { application, permissions, loading, error, refetch } =", 1)
    anchor = '''        {/* ─────────── ACTION: Assign Analyst (if can_assign) ─────────── */}
        {permissions.can_assign && (
          <ActionPanelAssign
            appId={application.id}
            open={assignOpen}
            setOpen={setAssignOpen}
            mutations={mutations}
            onSuccess={async () => {
              await refetch();
              setAssignOpen(false);
              toast({ tone: 'success', message: 'Analyst assigned.' });
            }}
            toast={toast}
          />
        )}'''
    inject = anchor + '''

        {/* C2: assignment purpose banner + correctness action set */}
        {application.assignment_purpose && (
          <div className={`mt-4 rounded-md px-4 py-2 text-sm ${
            application.assignment_purpose === 'correctness'
              ? 'bg-amber-50 text-amber-800' : 'bg-blue-50 text-blue-800'}`}>
            {application.assignment_purpose === 'correctness'
              ? 'Assigned for correctness check — confirm the case is well-packaged (CR complete, docs attached) and mark it ready for committee, or return it for rework.'
              : 'Assigned for decisioning — analyse the case and record the credit decision.'}
          </div>
        )}
        {application.committee_readiness && (
          <div className={`mt-2 rounded-md px-4 py-2 text-xs ${
            application.committee_readiness.state === 'ready_for_committee'
              ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
            {application.committee_readiness.state === 'ready_for_committee'
              ? `Ready for committee — checked by ${application.committee_readiness.by_name}`
              : `Returned for rework — by ${application.committee_readiness.by_name}`}
            {application.committee_readiness.opinion
              && <div className="mt-1 italic">Opinion: {application.committee_readiness.opinion}</div>}
          </div>
        )}
        {application.assignment_purpose === 'correctness'
          && String(application.analyst?.code ?? '') === String(user?.staff_code ?? '')
          && (
          <CorrectnessPanel appId={application.id} onDone={refetch} toast={toast} />
        )}'''
    s = s.replace(anchor, inject, 1)
    comp = '''

// C2: correctness-check action set — mark ready for committee or return for rework,
// with an optional opinion for the Chief.
function CorrectnessPanel({ appId, onDone, toast }: {
  appId: string; onDone: () => Promise<unknown> | unknown; toast: (t: { tone: 'success' | 'danger'; message: string }) => void;
}) {
  const [opinion, setOpinion] = useState('');
  const [busy, setBusy] = useState(false);
  const act = async (decision: 'ready' | 'rework') => {
    setBusy(true);
    try {
      await setCommitteeReadiness(appId, decision, opinion.trim() || undefined);
      toast({ tone: 'success', message: decision === 'ready' ? 'Marked ready for committee.' : 'Returned for rework.' });
      await onDone();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed' });
    } finally { setBusy(false); }
  };
  return (
    <Card className="mt-4" stripe="accent">
      <Card.Header><h3 className="text-sm font-semibold text-gray-900">Correctness check</h3></Card.Header>
      <Card.Body>
        <p className="mb-2 text-xs text-gray-500">Confirm the case is well-packaged for committee, or return it for rework. You may add an opinion for the Chief.</p>
        <textarea
          value={opinion}
          onChange={(e) => setOpinion(e.target.value)}
          placeholder="Optional opinion / notes for the Chief…"
          className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
          rows={3}
        />
        <div className="flex gap-2">
          <Button variant="primary" onClick={() => void act('ready')} disabled={busy}>Mark ready for committee</Button>
          <Button variant="ghost" onClick={() => void act('rework')} disabled={busy}>Return for rework</Button>
        </div>
      </Card.Body>
    </Card>
  );
}'''
    s = s.rstrip() + "\n" + comp + "\n"
    return s, True

def revert():
    for f in (TYPES, API, LMS, DETAIL):
        b = f.with_suffix(f.suffix + ".pre_correctness_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    files = []
    for f, fn in ((TYPES, patch_types), (API, patch_api), (LMS, patch_lms), (DETAIL, patch_detail)):
        new, ch = fn(f.read_text(encoding="utf-8"))
        files.append((f, new, ch)); print(f"  {f.name}: {'change' if ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in files:
        if ch:
            b = f.with_suffix(f.suffix + ".pre_correctness_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
