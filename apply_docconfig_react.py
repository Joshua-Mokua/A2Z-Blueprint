#!/usr/bin/env python3
"""scripts/apply_docconfig_react.py — Batch 1 React: per-product document config
in the product-flow editor (AdminConfig.tsx).

- types/pipeline.ts: ProductFlow gains required_documents + documents_required_at_stage
- api.ts: ProductFlowUpsertInput gains the two fields; + fetchDocumentCatalog()
- AdminConfig.tsx: load catalog, extend flowDraft init, doc-checklist + stage
  picker UI, include fields in saveFlow payload.

Config-only (no upload/gate). Backward compatible. SAFE: .pre_doccfg backups. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = ROOT / "frontend" / "web" / "src" / "types" / "pipeline.ts"
API_TS = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "AdminConfig.tsx"

def patch_types():
    s = TYPES.read_text(encoding="utf-8")
    if "required_documents" in s:
        return s, False
    anchor = "export interface ProductFlow {\n  client_types: string[];\n  stages: ProductFlowStage[];"
    if anchor not in s:
        return s, False
    new = anchor + "\n  required_documents?: string[];\n  documents_required_at_stage?: string;"
    return s.replace(anchor, new, 1), True

def patch_api():
    s = API_TS.read_text(encoding="utf-8")
    ch = False
    if "required_documents" not in s.split("ProductFlowUpsertInput")[1].split("}")[0]:
        s = s.replace(
            "export interface ProductFlowUpsertInput {\n  product: string;\n  stages?: ProductFlowStageInput[];\n  client_types?: string[];\n  delete?: boolean;\n}",
            "export interface ProductFlowUpsertInput {\n  product: string;\n  stages?: ProductFlowStageInput[];\n  client_types?: string[];\n  required_documents?: string[];\n  documents_required_at_stage?: string;\n  delete?: boolean;\n}", 1)
        ch = True
    if "fetchDocumentCatalog" not in s:
        block = '''
// document catalog (master list for per-product required documents)
export async function fetchDocumentCatalog(): Promise<string[]> {
  const res = await getJson<{ documents: string[] }>('/admin/document-catalog');
  return res.documents ?? [];
}
'''
        s = s.rstrip() + "\n" + block + "\n"
        ch = True
    return s, ch

def patch_page():
    s = PAGE.read_text(encoding="utf-8")
    ch = False

    # import fetcher
    if "fetchDocumentCatalog" not in s:
        s = s.replace("  upsertProductFlow,\n", "  upsertProductFlow,\n  fetchDocumentCatalog,\n", 1)
        ch = True

    # catalog state + load
    if "docCatalog" not in s:
        anchor = "  const [flowDraft, setFlowDraft] = useState<ProductFlow>({ client_types: [], stages: [] });"
        if anchor in s:
            inject = anchor + '''
  const [docCatalog, setDocCatalog] = useState<string[]>([]);
  useEffect(() => {
    fetchDocumentCatalog().then(setDocCatalog).catch(() => setDocCatalog([]));
  }, []);
  function toggleFlowDoc(doc: string) {
    setFlowDraft((f) => {
      const cur = f.required_documents ?? [];
      return { ...f, required_documents: cur.includes(doc) ? cur.filter((d) => d !== doc) : [...cur, doc] };
    });
  }'''
            s = s.replace(anchor, inject, 1)
            ch = True

    # extend the openFlow draft init to carry doc fields (both branches)
    old_init = "? { client_types: [...existing.client_types], stages: existing.stages.map((s) => ({ ...s })) }"
    if old_init in s and "required_documents: existing" not in s:
        s = s.replace(old_init,
            "? { client_types: [...existing.client_types], stages: existing.stages.map((s) => ({ ...s })), required_documents: [...(existing.required_documents ?? [])], documents_required_at_stage: existing.documents_required_at_stage ?? '' }", 1)
        ch = True
    old_empty = ": { client_types: [], stages: [{ stage: '', target_days: 3, win_probability: null }] });"
    if old_empty in s and "required_documents: []" not in s:
        s = s.replace(old_empty,
            ": { client_types: [], stages: [{ stage: '', target_days: 3, win_probability: null }], required_documents: [], documents_required_at_stage: '' });", 1)
        ch = True

    # include in saveFlow payload
    old_save = "await upsertProductFlow({ product: flowProduct, stages, client_types: flowDraft.client_types });"
    if old_save in s and "required_documents:" not in s.split("upsertProductFlow(")[1].split(");")[0]:
        s = s.replace(old_save,
            "await upsertProductFlow({ product: flowProduct, stages, client_types: flowDraft.client_types, required_documents: flowDraft.required_documents ?? [], documents_required_at_stage: flowDraft.documents_required_at_stage ?? '' });", 1)
        # also update the local state mirror
        s = s.replace(
            "setProductFlows((p) => ({ ...p, [flowProduct]: { client_types: flowDraft.client_types, stages } }));",
            "setProductFlows((p) => ({ ...p, [flowProduct]: { client_types: flowDraft.client_types, stages, required_documents: flowDraft.required_documents ?? [], documents_required_at_stage: flowDraft.documents_required_at_stage ?? '' } }));", 1)
        ch = True

    # UI: inject the doc-config block. Anchor on the flow SLA budget field or the
    # stages editor. We insert before the saveFlow button. Look for a stable marker.
    if "Required documents" not in s:
        # anchor: the Save button for the flow editor. Common pattern: onClick={saveFlow}
        marker = "onClick={saveFlow}"
        idx = s.find(marker)
        if idx != -1:
            # back up to the start of that button's <Button ... > opening tag line
            start = s.rfind("<Button", 0, idx)
            block = '''<div className="mb-3 rounded border p-3">
                <p className="mb-1 text-sm font-medium">Required documents (this product)</p>
                <p className="mb-2 text-xs text-gray-500">Tick documents this product requires. Choose the stage they must be attached at.</p>
                <div className="mb-2 grid max-h-40 grid-cols-2 gap-x-4 gap-y-1 overflow-auto rounded border p-2">
                  {docCatalog.map((doc) => (
                    <label key={doc} className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={(flowDraft.required_documents ?? []).includes(doc)} onChange={() => toggleFlowDoc(doc)} />
                      {doc}
                    </label>
                  ))}
                </div>
                <label className="mb-1 block text-xs font-medium text-gray-600">Documents required at stage</label>
                <select
                  className="w-full rounded border px-2 py-1.5 text-sm"
                  value={flowDraft.documents_required_at_stage ?? ''}
                  onChange={(e) => setFlowDraft((f) => ({ ...f, documents_required_at_stage: e.target.value }))}
                >
                  <option value="">— none —</option>
                  {flowDraft.stages.filter((s) => s.stage.trim()).map((s) => (
                    <option key={s.stage} value={s.stage}>{s.stage}</option>
                  ))}
                </select>
              </div>
              '''
            if start != -1:
                s = s[:start] + block + s[start:]
                ch = True

    return s, ch

def revert():
    for f in (TYPES, API_TS, PAGE):
        b = f.with_suffix(f.suffix + ".pre_doccfg")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    t, tc = patch_types()
    a, ac = patch_api()
    p, pc = patch_page()
    print(f"  types/pipeline.ts: {'change' if tc else 'skip'}")
    print(f"  api.ts: {'change' if ac else 'skip'}")
    print(f"  AdminConfig.tsx: {'change' if pc else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in ((TYPES, t, tc), (API_TS, a, ac), (PAGE, p, pc)):
        if ch:
            b = f.with_suffix(f.suffix + ".pre_doccfg")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate before commit.")

if __name__ == "__main__":
    main()
