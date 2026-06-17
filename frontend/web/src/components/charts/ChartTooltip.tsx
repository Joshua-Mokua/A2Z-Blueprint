// ChartTooltip — one polished tooltip for every recharts chart.
//
// White rounded card, soft shadow, a colour dot per series, and values
// formatted with thousands separators. Pass as <Tooltip content={<ChartTooltip/>}/>.

interface TooltipEntry {
  name?: string | number;
  value?: number | string;
  color?: string;
  payload?: Record<string, unknown>;
}

export interface ChartTooltipProps {
  active?: boolean;
  label?: string | number;
  payload?: TooltipEntry[];
  /** Optional value formatter (e.g. currency). Defaults to locale number. */
  format?: (v: number) => string;
}

export function ChartTooltip({ active, label, payload, format }: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const fmt = (v: number | string | undefined): string => {
    if (typeof v === 'number') return format ? format(v) : v.toLocaleString();
    return String(v ?? '');
  };
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs shadow-lg">
      {label !== undefined && label !== '' && (
        <div className="mb-1 font-semibold text-[var(--brand-secondary)]">{label}</div>
      )}
      <div className="space-y-0.5">
        {payload.map((e, i) => (
          <div key={i} className="flex items-center gap-2">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: e.color ?? 'var(--brand-primary)' }}
            />
            <span className="text-gray-500">{e.name}</span>
            <span className="ml-auto font-medium tabular-nums text-gray-800">{fmt(e.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
