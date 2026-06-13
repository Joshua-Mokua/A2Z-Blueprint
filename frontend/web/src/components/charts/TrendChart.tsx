// v10.548 Phase P Batch P3b — TrendChart (line / area).
//
// Time-series trend for BSC-over-time, NPL trend, pipeline velocity, etc.
// Pass `area` for a filled area chart. Colors default to the brand palette.

import {
  LineChart, Line, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { useChartPalette } from '@/hooks/useChartPalette';

export interface TrendSeries {
  key: string;
  label?: string;
  color?: string;
}

export interface TrendChartProps {
  data: Array<Record<string, unknown>>;
  xKey: string;
  series: TrendSeries[];
  area?: boolean;
  height?: number;
  palette?: string[];
}

export function TrendChart({
  data, xKey, series, area = false, height = 260, palette,
}: TrendChartProps) {
  const { palette: defaultPalette, chrome } = useChartPalette();
  const colors = palette ?? defaultPalette;

  const axisTick = { fontSize: 11, fill: chrome.text };

  return (
    <ResponsiveContainer width="100%" height={height}>
      {area ? (
        <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} vertical={false} />
          <XAxis dataKey={xKey} stroke={chrome.axis} tick={axisTick} />
          <YAxis stroke={chrome.axis} tick={axisTick} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {series.map((s, i) => {
            const c = s.color ?? colors[i % colors.length];
            return (
              <Area key={s.key} type="monotone" dataKey={s.key}
                    name={s.label ?? s.key} stroke={c} fill={c}
                    fillOpacity={0.15} strokeWidth={2} />
            );
          })}
        </AreaChart>
      ) : (
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} vertical={false} />
          <XAxis dataKey={xKey} stroke={chrome.axis} tick={axisTick} />
          <YAxis stroke={chrome.axis} tick={axisTick} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {series.map((s, i) => {
            const c = s.color ?? colors[i % colors.length];
            return (
              <Line key={s.key} type="monotone" dataKey={s.key}
                    name={s.label ?? s.key} stroke={c} strokeWidth={2} dot={false} />
            );
          })}
        </LineChart>
      )}
    </ResponsiveContainer>
  );
}
