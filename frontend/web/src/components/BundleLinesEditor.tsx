// ──────────────────────────────────────────────────────────────────────────
// BundleLinesEditor — for the "Bundled Loan Product": several loan products in
// one application, each with an amount, summing to a total. Replaces the single
// deal-value field on the create form when that product is selected.
//
// Self-contained: owns its rows, reports lines + total up via onChange. The
// parent sends `bundle_lines` in the create payload (backend sums them to
// deal_value — verified: 4M + 3.5M -> 7,500,000, deal D2977).
// ──────────────────────────────────────────────────────────────────────────
import { useEffect, useMemo, useState } from 'react';

export interface BundleLine {
  product_type: string;
  amount: string; // kept as string so the input behaves; parsed on submit
}

const LOAN_PRODUCTS = [
  'Personal Loan',
  'Business Loan',
  'Mortgage',
  'Asset Finance',
  'Overdraft',
  'Invoice Discounting',
  'Trade Finance LC',
  'Term Loan',
];

const inputCls =
  'w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:outline-none ' +
  'focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20';

function parseAmt(s: string): number {
  const n = Number(String(s).replace(/[,\s]/g, ''));
  return Number.isFinite(n) && n > 0 ? n : 0;
}

export function BundleLinesEditor({
  value,
  onChange,
  currencySymbol = 'KES',
  loanProducts = LOAN_PRODUCTS,
}: {
  value: BundleLine[];
  onChange: (lines: BundleLine[], total: number) => void;
  currencySymbol?: string;
  loanProducts?: string[];
}) {
  const [rows, setRows] = useState<BundleLine[]>(
    value.length ? value : [{ product_type: '', amount: '' }],
  );

  const total = useMemo(
    () => rows.reduce((sum, r) => sum + parseAmt(r.amount), 0),
    [rows],
  );

  useEffect(() => {
    // report only complete lines (product + positive amount) upward
    const clean = rows.filter((r) => r.product_type && parseAmt(r.amount) > 0);
    onChange(clean, clean.reduce((s, r) => s + parseAmt(r.amount), 0));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  const setRow = (i: number, patch: Partial<BundleLine>) =>
    setRows((p) => p.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const addRow = () => setRows((p) => [...p, { product_type: '', amount: '' }]);
  const removeRow = (i: number) =>
    setRows((p) => (p.length > 1 ? p.filter((_, j) => j !== i) : p));

  return (
    <div className="space-y-2">
      <div className="text-sm font-medium text-gray-700">Bundled loan products</div>
      <p className="text-xs text-gray-400">
        Add each loan product in this application and its amount. The deal value is their sum.
      </p>

      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-2">
          <select
            className={`${inputCls} flex-1`}
            value={r.product_type}
            onChange={(e) => setRow(i, { product_type: e.target.value })}
          >
            <option value="">Select loan product…</option>
            {loanProducts.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <input
            className={`${inputCls} w-40`}
            inputMode="numeric"
            placeholder="Amount"
            value={r.amount}
            onChange={(e) => setRow(i, { amount: e.target.value })}
          />
          <button
            type="button"
            onClick={() => removeRow(i)}
            disabled={rows.length === 1}
            className="px-2 text-gray-400 hover:text-red-600 disabled:opacity-30"
            title="Remove line"
          >
            ✕
          </button>
        </div>
      ))}

      <div className="flex items-center justify-between pt-1">
        <button
          type="button"
          onClick={addRow}
          className="text-xs font-medium text-[#0082BB] hover:underline"
        >
          + Add product
        </button>
        <div className="text-sm">
          <span className="text-gray-500">Total: </span>
          <span className="font-semibold text-gray-900">
            {currencySymbol} {total.toLocaleString()}
          </span>
        </div>
      </div>
    </div>
  );
}
