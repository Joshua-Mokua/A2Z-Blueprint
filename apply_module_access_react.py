#!/usr/bin/env python3
"""scripts/apply_module_access_react.py — module-access checkboxes in the Staff
Admin edit modal (module-level only).

api.ts:   + fetchAccessModules(), AccessModule type, StaffRow.accessible_modules,
          StaffPatchInput.accessible_modules
StaffAdmin.tsx: + module list load, FormState.accessible_modules, edit-patch field,
          a checkbox grid in the edit modal.

SAFE: backs up both files (.pre_modaccess_ui). Idempotent. --revert.
"""
import sys, shutil, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_TS = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "StaffAdmin.tsx"

def patch_api():
    s = API_TS.read_text(encoding="utf-8")
    ch = False
    if "fetchAccessModules" not in s:
        block = '''
// staff module-access (module-level RBAC)
export interface AccessModule { key: string; label: string; min: string; }
export async function fetchAccessModules(): Promise<AccessModule[]> {
  const res = await getJson<{ modules: AccessModule[] }>('/admin/modules');
  return res.modules ?? [];
}
'''
        s = s.rstrip() + "\n" + block + "\n"
        ch = True
    # add accessible_modules to StaffRow + StaffPatchInput
    if "interface StaffRow" in s and "accessible_modules" not in s.split("interface StaffRow")[1].split("}")[0]:
        s = s.replace("export interface StaffRow {",
                      "export interface StaffRow {\n  accessible_modules?: string[];", 1)
        ch = True
    if "interface StaffPatchInput" in s and "accessible_modules" not in s.split("interface StaffPatchInput")[1].split("}")[0]:
        s = s.replace("export interface StaffPatchInput {",
                      "export interface StaffPatchInput {\n  accessible_modules?: string[];", 1)
        ch = True
    return s, ch

def patch_page():
    s = PAGE.read_text(encoding="utf-8")
    ch = False
    # import fetcher + type
    if "fetchAccessModules" not in s:
        s = s.replace("  type StaffUploadPreview,\n",
                      "  type StaffUploadPreview,\n  fetchAccessModules,\n  type AccessModule,\n", 1)
        ch = True
    # FormState field
    if "accessible_modules" not in s.split("interface FormState")[1].split("}")[0]:
        s = s.replace("  is_admin: boolean;\n}",
                      "  is_admin: boolean;\n  accessible_modules: string[];\n}", 1)
        s = s.replace("can_view_all: false, is_admin: false,\n};",
                      "can_view_all: false, is_admin: false, accessible_modules: [],\n};", 1)
        ch = True
    # module list state + load on mount
    if "const [allModules" not in s:
        anchor = "const [form, setForm] = useState<FormState>(EMPTY_FORM);"
        inject = anchor + '''
  const [allModules, setAllModules] = useState<AccessModule[]>([]);
  useEffect(() => {
    fetchAccessModules().then(setAllModules).catch(() => setAllModules([]));
  }, []);
  function toggleModule(key: string) {
    setForm((f) => ({
      ...f,
      accessible_modules: f.accessible_modules.includes(key)
        ? f.accessible_modules.filter((m) => m !== key)
        : [...f.accessible_modules, key],
    }));
  }'''
        s = s.replace(anchor, inject, 1)
        ch = True
    # populate accessible_modules when opening edit
    if "accessible_modules: row.accessible_modules" not in s:
        s = s.replace("      is_admin: row.is_admin,\n",
                      "      is_admin: row.is_admin,\n      accessible_modules: row.accessible_modules ?? [],\n", 1)
        ch = True
    # include in the edit patch
    if "accessible_modules: form.accessible_modules," not in s:
        s = s.replace("          is_admin: form.is_admin,\n        };\n        await updateAdminStaff",
                      "          is_admin: form.is_admin,\n          accessible_modules: form.accessible_modules,\n        };\n        await updateAdminStaff", 1)
        ch = True
    # render checkbox grid before the "Can view all staff" checkbox (edit mode only)
    if "Module access" not in s:
        # anchor: the wrapper around can_view_all checkbox. Find the label text.
        anchor = "Can view all staff"
        # inject a module grid block just before the checkboxes container.
        grid = '''{modal === 'edit' && allModules.length > 0 && (
                <div className="mb-3">
                  <p className="mb-1 text-sm font-medium">Module access</p>
                  <p className="mb-2 text-xs text-gray-500">
                    Tick modules this user can access. Empty = role default applies.
                  </p>
                  <div className="grid max-h-48 grid-cols-2 gap-x-4 gap-y-1 overflow-auto rounded border p-2">
                    {allModules.map((m) => (
                      <label key={m.key} className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={form.accessible_modules.includes(m.key)}
                          onChange={() => toggleModule(m.key)}
                        />
                        {m.label}
                      </label>
                    ))}
                  </div>
                </div>
              )}
              '''
        # Insert before the first occurrence of the can_view_all label's enclosing block.
        # We look for the line that renders the "Can view all staff" label and back up to its <label or <div.
        # Insert the grid immediately BEFORE the flex row that wraps the
        # can_view_all / is_admin checkboxes, so it renders full-width above them.
        wrapper = '<div className="flex gap-6 pt-1">'
        widx = s.find(wrapper)
        if widx != -1:
            s = s[:widx] + grid + s[widx:]
            ch = True
    return s, ch

def revert():
    for f in (API_TS, PAGE):
        b = f.with_suffix(f.suffix + ".pre_modaccess_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    api_new, api_ch = patch_api()
    page_new, page_ch = patch_page()
    print(f"  api.ts: {'will change' if api_ch else 'no change'}")
    print(f"  StaffAdmin.tsx: {'will change' if page_ch else 'no change'}")
    if dry:
        print("  --dry-run: nothing written."); return
    if api_ch:
        b = API_TS.with_suffix(API_TS.suffix + ".pre_modaccess_ui")
        if not b.exists(): b.write_text(API_TS.read_text(encoding="utf-8"), encoding="utf-8")
        API_TS.write_text(api_new, encoding="utf-8")
    if page_ch:
        b = PAGE.with_suffix(PAGE.suffix + ".pre_modaccess_ui")
        if not b.exists(): b.write_text(PAGE.read_text(encoding="utf-8"), encoding="utf-8")
        PAGE.write_text(page_new, encoding="utf-8")
    print("  applied. Run the TSC gate before commit.")

if __name__ == "__main__":
    main()
