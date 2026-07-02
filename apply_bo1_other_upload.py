#!/usr/bin/env python3
"""scripts/apply_bo1_other_upload.py — BO1: "Other" ad-hoc document upload.

Lets a user attach ad-hoc documents beyond the fixed required-documents list (e.g.
during branch origination, before submitting to the DCC). An "Other" document is
ADDITIONAL — it never substitutes a required document, so the submit-to-credit gate is
unchanged.

Backend (utils/api.py, upload_deal_document): a doc_name starting with the "Other: "
prefix bypasses the required-list check (but is still size/limit validated and stored).
Everything else is unchanged; required docs still gated exactly as before.

Frontend (PipelineDealDetail.tsx): an "Other (describe)" row in the submit panel lets
the user type a label and upload an ad-hoc file; attached "Other" docs are listed with
view/remove, separate from the required list.

SAFE: .pre_bo1 backups. Idempotent. --revert. TSC-gated (frontend).
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
DETAIL = ROOT / "frontend" / "web" / "src" / "pages" / "PipelineDealDetail.tsx"
BAKS = {API: API.with_suffix(".py.pre_bo1"), DETAIL: DETAIL.with_suffix(".tsx.pre_bo1")}

OTHER_PREFIX = "Other: "

def patch_api(s):
    if "OTHER_DOC_PREFIX" not in s:
        anchor = '''    required = _get_required_documents_for_deal(deal)
    if required and doc_name not in required:
        raise HTTPException(status_code=400,
            detail=f"'{doc_name}' is not a required document for this deal")'''
        new = '''    # BO1: an ad-hoc "Other: <label>" document is ADDITIONAL — it bypasses the
    # required-list check (it's not a substitute for a required doc, so the
    # submit-to-credit gate is unchanged) but is still validated + stored.
    OTHER_DOC_PREFIX = "Other: "
    is_other = doc_name.startswith(OTHER_DOC_PREFIX)
    required = _get_required_documents_for_deal(deal)
    if not is_other and required and doc_name not in required:
        raise HTTPException(status_code=400,
            detail=f"'{doc_name}' is not a required document for this deal")'''
        s = s.replace(anchor, new, 1)
        return s, True
    return s, False

def patch_detail(s):
    changed = False
    # a) state for the Other label + list of attached Other docs (derive from docFiles keys)
    if "otherLabel" not in s:
        anchor = "  const [busyDoc,    setBusyDoc]    = useState<string | null>(null);"
        new = anchor + '''
  const [otherLabel, setOtherLabel] = useState('');
  const OTHER_PREFIX = 'Other: ';'''
        s = s.replace(anchor, new, 1)
        changed = True

    # b) the "Other" upload row + attached-others list, inserted after the required list's closing </div>
    if "Other (describe)" not in s:
        anchor = '''        {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
        {!error && missing.length > 0 && (
          <div className="mt-3 text-xs text-amber-600">
            {missing.length} document{missing.length === 1 ? '' : 's'} still required.
          </div>
        )}'''
        new = '''        {/* BO1: attached ad-hoc "Other" documents */}
        {Object.keys(docFiles).filter((k) => k.startsWith(OTHER_PREFIX)).length > 0 && (
          <div className="mt-3 space-y-2">
            <p className="text-xs font-medium text-gray-600">Other documents</p>
            {Object.keys(docFiles).filter((k) => k.startsWith(OTHER_PREFIX)).map((k) => (
              <div key={k} className="flex items-center justify-between gap-2 rounded border p-2 text-sm">
                <span className="text-green-700">✓ {k.slice(OTHER_PREFIX.length)}</span>
                <div className="flex items-center gap-2">
                  <button type="button" className="text-brand-primary hover:underline text-xs"
                    onClick={() => void viewDoc(k)}>View</button>
                  <button type="button" className="text-red-600 hover:underline text-xs"
                    onClick={() => void removeDoc(k)} disabled={busyDoc === k}>Remove</button>
                </div>
              </div>
            ))}
          </div>
        )}
        {/* BO1: add an ad-hoc "Other" document */}
        <div className="mt-3 flex items-center gap-2">
          <input
            type="text"
            className="flex-1 rounded border px-2 py-1.5 text-sm"
            placeholder="Other (describe) — e.g. board resolution, extra KYC…"
            value={otherLabel}
            onChange={(e) => setOtherLabel(e.target.value)}
          />
          <button
            type="button"
            className="rounded border px-3 py-1.5 text-sm text-brand-primary hover:bg-gray-50 disabled:opacity-50"
            disabled={!otherLabel.trim() || busyDoc !== null}
            onClick={() => { const label = otherLabel.trim(); if (label) { uploadFor(OTHER_PREFIX + label); setOtherLabel(''); } }}
          >
            Attach other
          </button>
        </div>
        {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
        {!error && missing.length > 0 && (
          <div className="mt-3 text-xs text-amber-600">
            {missing.length} document{missing.length === 1 ? '' : 's'} still required.
          </div>
        )}'''
        s = s.replace(anchor, new, 1)
        changed = True

    return s, changed

def revert():
    for tgt, bak in BAKS.items():
        if bak.exists():
            shutil.copy2(bak, tgt); bak.unlink(); print(f"  reverted {tgt.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    a = API.read_text(encoding="utf-8"); d = DETAIL.read_text(encoding="utf-8")
    a_new, a_ch = patch_api(a); d_new, d_ch = patch_detail(d)
    print(f"  api.py (Other bypasses required-list): {'change' if a_ch else 'skip'}")
    print(f"  PipelineDealDetail.tsx (Other upload row): {'change' if d_ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for tgt, new, ch in ((API, a_new, a_ch), (DETAIL, d_new, d_ch)):
        if ch:
            if not BAKS[tgt].exists(): BAKS[tgt].write_text(tgt.read_text(encoding="utf-8"), encoding="utf-8")
            tgt.write_text(new, encoding="utf-8")
    print("  applied. Restart API + TSC gate.")

if __name__ == "__main__":
    main()
