// v10.541 Phase 8 Batch γ4b — Single initiative detail page.

import { useParams, useNavigate } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useInitiativeDetail } from '@/hooks/useInitiativeDetail';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { PageHeader } from '@/components/PageHeader';
import { Skeleton } from '@/components/Skeleton';
import {
  ragTone,
  phaseTone,
  riskTone,
  milestoneStateTone,
  formatBudget,
  type InitiativeMilestone,
  type InitiativeDependency,
  type InitiativeBsc,
} from '@/types/initiatives';


export function InitiativeDetail() {
  const { initiativeId } = useParams<{ initiativeId: string }>();
  const { branding } = useBranding();
  const { initiative, loading, error, notFound, refetch } = useInitiativeDetail(initiativeId);
  const navigate = useNavigate();

  const currencySymbol = branding?.currency_symbol ?? 'KES';

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="Initiative Detail"
        breadcrumbs={[{ label: 'Initiatives', to: '/initiatives' }, { label: initiativeId ?? '—' }]}
        actions={
          <Button variant="ghost" size="sm" onClick={() => navigate('/initiatives')}>
            ← Back to Initiatives
          </Button>
        }
      />

      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6 space-y-5">

        {loading && (
          <Card>
            <Card.Body>
              <Skeleton className="h-8 w-1/2" />
              <Skeleton className="h-4 w-full mt-3" />
              <Skeleton className="h-4 w-3/4 mt-2" />
            </Card.Body>
          </Card>
        )}

        {notFound && !loading && (
          <Card>
            <Card.Body>
              <div className="text-sm text-gray-700">
                <span className="font-medium">Initiative not found.</span> No initiative with id{' '}
                <span className="font-mono">{initiativeId}</span> is registered. This could be a
                stale link, a typo in the id, or the engine has no data file yet.
              </div>
              <div className="mt-3">
                <Button variant="primary" size="sm" onClick={() => navigate('/initiatives')}>
                  Back to portfolio
                </Button>
              </div>
            </Card.Body>
          </Card>
        )}

        {error && !loading && !notFound && (
          <Card>
            <Card.Body>
              <div className="text-sm text-red-700">{error}</div>
              <div className="mt-3">
                <Button variant="ghost" size="sm" onClick={() => refetch()}>
                  Retry
                </Button>
              </div>
            </Card.Body>
          </Card>
        )}

        {!loading && !error && !notFound && initiative && (
          <>
            {/* ─── Identity card ─── */}
            <Card stripe="primary">
              <Card.Header>
                <div className="flex items-center gap-3 flex-wrap">
                  <h2 className="text-lg font-semibold text-brand-secondary">
                    {(initiative.name as string) ?? '—'}
                  </h2>
                  {initiative.rag && (
                    <Badge tone={ragTone(initiative.rag as string)} size="md">
                      RAG: {initiative.rag as string}
                    </Badge>
                  )}
                  {initiative.phase && (
                    <Badge tone={phaseTone(initiative.phase as string)} size="sm">
                      {initiative.phase as string}
                    </Badge>
                  )}
                  {initiative.risk_level && (
                    <Badge tone={riskTone(initiative.risk_level as string)} size="sm">
                      Risk: {initiative.risk_level as string}
                    </Badge>
                  )}
                </div>
                <span className="font-mono text-xs text-gray-500">{(initiative.id as string) ?? '—'}</span>
              </Card.Header>
              <Card.Body>
                {initiative.description ? (
                  <p className="text-sm text-gray-700">{initiative.description as string}</p>
                ) : (
                  <p className="text-sm text-gray-400 italic">No description provided.</p>
                )}

                <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <KV label="Owner"      value={(initiative.owner as string) ?? '—'} />
                  <KV label="Start"      value={(initiative.start_date as string) ?? '—'} />
                  <KV label="End"        value={(initiative.end_date as string) ?? '—'} />
                  <KV label="Budget"     value={formatBudget(initiative.budget as number | undefined, currencySymbol)} />
                </div>
              </Card.Body>
            </Card>


            {/* ─── Milestones ─── */}
            <Card>
              <Card.Header>
                <h3 className="text-base font-semibold text-gray-900">
                  Milestones ({(initiative.milestones as InitiativeMilestone[] | undefined)?.length ?? 0})
                </h3>
              </Card.Header>
              <Card.Body className="p-0">
                {!initiative.milestones || (initiative.milestones as InitiativeMilestone[]).length === 0 ? (
                  <div className="px-6 py-4 text-xs text-gray-400 italic">No milestones registered.</div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-gray-50 border-b border-gray-200">
                        <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                          <th className="px-4 py-3">Milestone</th>
                          <th className="px-4 py-3">Due</th>
                          <th className="px-4 py-3">State</th>
                          <th className="px-4 py-3">Completed</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {(initiative.milestones as InitiativeMilestone[]).map((m, i) => (
                          <tr key={m.id ?? `ms-${i}`} className="hover:bg-gray-50">
                            <td className="px-4 py-2 font-medium text-gray-900">{m.name ?? '—'}</td>
                            <td className="px-4 py-2 text-xs text-gray-700">{m.due_date ?? '—'}</td>
                            <td className="px-4 py-2">
                              <Badge tone={milestoneStateTone(m.state as string)} size="sm">
                                {(m.state as string) ?? '—'}
                              </Badge>
                            </td>
                            <td className="px-4 py-2 text-xs text-gray-600">{m.completed_at ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card.Body>
            </Card>


            {/* ─── BSC linkage ─── */}
            <Card>
              <Card.Header>
                <h3 className="text-base font-semibold text-gray-900">
                  BSC linkage ({(initiative.bsc_linkage as InitiativeBsc[] | undefined)?.length ?? 0})
                </h3>
              </Card.Header>
              <Card.Body className="p-0">
                {!initiative.bsc_linkage || (initiative.bsc_linkage as InitiativeBsc[]).length === 0 ? (
                  <div className="px-6 py-4 text-xs text-gray-400 italic">
                    Not linked to a balanced scorecard KPI.
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-gray-50 border-b border-gray-200">
                        <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                          <th className="px-4 py-3">Perspective</th>
                          <th className="px-4 py-3">KPI ID</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {(initiative.bsc_linkage as InitiativeBsc[]).map((b, i) => (
                          <tr key={`bsc-${i}`}>
                            <td className="px-4 py-2 text-sm text-gray-700">{b.perspective ?? '—'}</td>
                            <td className="px-4 py-2 text-xs font-mono text-gray-600">{b.kpi_id ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card.Body>
            </Card>


            {/* ─── Dependencies ─── */}
            <Card>
              <Card.Header>
                <h3 className="text-base font-semibold text-gray-900">
                  Dependencies ({(initiative.dependencies as InitiativeDependency[] | undefined)?.length ?? 0})
                </h3>
              </Card.Header>
              <Card.Body className="p-0">
                {!initiative.dependencies || (initiative.dependencies as InitiativeDependency[]).length === 0 ? (
                  <div className="px-6 py-4 text-xs text-gray-400 italic">No upstream dependencies registered.</div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-gray-50 border-b border-gray-200">
                        <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                          <th className="px-4 py-3">Depends on</th>
                          <th className="px-4 py-3">Status</th>
                          <th className="px-4 py-3"></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {(initiative.dependencies as InitiativeDependency[]).map((d, i) => (
                          <tr key={d.depends_on_id ?? `dep-${i}`} className="hover:bg-gray-50">
                            <td className="px-4 py-2 text-sm text-gray-700">
                              {d.depends_on_name ?? '—'}
                              {d.depends_on_id && <span className="text-gray-400 ml-1 font-mono text-xs">({d.depends_on_id})</span>}
                            </td>
                            <td className="px-4 py-2 text-xs text-gray-600">{d.status ?? '—'}</td>
                            <td className="px-4 py-2 text-right">
                              {d.depends_on_id && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => navigate(`/initiatives/${encodeURIComponent(String(d.depends_on_id))}`)}
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
          </>
        )}
      </main>
    </div>
  );
}


// ── KV helper ────────────────────────────────────────────────────────────

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className="text-sm text-gray-900 mt-0.5">{value}</div>
    </div>
  );
}
