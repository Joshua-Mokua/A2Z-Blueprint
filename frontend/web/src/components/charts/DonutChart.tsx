// v10.548 Phase P Batch P3b — DonutChart.
//
// Composition: portfolio by product, deposits by tier, RAG distribution.
// Optional center label (e.g. total). Colors default to the brand palette;
// per-slice color override via datum.color.

import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useChartPalette } from '@/hooks/useChartPalette';

export interface DonutDatum {
  name: string;
  value: number;
  color?: string;
}

export interface DonutChartProps {
  data: DonutDatum[];
  height?: number;
  palette?: string[];
  centerLabel?: string;
  centerValue?: string;
}

export function DonutChart({
  data, height = 260, palette, centerLabel, centerValue,
}: DonutChartProps) {
  const { palette: defaultPalette } = useChartPalette();
  const colors = palette ?? defaultPalette;

  return (
    <div className="relative" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name"
               cx="50%" cy="50%" innerRadius="58%" outerRadius="80%"
               paddingAngle={2}>
            {data.map((d, i) => (
              <Cell key={d.name} fill={d.color ?? colors[i % colors.length]} />
            ))}
          </Pie>
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 12 }} />
        </PieChart>
      </ResponsiveContainer>
      {(centerLabel || centerValue) && (
        <div className="pointer-events-none absolute inset-0 flex flex-col
                        items-center justify-center"
             style={{ paddingBottom: 24 }}>
          {centerValue && (
            <div className="text-2xl font-bold text-brand-secondary tabular-nums">
              {centerValue}
            </div>
          )}
          {centerLabel && (
            <div className="text-[11px] uppercase tracking-wider text-gray-400">
              {centerLabel}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
