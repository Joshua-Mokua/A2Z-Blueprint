// WorkbenchShell — the shared workbench chrome (Phase 2e).
//
// One reusable header standard for every workbench: a coloured Ecobank-blue
// ribbon (back · title · stage · badges · cross-link · id · refresh · details
// toggle), a collapsible "Details" slot, and a colour-coded tab strip. Extracted
// from the deal workbench so LMS/Credit Analysis, Credit Admin, Trops, and
// Credit Analytics can all adopt the identical look with one component.

import { useState, type ReactNode } from 'react';

export interface WorkbenchTab {
  id: string;
  label: string;
  /** Accent colour (hex) for the tab — active text + top border. */
  color: string;
  content: ReactNode;
}

export interface WorkbenchBadge {
  label: string;
}

export interface WorkbenchShellProps {
  title: string;
  /** Primary status pill shown next to the title (e.g. the stage). */
  stage?: string;
  /** Extra pills (e.g. Locked, Validated, Draft). */
  badges?: WorkbenchBadge[];
  /** Small monospace id shown on the right (e.g. deal / application id). */
  idLabel?: string;
  onBack?: () => void;
  onRefresh?: () => void;
  /** Optional cross-link rendered in the ribbon (e.g. "View Credit Analysis →"). */
  crossLink?: { label: string; onClick: () => void };
  /** Collapsible content revealed by the "Details" toggle. */
  details?: ReactNode;
  /** Colour-coded tabs. Omit to render `children` directly under the ribbon. */
  tabs?: WorkbenchTab[];
  defaultTabId?: string;
  /** Content rendered under the ribbon when `tabs` is not supplied (ribbon-only
   *  adoption for pages not yet tab-converted). */
  children?: ReactNode;
}

export function WorkbenchShell({
  title, stage, badges, idLabel, onBack, onRefresh, crossLink, details, tabs, defaultTabId, children,
}: WorkbenchShellProps) {
  const tabList = tabs ?? [];
  const [activeTab, setActiveTab] = useState(defaultTabId ?? (tabList[0]?.id ?? ''));
  const [detailsOpen, setDetailsOpen] = useState(false);
  const active = tabList.find((t) => t.id === activeTab) ?? tabList[0];

  return (
    <div>
      {/* Coloured ribbon — the clean top landing. */}
      <div className="mt-1 flex flex-wrap items-center justify-between gap-3 rounded-t-lg bg-gradient-to-r from-[#0082BB] to-[#005B82] px-6 py-3.5 text-white shadow-sm">
        <div className="flex flex-wrap items-center gap-2.5">
          {onBack && (
            <button onClick={onBack}
              className="rounded border border-white/40 px-2 py-0.5 text-xs font-medium hover:bg-white/10">← Back</button>
          )}
          <h2 className="text-base font-semibold">{title || '—'}</h2>
          {stage && <span className="rounded-full bg-white/20 px-2 py-0.5 text-xs">{stage}</span>}
          {(badges ?? []).map((b) => (
            <span key={b.label} className="rounded-full bg-white/20 px-2 py-0.5 text-xs">{b.label}</span>
          ))}
          {crossLink && (
            <button onClick={crossLink.onClick}
              className="text-xs font-medium text-white/90 underline hover:text-white">{crossLink.label}</button>
          )}
        </div>
        <div className="flex items-center gap-3">
          {idLabel && <span className="font-mono text-xs text-white/70">{idLabel}</span>}
          {onRefresh && (
            <button onClick={onRefresh}
              className="rounded border border-white/40 px-2 py-0.5 text-xs font-medium hover:bg-white/10">Refresh</button>
          )}
          {details != null && (
            <button onClick={() => setDetailsOpen((v) => !v)}
              className="rounded border border-white/40 px-2 py-0.5 text-xs font-medium hover:bg-white/10">
              {detailsOpen ? 'Hide details ▴' : 'Details ▾'}
            </button>
          )}
        </div>
      </div>

      {details != null && detailsOpen && <div className="mt-4">{details}</div>}

      {tabList.length > 0 ? (
        <div className="mt-3">
          <div className="flex flex-wrap gap-1 rounded-t-lg border-b border-gray-200 bg-[#EAF4FA] px-2 pt-1.5 text-sm">
            {tabList.map((t) => {
              const isActive = active?.id === t.id;
              return (
                <button key={t.id} onClick={() => setActiveTab(t.id)}
                  style={isActive ? { color: t.color, borderTopColor: t.color, borderTopWidth: 2 } : { color: t.color }}
                  className={`-mb-px rounded-t-md px-3 py-2 font-medium transition-colors ${
                    isActive ? 'bg-white font-semibold shadow-sm' : 'opacity-60 hover:bg-white/60 hover:opacity-100'}`}>
                  {t.label}
                </button>
              );
            })}
          </div>
          <div className="pt-4">{active?.content}</div>
        </div>
      ) : (
        <div className="mt-4 space-y-4">{children}</div>
      )}
    </div>
  );
}
