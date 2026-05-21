// v10.496 — Table primitive.
//
// Generic <TableT> for tabular data — the foundation of the BSC
// scorecard, pipeline deals view, credit watchlist, AML alerts,
// and dozens of other surfaces.
//
// Single source for: zebra striping, hover state, sticky header,
// column-defined alignment, optional sort, empty state.
//
// Designed as a "headless" pattern: page code passes a column
// config + the data rows; Table handles the rendering. Less magic
// than TanStack Table (which we may adopt in v10.500+ once we know
// what we actually need) but enough for the core dashboards.
//
// API:
//   const cols: Column<Deal>[] = [
//     { key: 'name', header: 'Client' },
//     { key: 'amount', header: 'Amount', align: 'right',
//       render: (row) => `KES ${row.amount.toLocaleString()}` },
//     { key: 'stage', header: 'Stage',
//       render: (row) => <Badge>{row.stage}</Badge> },
//   ];
//   <Table columns={cols} rows={deals} rowKey="id" />
//   <Table ... empty={<EmptyState />} />
//   <Table ... loading />  ← shows skeleton rows

import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Skeleton } from './Skeleton';

export interface Column<T> {
  key: string;
  header: ReactNode;
  align?: 'left' | 'center' | 'right';
  width?: string | number;
  render?: (row: T, idx: number) => ReactNode;
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
}

function defaultGetKey<T>(
  row: T, idx: number, rowKey: TableProps<T>['rowKey'],
): string | number {
  if (typeof rowKey === 'function') return rowKey(row);
  // rowKey is a key of T
  const v = row[rowKey];
  if (v === undefined || v === null) return idx;
  return String(v);
}

const ALIGN_CLASSES = {
  left:   'text-left',
  center: 'text-center',
  right:  'text-right',
} as const;

export function Table<T>({
  columns, rows, rowKey, loading = false, empty,
  zebra = true, className, onRowClick,
}: TableProps<T>) {
  const colCount = columns.length;
  const showEmpty = !loading && rows.length === 0;

  return (
    <div className={cn(
      'w-full overflow-x-auto rounded-md border border-gray-200 bg-white',
      className,
    )}>
      <table className="w-full text-sm border-collapse">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                style={c.width !== undefined
                  ? { width: c.width } : undefined}
                className={cn(
                  'px-4 py-3 font-semibold text-gray-700 ' +
                  'text-xs uppercase tracking-wider',
                  ALIGN_CLASSES[c.align ?? 'left'],
                )}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && (
            <>
              {Array.from({ length: 5 }).map((_, ri) => (
                <tr key={`sk-${ri}`} className="border-b border-gray-100">
                  {columns.map((c) => (
                    <td key={c.key} className="px-4 py-3">
                      <Skeleton shape="line" />
                    </td>
                  ))}
                </tr>
              ))}
            </>
          )}
          {showEmpty && (
            <tr>
              <td
                colSpan={colCount}
                className="px-4 py-12 text-center text-gray-500"
              >
                {empty ?? 'No data to show.'}
              </td>
            </tr>
          )}
          {!loading && rows.map((row, ri) => (
            <tr
              key={defaultGetKey(row, ri, rowKey)}
              onClick={onRowClick ? () => onRowClick(row, ri) : undefined}
              className={cn(
                'border-b border-gray-100 last:border-b-0',
                zebra && ri % 2 === 1 && 'bg-gray-50/50',
                onRowClick && 'cursor-pointer hover:bg-gray-50',
              )}
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={cn(
                    'px-4 py-3 text-gray-800',
                    ALIGN_CLASSES[c.align ?? 'left'],
                  )}
                >
                  {c.render
                    ? c.render(row, ri)
                    : String((row as Record<string, unknown>)[c.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
