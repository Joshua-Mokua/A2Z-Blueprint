#!/usr/bin/env python3
"""scripts/apply_topup_toggle.py — A1: New-facility vs Top-up toggle on create-deal.

Wires the create form to the EXISTING is_top_up backend (deal_value := top_up_amount,
api.py:5060). Design keeps the shared 3-cell value/stage/win-prob grid intact:
  - a "Facility type" toggle + (when Top-up) an existing-amount + top-up-amount row
    ABOVE the grid;
  - the grid's Deal-value cell swaps to a read-only "pipeline value = top-up" display
    when Top-up is on (stage + win-prob cells untouched).
Pipeline value = the increment only.

SAFE: .pre_topup backups. Idempotent. --revert. TSC-gated.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = ROOT / "frontend" / "web" / "src" / "types" / "pipeline.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "PipelineCreate.tsx"

def patch_types():
    s = TYPES.read_text(encoding="utf-8")
    if "is_top_up" in s:
        return s, False
    anchor = "  is_ntb?:               boolean;\n  pipeline_category?:    string;"
    if anchor not in s:
        return s, False
    new = anchor + '''
  is_top_up?:            boolean;   // true if topping up an existing facility
  top_up_amount?:        number;    // the increment (becomes pipeline value)
  original_facility_amount?: number; // existing facility size (context only)'''
    return s.replace(anchor, new, 1), True

def patch_page():
    s = PAGE.read_text(encoding="utf-8")
    ch = False

    # 1. state
    anchor_state = "  const [category,    setCategory]    = useState<string>('Loan');"
    if anchor_state in s and "isTopUp" not in s:
        s = s.replace(anchor_state, anchor_state + '''
  const [isTopUp,     setIsTopUp]     = useState<boolean>(false);
  const [existingAmt, setExistingAmt] = useState<string>('');
  const [topUpAmt,    setTopUpAmt]    = useState<string>('');''', 1)
        ch = True

    # 2. numeric memos
    anchor_memo = '''  const dealValueNum       = useMemo(() => {
    const n = Number(String(dealValue).replace(/[,\\s]/g, ''));
    return Number.isFinite(n) ? n : NaN;
  }, [dealValue]);'''
    if anchor_memo in s and "topUpAmtNum" not in s:
        s = s.replace(anchor_memo, anchor_memo + '''
  const existingAmtNum = useMemo(() => {
    const n = Number(String(existingAmt).replace(/[,\\s]/g, ''));
    return Number.isFinite(n) ? n : NaN;
  }, [existingAmt]);
  const topUpAmtNum = useMemo(() => {
    const n = Number(String(topUpAmt).replace(/[,\\s]/g, ''));
    return Number.isFinite(n) ? n : NaN;
  }, [topUpAmt]);''', 1)
        ch = True

    # 3. toggle + top-up amount row, injected before the value/stage/win-prob grid
    anchor_grid = '''            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
              <div data-field="dealValue">
                <Input
                  label={category === 'Account'
                    ? <>Number of accounts <RedStar /></>
                    : <>Deal value (KES) <RedStar /></>}
                  placeholder={category === 'Account' ? 'e.g. 1' : 'e.g. 5000000'}
                  type="number"
                  value={dealValue}
                  onChange={(e) => { setDealValue(e.target.value); clearFieldError('dealValue'); }}
                  disabled={mutations.loading}
                  helper={Number.isFinite(dealValueNum) && dealValueNum > 0
                    ? `${branding?.currency_symbol ?? 'KES'} ${dealValueNum.toLocaleString()}`
                    : undefined}
                  error={fieldErrors.dealValue}
                />
              </div>'''
    if "Facility type" not in s and anchor_grid in s:
        replacement = '''            <div className="mt-4">
              <label className="text-sm font-medium text-gray-700">Facility type</label>
              <div className="mt-1 inline-flex rounded-md border border-gray-300 overflow-hidden">
                <button type="button"
                  className={`px-4 py-1.5 text-sm ${!isTopUp ? 'bg-brand-primary text-white' : 'bg-white text-gray-700'}`}
                  onClick={() => { setIsTopUp(false); clearFieldError('dealValue'); }}
                  disabled={mutations.loading}>New facility</button>
                <button type="button"
                  className={`px-4 py-1.5 text-sm ${isTopUp ? 'bg-brand-primary text-white' : 'bg-white text-gray-700'}`}
                  onClick={() => { setIsTopUp(true); clearFieldError('dealValue'); }}
                  disabled={mutations.loading}>Top-up</button>
              </div>
              {isTopUp && (
                <p className="mt-1 text-xs text-gray-500">
                  A top-up adds to an existing facility. The pipeline value reflects only the increment (the new money), not the whole facility.
                </p>
              )}
            </div>

            {isTopUp && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                <div>
                  <Input
                    label={<>Existing facility amount (KES) <RedStar /></>}
                    placeholder="e.g. 20000000" type="number"
                    value={existingAmt}
                    onChange={(e) => setExistingAmt(e.target.value)}
                    disabled={mutations.loading}
                    helper={Number.isFinite(existingAmtNum) && existingAmtNum > 0
                      ? `${branding?.currency_symbol ?? 'KES'} ${existingAmtNum.toLocaleString()} (context only)`
                      : 'Context only — not counted in pipeline value'}
                  />
                </div>
                <div data-field="dealValue">
                  <Input
                    label={<>Top-up amount (KES) <RedStar /></>}
                    placeholder="e.g. 5000000" type="number"
                    value={topUpAmt}
                    onChange={(e) => { setTopUpAmt(e.target.value); clearFieldError('dealValue'); }}
                    disabled={mutations.loading}
                    helper={Number.isFinite(topUpAmtNum) && topUpAmtNum > 0
                      ? `${branding?.currency_symbol ?? 'KES'} ${topUpAmtNum.toLocaleString()} — this IS the pipeline value`
                      : undefined}
                    error={fieldErrors.dealValue}
                  />
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
              {!isTopUp && (
              <div data-field="dealValue">
                <Input
                  label={category === 'Account'
                    ? <>Number of accounts <RedStar /></>
                    : <>Deal value (KES) <RedStar /></>}
                  placeholder={category === 'Account' ? 'e.g. 1' : 'e.g. 5000000'}
                  type="number"
                  value={dealValue}
                  onChange={(e) => { setDealValue(e.target.value); clearFieldError('dealValue'); }}
                  disabled={mutations.loading}
                  helper={Number.isFinite(dealValueNum) && dealValueNum > 0
                    ? `${branding?.currency_symbol ?? 'KES'} ${dealValueNum.toLocaleString()}`
                    : undefined}
                  error={fieldErrors.dealValue}
                />
              </div>
              )}
              {isTopUp && (
              <div>
                <label className="text-sm font-medium text-gray-700">Pipeline value</label>
                <div className="mt-2 flex items-center gap-2">
                  <Badge tone="info" size="sm">
                    {Number.isFinite(topUpAmtNum) && topUpAmtNum > 0
                      ? `${branding?.currency_symbol ?? 'KES'} ${topUpAmtNum.toLocaleString()}`
                      : '—'}
                  </Badge>
                  <span className="text-xs text-gray-400">top-up increment</span>
                </div>
              </div>
              )}'''
        s = s.replace(anchor_grid, replacement, 1); ch = True

    # 4. payload: send top-up fields + deal_value swap
    anchor_payload = "      pipeline_category:  category,"
    if anchor_payload in s and "is_top_up:" not in s:
        s = s.replace(anchor_payload,
            "      pipeline_category:  category,\n"
            "      is_top_up:          isTopUp || undefined,\n"
            "      top_up_amount:      isTopUp && Number.isFinite(topUpAmtNum) ? topUpAmtNum : undefined,\n"
            "      original_facility_amount: isTopUp && Number.isFinite(existingAmtNum) ? existingAmtNum : undefined,", 1)
        ch = True
    anchor_dv = "      deal_value:   dealValueNum,"
    if anchor_dv in s and "isTopUp ? topUpAmtNum" not in s:
        s = s.replace(anchor_dv, "      deal_value:   isTopUp ? topUpAmtNum : dealValueNum,", 1)
        ch = True

    # 5. validation: top-up validates the increment, not dealValue
    val_old = """    if (!Number.isFinite(dealValueNum) || dealValueNum < 0) {
      errors.dealValue = 'Deal value must be a non-negative number.';
    }"""
    val_new = """    if (isTopUp) {
      if (!Number.isFinite(topUpAmtNum) || topUpAmtNum <= 0) {
        errors.dealValue = 'Top-up amount must be greater than zero.';
      } else if (Number.isFinite(existingAmtNum) && existingAmtNum > 0 && existingAmtNum < topUpAmtNum) {
        errors.dealValue = 'Existing facility amount should be at least the top-up amount.';
      }
    } else if (!Number.isFinite(dealValueNum) || dealValueNum < 0) {
      errors.dealValue = 'Deal value must be a non-negative number.';
    }"""
    if val_old in s and "Top-up amount must be greater" not in s:
        s = s.replace(val_old, val_new, 1); ch = True

    return s, ch

def revert():
    for f in (TYPES, PAGE):
        b = f.with_suffix(f.suffix + ".pre_topup")
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
            b = f.with_suffix(f.suffix + ".pre_topup")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
