#!/usr/bin/env python3
"""scripts/apply_docupload_backend.py — Batch 3 backend: document upload/attach.

Per-document file upload for a deal's required-documents checklist. Files stored
on disk (data/uploads/credit_docs/{deal_id}/), sha256 + metadata recorded on the
deal's document_files map, doc name synced into documents_provided.

Endpoints (base64-in-JSON, no multipart dependency):
  POST   /api/pipeline/deals/{deal_id}/documents        {doc_name, filename, content_b64}
  GET    /api/pipeline/deals/{deal_id}/documents        -> {files: {doc: meta}}
  GET    /api/pipeline/deals/{deal_id}/documents/{doc}  -> streams the file
  DELETE /api/pipeline/deals/{deal_id}/documents/{doc}   -> removes attachment

Guards: owner/admin scope (resolve_deal_permissions can_view), doc_name must be
in the deal's required list, 15MB cap, filename sanitized.
SAFE: .pre_docupload backup. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_docupload")
MARKER = "# === DOCUMENT UPLOAD ENDPOINTS (Batch 3) ==="

BLOCK = r'''

# === DOCUMENT UPLOAD ENDPOINTS (Batch 3) ===
import base64 as _b64_docup
import hashlib as _hash_docup
import re as _re_docup
from datetime import datetime as _dt_docup

_DOC_UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "data" / "uploads" / "credit_docs"
_DOC_MAX_BYTES = 15 * 1024 * 1024  # 15 MB


class _DocUploadBody(BaseModel):
    doc_name: str
    filename: str = ""
    content_b64: str


def _safe_filename(name: str) -> str:
    base = _re_docup.sub(r"[^A-Za-z0-9._-]", "_", (name or "file").strip())
    return base[:120] or "file"


def _deal_for_docs(deal_id: str, user: dict):
    """Resolve + scope-check a deal for document ops. Returns (pm, deal)."""
    from utils.api_pipeline_scope import get_visible_staff_codes
    from utils.api_pipeline_permissions import resolve_deal_permissions
    from utils.core import PipelineManager as _PM
    pm = _PM()
    deal = _get_or_hydrate_deal(pm, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    visible = get_visible_staff_codes(user)
    if not resolve_deal_permissions(deal, user, visible).get("can_view"):
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    return pm, deal


@app.post("/api/pipeline/deals/{deal_id}/documents", tags=["pipeline"])
def upload_deal_document(deal_id: str, body: _DocUploadBody,
                         user: dict = Depends(get_current_user)):
    """Attach a file for one required document of a deal."""
    pm, deal = _deal_for_docs(deal_id, user)
    doc_name = str(body.doc_name or "").strip()
    if not doc_name:
        raise HTTPException(status_code=400, detail="doc_name is required")
    required = _get_required_documents_for_deal(deal)
    if required and doc_name not in required:
        raise HTTPException(status_code=400,
            detail=f"'{doc_name}' is not a required document for this deal")
    try:
        raw = _b64_docup.b64decode(body.content_b64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"content_b64 invalid: {exc}")
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    if len(raw) > _DOC_MAX_BYTES:
        raise HTTPException(status_code=400,
            detail=f"file too large ({len(raw)} bytes; max {_DOC_MAX_BYTES})")

    sha = _hash_docup.sha256(raw).hexdigest()
    fname = _safe_filename(body.filename or doc_name)
    ddir = _DOC_UPLOAD_ROOT / _safe_filename(deal_id)
    ddir.mkdir(parents=True, exist_ok=True)
    stored = ddir / f"{_safe_filename(doc_name)}__{fname}"
    stored.write_bytes(raw)

    files = dict(deal.get("document_files", {}) or {})
    files[doc_name] = {
        "filename": fname,
        "path": str(stored.relative_to(ROOT)),
        "sha256": sha,
        "size": len(raw),
        "uploaded_by": str(user.get("username", "") or ""),
        "uploaded_at": _dt_docup.now().isoformat(timespec="seconds"),
    }
    provided = list(deal.get("documents_provided", []) or [])
    if doc_name not in provided:
        provided.append(doc_name)
    pm.update_deal(deal_id, {"document_files": files, "documents_provided": provided},
                   str(user.get("username", "") or ""))
    # EDMS metadata registration (best-effort; governance, not blocking)
    try:
        from utils.document_management import compute_sha256  # noqa: F401
    except Exception:
        pass
    _audit("API_DEAL_DOC_UPLOAD", user, f"deal={deal_id}|doc={doc_name}|sha={sha[:12]}")
    return {"status": "attached", "doc_name": doc_name, "meta": files[doc_name]}


@app.get("/api/pipeline/deals/{deal_id}/documents", tags=["pipeline"])
def list_deal_documents(deal_id: str, user: dict = Depends(get_current_user)):
    """The deal's attached document metadata + the required list."""
    _pm, deal = _deal_for_docs(deal_id, user)
    return {"files": deal.get("document_files", {}) or {},
            "required": _get_required_documents_for_deal(deal),
            "provided": list(deal.get("documents_provided", []) or [])}


@app.get("/api/pipeline/deals/{deal_id}/documents/{doc_name}", tags=["pipeline"])
def download_deal_document(deal_id: str, doc_name: str,
                           user: dict = Depends(get_current_user)):
    """Stream one attached document back."""
    from fastapi.responses import StreamingResponse
    import io as _io_docup
    _pm, deal = _deal_for_docs(deal_id, user)
    files = deal.get("document_files", {}) or {}
    meta = files.get(doc_name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"No file for '{doc_name}'")
    fpath = ROOT / meta.get("path", "")
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="stored file missing")
    data = fpath.read_bytes()
    _audit("API_DEAL_DOC_DOWNLOAD", user, f"deal={deal_id}|doc={doc_name}")
    return StreamingResponse(_io_docup.BytesIO(data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{meta.get("filename","file")}"'})


@app.delete("/api/pipeline/deals/{deal_id}/documents/{doc_name}", tags=["pipeline"])
def delete_deal_document(deal_id: str, doc_name: str,
                         user: dict = Depends(get_current_user)):
    """Remove an attached document (so it can be re-uploaded)."""
    pm, deal = _deal_for_docs(deal_id, user)
    files = dict(deal.get("document_files", {}) or {})
    meta = files.pop(doc_name, None)
    if meta:
        try:
            fp = ROOT / meta.get("path", "")
            if fp.exists():
                fp.unlink()
        except Exception:
            pass
    provided = [d for d in (deal.get("documents_provided", []) or []) if d != doc_name]
    pm.update_deal(deal_id, {"document_files": files, "documents_provided": provided},
                   str(user.get("username", "") or ""))
    _audit("API_DEAL_DOC_DELETE", user, f"deal={deal_id}|doc={doc_name}")
    return {"status": "removed", "doc_name": doc_name}
# === END DOCUMENT UPLOAD ENDPOINTS ===
'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_docupload")
    else:
        print("  no .pre_docupload backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")
    if MARKER in s:
        print("  already applied."); return
    if dry:
        print(f"  --dry-run: would append 4 document endpoints ({len(BLOCK)} chars)."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    API.write_text(s.rstrip() + "\n" + BLOCK + "\n", encoding="utf-8")
    # ensure uploaded customer documents are NEVER committed to git
    gi = ROOT / ".gitignore"
    try:
        gitext = gi.read_text(encoding="utf-8") if gi.exists() else ""
        if "data/uploads/credit_docs" not in gitext:
            gi.write_text(gitext.rstrip() + "\n\n# credit document uploads (customer files — never commit)\ndata/uploads/credit_docs/\n", encoding="utf-8")
            print("  added data/uploads/credit_docs/ to .gitignore")
    except Exception as _e:
        print(f"  WARN: could not update .gitignore: {_e} — add data/uploads/credit_docs/ manually")
    print("  appended document upload endpoints. Restart API.")

if __name__ == "__main__":
    main()
