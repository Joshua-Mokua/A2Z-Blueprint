// Table primitive — the foundation of the BSC scorecard, pipeline deals,
// credit watchlist, AML alerts, and other tabular surfaces.
//
// Provides: sticky header, zebra striping, hover, column alignment/render,
// loading skeleton, empty state — and OPT-IN power-ups that every table
// inherits at once: column sort, global search, pagination, CSV export.
//
// All power-ups default OFF, so existing callers are unchanged:
//   <Table columns={cols} rows={deals} rowKey="id" />
// Enable per table:
//   <Table ... searchable paginated exportable
//          pageSize={25} exportFilename="pipeline.csv" />
// Per-column:
//   { key:'amount', header:'Amount', align:'right', sortable:true,
//     sortAccessor:(r)=>r.amount, exportValue:(r)=>String(r.amount) }

import { useState, useMemo, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Skeleton } from './Skeleton';

export interface Column<T> {
  key: string;
  header: ReactNode;
  align?: 'left' | 'center' | 'right';
  width?: string | number;
  render?: (row: T, idx: number) => ReactNode;
  /** Enable click-to-sort on this column. */
  sortable?: boolean;
  /** Value used for sorting (defaults to row[key]). */
  sortAccessor?: (row: T) => string | number;
  /** Plain-text value used for CSV export (defaults to row[key]). */
  exportValue?: (row: T) => string;
  /** Plain-text header for CSV export (defaults to header if string, else key). */
  exportHeader?: string;
}

export interface TableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: keyof T | ((row: T) => string | number);
  loading?: boolean;
  empty?: ReactNode;
  zebra?: boolean;
  className?: string;
  onRowClick?: (row: T, idx: number) => void;
  // opt-in power-ups
  searchable?: boolean;
  searchPlaceholder?: string;
  /** Text searched per row (defaults to all column raw values joined). */
  searchAccessor?: (row: T) => string;
  paginated?: boolean;
  pageSize?: number;
  exportable?: boolean;
  exportFilename?: string;
  /** Sticky header (default true). */
  stickyHeader?: boolean;
  /** Extra controls rendered in the toolbar (left of search). */
  toolbar?: ReactNode;
}

type SortState = { key: string; dir: 'asc' | 'desc' } | null;

const ALIGN_CLASSES = {
  left:   'text-left',
  center: 'text-center',
  right:  'text-right',
} as const;

function getKey<T>(row: T, idx: number, rowKey: TableProps<T>['rowKey']): string | number {
  if (typeof rowKey === 'function') return rowKey(row);
  const v = row[rowKey];
  return v === undefined || v === null ? idx : String(v);
}

function rawCell<T>(row: T, key: string): unknown {
  return (row as Record<string, unknown>)[key];
}

function csvCell(v: string): string {
  return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
}

function downloadCsv<T>(columns: Column<T>[], rows: T[], filename: string): void {
  const head = columns.map((c) =>
    csvCell(c.exportHeader ?? (typeof c.header === 'string' ? c.header : c.key)));
  const lines = [head.join(',')];
  for (const row of rows) {
    lines.push(columns.map((c) =>
      csvCell(c.exportValue ? c.exportValue(row) : String(rawCell(row, c.key) ?? ''))).join(','));
  }
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function Table<T>({
  columns, rows, rowKey, loading = false, empty,
  zebra = true, className, onRowClick,
  searchable = false, searchPlaceholder = 'Search…', searchAccessor,
  paginated = false, pageSize = 25,
  exportable = false, exportFilename = 'export.csv',
  stickyHeader = true, toolbar,
}: TableProps<T>) {
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<SortState>(null);
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    if (!searchable || !query.trim()) return rows;
    const q = query.trim().toLowerCase();
    const text = (row: T) =>
      (searchAccessor
        ? searchAccessor(row)
        : columns.map((c) => String(rawCell(row, c.key) ?? '')).join(' ')
      ).toLowerCase();
    return rows.filter((r) => text(r).includes(q));
  }, [rows, searchable, query, searchAccessor, columns]);

  const sorted = useMemo(() => {
    if (!sort) return filtered;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return filtered;
    const acc = (row: T): string | number =>
      col.sortAccessor ? col.sortAccessor(row) : (rawCell(row, col.key) as string | number);
    const out = [...filtered].sort((a, b) => {
      const av = acc(a); const bv = acc(b);
      if (typeof av === 'number' && typeof bv === 'number') return av - bv;
      return String(av ?? '').localeCompare(String(bv ?? ''), undefined, { numeric: true });
    });
    return sort.dir === 'desc' ? out.reverse() : out;
  }, [filtered, sort, columns]);

  const total = sorted.length;
  const pageCount = paginated ? Math.max(1, Math.ceil(total / pageSize)) : 1;
  const safePage = Math.min(page, pageCount - 1);
  const visible = paginated ? sorted.slice(safePage * pageSize, safePage * pageSize + pageSize) : sorted;

  const colCount = columns.length;
  const showEmpty = !loading && visible.length === 0;
  const hasToolbar = searchable || exportable || !!toolbar;

  const toggleSort = (key: string) =>
    setSort((s) =>
      s?.key !== key ? { key, dir: 'asc' }
        : s.dir === 'asc' ? { key, dir: 'desc' }
          : null);

  return (
    <div className={cn('w-full', className)}>
      {hasToolbar && (
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          {toolbar}
          {searchable && (
            <div className="relative flex-1 min-w-[200px] max-w-sm">
              <input
                value={query}
                onChange={(e) => { setQuery(e.target.value); setPage(0); }}
                placeholder={searchPlaceholder}
                aria-label="Search table"
                className="w-full h-9 rounded-md border border-gray-200 bg-white px-3 text-sm outline-none focus:border-brand-primary transition-colors"
              />
            </div>
          )}
          <div className="flex-1" />
          {searchable && query.trim() && (
            <span className="text-xs text-gray-500">
              {total.toLocaleString()} match{total === 1 ? '' : 'es'}
            </span>
          )}
          {exportable && (
            <button
              type="button"
              onClick={() => downloadCsv(columns, sorted, exportFilename)}
              className="h-9 px-3 rounded-md border border-gray-200 bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Export CSV
            </button>
          )}
        </div>
      )}

      <div className="w-full overflow-x-auto rounded-md border border-gray-200 bg-white">
        <table className="w-full text-sm border-collapse">
          <thead className={cn('bg-gray-50 border-b border-gray-200', stickyHeader && 'sticky top-0 z-10')}>
            <tr>
              {columns.map((c) => {
                const isSorted = sort?.key === c.key;
                return (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={isSorted ? (sort!.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                    style={c.width !== undefined ? { width: c.width } : undefined}
                    className={cn(
                      'px-4 py-3 font-semibold text-gray-700 text-xs uppercase tracking-wider bg-gray-50',
                      ALIGN_CLASSES[c.align ?? 'left'],
                      c.sortable && 'cursor-pointer select-none hover:text-gray-900',
                    )}
                    onClick={c.sortable ? () => toggleSort(c.key) : undefined}
                  >
                    <span className="inline-flex items-center gap-1">
                      {c.header}
                      {c.sortable && (
                        <span className="text-gray-400">{isSorted ? (sort!.dir === 'asc' ? '▲' : '▼') : '⇅'}</span>
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {loading && Array.from({ length: 5 }).map((_, ri) => (
              <tr key={`sk-${ri}`} className="border-b border-gray-100">
                {columns.map((c) => (
                  <td key={c.key} className="px-4 py-3"><Skeleton shape="line" /></td>
                ))}
              </tr>
            ))}
            {showEmpty && (
              <tr>
                <td colSpan={colCount} className="px-4 py-12 text-center text-gray-500">
                  {empty ?? 'No data to show.'}
                </td>
              </tr>
            )}
            {!loading && visible.map((row, ri) => (
              <tr
                key={getKey(row, ri, rowKey)}
                onClick={onRowClick ? () => onRowClick(row, ri) : undefined}
                className={cn(
                  'border-b border-gray-100 last:border-b-0',
                  zebra && ri % 2 === 1 && 'bg-gray-50/50',
                  onRowClick && 'cursor-pointer hover:bg-gray-50',
                )}
              >
                {columns.map((c) => (
                  <td key={c.key} className={cn('px-4 py-3 text-gray-800', ALIGN_CLASSES[c.align ?? 'left'])}>
                    {c.render ? c.render(row, ri) : String(rawCell(row, c.key) ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {paginated && total > pageSize && (
        <div className="flex items-center justify-between mt-3 text-sm text-gray-600">
          <span>
            {(safePage * pageSize + 1).toLocaleString()}–{Math.min((safePage + 1) * pageSize, total).toLocaleString()} of {total.toLocaleString()}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPage(Math.max(0, safePage - 1))}
              disabled={safePage === 0}
              aria-label="Previous page"
              className="h-8 px-3 rounded-md border border-gray-200 bg-white disabled:opacity-40 hover:bg-gray-50 transition-colors"
            >
              Prev
            </button>
            <span className="px-2 tabular-nums">{safePage + 1} / {pageCount}</span>
            <button
              type="button"
              onClick={() => setPage(Math.min(pageCount - 1, safePage + 1))}
              disabled={safePage >= pageCount - 1}
              aria-label="Next page"
              className="h-8 px-3 rounded-md border border-gray-200 bg-white disabled:opacity-40 hover:bg-gray-50 transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
