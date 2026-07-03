#!/usr/bin/env python3
"""scripts/apply_docupload_react.py — Batch 3 frontend: per-document upload UI.

Reworks the Submit-to-Credit panel (PipelineDealDetail.tsx CreditSubmissionPanel)
to replace tick-to-attest checkboxes with per-document UPLOAD / view / replace /
remove controls, backed by the Batch 3 endpoints. A document counts as provided
when a file is attached; Submit stays gated on all required docs attached.

api.ts: uploadDealDocument / listDealDocuments / deleteDealDocument /
downloadDealDocument + DealDocumentsResponse type.

SAFE: .pre_docupload_ui backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_TS = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "PipelineDealDetail.tsx"

API_BLOCK = '''
// deal document upload/attach (Batch 3)
export interface DealDocumentMeta {
  filename: string; path: string; sha256: string; size: number;
  uploaded_by: string; uploaded_at: string;
}
export interface DealDocumentsResponse {
  files: Record<string, DealDocumentMeta>;
  required: string[];
  provided: string[];
}
export async function listDealDocuments(dealId: string): Promise<DealDocumentsResponse> {
  return getJson<DealDocumentsResponse>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/documents`);
}
export async function uploadDealDocument(
  dealId: string, docName: string, filename: string, contentB64: string,
): Promise<{ status: string; doc_name: string; meta: DealDocumentMeta }> {
  return postJson<{ status: string; doc_name: string; meta: DealDocumentMeta },
    { doc_name: string; filename: string; content_b64: string }>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/documents`,
    { doc_name: docName, filename, content_b64: contentB64 });
}
export async function deleteDealDocument(dealId: string, docName: string): Promise<{ status: string }> {
  return postJson<{ status: string }, Record<string, never>>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/documents/${encodeURIComponent(docName)}`,
    {}, 'DELETE');
}
export async function downloadDealDocument(dealId: string, docName: string): Promise<Blob> {
  const headers: Record<string, string> = {};
  const tok = getCurrentTokenForBlob();
  if (tok) headers['Authorization'] = `Bearer ${tok}`;
  const res = await fetch(
    `/api/pipeline/deals/${encodeURIComponent(dealId)}/documents/${encodeURIComponent(docName)}`,
    { headers });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  return res.blob();
}
'''

# small helper so the blob download can read the module token without exporting internals
TOKEN_HELPER = '''
let _blobTokenRef: string | null = null;
export function getCurrentTokenForBlob(): string | null { return _blobTokenRef; }
'''

def patch_api():
    s = API_TS.read_text(encoding="utf-8")
    if "uploadDealDocument" in s:
        return s, False
    # wire the blob token ref to setCurrentToken so downloads are authed
    if "_blobTokenRef" not in s:
        s = s.replace(
            "export function setCurrentToken(token: string | null): void {\n  _currentToken = token;",
            "let _blobTokenRef: string | null = null;\nexport function getCurrentTokenForBlob(): string | null { return _blobTokenRef; }\nexport function setCurrentToken(token: string | null): void {\n  _currentToken = token;\n  _blobTokenRef = token;", 1)
    s = s.rstrip() + "\n" + API_BLOCK + "\n"
    return s, True

# The reworked panel body. We replace from the checklist.required.map checkbox
# block through the submit button's disabled logic, swapping ticks for uploads.
OLD_IMPORT = "import { fetchPipelineDealDetail, fetchCreditChecklist, submitDealToCredit, referExistingDeal, fetchDealSla, ApiValidationError, AuthExpiredError, type StaffMember, type SlaViolation } from '@/lib/api';"
NEW_IMPORT = "import { fetchPipelineDealDetail, fetchCreditChecklist, submitDealToCredit, referExistingDeal, fetchDealSla, ApiValidationError, AuthExpiredError, listDealDocuments, uploadDealDocument, deleteDealDocument, downloadDealDocument, type StaffMember, type SlaViolation, type DealDocumentsResponse } from '@/lib/api';"

# Replace the checkbox rendering block with the upload rendering block.
OLD_PANEL = '''        <p className="text-xs text-gray-500 mb-3">
          Confirm each required document is on file. All required documents
          must be checked before the deal can be submitted to credit analysis.
        </p>
        <div className="space-y-2">
          {checklist.required.map((doc) => (
            <label key={doc} className="flex items-center gap-2 text-sm text-gray-800">
              <input
                type="checkbox"
                checked={checked.has(doc)}
                onChange={() => toggle(doc)}
                disabled={submitting}
                className="h-4 w-4 rounded border-gray-300 text-brand-primary focus:ring-brand-primary/30"
              />
              <span>{doc}</span>
            </label>
          ))}
        </div>'''

NEW_PANEL = '''        <p className="text-xs text-gray-500 mb-3">
          Upload each required document. All required documents must be attached
          before the deal can be submitted to credit analysis.
        </p>
        <div className="space-y-2">
          {checklist.required.map((doc) => {
            const attached = docFiles[doc];
            return (
              <div key={doc} className="flex items-center justify-between gap-2 rounded border p-2 text-sm">
                <div className="flex items-center gap-2">
                  <span className={attached ? 'text-green-700' : 'text-gray-800'}>
                    {attached ? '✓' : '○'} {doc}
                  </span>
                  {attached && (
                    <span className="text-xs text-gray-500">{attached.filename}</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {attached && (
                    <button type="button" className="text-brand-primary hover:underline text-xs"
                      onClick={() => void viewDoc(doc)}>View</button>
                  )}
                  <button type="button" className="text-brand-primary hover:underline text-xs"
                    onClick={() => uploadFor(doc)} disabled={busyDoc === doc}>
                    {busyDoc === doc ? 'Uploading…' : attached ? 'Replace' : 'Upload'}
                  </button>
                  {attached && (
                    <button type="button" className="text-red-600 hover:underline text-xs"
                      onClick={() => void removeDoc(doc)} disabled={busyDoc === doc}>Remove</button>
                  )}
                </div>
              </div>
            );
          })}
        </div>'''

# State + handlers injected into the component. Anchor after the existing state.
STATE_ANCHOR = '''  const [error,      setError]      = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchCreditChecklist(deal.id)'''
STATE_NEW = '''  const [error,      setError]      = useState<string | null>(null);
  const [docFiles,   setDocFiles]   = useState<Record<string, DealDocumentsResponse['files'][string]>>({});
  const [busyDoc,    setBusyDoc]    = useState<string | null>(null);

  const reloadDocs = () => {
    listDealDocuments(deal.id)
      .then((d) => setDocFiles(d.files || {}))
      .catch(() => { /* leave as-is */ });
  };
  useEffect(() => { reloadDocs(); /* eslint-disable-next-line */ }, [deal.id]);

  const uploadFor = (doc: string) => {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.onchange = async () => {
      const f = inp.files?.[0];
      if (!f) return;
      setBusyDoc(doc); setError(null);
      try {
        const buf = await f.arrayBuffer();
        let bin = '';
        const bytes = new Uint8Array(buf);
        for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
        await uploadDealDocument(deal.id, doc, f.name, btoa(bin));
        reloadDocs();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Upload failed');
      } finally {
        setBusyDoc(null);
      }
    };
    inp.click();
  };

  const viewDoc = async (doc: string) => {
    try {
      const blob = await downloadDealDocument(deal.id, doc);
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not open document');
    }
  };

  const removeDoc = async (doc: string) => {
    setBusyDoc(doc);
    try {
      await deleteDealDocument(deal.id, doc);
      reloadDocs();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Remove failed');
    } finally {
      setBusyDoc(null);
    }
  };

  useEffect(() => {
    let alive = true;
    fetchCreditChecklist(deal.id)'''

# Submit gating: use attached docs instead of `checked`. Replace the missing calc
# and the submit payload + button disabled.
OLD_MISSING = "  const missing = checklist.required.filter((d) => !checked.has(d));"
NEW_MISSING = "  const missing = checklist.required.filter((d) => !docFiles[d]);"
OLD_SUBMIT_CALL = "      const res = await submitDealToCredit(deal.id, Array.from(checked));"
NEW_SUBMIT_CALL = "      const res = await submitDealToCredit(deal.id, checklist.required.filter((d) => docFiles[d]));"


def patch_page():
    s = PAGE.read_text(encoding="utf-8")
    ch = False
    if OLD_IMPORT in s:
        s = s.replace(OLD_IMPORT, NEW_IMPORT, 1); ch = True
    if STATE_ANCHOR in s and "reloadDocs" not in s:
        s = s.replace(STATE_ANCHOR, STATE_NEW, 1); ch = True
    if OLD_PANEL in s:
        s = s.replace(OLD_PANEL, NEW_PANEL, 1); ch = True
    if OLD_MISSING in s:
        s = s.replace(OLD_MISSING, NEW_MISSING, 1); ch = True
    if OLD_SUBMIT_CALL in s:
        s = s.replace(OLD_SUBMIT_CALL, NEW_SUBMIT_CALL, 1); ch = True
    # remove dead checkbox machinery (replaced by uploads)
    dead_state = "  const [checked,    setChecked]    = useState<Set<string>>(new Set());\n"
    if dead_state in s:
        s = s.replace(dead_state, "", 1); ch = True
    dead_setchecked = "        setChecklist(c);\n        setChecked(new Set(c.provided));\n"
    if dead_setchecked in s:
        s = s.replace(dead_setchecked, "        setChecklist(c);\n", 1); ch = True
    dead_toggle = """  const toggle = (doc: string) => {
    setError(null);
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(doc)) next.delete(doc);
      else next.add(doc);
      return next;
    });
  };

"""
    if dead_toggle in s:
        s = s.replace(dead_toggle, "", 1); ch = True
    return s, ch

def revert():
    for f in (API_TS, PAGE):
        b = f.with_suffix(f.suffix + ".pre_docupload_ui")
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
            b = f.with_suffix(f.suffix + ".pre_docupload_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate before commit.")

if __name__ == "__main__":
    main()
