// v10.541 Phase 8 Batch γ4b — Strategic Initiatives landing page.
//
// Read-only portfolio dashboard. Top: aggregate RAG distribution card.
// Below: at-risk initiatives list (clickable to /initiatives/{id}).
// Empty-state: friendly "No initiatives registered yet" panel when
// the backend reports status="no_data" (data file missing).

import { useNavigate } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { usePortfolioSummary } from '@/hooks/usePortfolioSummary';
import { Card } from '@/components/Card';
import { PageHeader } from '@/components/PageHeader';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Skeleton } from '@/components/Skeleton';
import { ragTone, type AtRiskItem } from '@/types/initiatives';


export function Initiatives() {
  const { branding } = useBranding();
  const { summary, status, note, loading, error, refetch } = usePortfolioSummary();
  const navigate = useNavigate();

  const total       = summary?.total ?? 0;
  const green       = summary?.rag_distribution?.GREEN ?? 0;
  const amber       = summary?.rag_distribution?.AMBER ?? 0;
  const red         = summary?.rag_distribution?.RED ?? 0;
  const atRisk      = Array.isArray(summary?.at_risk) ? summary!.at_risk! : [];
  const isNoData    = status === 'no_data';

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        breadcrumbs={[{ label: 'Executive Intelligence' }, { label: 'Strategic Initiatives' }]}
        title="Strategic Initiatives"
        subtitle="Portfolio rollup · RAG distribution · initiatives at risk."
      />

      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6 space-y-5">

        <div className="flex items-center justify-between">
          <div className="text-xs text-gray-500">
            Strategic initiative portfolio · {branding?.bank_name ?? 'Bank'}
          </div>
          <Button variant="ghost" size="sm" onClick={() => refetch()}>
            Refresh
          </Button>
        </div>


        {/* ─────────── Portfolio rollup ─────────── */}
        <Card stripe="primary">
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">
              Portfolio Rollup
            </h2>
            <span className="text-xs text-gray-500">Bank-wide RAG distribution</span>
          </Card.Header>
          <Card.Body>
            {loading && (
              <div className="space-y-3">
                <Skeleton className="h-8 w-1/2" />
                <Skeleton className="h-20 w-full" />
              </div>
            )}

            {error && !loading && (
              <div className="text-sm text-red-700">{error}</div>
            )}

            {!loading && !error && (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <RollupTile label="Total" value={total} tone="neutral" />
                  <RollupTile label="On track" value={green} tone="success" />
                  <RollupTile label="Watch" value={amber} tone="warning" />
                  <RollupTile label="At risk" value={red} tone="danger" />
                </div>

                {isNoData && (
                  <div className="mt-4 rounded-md bg-yellow-50 border border-yellow-200 px-4 py-3 text-sm text-yellow-800">
                    <div className="font-medium">No initiatives registered yet</div>
                    <div className="text-xs mt-1 text-yellow-700">
                      {note ?? 'The strategic initiatives engine has no data file to read. Once initiatives get registered (via the Streamlit Command Centre page or future React write surface), this dashboard will populate automatically.'}
                    </div>
                  </div>
                )}
              </>
            )}
          </Card.Body>
        </Card>


        {/* ─────────── At-risk list ─────────── */}
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">
              Initiatives at risk ({atRisk.length})
            </h2>
            <span className="text-xs text-gray-500">
              Initiatives with RAG = AMBER or RED, or otherwise flagged by the engine
            </span>
          </Card.Header>
          <Card.Body className="p-0">
            {loading && (
              <div className="px-6 py-4 space-y-2">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-2/3" />
              </div>
            )}

            {!loading && !error && atRisk.length === 0 && (
              <div className="px-6 py-4 text-xs text-gray-400 italic">
                {isNoData
                  ? 'No data — see note above.'
                  : 'No initiatives flagged at risk. All registered initiatives are on track (GREEN).'}
              </div>
            )}

            {!loading && !error && atRisk.length > 0 && (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      <th className="px-4 py-3">Name</th>
                      <th className="px-4 py-3">RAG</th>
                      <th className="px-4 py-3">Phase</th>
                      <th className="px-4 py-3">Reason</th>
                      <th className="px-4 py-3"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {atRisk.map((item: AtRiskItem, i: number) => (
                      <tr key={item.id ?? `risk-${i}`} className="hover:bg-gray-50">
                        <td className="px-4 py-2 font-medium text-gray-900">
                          {item.name ?? '—'}
                        </td>
                        <td className="px-4 py-2">
                          <Badge tone={ragTone(item.rag as string)} size="sm">
                            {(item.rag as string) ?? '—'}
                          </Badge>
                        </td>
                        <td className="px-4 py-2 text-xs text-gray-700">{(item.phase as string) ?? '—'}</td>
                        <td className="px-4 py-2 text-xs text-gray-600">{(item.reason as string) ?? '—'}</td>
                        <td className="px-4 py-2 text-right">
                          {item.id && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => navigate(`/initiatives/${encodeURIComponent(String(item.id))}`)}
                            >
                              View →
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card.Body>
        </Card>


        <Card>
          <Card.Body>
            <div className="text-xs text-gray-500 italic">
              <strong>Read-only view (γ4).</strong> Initiative registration, milestone updates,
              RAG transitions, and dependency editing live in the Streamlit Command Centre page
              (the legacy admin interface). Edit surfaces may land in React later (γ4c+).
            </div>
          </Card.Body>
        </Card>

      </main>
    </div>
  );
}


// ── Rollup tile ──────────────────────────────────────────────────────────

function RollupTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: 'success' | 'warning' | 'danger' | 'neutral';
}) {
  const ringColor =
    tone === 'success' ? 'ring-green-200 bg-green-50'  :
    tone === 'warning' ? 'ring-yellow-200 bg-yellow-50' :
    tone === 'danger'  ? 'ring-red-200 bg-red-50'      :
                         'ring-gray-200 bg-gray-50';

  const valueColor =
    tone === 'success' ? 'text-green-700'  :
    tone === 'warning' ? 'text-yellow-700' :
    tone === 'danger'  ? 'text-red-700'    :
                         'text-gray-700';

  return (
    <div className={`rounded-md ring-1 ${ringColor} px-4 py-3`}>
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${valueColor}`}>{value}</div>
    </div>
  );
}
