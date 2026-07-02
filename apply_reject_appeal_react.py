#!/usr/bin/env python3
"""scripts/apply_reject_appeal_react.py — 4b-6 React: appeal / close-lost actions.

When a committee gate is REJECTED, the committee card shows Appeal (with reason)
and Close as Lost actions (owner fallback).

- api.ts: appealCommitteeDecision / closeDealAsLost
- PipelineDealDetail.tsx: appeal/close UI in the rejected-gate branch of the
  CommitteeJourneyCard.

SAFE: .pre_appeal_ui backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_TS = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "PipelineDealDetail.tsx"

API_BLOCK = '''
// reject -> owner fallback (4b-6)
export async function appealCommitteeDecision(
  dealId: string, code: string, reason: string,
): Promise<{ status: string; message: string }> {
  return postJson<{ status: string; message: string }, { code: string; reason: string }>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/committee-appeal`, { code, reason });
}
export async function closeDealAsLost(dealId: string, reason: string): Promise<{ status: string }> {
  return postJson<{ status: string }, { reason: string }>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/close-lost`, { reason });
}
'''

def patch_api():
    s = API_TS.read_text(encoding="utf-8")
    if "appealCommitteeDecision" in s:
        return s, False
    return s.rstrip() + "\n" + API_BLOCK + "\n", True

def patch_page():
    s = PAGE.read_text(encoding="utf-8")
    ch = False
    if "appealCommitteeDecision" not in s:
        s = s.replace("getDealCommitteeRecords, recordDealCommitteeDecision,",
                      "getDealCommitteeRecords, recordDealCommitteeDecision, appealCommitteeDecision, closeDealAsLost,", 1)
        ch = True
    # Add appeal/close UI + handlers to CommitteeJourneyCard. We add state and
    # helpers after the outcomeDraft state, and render actions in the record branch
    # when outcome === 'REJECTED'.
    if "appealReason" not in s and "function CommitteeJourneyCard" in s:
        # inject state + handlers after the voteDraft/outcomeDraft state block
        anchor = "  const [outcomeDraft, setOutcomeDraft] = useState<Record<string, string>>({});"
        inject = anchor + '''
  const [appealReason, setAppealReason] = useState<Record<string, string>>({});
  const doAppeal = async (code: string) => {
    const reason = (appealReason[code] ?? '').trim();
    if (!reason) { toast({ tone: 'danger', message: 'Enter an appeal reason.' }); return; }
    setBusy(code);
    try {
      const r = await appealCommitteeDecision(dealId, code, reason);
      toast({ tone: 'success', message: r.message });
      setAppealReason((p) => ({ ...p, [code]: '' }));
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Appeal failed' });
    } finally { setBusy(null); }
  };
  const doCloseLost = async (code: string) => {
    setBusy(code);
    try {
      await closeDealAsLost(dealId, `Committee ${code} rejected`);
      toast({ tone: 'success', message: 'Deal closed as Lost.' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Close failed' });
    } finally { setBusy(null); }
  };'''
        if anchor in s:
            s = s.replace(anchor, inject, 1); ch = True

    # render appeal/close in the record branch when rejected
    if "Appeal or close" not in s:
        anchor = '''              {gate.record ? (
                <div className="text-xs text-gray-600">
                  Recorded by {gate.record.recorded_by} on {gate.record.recorded_at}.
                  {gate.record.mode === 'voting' && gate.record.votes.length > 0 && (
                    <ul className="mt-1 list-disc pl-5">
                      {gate.record.votes.map((v, i) => (
                        <li key={i}>{v.name} ({v.role}): {v.vote}</li>
                      ))}
                    </ul>
                  )}
                </div>'''
        new = '''              {gate.record ? (
                <div className="text-xs text-gray-600">
                  Recorded by {gate.record.recorded_by} on {gate.record.recorded_at}.
                  {gate.record.mode === 'voting' && gate.record.votes.length > 0 && (
                    <ul className="mt-1 list-disc pl-5">
                      {gate.record.votes.map((v, i) => (
                        <li key={i}>{v.name} ({v.role}): {v.vote}</li>
                      ))}
                    </ul>
                  )}
                  {gate.record.outcome === 'REJECTED' && canEdit && (
                    <div className="mt-3 rounded bg-red-50 p-2">
                      <p className="mb-2 font-medium text-red-700">Rejected — appeal or close as lost.</p>
                      <textarea className="mb-2 w-full rounded border px-2 py-1 text-xs" rows={2}
                        placeholder="Appeal reason / justification"
                        value={appealReason[gate.code] ?? ''}
                        onChange={(e) => setAppealReason((p) => ({ ...p, [gate.code]: e.target.value }))} />
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => void doAppeal(gate.code)} disabled={busy === gate.code}>
                          {busy === gate.code ? 'Working…' : 'Appeal (re-open)'}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => void doCloseLost(gate.code)} disabled={busy === gate.code}>
                          Close as Lost
                        </Button>
                      </div>
                    </div>
                  )}
                </div>'''
        if anchor in s:
            s = s.replace(anchor, new, 1); ch = True

    return s, ch

def revert():
    for f in (API_TS, PAGE):
        b = f.with_suffix(f.suffix + ".pre_appeal_ui")
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
            b = f.with_suffix(f.suffix + ".pre_appeal_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
