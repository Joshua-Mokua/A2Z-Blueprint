#!/usr/bin/env python3
"""scripts/apply_deal_cr_react.py — 4b-3 React: deal-level CR form.

Adds a Credit Report card to the deal detail page (PipelineDealDetail), where the
deal owner fills the CR at the branch. Mirrors the LMS CR form, reusing the CrView
type. Deal CR endpoint returns CrView directly (not wrapped).

- api.ts: getDealCr / saveDealCr (return CrView)
- PipelineDealDetail.tsx: DealCreditReportCard component + injection before the
  submit panel.

SAFE: .pre_dealcr_ui backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_TS = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "PipelineDealDetail.tsx"

API_BLOCK = '''
// deal-level CR (4b-3): the CR originates at the branch on the deal.
export async function getDealCr(dealId: string): Promise<CrView> {
  return getJson<CrView>(`/pipeline/deals/${encodeURIComponent(dealId)}/cr`);
}
export async function saveDealCr(
  dealId: string, body: { values: Record<string, unknown>; completed?: boolean },
): Promise<CrView> {
  return postJson<CrView, typeof body>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/cr`, body);
}
'''

CARD_COMPONENT = '''
// ── Deal Credit Report (4b-3): CR originates at the branch, on the deal ──
function DealCreditReportCard({ dealId, canEdit }: { dealId: string; canEdit: boolean }) {
  const { toast } = useToast();
  const [cr, setCr] = useState<CrView | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const load = async () => {
    try { setCr(await getDealCr(dealId)); } catch { /* non-fatal */ }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, [dealId]);

  const valueFor = (key: string): string => {
    if (key in edits) return edits[key];
    const v = cr?.values?.[key];
    return v === undefined || v === null ? '' : String(v);
  };

  const save = async (completed: boolean) => {
    setBusy(true);
    try {
      await saveDealCr(dealId, { values: edits, completed });
      setEdits({});
      toast({ tone: 'success', message: completed ? 'CR marked complete.' : 'CR saved.' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Save failed.' });
    } finally { setBusy(false); }
  };

  if (!cr) return null;

  const sourceTint = (f: CrField, hasValue: boolean) => {
    if (f.source === 'cbs') return hasValue ? 'bg-blue-50/50' : '';
    if (f.source === 'auto') return hasValue ? 'bg-gray-50' : '';
    return '';
  };

  return (
    <Card className="mt-6">
      <Card.Header>
        <h2 className="text-base font-semibold text-gray-900">Credit Report (CR)</h2>
        <div className="flex items-center gap-2">
          {cr.completed && <Badge tone="success">Complete</Badge>}
          {!cr.cbs_available && <span className="text-xs text-gray-400">CBS data unavailable — fill manually</span>}
          <button className="text-sm text-brand-primary" onClick={() => setOpen((o) => !o)}>
            {open ? 'Hide' : 'Open'}
          </button>
        </div>
      </Card.Header>
      {open && (
        <Card.Body>
          <p className="text-xs text-gray-500 mb-4">
            Complete the CR at the branch (after documents). Blue = CBS, grey = deal;
            both editable. Plain fields are for the deal owner.
          </p>
          <div className="space-y-6">
            {cr.template.sections.map((sec) => (
              <div key={sec.key}>
                <div className="text-sm font-semibold text-gray-800 mb-2 pb-1 border-b border-gray-100">
                  {sec.title}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {sec.fields.map((f) => {
                    const val = valueFor(f.key);
                    const isLong = ['strengths', 'weaknesses', 'mitigants', 'rm_recommendation', 'conditions', 'purpose'].includes(f.key);
                    return (
                      <div key={f.key} className={isLong ? 'md:col-span-2' : ''}>
                        <label className="block text-xs text-gray-600 mb-1">
                          {f.label}{f.required && <span className="text-red-500"> *</span>}
                          {f.source !== 'rm' && <span className="ml-1 text-[10px] uppercase text-gray-400">({f.source})</span>}
                        </label>
                        {isLong ? (
                          <textarea
                            value={val} disabled={!canEdit || busy} rows={2}
                            onChange={(e) => setEdits((p) => ({ ...p, [f.key]: e.target.value }))}
                            className={`w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm ${sourceTint(f, !!val)}`}
                          />
                        ) : (
                          <input
                            value={val} disabled={!canEdit || busy}
                            onChange={(e) => setEdits((p) => ({ ...p, [f.key]: e.target.value }))}
                            className={`w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm ${sourceTint(f, !!val)}`}
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
          {canEdit && (
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => void save(false)} disabled={busy}>Save draft</Button>
              <Button onClick={() => void save(true)} disabled={busy}>Mark complete</Button>
            </div>
          )}
        </Card.Body>
      )}
    </Card>
  );
}
'''

def patch_api():
    s = API_TS.read_text(encoding="utf-8")
    if "getDealCr" in s:
        return s, False
    if "export interface CrView" not in s:
        return s, False
    return s.rstrip() + "\n" + API_BLOCK + "\n", True

def patch_page():
    s = PAGE.read_text(encoding="utf-8")
    ch = False
    # import CR fetchers + types
    if "getDealCr" not in s:
        # add to the existing @/lib/api import line
        anchor = "import { fetchPipelineDealDetail, fetchCreditChecklist,"
        s = s.replace(anchor,
                      "import { fetchPipelineDealDetail, fetchCreditChecklist, getDealCr, saveDealCr, type CrView, type CrField,", 1)
        ch = True
    # inject the card before the submit panel
    if "DealCreditReportCard" not in s.split("function DealCreditReportCard")[0]:
        # place the render before <CreditSubmissionPanel
        anchor = "      <CreditSubmissionPanel deal={deal} onChanged={() => void reloadDeal()} />"
        if anchor in s and "<DealCreditReportCard" not in s:
            s = s.replace(anchor,
                "      <DealCreditReportCard dealId={deal.id} canEdit={true} />\n" + anchor, 1)
            ch = True
    # append the component definition at end of file
    if "function DealCreditReportCard" not in s:
        s = s.rstrip() + "\n" + CARD_COMPONENT + "\n"
        ch = True
    return s, ch

def revert():
    for f in (API_TS, PAGE):
        b = f.with_suffix(f.suffix + ".pre_dealcr_ui")
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
            b = f.with_suffix(f.suffix + ".pre_dealcr_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
