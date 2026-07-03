#!/usr/bin/env python3
"""scripts/apply_legal_charging_react.py — CA2 React: submit-to-legal-for-charging.

- api.ts: submitForCharging, fetchChargingQueue, fetchMyLegalOfficers + types
- types/creditAdmin.ts: LegalReview gains 'submitted_for_charging' + stamp fields
- components/SecuredLendingPanels.tsx: LegalReviewPanel gains a "Submit to legal for
  charging" action + the officer-assign becomes a dropdown from my-legal-officers
  (falls back to code entry if the pool is empty).

Layers on CA2 backend. SAFE: .pre_legalchg_ui backups. Idempotent. --revert. TSC-gated.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
TYPES = ROOT / "frontend" / "web" / "src" / "types" / "creditAdmin.ts"
SLP = ROOT / "frontend" / "web" / "src" / "components" / "SecuredLendingPanels.tsx"

def patch_api(s):
    if "submitForCharging" in s: return s, False
    block = '''
// CA2: submit-to-legal-for-charging + Legal Chief queue + officer pool
export const submitForCharging = (id: string, note?: string) =>
  caPost(id, 'legal/submit-for-charging', { note: note ?? '' });
export interface ChargingQueueCase {
  case_id: string; client_name?: string; amount?: number;
  submitted_at?: string; submitted_by?: string;
  assigned_officer_code?: string | null; assigned_officer_name?: string | null;
}
export interface ChargingQueueResponse { cases: ChargingQueueCase[]; count: number; }
export async function fetchChargingQueue(): Promise<ChargingQueueResponse> {
  return getJson<ChargingQueueResponse>('/credit-admin/legal/charging-queue');
}
export interface LegalOfficer { staff_code: string; name: string; role: string; unit: string; }
export interface LegalOfficersResponse { officers: LegalOfficer[]; count: number; }
export async function fetchMyLegalOfficers(): Promise<LegalOfficersResponse> {
  return getJson<LegalOfficersResponse>('/credit-admin/my-legal-officers');
}
'''
    return s.rstrip() + "\n" + block + "\n", True

def patch_types(s):
    if "submitted_for_charging" in s: return s, False
    s = s.replace(
        "export interface LegalReview {\n"
        "  status:                 'not_started' | 'in_review' | 'queries_raised' | 'cleared' | 'rejected';",
        "export interface LegalReview {\n"
        "  status:                 'not_started' | 'in_review' | 'queries_raised' | 'cleared' | 'rejected' | 'submitted_for_charging';", 1)
    s = s.replace(
        "  completed_by?:          string;\n}",
        "  completed_by?:          string;\n"
        "  submitted_for_charging_by?: string;\n"
        "  submitted_for_charging_at?: string;\n}", 1)
    return s, True

def patch_slp(s):
    if "submitForCharging" in s: return s, False
    s = s.replace("import { useState } from 'react';",
                  "import { useState, useEffect } from 'react';", 1)
    s = s.replace(
        "  legalAssign, legalComment, legalOutcome, addPerfection, updatePerfection,\n  addInsurance, ApiValidationError, AuthExpiredError,\n} from '@/lib/api';",
        "  legalAssign, legalComment, legalOutcome, addPerfection, updatePerfection,\n  addInsurance, ApiValidationError, AuthExpiredError,\n  submitForCharging, fetchMyLegalOfficers, type LegalOfficer,\n} from '@/lib/api';", 1)
    s = s.replace(
        '''  const { busy, run } = useAction(onChange);
  const [officer, setOfficer] = useState('');
  const [comment, setComment] = useState('');
  const lr = caseRecord.legal_review;
  if (caseRecord.facility_security_type !== 'secured') return null;
  return (
    <Card className="mt-6"><Card.Header>Legal review</Card.Header><Card.Body>
      <div className="flex items-center gap-2 mb-3 text-sm">
        <span className="text-gray-500">Status:</span>
        <Badge tone={lr?.outcome === 'rejected' ? 'danger' : lr?.outcome ? 'success' : 'neutral'}>
          {lr?.status || 'not_started'}</Badge>
        {lr?.outcome && <span className="text-gray-500">outcome: {lr.outcome}</span>}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end mb-3">
        <label className={lbl}><span className={cap}>Assign officer (code)</span>
          <Input value={officer} onChange={(e) => setOfficer(e.target.value)} placeholder="LO001" /></label>
        <Button disabled={busy || !officer.trim()} onClick={() => run(
          () => legalAssign(caseRecord.id, { officer_code: officer.trim() }), 'Legal officer assigned.')}>Assign</Button>
      </div>''',
        '''  const { busy, run } = useAction(onChange);
  const [officer, setOfficer] = useState('');
  const [comment, setComment] = useState('');
  const [officers, setOfficers] = useState<LegalOfficer[]>([]);
  const lr = caseRecord.legal_review;
  useEffect(() => {
    fetchMyLegalOfficers().then((r) => setOfficers(r.officers)).catch(() => { /* fallback to code entry */ });
  }, []);
  if (caseRecord.facility_security_type !== 'secured') return null;
  const submitted = lr?.status === 'submitted_for_charging';
  return (
    <Card className="mt-6"><Card.Header>Legal review</Card.Header><Card.Body>
      <div className="flex items-center gap-2 mb-3 text-sm">
        <span className="text-gray-500">Status:</span>
        <Badge tone={lr?.outcome === 'rejected' ? 'danger' : lr?.outcome ? 'success' : submitted ? 'brand' : 'neutral'}>
          {lr?.status || 'not_started'}</Badge>
        {lr?.outcome && <span className="text-gray-500">outcome: {lr.outcome}</span>}
      </div>
      {/* CA2: Credit Admin submits the case to Legal for charging */}
      <div className="mb-3 rounded border border-dashed border-gray-300 p-3">
        <div className="mb-2 text-xs text-gray-500">
          {submitted
            ? `Submitted to Legal for charging${lr?.submitted_for_charging_by ? ` by ${lr.submitted_for_charging_by}` : ''}. The Legal Chief assigns an officer below.`
            : 'Send this case to Legal for charging — it enters the Legal Chief\\'s charging queue.'}
        </div>
        <Button disabled={busy} onClick={() => run(
          () => submitForCharging(caseRecord.id), 'Submitted to Legal for charging.')}>
          {submitted ? 'Re-submit for charging' : 'Submit to legal for charging'}
        </Button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end mb-3">
        <label className={lbl}><span className={cap}>Assign officer</span>
          {officers.length > 0 ? (
            <select className="w-full rounded border px-2 py-1.5 text-sm" value={officer}
              onChange={(e) => setOfficer(e.target.value)}>
              <option value="">— pick legal officer —</option>
              {officers.map((o) => <option key={o.staff_code} value={o.staff_code}>{o.name} ({o.staff_code})</option>)}
            </select>
          ) : (
            <Input value={officer} onChange={(e) => setOfficer(e.target.value)} placeholder="LO001" />
          )}
        </label>
        <Button disabled={busy || !officer.trim()} onClick={() => {
          const picked = officers.find((o) => o.staff_code === officer.trim());
          return run(() => legalAssign(caseRecord.id,
            { officer_code: officer.trim(), officer_name: picked?.name ?? '' }), 'Legal officer assigned.');
        }}>Assign</Button>
      </div>''', 1)
    return s, True

def revert():
    for f in (API, TYPES, SLP):
        b = f.with_suffix(f.suffix + ".pre_legalchg_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    files = []
    for f, fn in ((API, patch_api), (TYPES, patch_types), (SLP, patch_slp)):
        new, ch = fn(f.read_text(encoding="utf-8"))
        files.append((f, new, ch)); print(f"  {f.name}: {'change' if ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in files:
        if ch:
            b = f.with_suffix(f.suffix + ".pre_legalchg_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
