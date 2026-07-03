#!/usr/bin/env python3
"""scripts/apply_staff_upload_react_v2.py — 'Upload Staff Excel' UI, rebuilt
against current main (a2c735c). Adds preview->confirm upload to Staff Admin.

api.ts:  previewStaffUpload / applyStaffUpload + types (idempotent)
StaffAdmin.tsx: imports, upload state+handlers, "Upload Excel" button, preview modal.

SAFE: .pre_uploadui2 backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_TS = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "StaffAdmin.tsx"

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

IMPORT_ANCHOR = "  type AccessModule,\n"
IMPORT_NEW = ("  type AccessModule,\n"
              "  previewStaffUpload,\n  applyStaffUpload,\n  type StaffUploadPreview,\n")

STATE_ANCHOR = "  const [allModules, setAllModules] = useState<AccessModule[]>([]);\n"
STATE_NEW = STATE_ANCHOR + '''  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadB64, setUploadB64] = useState<string | null>(null);
  const [uploadName, setUploadName] = useState<string>('');
  const [uploadPreview, setUploadPreview] = useState<StaffUploadPreview | null>(null);

  function pickStaffFile() {
    const inp = document.createElement('input');
    inp.type = 'file'; inp.accept = '.xlsx';
    inp.onchange = async () => {
      const f = inp.files?.[0];
      if (!f) return;
      setUploadName(f.name);
      const buf = await f.arrayBuffer();
      let bin = '';
      const bytes = new Uint8Array(buf);
      for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      const b64 = btoa(bin);
      setUploadB64(b64); setUploadBusy(true); setUploadOpen(true); setUploadPreview(null);
      try {
        const p = await previewStaffUpload(b64);
        setUploadPreview(p);
      } catch (e) {
        setUploadPreview({ ok: false, errors: [String((e as Error)?.message || e)], summary: null });
      } finally { setUploadBusy(false); }
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
    } finally { setUploadBusy(false); }
  }
'''

BTN_ANCHOR = "          canAdmin ? <Button onClick={openCreate}>+ Add staff</Button> : undefined"
BTN_NEW = ("          canAdmin ? (\n"
           "            <div className=\"flex gap-2\">\n"
           "              <Button variant=\"ghost\" onClick={pickStaffFile}>Upload Excel</Button>\n"
           "              <Button onClick={openCreate}>+ Add staff</Button>\n"
           "            </div>\n"
           "          ) : undefined")

MODAL = '''
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
              <Button variant="ghost" onClick={() => setUploadOpen(false)} disabled={uploadBusy}>Cancel</Button>
              <Button onClick={() => void confirmStaffUpload()} disabled={uploadBusy || !uploadPreview?.ok}>
                {uploadBusy ? 'Applying…' : 'Confirm & Apply'}
              </Button>
            </div>
          </div>
        </div>
      )}
'''

def revert():
    for f in (API_TS, PAGE):
        b = f.with_suffix(f.suffix + ".pre_uploadui2")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv

    a = API_TS.read_text(encoding="utf-8")
    a_ch = "previewStaffUpload" not in a
    if a_ch:
        a2 = a.rstrip() + "\n" + API_BLOCK + "\n"

    p = PAGE.read_text(encoding="utf-8")
    checks = {
        "import": IMPORT_ANCHOR in p and "previewStaffUpload" not in p.split("from '@/lib/api'")[0],
        "state": STATE_ANCHOR in p and "uploadOpen" not in p,
        "button": BTN_ANCHOR in p,
        "modal": "Staff upload preview" not in p,
    }
    print("  anchor checks:", {k: ("ok" if v else "MISS/skip") for k, v in checks.items()})

    p2 = p
    if checks["import"]:
        p2 = p2.replace(IMPORT_ANCHOR, IMPORT_NEW, 1)
    if checks["state"]:
        p2 = p2.replace(STATE_ANCHOR, STATE_NEW, 1)
    if checks["button"]:
        p2 = p2.replace(BTN_ANCHOR, BTN_NEW, 1)
    if checks["modal"]:
        idx = p2.rfind("    </div>\n  );")
        if idx != -1:
            p2 = p2[:idx] + MODAL + p2[idx:]
        else:
            print("  WARN: modal close anchor not found; modal not injected")

    if dry:
        print("  --dry-run: nothing written."); return
    if a_ch:
        b = API_TS.with_suffix(API_TS.suffix + ".pre_uploadui2")
        if not b.exists(): b.write_text(a, encoding="utf-8")
        API_TS.write_text(a2, encoding="utf-8")
    b = PAGE.with_suffix(PAGE.suffix + ".pre_uploadui2")
    if not b.exists(): b.write_text(p, encoding="utf-8")
    PAGE.write_text(p2, encoding="utf-8")
    print("  applied. Run TSC gate before commit.")

if __name__ == "__main__":
    main()
