#!/usr/bin/env python3
"""scripts/apply_categories_admin.py — A2b: React admin editor for pipeline categories.

Adds a "Pipeline categories" panel to AdminConfig where the bank can add/edit/remove
pipeline categories: name, product classes (asset/liability/insurance/other), stages,
and whether it's shown (pipeline) or dormant. Saves the full deal_categories array via
the existing updatePipelineConfig({deal_categories}) path.

- AdminConfig.tsx: import DealCategoryConfig, categories state, load, a CategoryEditor
  panel + PanelShell, save wiring.

SAFE: .pre_catadmin backup. Idempotent. --revert. TSC-gated.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "AdminConfig.tsx"
API_TS = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"

def patch_api():
    """Self-healing: repair a broken import, ensure DealCategoryConfig is imported,
    and ensure AdminConfigPatch has deal_categories. Each step is independent so a
    partial/broken prior apply still gets fully fixed."""
    s = API_TS.read_text(encoding="utf-8")
    ch = False

    # STEP 0: repair a KNOWN broken line from the first buggy apply, where the
    # multi-line pipeline import was collapsed into ", DealCategoryConfig } from ...".
    broken = "\n, DealCategoryConfig } from '@/types/pipeline';"
    if broken in s:
        # restore the proper closing and put DealCategoryConfig on its own line
        s = s.replace(broken, "\n  DealCategoryConfig,\n} from '@/types/pipeline';")
        ch = True

    # STEP 1: ensure DealCategoryConfig is imported (only if not already valid).
    close = "} from '@/types/pipeline';"
    has_valid_import = "DealCategoryConfig,\n} from '@/types/pipeline';" in s \
        or "DealCategoryConfig } from '@/types/pipeline';" in s
    if "DealCategoryConfig" not in s or not has_valid_import:
        # if there is some stray DealCategoryConfig token but no valid import, and a
        # close marker exists, insert a clean line before the close.
        if "DealCategoryConfig" not in s and close in s:
            s = s.replace(close, "  DealCategoryConfig,\n" + close, 1)
            ch = True
        elif "DealCategoryConfig" not in s:
            idx = s.find("\n")
            s = s[:idx+1] + "import type { DealCategoryConfig } from '@/types/pipeline';\n" + s[idx+1:]
            ch = True

    # STEP 2: ensure AdminConfigPatch has deal_categories (independent of import).
    anchor = "  allow_other_mou?:    boolean;\n}"
    # only add if the field isn't already inside the AdminConfigPatch interface
    if "AdminConfigPatch" in s:
        block = s.split("interface AdminConfigPatch")[1].split("}")[0]
        if "deal_categories?" not in block and anchor in s:
            s = s.replace(anchor,
                          "  allow_other_mou?:    boolean;\n  deal_categories?:    DealCategoryConfig[];\n}", 1)
            ch = True

    return s, ch


def patch():
    s = PAGE.read_text(encoding="utf-8")
    ch = False

    # 1. import DealCategoryConfig
    if "DealCategoryConfig" not in s:
        s = s.replace("import type { PipelineConfig, ProductFlow } from '@/types/pipeline';",
                      "import type { PipelineConfig, ProductFlow, DealCategoryConfig } from '@/types/pipeline';", 1)
        ch = True

    # 2. categories state + load-from-config
    anchor_state = "  const [sectors, setSectors] = useState<string[]>([]);"
    if anchor_state in s and "dealCategories" not in s:
        s = s.replace(anchor_state,
                      anchor_state + "\n  const [dealCategories, setDealCategories] = useState<DealCategoryConfig[]>([]);", 1)
        ch = True
    # hydrate on load (next to setSectors)
    anchor_load = "    setSectors([...(c.business_sectors ?? [])]);"
    if anchor_load in s and "setDealCategories([...(c.deal_categories" not in s:
        s = s.replace(anchor_load,
                      anchor_load + "\n    setDealCategories([...(c.deal_categories ?? [])]);", 1)
        ch = True
    # re-hydrate after save (next to the other res.config.* rehydrations)
    anchor_rehydrate = "      if (res.config.product_catalogue) setProducts({ ...res.config.product_catalogue });"
    if anchor_rehydrate in s and "res.config.deal_categories) setDealCategories" not in s:
        s = s.replace(anchor_rehydrate,
                      anchor_rehydrate + "\n      if (res.config.deal_categories) setDealCategories([...res.config.deal_categories]);", 1)
        ch = True

    # 3. the panel — inject after the Sectors PanelShell
    anchor_panel = '''              <StringListEditor items={sectors} onChange={setSectors} placeholder="Add a sector…" />
            </PanelShell>'''
    if "Pipeline categories" not in s and anchor_panel in s:
        panel = anchor_panel + '''

            {/* Pipeline categories (A2b) — balance-sheet class the bank tracks */}
            <PanelShell
              title="Pipeline categories"
              hint="Balance-sheet classes shown on the create-deal form (Loan/Asset, Deposit/Liability, Insurance). Add a new pipeline class here. Dormant categories are kept but hidden."
              onSave={() => save('deal_categories', { deal_categories: dealCategories }, 'Pipeline categories')}
              saving={savingKey === 'deal_categories'}
            >
              <CategoryEditor categories={dealCategories} onChange={setDealCategories} />
            </PanelShell>'''
        s = s.replace(anchor_panel, panel, 1); ch = True

    # 4. the CategoryEditor component — append before the final closing of the file.
    if "function CategoryEditor" not in s:
        component = '''

// ── A2b: Pipeline category editor ──────────────────────────────────────
const PRODUCT_CLASSES = ['asset', 'liability', 'insurance', 'other'] as const;

function CategoryEditor({
  categories, onChange,
}: {
  categories: DealCategoryConfig[];
  onChange: (next: DealCategoryConfig[]) => void;
}) {
  const [newName, setNewName] = useState('');

  const update = (i: number, patch: Partial<DealCategoryConfig>) => {
    onChange(categories.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  };
  const remove = (i: number) => onChange(categories.filter((_, j) => j !== i));
  const add = () => {
    const name = newName.trim();
    if (!name || categories.some((c) => c.category === name)) return;
    onChange([...categories, {
      category: name, product_class: ['asset'], surface: 'pipeline',
      stages: ['Lead', 'Prospecting', 'Proposal', 'Negotiation', 'Closed Won', 'Closed Lost'],
    }]);
    setNewName('');
  };
  const toggleClass = (i: number, cls: string) => {
    const cur = categories[i].product_class ?? [];
    update(i, { product_class: cur.includes(cls) ? cur.filter((x) => x !== cls) : [...cur, cls] });
  };

  return (
    <div className="space-y-3">
      {categories.map((c, i) => {
        const dormant = (c.surface ?? 'pipeline') === 'dormant';
        return (
          <div key={c.category} className={`rounded border p-3 ${dormant ? 'bg-gray-50 opacity-70' : ''}`}>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-semibold">{c.category}</span>
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-1 text-xs text-gray-600">
                  <input type="checkbox" checked={!dormant}
                    onChange={(e) => update(i, { surface: e.target.checked ? 'pipeline' : 'dormant' })} />
                  Shown on create-deal
                </label>
                <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => remove(i)}>remove</button>
              </div>
            </div>
            <div className="mb-2">
              <span className="mr-2 text-xs text-gray-500">Product classes:</span>
              {PRODUCT_CLASSES.map((cls) => (
                <label key={cls} className="mr-3 inline-flex items-center gap-1 text-xs">
                  <input type="checkbox" checked={(c.product_class ?? []).includes(cls)}
                    onChange={() => toggleClass(i, cls)} />
                  {cls}
                </label>
              ))}
            </div>
            <div>
              <span className="mb-1 block text-xs text-gray-500">Stages (initial flow; a product's own flow overrides):</span>
              <StringListEditor
                items={c.stages ?? []}
                onChange={(items) => update(i, { stages: items })}
                placeholder="Add a stage…"
              />
            </div>
          </div>
        );
      })}
      <div className="flex items-center gap-2 pt-2">
        <input
          className="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm"
          placeholder="New pipeline category name (e.g. Trade Finance)…"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <Button size="sm" onClick={add} disabled={!newName.trim()}>Add category</Button>
      </div>
    </div>
  );
}'''
        s = s.rstrip() + "\n" + component + "\n"
        ch = True

    return s, ch

def revert():
    for f in (PAGE, API_TS):
        b = f.with_suffix(f.suffix + ".pre_catadmin")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    a, ac = patch_api()
    p, ch = patch()
    print(f"  api.ts: {'change' if ac else 'skip'}")
    print(f"  AdminConfig.tsx: {'change' if ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    if ac:
        b = API_TS.with_suffix(API_TS.suffix + ".pre_catadmin")
        if not b.exists(): b.write_text(API_TS.read_text(encoding="utf-8"), encoding="utf-8")
        API_TS.write_text(a, encoding="utf-8")
    if ch:
        b = PAGE.with_suffix(PAGE.suffix + ".pre_catadmin")
        if not b.exists(): b.write_text(PAGE.read_text(encoding="utf-8"), encoding="utf-8")
        PAGE.write_text(p, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
