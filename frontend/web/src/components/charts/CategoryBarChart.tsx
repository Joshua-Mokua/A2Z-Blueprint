// v10.548 Phase P Batch P3b — CategoryBarChart.
//
// Grouped categorical bars: deposits by region, disbursements by product,
// approvals by branch, etc. One or more series.

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { useChartPalette } from '@/hooks/useChartPalette';
import { ChartTooltip } from '@/components/charts/ChartTooltip';

export interface BarSeries {
  key: string;
  label?: string;
  color?: string;
}

export interface CategoryBarChartProps {
  data: Array<Record<string, unknown>>;
  xKey: string;
  series: BarSeries[];
  height?: number;
  palette?: string[];
  stacked?: boolean;
}

export function CategoryBarChart({
  data, xKey, series, height = 260, palette, stacked = false,
}: CategoryBarChartProps) {
  const { palette: defaultPalette, chrome } = useChartPalette();
  const colors = palette ?? defaultPalette;
  const axisTick = { fontSize: 11, fill: chrome.text };

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} vertical={false} />
        <XAxis dataKey={xKey} stroke={chrome.axis} tick={axisTick} />
        <YAxis stroke={chrome.axis} tick={axisTick} />
        <Tooltip cursor={{ fill: 'rgba(0,0,0,0.04)' }} content={<ChartTooltip />} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.label ?? s.key}
               fill={s.color ?? colors[i % colors.length]}
               stackId={stacked ? 'stack' : undefined}
               radius={[3, 3, 0, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
