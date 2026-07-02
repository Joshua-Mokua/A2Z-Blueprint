#!/usr/bin/env python3
"""scripts/apply_categories_react.py — A2a React: balance-sheet category dropdown.

Make the create-deal 'Pipeline category' dropdown show the 3 balance-sheet
categories (Loan/Asset, Deposit/Liability, Insurance) instead of the 9 deal-types.
Products filter by the category's product_class; deal-types (surface=dormant) are
hidden from the dropdown.

- types/pipeline.ts: DealCategoryConfig gains surface? + product_class?
- PipelineCreate.tsx:
    * categories memo filters to surface !== 'dormant' (pipeline categories only)
    * default category -> first pipeline category (not 'Loan')
    * productOptions 'want' map reads the category's product_class from config

SAFE: .pre_cats backups. Idempotent. --revert. TSC-gated.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = ROOT / "frontend" / "web" / "src" / "types" / "pipeline.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "PipelineCreate.tsx"

def patch_types():
    s = TYPES.read_text(encoding="utf-8")
    if "product_class" in s and "surface" in s.split("DealCategoryConfig")[1].split("}")[0]:
        return s, False
    anchor = '''export interface DealCategoryConfig {
  category:     string;
  description?: string;
  stages:       string[];
}'''
    if anchor not in s:
        return s, False
    new = '''export interface DealCategoryConfig {
  category:     string;
  description?: string;
  stages:       string[];
  /** A2a: which product classes this category filters to (asset/liability/insurance/other). */
  product_class?: string[];
  /** A2a: "pipeline" = shown in create-deal dropdown; "dormant" = kept but hidden. */
  surface?:     string;
}'''
    return s.replace(anchor, new, 1), True

def patch_page():
    s = PAGE.read_text(encoding="utf-8")
    ch = False

    # 1. categories memo: filter to non-dormant (pipeline) categories
    old_cats = '''  const categories = useMemo<string[]>(
    () => (config?.deal_categories && config.deal_categories.length
      ? config.deal_categories.map((c) => c.category)
      : [...PIPELINE_CATEGORIES]),
    [config],
  );'''
    new_cats = '''  const categories = useMemo<string[]>(
    () => {
      const cfg = config?.deal_categories ?? [];
      // A2a: show only pipeline-surfaced categories (balance-sheet class);
      // dormant deal-types are kept in config but hidden from the dropdown.
      const surfaced = cfg.filter((c) => (c.surface ?? 'pipeline') !== 'dormant');
      const list = surfaced.length ? surfaced : cfg;
      return list.length ? list.map((c) => c.category) : [...PIPELINE_CATEGORIES];
    },
    [config],
  );'''
    if old_cats in s:
        s = s.replace(old_cats, new_cats, 1); ch = True

    # 2. default category: initialise to first surfaced category once config loads.
    #    Add an effect that sets category if it's still the hardcoded default and
    #    not present in the surfaced list.
    anchor_effect = "  // When category changes, ensure stage is valid for the new category."
    if "A2a: default category to first pipeline" not in s and anchor_effect in s:
        inject = '''  // A2a: default category to first pipeline category once config loads (so the
  // create form opens on a balance-sheet class, not the hardcoded 'Loan').
  useEffect(() => {
    if (categories.length && !categories.includes(category)) {
      setCategory(categories[0]);
      const initStages = stagesForCategory(categories[0]);
      setStage((cur) => (initStages.includes(cur) ? cur : (initStages[0] ?? 'Lead')));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categories]);

'''
        s = s.replace(anchor_effect, inject + anchor_effect, 1); ch = True

    # 3. productOptions 'want' map: read product_class from the selected category
    old_want = '''    const want: Record<string, ProductClass[]> = {
      Loan: ['asset'], Deposit: ['liability'], Account: ['liability', 'other'],
    };
    const buckets = want[category] ?? ['asset', 'liability', 'insurance', 'other'];'''
    new_want = '''    // A2a: the category carries its own product_class (balance-sheet class);
    // fall back to the legacy name map, then to all classes.
    const catCfg = config?.deal_categories?.find((c) => c.category === category);
    const legacyWant: Record<string, ProductClass[]> = {
      Loan: ['asset'], Deposit: ['liability'], Account: ['liability', 'other'],
    };
    const buckets: ProductClass[] = (catCfg?.product_class?.length
      ? (catCfg.product_class as ProductClass[])
      : (legacyWant[category] ?? ['asset', 'liability', 'insurance', 'other']));'''
    if old_want in s:
        s = s.replace(old_want, new_want, 1); ch = True

    return s, ch

def revert():
    for f in (TYPES, PAGE):
        b = f.with_suffix(f.suffix + ".pre_cats")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    t, tc = patch_types()
    p, pc = patch_page()
    print(f"  types: {'change' if tc else 'skip'}")
    print(f"  PipelineCreate.tsx: {'change' if pc else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in ((TYPES, t, tc), (PAGE, p, pc)):
        if ch:
            b = f.with_suffix(f.suffix + ".pre_cats")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
