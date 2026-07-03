#!/usr/bin/env python3
"""scripts/apply_troops_actions_react.py — CA1: Trops disbursement actions.

The Trops page gains an actionable disbursement queue: each cleared case shows
Book -> Value-date -> Disburse based on its troops_status, wired to the existing
backend endpoints. Unblocks the final leg of create->disbursement in the UI.

- api.ts: troops queue + book/value-date/disburse fetchers
- Troops.tsx: TroopsActionQueue card + render

Frontend-only (backend endpoints exist). SAFE: .pre_troopsact backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
TROOPS = ROOT / "frontend" / "web" / "src" / "pages" / "Troops.tsx"

def patch_api(s):
    if "fetchTroopsQueue" in s: return s, False
    block = '''
// CA1: Troops disbursement queue + the 3 actions (book -> value-date -> disburse)
export interface TroopsQueueCase {
  case_id: string; application_id?: string; client_name?: string; amount?: number;
  rm_code?: string; troops_status: string; cbs_account_no?: string | null;
  value_date?: string | null; disbursed: boolean; disbursement_date?: string | null;
}
export interface TroopsQueueResponse { cases: TroopsQueueCase[]; count: number; source: string; }
export async function fetchTroopsQueue(): Promise<TroopsQueueResponse> {
  return getJson<TroopsQueueResponse>('/credit-admin/troops/queue');
}
export async function troopsBook(caseId: string, cbsAccountNo?: string): Promise<{ troops_status: string }> {
  return postJson<{ troops_status: string }, { cbs_account_no?: string }>(
    `/credit-admin/cases/${encodeURIComponent(caseId)}/troops/book`, { cbs_account_no: cbsAccountNo });
}
export async function troopsValueDate(caseId: string, valueDate: string): Promise<{ troops_status: string }> {
  return postJson<{ troops_status: string }, { value_date: string }>(
    `/credit-admin/cases/${encodeURIComponent(caseId)}/troops/value-date`, { value_date: valueDate });
}
export async function troopsDisburse(caseId: string, glReference?: string): Promise<{ troops_status: string }> {
  return postJson<{ troops_status: string }, { gl_reference?: string }>(
    `/credit-admin/cases/${encodeURIComponent(caseId)}/troops/disburse`, { gl_reference: glReference });
}
'''
    return s.rstrip() + "\n" + block + "\n", True

def patch_troops(s):
    if "TroopsActionQueue" in s: return s, False
    if "useToast" not in s:
        s = s.replace("import { Card } from '@/components/Card';",
                      "import { Card } from '@/components/Card';\nimport { Button } from '@/components/Button';\nimport { useToast } from '@/components/Toast';", 1)
    s = s.replace(
        "import { fetchTroopsFlowByStage, type TroopsFlowByStageResponse } from '@/lib/api';",
        "import { fetchTroopsFlowByStage, fetchTroopsQueue, troopsBook, troopsValueDate, troopsDisburse, type TroopsFlowByStageResponse, type TroopsQueueCase } from '@/lib/api';", 1)
    s = s.replace(
        '''          </Card.Body>
        </Card>

      </div>
    </>''',
        '''          </Card.Body>
        </Card>

        <TroopsActionQueue />

      </div>
    </>''', 1)
    comp = '''

// CA1: the actionable disbursement queue — book -> value-date -> disburse.
function TroopsActionQueue() {
  const { toast } = useToast();
  const [cases, setCases] = useState<TroopsQueueCase[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [vd, setVd] = useState<Record<string, string>>({});
  const load = async () => {
    try { const r = await fetchTroopsQueue(); setCases(r.cases); }
    catch { /* forbidden or empty — the flow view above still shows */ }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, []);
  const act = async (id: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(id);
    try { await fn(); toast({ tone: 'success', message: ok }); await load(); }
    catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed' }); }
    finally { setBusy(null); }
  };
  if (cases.length === 0) return null;
  return (
    <Card>
      <Card.Header>
        <h2 className="text-base font-semibold text-gray-900">Disbursement queue — actions</h2>
        <span className="text-xs text-gray-400">Book → value-date → disburse</span>
      </Card.Header>
      <Card.Body>
        <div className="space-y-2">
          {cases.map((c) => {
            const st = String(c.troops_status || 'queued').toLowerCase();
            return (
              <div key={c.case_id} className="flex items-center justify-between rounded border p-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium">{c.client_name || c.case_id}</div>
                  <div className="text-xs text-gray-500">
                    {c.case_id} · KES {(c.amount ?? 0).toLocaleString()}
                    {c.cbs_account_no && ` · a/c ${c.cbs_account_no}`}
                    {c.value_date && ` · value ${c.value_date}`}
                    {' · '}<span className="font-medium">{st}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {st === 'queued' && (
                    <Button size="sm" disabled={busy === c.case_id}
                      onClick={() => void act(c.case_id, () => troopsBook(c.case_id), 'Facility booked to core banking.')}>
                      {busy === c.case_id ? '…' : 'Book'}
                    </Button>
                  )}
                  {st === 'booked' && (
                    <>
                      <input type="date" className="rounded border px-2 py-1 text-xs"
                        value={vd[c.case_id] ?? ''} onChange={(e) => setVd({ ...vd, [c.case_id]: e.target.value })} />
                      <Button size="sm" disabled={busy === c.case_id || !vd[c.case_id]}
                        onClick={() => void act(c.case_id, () => troopsValueDate(c.case_id, vd[c.case_id]), 'Value date set.')}>
                        Value-date
                      </Button>
                    </>
                  )}
                  {st === 'value_dated' && (
                    <Button size="sm" disabled={busy === c.case_id}
                      onClick={() => void act(c.case_id, () => troopsDisburse(c.case_id), 'Disbursed — posted to GL.')}>
                      {busy === c.case_id ? '…' : 'Disburse'}
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </Card.Body>
    </Card>
  );
}'''
    s = s.rstrip() + "\n" + comp + "\n"
    return s, True

def revert():
    for f in (API, TROOPS):
        b = f.with_suffix(f.suffix + ".pre_troopsact")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    files = []
    for f, fn in ((API, patch_api), (TROOPS, patch_troops)):
        new, ch = fn(f.read_text(encoding="utf-8"))
        files.append((f, new, ch)); print(f"  {f.name}: {'change' if ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in files:
        if ch:
            b = f.with_suffix(f.suffix + ".pre_troopsact")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
