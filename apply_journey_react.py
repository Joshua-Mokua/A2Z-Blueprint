#!/usr/bin/env python3
"""scripts/apply_journey_react.py — 4b-2 React: per-product committee journey picker.

In the product-flow editor (AdminConfig), add an ordered committee-journey picker
(from the 4b-1 palette). Empty = CR-only.

- types/pipeline.ts: ProductFlow.committee_journey
- api.ts: ProductFlowUpsertInput.committee_journey
- AdminConfig.tsx: fetch palette, journey add/remove/reorder UI, draft-init + save.

SAFE: .pre_journey_ui backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = ROOT / "frontend" / "web" / "src" / "types" / "pipeline.ts"
API_TS = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "AdminConfig.tsx"

def patch_types():
    s = TYPES.read_text(encoding="utf-8")
    if "committee_journey" in s:
        return s, False
    anchor = "  required_documents?: string[];\n  documents_required_at_stage?: string;"
    if anchor not in s:
        # older shape — try just required_documents
        anchor2 = "  required_documents?: string[];"
        if anchor2 in s:
            return s.replace(anchor2, anchor2 + "\n  committee_journey?: string[];", 1), True
        return s, False
    return s.replace(anchor, anchor + "\n  committee_journey?: string[];", 1), True

def patch_api():
    s = API_TS.read_text(encoding="utf-8")
    if "committee_journey" in s.split("ProductFlowUpsertInput")[1].split("}")[0] if "ProductFlowUpsertInput" in s else True:
        return s, False
    anchor = "  required_documents?: string[];\n  documents_required_at_stage?: string;\n  delete?: boolean;"
    if anchor not in s:
        return s, False
    return s.replace(anchor,
        "  required_documents?: string[];\n  documents_required_at_stage?: string;\n  committee_journey?: string[];\n  delete?: boolean;", 1), True

def patch_page():
    s = PAGE.read_text(encoding="utf-8")
    ch = False

    # import palette fetcher + type
    if "fetchCommitteePalette" not in s:
        s = s.replace("  fetchDocumentCatalog,\n",
                      "  fetchDocumentCatalog,\n  fetchCommitteePalette,\n  type CommitteeDef,\n", 1)
        ch = True

    # palette state + load + journey helpers
    if "committeePalette" not in s:
        anchor = "  const [docCatalog, setDocCatalog] = useState<string[]>([]);"
        inject = anchor + '''
  const [committeePalette, setCommitteePalette] = useState<CommitteeDef[]>([]);
  useEffect(() => {
    fetchCommitteePalette().then((d) => setCommitteePalette(d.committees)).catch(() => setCommitteePalette([]));
  }, []);
  function addJourneyGate(code: string) {
    setFlowDraft((f) => {
      const cur = f.committee_journey ?? [];
      return cur.includes(code) ? f : { ...f, committee_journey: [...cur, code] };
    });
  }
  function removeJourneyGate(idx: number) {
    setFlowDraft((f) => ({ ...f, committee_journey: (f.committee_journey ?? []).filter((_, i) => i !== idx) }));
  }
  function moveJourneyGate(idx: number, dir: -1 | 1) {
    setFlowDraft((f) => {
      const arr = [...(f.committee_journey ?? [])];
      const j = idx + dir;
      if (j < 0 || j >= arr.length) return f;
      [arr[idx], arr[j]] = [arr[j], arr[idx]];
      return { ...f, committee_journey: arr };
    });
  }'''
        if anchor in s:
            s = s.replace(anchor, inject, 1); ch = True

    # draft-init: carry committee_journey (existing + empty branches)
    old_existing = "required_documents: [...(existing.required_documents ?? [])], documents_required_at_stage: existing.documents_required_at_stage ?? '' }"
    if old_existing in s and "committee_journey: [...(existing" not in s:
        s = s.replace(old_existing,
            "required_documents: [...(existing.required_documents ?? [])], documents_required_at_stage: existing.documents_required_at_stage ?? '', committee_journey: [...(existing.committee_journey ?? [])] }", 1)
        ch = True
    old_empty = "required_documents: [], documents_required_at_stage: '' });"
    if old_empty in s and "committee_journey: [] })" not in s:
        s = s.replace(old_empty,
            "required_documents: [], documents_required_at_stage: '', committee_journey: [] });", 1)
        ch = True

    # saveFlow payload + local mirror
    old_save = "required_documents: flowDraft.required_documents ?? [], documents_required_at_stage: flowDraft.documents_required_at_stage ?? '' });"
    if old_save in s and "committee_journey: flowDraft" not in s:
        s = s.replace(old_save,
            "required_documents: flowDraft.required_documents ?? [], documents_required_at_stage: flowDraft.documents_required_at_stage ?? '', committee_journey: flowDraft.committee_journey ?? [] });", 1)
        ch = True
    old_mirror = "required_documents: flowDraft.required_documents ?? [], documents_required_at_stage: flowDraft.documents_required_at_stage ?? '' } }));"
    if old_mirror in s and "committee_journey: flowDraft.committee_journey ?? [] } }))" not in s:
        s = s.replace(old_mirror,
            "required_documents: flowDraft.required_documents ?? [], documents_required_at_stage: flowDraft.documents_required_at_stage ?? '', committee_journey: flowDraft.committee_journey ?? [] } }));", 1)
        ch = True

    # UI: inject the journey picker after the doc-config block, before Save button.
    if "Credit committee journey" not in s:
        marker = '                <label className="mb-1 block text-xs font-medium text-gray-600">Documents required at stage</label>'
        # find the end of the doc-config div (the </div> after the select), then insert before saveFlow button
        save_anchor = '              <Button size="sm" onClick={saveFlow} disabled={flowBusy}>'
        idx = s.find(save_anchor)
        if idx != -1 and marker in s:
            block = '''<div className="mb-3 rounded border p-3">
                <p className="mb-1 text-sm font-medium">Credit committee journey (this product)</p>
                <p className="mb-2 text-xs text-gray-500">Ordered committee gates this product opens before Credit Analysis. Empty = CR only. Amount-triggered committees are added automatically.</p>
                {(flowDraft.committee_journey ?? []).length === 0 && (
                  <p className="mb-2 text-xs text-gray-400">No committees — CR-only path.</p>
                )}
                <ol className="mb-2 space-y-1">
                  {(flowDraft.committee_journey ?? []).map((code, i) => {
                    const def = committeePalette.find((c) => c.code === code);
                    return (
                      <li key={code} className="flex items-center justify-between rounded border px-2 py-1 text-sm">
                        <span>{i + 1}. {def ? `${def.code} — ${def.name}` : code}</span>
                        <span className="flex gap-1">
                          <button type="button" className="text-xs text-gray-500 hover:text-gray-800" onClick={() => moveJourneyGate(i, -1)}>up</button>
                          <button type="button" className="text-xs text-gray-500 hover:text-gray-800" onClick={() => moveJourneyGate(i, 1)}>down</button>
                          <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => removeJourneyGate(i)}>remove</button>
                        </span>
                      </li>
                    );
                  })}
                </ol>
                <div className="flex items-center gap-2">
                  <select id="journeyAdd" className="rounded border px-2 py-1.5 text-sm"
                    onChange={(e) => { if (e.target.value) { addJourneyGate(e.target.value); e.target.value = ''; } }}
                    defaultValue="">
                    <option value="">+ Add committee gate…</option>
                    {committeePalette
                      .filter((c) => !(flowDraft.committee_journey ?? []).includes(c.code))
                      .map((c) => <option key={c.code} value={c.code}>{c.code} — {c.name}</option>)}
                  </select>
                </div>
              </div>
              '''
            s = s[:idx] + block + s[idx:]
            ch = True

    return s, ch

def revert():
    for f in (TYPES, API_TS, PAGE):
        b = f.with_suffix(f.suffix + ".pre_journey_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    t, tc = patch_types()
    a, ac = patch_api()
    p, pc = patch_page()
    print(f"  types: {'change' if tc else 'skip'}")
    print(f"  api.ts: {'change' if ac else 'skip'}")
    print(f"  AdminConfig.tsx: {'change' if pc else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in ((TYPES, t, tc), (API_TS, a, ac), (PAGE, p, pc)):
        if ch:
            b = f.with_suffix(f.suffix + ".pre_journey_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
