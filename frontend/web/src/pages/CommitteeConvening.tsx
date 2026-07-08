// C4: MD convening queue — referred cases grouped by committee tier. The MD sees
// per-tier counts, case details, pre-read tallies, and convenes the binding meeting.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/PageHeader';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { useToast } from '@/components/Toast';
import {
  fetchConveningQueue, convokeCommittee,
  type ConveningQueueResponse, type ConveningCase,
} from '@/lib/api';

function fmt(n?: number): string {
  if (n == null) return '—';
  return n.toLocaleString();
}

export function CommitteeConvening() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [data, setData] = useState<ConveningQueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try { setData(await fetchConveningQueue()); }
    catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load queue' }); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, []);

  const convene = async (appId: string) => {
    setBusy(appId);
    try {
      await convokeCommittee(appId);
      toast({ tone: 'success', message: 'Committee convened — the binding vote is open.' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Convene failed' });
    } finally { setBusy(null); }
  };

  const slaBadge = (c: ConveningCase) => {
    if (!c.sla) return null;
    const st = c.sla.state;
    const cls = st === 'breached' ? 'bg-red-100 text-red-700'
      : st === 'due_soon' ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700';
    const txt = st === 'breached' ? `${c.sla.overdue_business_days}d over`
      : st === 'due_soon' ? `${c.sla.remaining_business_days}d left` : 'On track';
    return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>{txt}</span>;
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        breadcrumbs={[{ label: 'EKE Credit Intelligence System (CIS)' }, { label: 'Committee Convening' }]}
        title="Committee Convening"
        subtitle="Cases referred to committee, grouped by tier. Convene the meeting to open the binding vote."
      />
      <main className="max-w-6xl mx-auto px-6 py-6">
        {!loading && data && (
          <div className="mb-4 flex gap-3">
            <Card><Card.Body className="py-3">
              <div className="text-xs text-gray-500">Total before committee</div>
              <div className="text-xl font-semibold">{data.total}</div>
            </Card.Body></Card>
            <Card><Card.Body className="py-3">
              <div className="text-xs text-gray-500">Awaiting convening</div>
              <div className="text-xl font-semibold text-brand-primary">{data.awaiting}</div>
            </Card.Body></Card>
          </div>
        )}

        {loading && <Card><Card.Body>Loading…</Card.Body></Card>}
        {!loading && data && data.tiers.length === 0 && (
          <Card><Card.Body>
            <div className="py-8 text-center text-sm text-gray-500">No cases before any committee right now.</div>
          </Card.Body></Card>
        )}

        {!loading && data && data.tiers.map((t) => (
          <Card key={String(t.tier)} className="mb-4" stripe="primary">
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">{t.name ?? `Tier ${t.tier}`}</h2>
              <Badge tone="brand" size="sm">{t.count}</Badge>
            </Card.Header>
            <Card.Body>
              <div className="space-y-2">
                {t.cases.map((c) => (
                  <div key={c.id} className="flex items-center justify-between rounded border p-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <button className="font-mono text-xs text-brand-primary hover:underline"
                          onClick={() => navigate(`/lms/${encodeURIComponent(c.id)}`)}>{c.id}</button>
                        <span className="text-sm font-medium">{c.client_name}</span>
                        {slaBadge(c)}
                      </div>
                      <div className="mt-0.5 text-xs text-gray-500">
                        {c.product} · KES {fmt(c.amount)} · pre-reads: {c.pre_read_count}
                        {' '}(<span className="text-green-600">{c.pre_read_tally.leaning_approve ?? 0}▲</span>
                        {' '}<span className="text-red-600">{c.pre_read_tally.leaning_decline ?? 0}▼</span>
                        {' '}<span className="text-amber-600">{c.pre_read_tally.questions ?? 0}?</span>)
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {c.convened
                        ? <Badge tone="success" size="sm">Convened</Badge>
                        : <Button size="sm" onClick={() => void convene(c.id)} disabled={busy === c.id}>
                            {busy === c.id ? 'Convening…' : 'Convene'}
                          </Button>}
                    </div>
                  </div>
                ))}
              </div>
            </Card.Body>
          </Card>
        ))}
      </main>
    </div>
  );
}
