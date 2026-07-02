#!/usr/bin/env python3
"""scripts/apply_request_assignment_react.py — B2 React: request/resolve assignment.

- types/lms.ts: AssignmentRequest + app.assignment_requests
- api.ts: requestLmsAssignment / fetchAssignmentRequests + AssignmentRequestCase
- Lms.tsx: analyst "Request assignment" button (pool tab) + manager "Assignment
  requests" panel (one-click assign to requester or chosen analyst).

SAFE: .pre_reqasgn backups. Idempotent. --revert. TSC-gated.
"""
import sys, shutil, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = ROOT / "frontend" / "web" / "src" / "types" / "lms.ts"
API = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
LMS = ROOT / "frontend" / "web" / "src" / "pages" / "Lms.tsx"

def patch_types(s):
    if "assignment_requests" in s: return s, False
    s = s.replace(
        "  analyst?:               LoanApplicationAnalyst | null;",
        "  analyst?:               LoanApplicationAnalyst | null;\n  assignment_requests?:   AssignmentRequest[];", 1)
    s = s.replace(
        "export interface LoanApplication {",
        "export interface AssignmentRequest {\n  by_code: string;\n  by_name: string;\n  at:      string;\n  note?:   string;\n}\n\nexport interface LoanApplication {", 1)
    return s, True

def patch_api(s):
    if "requestLmsAssignment" in s: return s, False
    block = '''

// B2: assignment requests (analyst pull + manager resolve)
export interface AssignmentRequestCase {
  id: string; client_name?: string; product?: string; amount?: number;
  rm_name?: string; status?: string;
  requests: { by_code: string; by_name: string; at: string; note?: string }[];
}
export async function requestLmsAssignment(
  appId: string, note?: string,
): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, { note?: string }>(
    `/lms/applications/${encodeURIComponent(appId)}/request-assignment`, { note });
}
export async function fetchAssignmentRequests(): Promise<{ cases: AssignmentRequestCase[]; count: number }> {
  return getJson<{ cases: AssignmentRequestCase[]; count: number }>(
    '/lms/applications/assignment-requests');
}
'''
    return s.rstrip() + "\n" + block + "\n", True

def patch_lms(s):
    if "requestLmsAssignment" in s: return s, False

    # imports
    if "from '@/lib/api'" in s:
        s = re.sub(r"(import \{[^}]*)\} from '@/lib/api'",
                   r"\1, requestLmsAssignment, fetchAssignmentRequests, assignLmsAnalyst, fetchMyAnalysts, type AssignmentRequestCase, type AssignableAnalyst } from '@/lib/api'",
                   s, count=1)
    else:
        s = s.replace("import { useLmsApplications } from '@/hooks/useLmsApplications';",
                      "import { useLmsApplications } from '@/hooks/useLmsApplications';\n"
                      "import { requestLmsAssignment, fetchAssignmentRequests, assignLmsAnalyst, fetchMyAnalysts, type AssignmentRequestCase, type AssignableAnalyst } from '@/lib/api';", 1)
    if "useToast" not in s:
        s = s.replace("import { useLmsApplications } from '@/hooks/useLmsApplications';",
                      "import { useLmsApplications } from '@/hooks/useLmsApplications';\nimport { useToast } from '@/components/Toast';", 1)

    # state + doRequest
    anchor = "  const [tab, setTab] = useState<'mine' | 'pool' | 'all'>('all');"
    s = s.replace(anchor, anchor + '''
  const { toast } = useToast();
  const [requestBusy, setRequestBusy] = useState<string | null>(null);
  const isManagerRole = isAdmin || /chief|head|manager|officer|director|managing/.test(roleLc);
  const doRequest = async (appId: string) => {
    setRequestBusy(appId);
    try {
      await requestLmsAssignment(appId);
      toast({ tone: 'success', message: 'Assignment requested — the credit manager will action it.' });
      await refetch();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Request failed' });
    } finally { setRequestBusy(null); }
  };''', 1)

    # manager state + loader + assign
    marker = '''    } finally { setRequestBusy(null); }
  };'''
    s = s.replace(marker, marker + '''
  const [requestsCases, setRequestsCases] = useState<AssignmentRequestCase[]>([]);
  const [analystPool, setAnalystPool] = useState<AssignableAnalyst[]>([]);
  const [assignBusy, setAssignBusy] = useState<string | null>(null);
  const loadRequests = async () => {
    if (!isManagerRole) return;
    try { const r = await fetchAssignmentRequests(); setRequestsCases(r.cases); } catch { /* non-fatal */ }
    try { const a = await fetchMyAnalysts(); setAnalystPool(a.analysts); } catch { /* non-fatal */ }
  };
  useEffect(() => { void loadRequests(); /* eslint-disable-next-line */ }, [isManagerRole, applications]);
  const doAssign = async (appId: string, code: string, name: string) => {
    setAssignBusy(appId + code);
    try {
      await assignLmsAnalyst(appId, { analyst_code: code, analyst_name: name });
      toast({ tone: 'success', message: `Assigned to ${name}.` });
      await refetch();
      await loadRequests();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Assign failed' });
    } finally { setAssignBusy(null); }
  };''', 1)

    # analyst cell -> request button
    old_cell = '''                        <td className="px-4 py-3 text-gray-700 text-xs">
                          {app.analyst?.name || <span className="text-gray-400">unassigned</span>}
                        </td>'''
    new_cell = '''                        <td className="px-4 py-3 text-gray-700 text-xs">
                          {app.analyst?.name
                            ? app.analyst.name
                            : (tab === 'pool' && isPureAnalyst ? (
                              <button
                                onClick={(e) => { e.stopPropagation(); void doRequest(app.id); }}
                                disabled={requestBusy === app.id
                                  || (app.assignment_requests ?? []).some((r) => String(r.by_code) === myCode)}
                                className="rounded border border-brand-primary px-2 py-0.5 text-xs text-brand-primary hover:bg-brand-primary/5 disabled:opacity-50"
                              >
                                {(app.assignment_requests ?? []).some((r) => String(r.by_code) === myCode)
                                  ? 'Requested'
                                  : (requestBusy === app.id ? 'Requesting…' : 'Request assignment')}
                              </button>
                            ) : <span className="text-gray-400">unassigned</span>)}
                        </td>'''
    s = s.replace(old_cell, new_cell, 1)

    # manager panel
    anchor_panel = "        {/* ── Filter bar ─────────────────────────────────────────── */}"
    panel = '''        {/* B2: assignment requests (manager) */}
        {isManagerRole && requestsCases.length > 0 && (
          <Card className="mb-4" stripe="accent">
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">Assignment requests</h2>
              <Badge tone="warning" size="sm">{requestsCases.length}</Badge>
            </Card.Header>
            <Card.Body>
              <div className="space-y-3">
                {requestsCases.map((c) => (
                  <div key={c.id} className="rounded border p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <div>
                        <span className="font-mono text-xs text-gray-500">{c.id}</span>
                        <span className="ml-2 text-sm font-medium">{c.client_name}</span>
                        <span className="ml-2 text-xs text-gray-400">{c.product}</span>
                      </div>
                    </div>
                    <div className="space-y-1">
                      {c.requests.map((r) => (
                        <div key={r.by_code} className="flex items-center justify-between rounded bg-gray-50 px-2 py-1 text-sm">
                          <span>Requested by <span className="font-medium">{r.by_name}</span> ({r.by_code})</span>
                          <Button size="sm" onClick={() => void doAssign(c.id, r.by_code, r.by_name)}
                            disabled={assignBusy === c.id + r.by_code}>
                            {assignBusy === c.id + r.by_code ? 'Assigning…' : `Assign to ${r.by_name.split(' ')[0]}`}
                          </Button>
                        </div>
                      ))}
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <span className="text-xs text-gray-500">or assign someone else:</span>
                      <select
                        className="rounded border px-2 py-1 text-xs"
                        defaultValue=""
                        onChange={(e) => {
                          const a = analystPool.find((x) => x.staff_code === e.target.value);
                          if (a) void doAssign(c.id, a.staff_code, a.name);
                          e.target.value = '';
                        }}
                      >
                        <option value="">— pick analyst —</option>
                        {analystPool.map((a) => (
                          <option key={a.staff_code} value={a.staff_code}>{a.name} ({a.staff_code})</option>
                        ))}
                      </select>
                    </div>
                  </div>
                ))}
              </div>
            </Card.Body>
          </Card>
        )}

''' + anchor_panel
    s = s.replace(anchor_panel, panel, 1)

    return s, True

def revert():
    for f in (TYPES, API, LMS):
        b = f.with_suffix(f.suffix + ".pre_reqasgn")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    files = []
    for f, fn in ((TYPES, patch_types), (API, patch_api), (LMS, patch_lms)):
        s = f.read_text(encoding="utf-8")
        new, ch = fn(s)
        files.append((f, new, ch))
        print(f"  {f.name}: {'change' if ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in files:
        if ch:
            b = f.with_suffix(f.suffix + ".pre_reqasgn")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
