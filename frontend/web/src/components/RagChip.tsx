// v10.543 Phase P Batch P3a — RagChip primitive.
//
// RAG (Red / Amber / Green) status indicator — the universal language
// of executive scorecards. Thin, opinionated wrapper over <Badge> that
// fixes the four canonical statuses to their tone + label so every
// intelligence surface (CEO Dashboard, BSC, Cascade, Initiatives) shows
// status identically.
//
// API:
//   <RagChip status="on_track" />      → green  "On Track"
//   <RagChip status="at_risk" />       → amber  "At Risk"
//   <RagChip status="off_track" />     → red    "Off Track"
//   <RagChip status="no_data" />       → grey   "No Data"
//   <RagChip status="at_risk" label="Behind" />   ← override label
//   <RagChip status="on_track" dot />  ← leading status dot
//   <RagChip status="off_track" size="sm" />
//
// Status names are deliberately snake_case to match the backend RAG
// vocabulary (initiatives portfolio-summary, BSC roll-ups).

import { Badge, type BadgeTone } from '@/components/Badge';
import { cn } from '@/lib/cn';

export type RagStatus = 'on_track' | 'at_risk' | 'off_track' | 'no_data';

interface RagMeta {
  tone:  BadgeTone;
  label: string;
  dot:   string; // tailwind bg-* for the leading dot
}

const RAG: Record<RagStatus, RagMeta> = {
  on_track:  { tone: 'success', label: 'On Track',  dot: 'bg-green-500' },
  at_risk:   { tone: 'warning', label: 'At Risk',   dot: 'bg-amber-500' },
  off_track: { tone: 'danger',  label: 'Off Track', dot: 'bg-red-500'   },
  no_data:   { tone: 'neutral', label: 'No Data',   dot: 'bg-gray-400'  },
};

export interface RagChipProps {
  status: RagStatus;
  /** Override the default label text for the status. */
  label?: string;
  /** Show a leading status-colored dot. */
  dot?: boolean;
  size?: 'sm' | 'md';
  className?: string;
}

export function RagChip({
  status, label, dot = false, size = 'md', className,
}: RagChipProps) {
  const meta = RAG[status] ?? RAG.no_data;
  return (
    <Badge tone={meta.tone} size={size} className={className}>
      {dot && (
        <span
          className={cn('inline-block w-1.5 h-1.5 rounded-full mr-1', meta.dot)}
          aria-hidden="true"
        />
      )}
      {label ?? meta.label}
    </Badge>
  );
}
