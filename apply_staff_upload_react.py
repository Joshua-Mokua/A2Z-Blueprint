#!/usr/bin/env python3
"""scripts/apply_staff_upload_react.py — add the 'Upload Staff Excel' UI to the
Staff Admin panel (preview-then-confirm flow).

Adds to frontend/web/src/lib/api.ts:
  - previewStaffUpload(content_b64) / applyStaffUpload(content_b64, keep)
  - types StaffUploadPreview, StaffUploadResult
Adds to frontend/web/src/pages/StaffAdmin.tsx:
  - an "Upload Excel" button in the header
  - a hidden file input + handler that base64-encodes the file and calls preview
  - a modal showing the validation result (errors OR the resolved summary/tree)
    with a "Confirm & Apply" button that calls apply.

SAFE: backs up both files (.pre_upload_ui). Idempotent. --revert.
Run from repo root after the backend endpoints patch.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_TS = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "StaffAdmin.tsx"

API_MARKER = "// staff Excel upload (preview + apply)"
API_BLOCK = '''
// staff Excel upload (preview + apply)
export interface StaffUploadPreview {
  ok: boolean;
  errors: string[];
  summary: {
    total: number;
    root: { code: string; name: string; role: string } | null;
    reporting_to_md: { code: string; name: string; role: string }[];
    staff_per_branch: Record<string, number>;
    roles: Record<string, number>;
  } | null;
}
export interface StaffUploadResult {
  ok: boolean; applied: number; before: number; after: number; preserved: string[];
}
export async function previewStaffUpload(contentB64: string): Promise<StaffUploadPreview> {
  return postJson<StaffUploadPreview, { content_b64: string }>(
    '/admin/staff/upload/preview', { content_b64: contentB64 });
}
export async function applyStaffUpload(contentB64: string, keep: string[]): Promise<StaffUploadResult> {
  return postJson<StaffUploadResult, { content_b64: string; keep: string[] }>(
    '/admin/staff/upload/apply', { content_b64: contentB64, keep });
}
'''

def patch_api_ts():
    s = API_TS.read_text(encoding="utf-8")
    if API_MARKER in s:
        print("  api.ts: already has upload fetchers"); return s, False
    s2 = s.rstrip() + "\n" + API_BLOCK + "\n"
    return s2, True

# --- StaffAdmin.tsx edits ---
def patch_page():
    s = PAGE.read_text(encoding="utf-8")
    changed = False

    # 1. import the new fetchers (append into the existing api import list)
    if "previewStaffUpload" not in s:
        s = s.replace(
            "  reactivateAdminStaff,\n",
            "  reactivateAdminStaff,\n  previewStaffUpload,\n  applyStaffUpload,\n  type StaffUploadPreview,\n",
            1)
        changed = True

    # 2. add upload state + handlers right after the component's first useState block.
    # Anchor on the toast hook which exists once.
    if "uploadPreview" not in s:
        anchor = "const { toast } = useToast();"
        if anchor not in s:
            # fallback: try a generic toast hook signature
            import re
            m = re.search(r"const \{[^}]*\} = useToast\(\);", s)
            if m: anchor = m.group(0)
        inject = anchor + '''

  // --- staff Excel upload (preview -> confirm) ---
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadB64, setUploadB64] = useState<string | null>(null);
  const [uploadName, setUploadName] = useState<string>('');
  const [uploadPreview, setUploadPreview] = useState<StaffUploadPreview | null>(null);

  function pickStaffFile() {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.accept = '.xlsx';
    inp.onchange = async () => {
      const f = inp.files?.[0];
      if (!f) return;
      setUploadName(f.name);
      const buf = await f.arrayBuffer();
      let bin = '';
      const bytes = new Uint8Array(buf);
      for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      const b64 = btoa(bin);
      setUploadB64(b64);
      setUploadBusy(true); setUploadOpen(true); setUploadPreview(null);
      try {
        const p = await previewStaffUpload(b64);
        setUploadPreview(p);
      } catch (e) {
        setUploadPreview({ ok: false, errors: [String((e as Error)?.message || e)], summary: null });
      } finally {
        setUploadBusy(false);
      }
    };
    inp.click();
  }

  async function confirmStaffUpload() {
    if (!uploadB64) return;
    setUploadBusy(true);
    try {
      const r = await applyStaffUpload(uploadB64, ['william001', 'admin']);
      toast({ tone: 'success', message: `Uploaded ${r.applied} staff (was ${r.before}, now ${r.after}).` });
      setUploadOpen(false); setUploadB64(null); setUploadPreview(null);
      void load();
    } catch (e) {
      toast({ tone: 'danger', message: `Upload failed: ${String((e as Error)?.message || e)}` });
    } finally {
      setUploadBusy(false);
    }
  }'''
        s = s.replace(anchor, inject, 1)
        changed = True

    # 3. add the Upload button next to "+ Add staff"
    if "Upload Excel" not in s:
        s = s.replace(
            "canAdmin ? <Button onClick={openCreate}>+ Add staff</Button> : undefined",
            "canAdmin ? (\n            <div className=\"flex gap-2\">\n              <Button variant=\"ghost\" onClick={pickStaffFile}>Upload Excel</Button>\n              <Button onClick={openCreate}>+ Add staff</Button>\n            </div>\n          ) : undefined",
            1)
        changed = True

    # 4. add the preview modal before the closing </div> of the component.
    if "Staff upload preview" not in s:
        modal = '''
      {uploadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
             onClick={() => !uploadBusy && setUploadOpen(false)}>
          <div className="max-h-[85vh] w-full max-w-2xl overflow-auto rounded-lg bg-white p-6 shadow-xl"
               onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-1 text-lg font-semibold">Staff upload preview</h3>
            <p className="mb-4 text-sm text-gray-500">{uploadName}</p>
            {uploadBusy && !uploadPreview && <p className="text-sm">Validating…</p>}
            {uploadPreview && !uploadPreview.ok && (
              <div className="space-y-2">
                <p className="text-sm font-medium text-red-600">
                  Validation failed — {uploadPreview.errors.length} error(s). Nothing was written.
                </p>
                <ul className="max-h-64 list-disc overflow-auto pl-5 text-sm text-red-600">
                  {uploadPreview.errors.map((er, i) => <li key={i}>{er}</li>)}
                </ul>
              </div>
            )}
            {uploadPreview && uploadPreview.ok && uploadPreview.summary && (
              <div className="space-y-3 text-sm">
                <p className="font-medium text-green-700">
                  ✓ Valid. {uploadPreview.summary.total} staff. Root:{' '}
                  {uploadPreview.summary.root?.name} ({uploadPreview.summary.root?.role}).
                </p>
                <div>
                  <p className="font-medium">Reporting directly to MD ({uploadPreview.summary.reporting_to_md.length}):</p>
                  <ul className="list-disc pl-5">
                    {uploadPreview.summary.reporting_to_md.map((m) => (
                      <li key={m.code}>{m.name} — {m.role}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="font-medium">Staff per branch:</p>
                  <div className="grid grid-cols-2 gap-x-4">
                    {Object.entries(uploadPreview.summary.staff_per_branch).map(([b, n]) => (
                      <div key={b} className="flex justify-between"><span>{b}</span><span>{n}</span></div>
                    ))}
                  </div>
                </div>
                <p className="rounded bg-amber-50 p-2 text-amber-800">
                  Applying will REPLACE the staff table (preserving william001 + admin) and
                  cannot be undone. Confirm only if the tree above is correct.
                </p>
              </div>
            )}
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setUploadOpen(false)} disabled={uploadBusy}>
                Cancel
              </Button>
              <Button onClick={() => void confirmStaffUpload()}
                      disabled={uploadBusy || !uploadPreview?.ok}>
                {uploadBusy ? 'Applying…' : 'Confirm & Apply'}
              </Button>
            </div>
          </div>
        </div>
      )}
'''
        # inject before the final closing "    </div>\n  );\n}" of the component
        idx = s.rfind("    </div>\n  );")
        if idx != -1:
            s = s[:idx] + modal + s[idx:]
            changed = True

    return s, changed


def revert():
    for f in (API_TS, PAGE):
        bak = f.with_suffix(f.suffix + ".pre_upload_ui")
        if bak.exists():
            shutil.copy2(bak, f); bak.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    api_new, api_ch = patch_api_ts()
    page_new, page_ch = patch_page()
    print(f"  api.ts: {'will change' if api_ch else 'no change'}")
    print(f"  StaffAdmin.tsx: {'will change' if page_ch else 'no change'}")
    if dry:
        print("  --dry-run: nothing written."); return
    if api_ch:
        b = API_TS.with_suffix(API_TS.suffix + ".pre_upload_ui")
        if not b.exists(): b.write_text(API_TS.read_text(encoding="utf-8"), encoding="utf-8")
        API_TS.write_text(api_new, encoding="utf-8")
    if page_ch:
        b = PAGE.with_suffix(PAGE.suffix + ".pre_upload_ui")
        if not b.exists(): b.write_text(PAGE.read_text(encoding="utf-8"), encoding="utf-8")
        PAGE.write_text(page_new, encoding="utf-8")
    print("  applied. Run the TSC gate before commit.")

if __name__ == "__main__":
    main()
