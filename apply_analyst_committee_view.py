#!/usr/bin/env python3
"""scripts/apply_analyst_committee_view.py — 4b-7b: analyst sees committee decisions.

A read-only "Branch Committee Decisions" view on the LMS application: the committee
records carried over from the deal (4b-7). The branch CR already shows via the
existing CreditReportCard (app['cr']).

- backend: GET /api/lms/applications/{app_id}/committee-records (read-only, from
  app['committee_records'] + app['committee_appeals'])
- api.ts: getLmsCommitteeRecords + type
- LmsApplicationDetail.tsx: read-only card.

SAFE: .pre_analystcmte backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
API_TS = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "LmsApplicationDetail.tsx"
API_BAK = API.with_suffix(".py.pre_analystcmte")
MARKER = "# === ANALYST COMMITTEE VIEW (4b-7b) ==="

API_BLOCK = r'''

# === ANALYST COMMITTEE VIEW (4b-7b) ===
@app.get("/api/lms/applications/{app_id}/committee-records", tags=["lms"])
def get_lms_committee_records(app_id: str, user: dict = Depends(get_current_user)):
    """Read-only branch committee decisions carried onto the application (4b-7)."""
    from utils.core import LoanApplicationManager
    lam = LoanApplicationManager()
    app_rec = lam.get(app_id)
    if not app_rec:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")
    return {
        "committee_records": app_rec.get("committee_records", {}) or {},
        "committee_appeals": app_rec.get("committee_appeals", []) or [],
        "cr_origin": app_rec.get("cr_origin", ""),
    }
# === END ANALYST COMMITTEE VIEW ===
'''

TS_BLOCK = '''
// analyst read-only view of branch committee decisions (4b-7b)
export interface LmsCommitteeRecordsResponse {
  committee_records: Record<string, {
    outcome: string; mode: string;
    votes: { name: string; role: string; vote: string }[];
    note?: string; recorded_by?: string; recorded_at?: string;
  }>;
  committee_appeals: { code: string; reason: string; outcome: string; by: string; at: string }[];
  cr_origin: string;
}
export async function getLmsCommitteeRecords(appId: string): Promise<LmsCommitteeRecordsResponse> {
  return getJson<LmsCommitteeRecordsResponse>(`/lms/applications/${appId}/committee-records`);
}
'''

CARD = '''
// ── Branch committee decisions (4b-7b): read-only, carried from the deal ──
function BranchCommitteeDecisionsCard({ appId }: { appId: string }) {
  const [data, setData] = useState<LmsCommitteeRecordsResponse | null>(null);
  useEffect(() => {
    getLmsCommitteeRecords(appId).then(setData).catch(() => setData(null));
  }, [appId]);
  if (!data) return null;
  const codes = Object.keys(data.committee_records || {});
  if (codes.length === 0) return null;
  const tone = (o: string) => (o === 'APPROVED' ? 'success' : o === 'REJECTED' ? 'danger' : 'warning');
  return (
    <Card className="mt-6">
      <Card.Header>
        <h2 className="text-base font-semibold text-gray-900">Branch Committee Decisions</h2>
        <Badge tone="info" size="sm">from branch</Badge>
      </Card.Header>
      <Card.Body>
        <p className="mb-3 text-xs text-gray-500">Recorded at the branch before submission (read-only).</p>
        <div className="space-y-3">
          {codes.map((code) => {
            const r = data.committee_records[code];
            return (
              <div key={code} className="rounded border p-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{code}</span>
                  <Badge tone={tone(r.outcome)} size="sm">{r.outcome}</Badge>
                </div>
                <p className="text-xs text-gray-500">Recorded by {r.recorded_by} on {r.recorded_at}.</p>
                {r.mode === 'voting' && r.votes.length > 0 && (
                  <ul className="mt-1 list-disc pl-5 text-xs text-gray-600">
                    {r.votes.map((v, i) => <li key={i}>{v.name} ({v.role}): {v.vote}</li>)}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      </Card.Body>
    </Card>
  );
}
'''

def patch_backend():
    s = API.read_text(encoding="utf-8")
    if MARKER in s:
        return s, False
    return s.rstrip() + "\n" + API_BLOCK + "\n", True

def patch_api_ts():
    s = API_TS.read_text(encoding="utf-8")
    if "getLmsCommitteeRecords" in s:
        return s, False
    return s.rstrip() + "\n" + TS_BLOCK + "\n", True

def patch_page():
    s = PAGE.read_text(encoding="utf-8")
    ch = False
    if "getLmsCommitteeRecords" not in s:
        s = s.replace("  getLmsCr, saveLmsCr, getCommitteeCharter, getCommitteeTiers,",
                      "  getLmsCr, saveLmsCr, getCommitteeCharter, getCommitteeTiers, getLmsCommitteeRecords, type LmsCommitteeRecordsResponse,", 1)
        ch = True
    # inject the card after the CreditReportCard render
    anchor = "        <CreditReportCard appId={application.id} canEdit={!!permissions.can_view} toast={toast} />"
    if anchor in s and "<BranchCommitteeDecisionsCard" not in s:
        s = s.replace(anchor, anchor + "\n        <BranchCommitteeDecisionsCard appId={application.id} />", 1)
        ch = True
    if "function BranchCommitteeDecisionsCard" not in s:
        s = s.rstrip() + "\n" + CARD + "\n"
        ch = True
    return s, ch

def revert():
    if API_BAK.exists():
        shutil.copy2(API_BAK, API); API_BAK.unlink(); print("  reverted api.py")
    for f in (API_TS, PAGE):
        b = f.with_suffix(f.suffix + ".pre_analystcmte")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    b, bc = patch_backend()
    a, ac = patch_api_ts()
    p, pc = patch_page()
    print(f"  api.py: {'change' if bc else 'skip'}")
    print(f"  api.ts: {'change' if ac else 'skip'}")
    print(f"  LmsApplicationDetail.tsx: {'change' if pc else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    if bc:
        if not API_BAK.exists(): API_BAK.write_text(API.read_text(encoding="utf-8"), encoding="utf-8")
        API.write_text(b, encoding="utf-8")
    for f, new, ch in ((API_TS, a, ac), (PAGE, p, pc)):
        if ch:
            bb = f.with_suffix(f.suffix + ".pre_analystcmte")
            if not bb.exists(): bb.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
