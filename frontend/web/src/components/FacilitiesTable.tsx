// ──────────────────────────────────────────────────────────────────────────
// FacilitiesTable — the Transaction Memo's multi-row facilities grid. Stores its
// rows as a JSON string in a single CR value key (fits the flat key->value
// model). Columns match the bank's TM: Facility Type · Ccy · Current Limit ·
// Balance · Increase/Decrease · Proposed Limit · Tenor · Status · Pricing, with
// a computed TOTAL row for the numeric columns.
// ──────────────────────────────────────────────────────────────────────────
import { useMemo } from 'react';

interface FacRow {
  facility_type: string; currency: string; current_limit: string; balance: string;
  increase_decrease: string; proposed_limit: string; tenor: string; status: string; pricing: string;
}

const EMPTY: FacRow = {
  facility_type: '', currency: 'KES', current_limit: '', balance: '',
  increase_decrease: '', proposed_limit: '', tenor: '', status: '', pricing: '',
};

const COLS: { key: keyof FacRow; label: string; num?: boolean }[] = [
  { key: 'facility_type', label: 'Facility type' },
  { key: 'currency', label: 'Ccy' },
  { key: 'current_limit', label: 'Current limit', num: true },
  { key: 'balance', label: 'Balance', num: true },
  { key: 'increase_decrease', label: 'Increase / Decrease', num: true },
  { key: 'proposed_limit', label: 'Proposed limit', num: true },
  { key: 'tenor', label: 'Tenor' },
  { key: 'status', label: 'Status' },
  { key: 'pricing', label: 'Pricing' },
];

export function FacilitiesTable({ value, onChange, disabled }: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  const rows: FacRow[] = useMemo(() => {
    try {
      const p = JSON.parse(value || '[]');
      return Array.isArray(p) ? p.map((r) => ({ ...EMPTY, ...r })) : [];
    } catch {
      return [];
    }
  }, [value]);

  const commit = (next: FacRow[]) => onChange(JSON.stringify(next));
  const setCell = (i: number, k: keyof FacRow, v: string) =>
    commit(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const addRow = () => commit([...rows, { ...EMPTY }]);
  const removeRow = (i: number) => commit(rows.filter((_, j) => j !== i));

  const sum = (k: keyof FacRow) =>
    rows.reduce((a, r) => a + (parseFloat(String(r[k]).replace(/,/g, '')) || 0), 0);
  const fmt = (n: number) => (n ? n.toLocaleString() : '');

  return (
    <div className="overflow-x-auto rounded-md border border-gray-200">
      <table className="w-full text-xs">
        <thead className="bg-gray-50 text-gray-600">
          <tr>
            {COLS.map((c) => (
              <th key={c.key} className="whitespace-nowrap px-2 py-1.5 text-left font-medium">{c.label}</th>
            ))}
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-gray-100">
              {COLS.map((c) => (
                <td key={c.key} className="px-1 py-1">
                  <input
                    value={r[c.key]}
                    disabled={disabled}
                    onChange={(e) => setCell(i, c.key, e.target.value)}
                    className="w-full min-w-[5rem] rounded border border-gray-200 px-1.5 py-1 text-xs"
                  />
                </td>
              ))}
              <td className="px-1">
                {!disabled && (
                  <button
                    type="button"
                    onClick={() => removeRow(i)}
                    className="px-1 text-gray-400 hover:text-red-600"
                    aria-label="Remove row"
                  >
                    ×
                  </button>
                )}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={COLS.length + 1} className="px-2 py-3 text-center text-gray-400">No facilities yet.</td></tr>
          )}
          {rows.length > 0 && (
            <tr className="border-t border-gray-300 bg-gray-50 font-medium">
              <td className="px-2 py-1.5">TOTAL</td>
              <td />
              <td className="px-2 py-1.5">{fmt(sum('current_limit'))}</td>
              <td className="px-2 py-1.5">{fmt(sum('balance'))}</td>
              <td className="px-2 py-1.5">{fmt(sum('increase_decrease'))}</td>
              <td className="px-2 py-1.5">{fmt(sum('proposed_limit'))}</td>
              <td colSpan={3} />
            </tr>
          )}
        </tbody>
      </table>
      {!disabled && (
        <div className="p-2">
          <button type="button" onClick={addRow} className="text-xs text-[#0082BB] hover:underline">
            + Add facility row
          </button>
        </div>
      )}
    </div>
  );
}
