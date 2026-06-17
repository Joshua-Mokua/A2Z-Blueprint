// Executive exceptions strip — the dashboard's "needs a decision" surface.
// Each item is a drill link (no dead-end widgets). Reads the scoped,
// read-only /api/dashboard/exceptions feed. Presentation only.

import { useNavigate } from 'react-router-dom';
import { useExceptions } from '@/hooks/useExceptions';
import type { ExceptionSeverity } from '@/types/exceptions';

const SEV: Record<ExceptionSeverity, { stripe: string; dot: string; label: string }> = {
  danger:  { stripe: '#dc2626', dot: 'bg-red-500',   label: 'Critical' },
  warning: { stripe: '#d97706', dot: 'bg-amber-500', label: 'Attention' },
  info:    { stripe: '#2563eb', dot: 'bg-blue-500',  label: 'Info' },
};

export function ExceptionsStrip() {
  const navigate = useNavigate();
  const { data, loading } = useExceptions();

  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-[88px] rounded-lg border border-gray-200 bg-white animate-pulse" />
        ))}
      </div>
    );
  }

  const items = data?.exceptions ?? [];

  if (items.length === 0) {
    return (
      <div className="mb-6 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
        <span className="w-2 h-2 rounded-full bg-green-500" />
        No exceptions — everything is within thresholds.
      </div>
    );
  }

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          Needs a decision
        </h2>
        <span className="text-xs text-gray-400">
          {items.length} item{items.length === 1 ? '' : 's'}
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {items.map((item) => {
          const sev = SEV[item.severity] ?? SEV.info;
          return (
            <button
              key={item.id}
              onClick={() => navigate(item.link)}
              className="text-left rounded-lg border border-gray-200 bg-white hover:shadow-md hover:border-gray-300 transition-all overflow-hidden flex"
            >
              <span className="w-1 flex-shrink-0" style={{ background: sev.stripe }} />
              <div className="flex-1 px-4 py-3 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`w-1.5 h-1.5 rounded-full ${sev.dot}`} />
                  <span className="text-[10px] uppercase tracking-wider font-bold text-gray-400">
                    {sev.label}
                  </span>
                </div>
                <div className="font-semibold text-gray-900 text-sm mt-1 truncate">{item.title}</div>
                <div className="text-xs text-gray-500 mt-0.5 truncate">{item.detail}</div>
                <div className="text-xs font-medium text-brand-primary mt-1.5">Drill in →</div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
