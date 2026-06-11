// v10.522 Phase 4 Batch β6 — Credit Admin case list page.
//
// First consumer of GET /api/credit-admin/cases (α9). Cascade-scoped
// table. Filter chips by case category (pending conditions / ready /
// cleared / disbursed) rather than by single status string, because
// case state is a combination of three boolean flags.
//
// Pattern mirrors Lms.tsx (β5).

import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useCreditAdminCases } from '@/hooks/useCreditAdminCases';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Skeleton } from '@/components/Skeleton';
import {
  CASE_CATEGORIES,
  caseCategoryLabel,
  categorizeCase,
  caseStatusTone,
  caseStatusLabel,
  type CaseCategory,
  type CreditAdminCase,
} from '@/types/creditAdmin';


// ── Format helpers ──────────────────────────────────────────────────────

function formatAmount(v: number | undefined, symbol: string): string {
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return '—';
  if (n >= 1e9) return `${symbol} ${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${symbol} ${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${symbol} ${(n / 1e3).toFixed(0)}K`;
  return `${symbol} ${n.toLocaleString()}`;
}

function formatDate(s: string | undefined | null): string {
  if (!s) return '—';
  return s.slice(0, 10);
}

function conditionProgress(c: CreditAdminCase): string {
  const total = (c.conditions || []).length;
  if (total === 0) return '—';
  const fulfilled = c.conditions.filter((cond) => cond.fulfilled).length;
  return `${fulfilled} / ${total}`;
}


// ── Page component ──────────────────────────────────────────────────────

export function CreditAdmin() {
  const navigate = useNavigate();
  const { branding } = useBranding();
  const { cases, count, loading, error, refetch } = useCreditAdminCases();

  // ── Filter state ──
  const [categoryFilter, setCategoryFilter] = useState<CaseCategory>('all');
  const [searchTerm,     setSearchTerm]     = useState<string>('');

  // ── Filtered cases ──
  const filteredCases = useMemo<CreditAdminCase[]>(() => {
    let result = cases;
    if (categoryFilter !== 'all') {
      result = result.filter((c) => categorizeCase(c) === categoryFilter);
    }
    if (searchTerm.trim()) {
      const t = searchTerm.trim().toLowerCase();
      result = result.filter((c) =>
        (c.client_name || '').toLowerCase().includes(t) ||
        (c.id || '').toLowerCase().includes(t) ||
        (c.application_id || '').toLowerCase().includes(t) ||
        (c.product || '').toLowerCase().includes(t) ||
        (c.rm_name || '').toLowerCase().includes(t)
      );
    }
    return result;
  }, [cases, categoryFilter, searchTerm]);

  // ── Counts per category ──
  const categoryCounts = useMemo(() => {
    const counts: Record<CaseCategory, number> = {
      all: cases.length,
      pending_conditions: 0,
      ready_for_disbursement: 0,
      cleared: 0,
      disbursed: 0,
    };
    for (const c of cases) {
      counts[categorizeCase(c)]++;
    }
    return counts;
  }, [cases]);

  const currencySymbol = branding?.currency_symbol ?? 'KES';


  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="text-white shadow" style={{ background: 'var(--brand-secondary)' }}>
        <div className="max-w-7xl mx-auto px-6 py-5">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-semibold">Credit Admin</h1>
              <p className="text-xs text-white/70 mt-0.5">
                Approved loans in the disbursement pipeline · condition tracking
              </p>
            </div>
            <Badge tone="brand" size="sm">β6</Badge>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6">

        {/* Filter bar */}
        <Card className="mb-4">
          <Card.Body>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              {CASE_CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setCategoryFilter(cat)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
                    categoryFilter === cat
                      ? 'bg-brand-primary text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                  disabled={cat !== 'all' && categoryCounts[cat] === 0}
                >
                  {caseCategoryLabel(cat)} ({categoryCounts[cat]})
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Search by client name, case id, app id, product, or RM..."
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


        {/* Error */}
        {error && (
          <Card className="mb-4">
            <Card.Body>
              <div className="text-sm text-red-800">
                <div className="font-semibold mb-1">Failed to load cases</div>
                <div>{error}</div>
              </div>
            </Card.Body>
          </Card>
        )}


        {/* Loading */}
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


        {/* Empty */}
        {!loading && !error && filteredCases.length === 0 && (
          <Card>
            <Card.Body>
              <div className="text-center py-8">
                <div className="text-sm font-medium text-gray-700 mb-1">
                  No cases match the current filter
                </div>
                <div className="text-xs text-gray-500">
                  {cases.length === 0
                    ? 'No credit-admin cases in your cascade.'
                    : `${cases.length} total in cascade; ${count} returned by server.`}
                </div>
              </div>
            </Card.Body>
          </Card>
        )}


        {/* Table */}
        {!loading && !error && filteredCases.length > 0 && (
          <Card>
            <Card.Body className="p-0">
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      <th className="px-4 py-3">Case ID</th>
                      <th className="px-4 py-3">Client</th>
                      <th className="px-4 py-3">Product</th>
                      <th className="px-4 py-3 text-right">Amount</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3 text-center">Conditions</th>
                      <th className="px-4 py-3">RM</th>
                      <th className="px-4 py-3">Approved</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {filteredCases.map((c) => (
                      <tr
                        key={c.id}
                        onClick={() => navigate(`/credit-admin/${encodeURIComponent(c.id)}`)}
                        className="hover:bg-gray-50 cursor-pointer transition"
                      >
                        <td className="px-4 py-3 font-mono text-xs text-gray-600">
                          {c.id}
                        </td>
                        <td className="px-4 py-3 font-medium text-gray-900">
                          {c.client_name}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {c.product || '—'}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-gray-700">
                          {formatAmount(c.amount, currencySymbol)}
                        </td>
                        <td className="px-4 py-3">
                          <Badge tone={caseStatusTone(c)} size="sm">
                            {caseStatusLabel(c)}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-center font-mono text-xs text-gray-700">
                          {conditionProgress(c)}
                        </td>
                        <td className="px-4 py-3 text-gray-700 text-xs">
                          {c.rm_name || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-600 text-xs">
                          {formatDate(c.approval_date)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="px-4 py-3 border-t border-gray-100 text-xs text-gray-500">
                Showing {filteredCases.length} of {cases.length} cases
                {categoryFilter !== 'all' && ` (category: ${caseCategoryLabel(categoryFilter)})`}
                {searchTerm && ` (search: "${searchTerm}")`}
              </div>
            </Card.Body>
          </Card>
        )}

      </main>
    </div>
  );
}
