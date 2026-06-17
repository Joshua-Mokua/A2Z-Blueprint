// v10.520 Phase 4 Batch β5 — LMS application list page.
//
// First consumer of GET /api/lms/applications (α8). Cascade-scoped
// table with status filters. Clicking a row navigates to detail.
//
// Layout mirrors Pipeline.tsx: header strip + filter chips + Card-based
// table + empty/loading/error states.

import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useRole } from '@/hooks/useRole';
import { useLmsApplications } from '@/hooks/useLmsApplications';
import { Card } from '@/components/Card';
import { PageHeader } from '@/components/PageHeader';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Skeleton } from '@/components/Skeleton';
import {
  statusTone,
  APPLICATION_STATUSES,
  type LoanApplication,
} from '@/types/lms';


// ── Helpers ─────────────────────────────────────────────────────────────

function formatAmount(v: number | undefined, symbol: string): string {
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return '—';
  if (n >= 1e9) return `${symbol} ${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${symbol} ${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${symbol} ${(n / 1e3).toFixed(0)}K`;
  return `${symbol} ${n.toLocaleString()}`;
}

function formatDate(s: string | undefined): string {
  if (!s) return '—';
  return s.slice(0, 10);
}


// ── Page component ──────────────────────────────────────────────────────

export function Lms() {
  const navigate = useNavigate();
  const { branding } = useBranding();
  const { user } = useRole();
  const { applications, count, loading, error, refetch } = useLmsApplications();

  // ── Filter state (client-side; server always returns all in-scope) ──
  const [statusFilter, setStatusFilter] = useState<string | 'all'>('all');
  const [searchTerm,   setSearchTerm]   = useState<string>('');

  // ── Filtered apps ──
  const filteredApps = useMemo<LoanApplication[]>(() => {
    let result = applications;
    if (statusFilter !== 'all') {
      result = result.filter((a) => (a.status || '').toLowerCase() === statusFilter);
    }
    if (searchTerm.trim()) {
      const t = searchTerm.trim().toLowerCase();
      result = result.filter((a) =>
        (a.client_name || '').toLowerCase().includes(t) ||
        (a.id || '').toLowerCase().includes(t) ||
        (a.product || '').toLowerCase().includes(t) ||
        (a.rm_name || '').toLowerCase().includes(t)
      );
    }
    return result;
  }, [applications, statusFilter, searchTerm]);

  // ── Status counts for the filter chips ──
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { all: applications.length };
    for (const status of APPLICATION_STATUSES) counts[status] = 0;
    for (const a of applications) {
      const s = (a.status || '').toLowerCase();
      counts[s] = (counts[s] || 0) + 1;
    }
    return counts;
  }, [applications]);

  const currencySymbol = branding?.currency_symbol ?? 'KES';


  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header strip — same brand-navy as Pipeline pages */}
      <PageHeader
        breadcrumbs={[{ label: 'Credit Factory' }, { label: 'Loan Applications' }]}
        title="Loan Applications"
        subtitle="Submitted, assigned, and decided applications in your cascade."
      />

      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">

        {/* ── Filter bar ─────────────────────────────────────────── */}
        <Card className="mb-4">
          <Card.Body>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <button
                onClick={() => setStatusFilter('all')}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
                  statusFilter === 'all'
                    ? 'bg-brand-primary text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                All ({statusCounts.all})
              </button>
              {APPLICATION_STATUSES.map((status) => (
                <button
                  key={status}
                  onClick={() => setStatusFilter(status)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
                    statusFilter === status
                      ? 'bg-brand-primary text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                  disabled={statusCounts[status] === 0}
                >
                  {status} ({statusCounts[status] || 0})
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Search by client name, app id, product, or RM..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="flex-1 h-9 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              />
              {searchTerm && (
                <Button variant="ghost" size="sm" onClick={() => setSearchTerm('')}>
                  Clear
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={() => refetch()}>
                Refresh
              </Button>
            </div>
          </Card.Body>
        </Card>


        {/* ── Error state ─────────────────────────────────────────── */}
        {error && (
          <Card className="mb-4">
            <Card.Body>
              <div className="text-sm text-red-800">
                <div className="font-semibold mb-1">Failed to load applications</div>
                <div>{error}</div>
              </div>
            </Card.Body>
          </Card>
        )}


        {/* ── Loading state ───────────────────────────────────────── */}
        {loading && !error && (
          <Card>
            <Card.Body>
              <div className="space-y-2">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-3/4" />
              </div>
            </Card.Body>
          </Card>
        )}


        {/* ── Empty state ─────────────────────────────────────────── */}
        {!loading && !error && filteredApps.length === 0 && (
          <Card>
            <Card.Body>
              <div className="text-center py-8">
                <div className="text-sm font-medium text-gray-700 mb-1">
                  No applications match the current filter
                </div>
                <div className="text-xs text-gray-500">
                  {applications.length === 0
                    ? `No applications in your cascade${user?.full_name ? ` (${user.full_name})` : ''}.`
                    : `${applications.length} total in cascade; ${count} returned by server.`}
                </div>
              </div>
            </Card.Body>
          </Card>
        )}


        {/* ── List table ──────────────────────────────────────────── */}
        {!loading && !error && filteredApps.length > 0 && (
          <Card>
            <Card.Body className="p-0">
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      <th className="px-4 py-3">ID</th>
                      <th className="px-4 py-3">Client</th>
                      <th className="px-4 py-3">Product</th>
                      <th className="px-4 py-3 text-right">Amount</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">RM</th>
                      <th className="px-4 py-3">Analyst</th>
                      <th className="px-4 py-3">Applied</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {filteredApps.map((app) => (
                      <tr
                        key={app.id}
                        onClick={() => navigate(`/lms/${encodeURIComponent(app.id)}`)}
                        className="hover:bg-gray-50 cursor-pointer transition"
                      >
                        <td className="px-4 py-3 font-mono text-xs text-gray-600">
                          {app.id}
                        </td>
                        <td className="px-4 py-3 font-medium text-gray-900">
                          {app.client_name}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {app.product || '—'}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-gray-700">
                          {formatAmount(app.amount, currencySymbol)}
                        </td>
                        <td className="px-4 py-3">
                          <Badge tone={statusTone(app.status)} size="sm">
                            {app.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-gray-700 text-xs">
                          {app.rm_name || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700 text-xs">
                          {app.analyst?.name || <span className="text-gray-400">unassigned</span>}
                        </td>
                        <td className="px-4 py-3 text-gray-600 text-xs">
                          {formatDate(app.application_date)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="px-4 py-3 border-t border-gray-100 text-xs text-gray-500">
                Showing {filteredApps.length} of {applications.length} applications
                {statusFilter !== 'all' && ` (filtered by status: ${statusFilter})`}
                {searchTerm && ` (search: "${searchTerm}")`}
              </div>
            </Card.Body>
          </Card>
        )}

      </main>
    </div>
  );
}
