// Referrals inbox — Batch B frontend.
//
// Three views over the refer-existing-deal lifecycle:
//   • Incoming  — pending referrals addressed to me; Accept or Decline (reason).
//   • Returned  — referrals I made that were declined; Reassign to someone new.
//   • Following — referrals I made that are live (pending/accepted); read-only.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/PageHeader';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge, type BadgeTone } from '@/components/Badge';
import { useToast } from '@/components/Toast';
import {
  fetchIncomingReferrals, fetchReturnedReferrals, fetchOutgoingReferrals,
  fetchOutgoingReferralAnalytics, fetchReferralsByDepartment, fetchTeamReferrals,
  acceptReferral, declineReferral, reReferReferral, reassignReferral,
  type ReferralView, type OutgoingReferralAnalytics, type ReferralsByDepartment,
  type TeamReferralsResponse,
} from '@/lib/api';

type Tab = 'incoming' | 'returned' | 'following' | 'team';

const inputCls =
  'w-full px-3 py-1.5 rounded-md border border-gray-300 text-sm focus:outline-none ' +
  'focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20';

function formatKes(n: number | undefined): string {
  if (typeof n !== 'number' || !isFinite(n)) return '—';
  return `KES ${Math.round(n).toLocaleString()}`;
}
function formatDate(s: string | undefined): string {
  if (!s) return '';
  const d = new Date(s);
  return isNaN(d.getTime()) ? '' : d.toLocaleDateString();
}
function statusTone(s: string | undefined): BadgeTone {
  if (s === 'accepted') return 'success';
  if (s === 'pending') return 'info';
  if (s === 'declined') return 'warning';
  return 'neutral';
}

export default function Referrals() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('incoming');
  const [incoming, setIncoming] = useState<ReferralView[]>([]);
  const [returned, setReturned] = useState<ReferralView[]>([]);
  const [outgoing, setOutgoing] = useState<ReferralView[]>([]);
  const [analytics, setAnalytics] = useState<OutgoingReferralAnalytics | null>(null);
  const [dept, setDept] = useState<ReferralsByDepartment | null>(null);
  const [team, setTeam] = useState<ReferralView[]>([]);
  const [reReferFor, setReReferFor] = useState<string | null>(null);
  const [rrCode, setRrCode] = useState('');
  const [rrName, setRrName] = useState('');
  const [rrNote, setRrNote] = useState('');
  const [teamSummary, setTeamSummary] = useState<TeamReferralsResponse['summary'] | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [declineFor, setDeclineFor] = useState<string | null>(null);
  const [declineReason, setDeclineReason] = useState('');
  const [reassignFor, setReassignFor] = useState<string | null>(null);
  const [reCode, setReCode] = useState('');
  const [reName, setReName] = useState('');
  const [reNote, setReNote] = useState('');

  function loadAll() {
    setLoading(true);
    Promise.all([fetchIncomingReferrals(), fetchReturnedReferrals(), fetchOutgoingReferrals()])
      .then(([i, r, o]) => { setIncoming(i.deals); setReturned(r.deals); setOutgoing(o.deals); })
      .catch(() => toast({ tone: 'danger', message: 'Could not load referrals.' }))
      .finally(() => setLoading(false));
    // Funnel + alerts (own referrals); department view is management-only (403 -> hidden).
    fetchOutgoingReferralAnalytics().then(setAnalytics).catch(() => setAnalytics(null));
    fetchReferralsByDepartment().then(setDept).catch(() => setDept(null));
    fetchTeamReferrals().then((t) => { setTeam(t.deals); setTeamSummary(t.summary); }).catch(() => {});
  }
  useEffect(() => { loadAll(); /* eslint-disable-next-line */ }, []);

  async function onAccept(d: ReferralView) {
    setBusyId(d.id);
    try {
      await acceptReferral(d.id);
      toast({ tone: 'success', message: `Accepted ${d.client_name ?? d.id}.` });
      loadAll();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Accept failed.' });
    } finally { setBusyId(null); }
  }

  async function onDecline(d: ReferralView) {
    if (declineReason.trim().length < 3) {
      toast({ tone: 'warning', message: 'A decline reason (3+ characters) is required.' });
      return;
    }
    setBusyId(d.id);
    try {
      await declineReferral(d.id, declineReason.trim());
      toast({ tone: 'success', message: `Declined — returned to the referrer.` });
      setDeclineFor(null); setDeclineReason(''); loadAll();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Decline failed.' });
    } finally { setBusyId(null); }
  }

  async function onReassign(d: ReferralView) {
    if (!reCode.trim() || !reName.trim()) {
      toast({ tone: 'warning', message: 'Recipient code and name are required.' });
      return;
    }
    setBusyId(d.id);
    try {
      await reassignReferral(d.id, reCode.trim(), reName.trim(), reNote.trim());
      toast({ tone: 'success', message: `Reassigned to ${reName.trim()}.` });
      setReassignFor(null); setReCode(''); setReName(''); setReNote(''); loadAll();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Reassign failed.' });
    } finally { setBusyId(null); }
  }

  async function onReRefer(d: ReferralView) {
    if (!rrCode.trim() || !rrName.trim()) { toast({ tone: 'danger', message: 'Recipient code and name are required.' }); return; }
    setBusyId(d.id);
    try {
      await reReferReferral(d.id, rrCode.trim(), rrName.trim(), rrNote.trim() || undefined);
      toast({ tone: 'success', message: 'Re-referred onward.' });
      setReReferFor(null); setRrCode(''); setRrName(''); setRrNote('');
      await loadAll();
    } catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Re-refer failed' }); }
    finally { setBusyId(null); }
  }

  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: 'incoming', label: 'Incoming', count: incoming.length },
    { key: 'returned', label: 'Returned', count: returned.length },
    { key: 'following', label: 'Following', count: outgoing.length },
    { key: 'team', label: 'Team', count: team.length },
  ];
  const active = tab === 'incoming' ? incoming
    : tab === 'returned' ? returned
    : tab === 'team' ? team
    : outgoing;

  function ReferralJourney({ chain }: { chain?: ReferralView['referral_chain'] }) {
    if (!chain || chain.length === 0) return null;
    return (
      <div className="mt-2 border-t border-gray-100 pt-2">
        <div className="mb-1 text-xs font-medium text-gray-500">Referral journey</div>
        <ol className="space-y-1">
          {chain.map((h, i) => (
            <li key={i} className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-gray-600">{h.seq}</span>
              <span className="text-gray-700">{h.from_name || h.from_code}{h.from_dept ? ` · ${h.from_dept}` : ''}</span>
              <span className="text-gray-400">→</span>
              <span className="text-gray-700">{h.to_name || h.to_code}{h.to_dept ? ` · ${h.to_dept}` : ''}</span>
              <span className={'rounded px-1.5 py-0.5 ' + (h.status === 'accepted' ? 'bg-emerald-50 text-emerald-700' : h.status === 'declined' ? 'bg-amber-50 text-amber-700' : 'bg-gray-50 text-gray-500')}>{h.status}</span>
            </li>
          ))}
        </ol>
      </div>
    );
  }

  function DealMeta({ d }: { d: ReferralView }) {
    return (
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-gray-900 truncate">{d.client_name ?? d.id}</span>
          <Badge tone={statusTone(d.referral_status)} size="sm">{d.referral_status ?? '—'}</Badge>
          {d.referral_tier && (
            <Badge tone={d.referral_tier === 'S2B' ? 'success' : 'info'} size="sm">{d.referral_tier}</Badge>
          )}
          {d.cross_unit && (
            <Badge tone="neutral" size="sm">cross-unit</Badge>
          )}
        </div>
        <div className="mt-0.5 text-xs text-gray-500">
          {[d.product_type, d.stage, d.segment].filter(Boolean).join(' · ') || '—'}
        </div>
        <div className="mt-0.5 text-sm text-gray-700 tabular-nums">{formatKes(d.amount_kes ?? d.deal_value)}</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        ribbon
        title="A2Z Sales Referral"
        subtitle="Deals referred to you, returned to you, and the ones you're following."
        breadcrumbs={[{ label: 'A2Z Pipeline Intelligence System (PIS)' }, { label: 'A2Z Sales Referral' }]}
        actions={
          <Button variant="primary" size="sm" onClick={() => navigate('/pipeline/new?refer=1')}>
            New referral
          </Button>
        }
      />
      <main className="max-w-4xl mx-auto px-6 py-6">
        <div className="mb-4 inline-flex rounded-lg border border-gray-200 bg-white p-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={
                'px-4 py-1.5 rounded-md text-sm font-medium transition-colors ' +
                (tab === t.key
                  ? 'bg-brand-primary text-white'
                  : 'text-gray-600 hover:text-gray-900')
              }
            >
              {t.label}
              <span className={
                'ml-2 rounded-full px-1.5 py-0.5 text-xs ' +
                (tab === t.key ? 'bg-white/20' : 'bg-gray-100 text-gray-500')
              }>{t.count}</span>
            </button>
          ))}
        </div>

        {tab === 'team' && teamSummary && (
          <div className="space-y-3 mb-3">
            <Card><Card.Body>
              <div className="text-sm font-semibold text-gray-900 mb-1">Team referral funnel</div>
              <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                <span className="text-gray-500">Total <b className="text-gray-900">{teamSummary.total}</b></span>
                <span className="text-gray-500">Pending <b className="text-amber-700">{teamSummary.by_status.pending}</b></span>
                <span className="text-gray-500">Accepted <b className="text-emerald-700">{teamSummary.by_status.accepted}</b></span>
                <span className="text-gray-500">Closed won <b className="text-emerald-700">{teamSummary.closed.won}</b></span>
                <span className="text-gray-500">Closed lost <b className="text-gray-700">{teamSummary.closed.lost}</b></span>
              </div>
              {teamSummary.by_tier && (
                <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm border-t border-gray-100 pt-2">
                  <span className="text-gray-500">B2B (business→business) <b className="text-gray-900">{teamSummary.by_tier.B2B}</b></span>
                  <span className="text-gray-500">S2B (support→business) <b className="text-gray-900">{teamSummary.by_tier.S2B}</b></span>
                </div>
              )}
            </Card.Body></Card>
            {dept && dept.departments.length > 0 && (
              <Card><Card.Body>
                <div className="text-sm font-semibold text-gray-900 mb-2">By department</div>
                <div className="space-y-1">
                  {dept.departments.map((row) => (
                    <div key={row.department} className="flex items-center justify-between text-sm">
                      <span className="text-gray-700">{row.department}</span>
                      <span className="text-gray-500 tabular-nums">
                        {row.total} total · {row.by_status.accepted} accepted · {row.closed.won} won
                      </span>
                    </div>
                  ))}
                </div>
              </Card.Body></Card>
            )}
          </div>
        )}

        {tab === 'following' && analytics && (
          <div className="space-y-3 mb-3">
            <Card><Card.Body>
              <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                <span className="text-gray-500">Total referred <b className="text-gray-900">{analytics.total}</b></span>
                <span className="text-gray-500">Pending <b className="text-amber-700">{analytics.by_status.pending}</b></span>
                <span className="text-gray-500">Accepted <b className="text-emerald-700">{analytics.by_status.accepted}</b></span>
                <span className="text-gray-500">Closed won <b className="text-emerald-700">{analytics.closed.won}</b></span>
                <span className="text-gray-500">Closed lost <b className="text-gray-700">{analytics.closed.lost}</b></span>
              </div>
            </Card.Body></Card>

            {analytics.by_stage && Object.keys(analytics.by_stage).length > 0 && (
              <Card><Card.Body>
                <div className="text-sm font-semibold text-gray-900 mb-2">Where they are now</div>
                <div className="space-y-1">
                  {Object.entries(analytics.by_stage).sort((a, b) => b[1] - a[1]).map(([stage, n]) => (
                    <div key={stage} className="flex items-center justify-between text-sm">
                      <span className="text-gray-700">{stage}</span>
                      <span className="text-gray-500 tabular-nums">{n}</span>
                    </div>
                  ))}
                </div>
              </Card.Body></Card>
            )}

            {analytics.alerts.length > 0 && (
              <Card stripe="accent"><Card.Body>
                <div className="text-sm font-semibold text-gray-900 mb-1">Needs attention</div>
                <ul className="space-y-1">
                  {analytics.alerts.map((al, i) => (
                    <li key={al.id || i} className="text-sm text-gray-700">
                      <span className="font-medium">{al.client_name || al.id}</span>
                      {al.referred_to ? ` → ${al.referred_to}` : ''} — {al.message}
                    </li>
                  ))}
                </ul>
              </Card.Body></Card>
            )}

            {dept && dept.departments.length > 0 && (
              <Card><Card.Body>
                <div className="text-sm font-semibold text-gray-900 mb-2">By department</div>
                <div className="space-y-1">
                  {dept.departments.map((row) => (
                    <div key={row.department} className="flex items-center justify-between text-sm">
                      <span className="text-gray-700">{row.department}</span>
                      <span className="text-gray-500 tabular-nums">
                        {row.total} total · {row.by_status.accepted} accepted · {row.closed.won} won
                      </span>
                    </div>
                  ))}
                </div>
              </Card.Body></Card>
            )}
          </div>
        )}

        {loading ? (
          <div className="py-16 text-center text-sm text-gray-500">Loading referrals…</div>
        ) : active.length === 0 ? (
          <Card><Card.Body>
            <p className="py-8 text-center text-sm text-gray-400">
              {tab === 'incoming' && 'No referrals waiting for you.'}
              {tab === 'returned' && 'No returned referrals to reassign.'}
              {tab === 'following' && "You aren't following any referrals yet."}
              {tab === 'team' && 'No referrals across your team yet.'}
            </p>
          </Card.Body></Card>
        ) : (
          <div className="space-y-3">
            {active.map((d) => (
              <Card key={d.id}>
                <Card.Body>
                  <div className="flex items-start justify-between gap-4">
                    <DealMeta d={d} />
                    <div className="shrink-0 text-right text-xs text-gray-400">
                      {tab === 'incoming' && d.referred_by_name && (
                        <div>from <span className="text-gray-600">{d.referred_by_name}</span></div>
                      )}
                      {tab === 'following' && d.referred_to && (
                        <div>to <span className="text-gray-600">{d.referred_to}</span></div>
                      )}
                      {tab === 'team' && (
                        <div>
                          {d.referred_by_name && <div><span className="text-gray-600">{d.referred_by_name}</span></div>}
                          {d.referred_to && <div className="mt-0.5">→ <span className="text-gray-600">{d.referred_to}</span></div>}
                        </div>
                      )}
                      {formatDate(d.referred_at) && <div className="mt-0.5">{formatDate(d.referred_at)}</div>}
                    </div>
                  </div>

                  {d.referral_note && (
                    <p className="mt-2 text-sm text-gray-600">
                      <span className="text-gray-400">Note: </span>{d.referral_note}
                    </p>
                  )}
                  {tab === 'returned' && d.decline_reason && (
                    <p className="mt-1 text-sm text-amber-700">
                      <span className="text-amber-500">Declined: </span>{d.decline_reason}
                    </p>
                  )}

                  {(tab === 'following' || tab === 'team') && d.stage && (
                    <p className="mt-2 text-sm">
                      <span className="text-gray-400">Currently at: </span>
                      <span className="font-medium text-gray-800">{d.stage}</span>
                    </p>
                  )}

                  <ReferralJourney chain={d.referral_chain} />

                  {d.referral_status === 'accepted' && (
                    <div className="mt-3 border-t border-gray-100 pt-3">
                      {reReferFor === d.id ? (
                        <div className="space-y-2">
                          <div className="grid sm:grid-cols-2 gap-2">
                            <input className={inputCls} placeholder="Onward recipient staff code"
                              value={rrCode} onChange={(e) => setRrCode(e.target.value)} />
                            <input className={inputCls} placeholder="Onward recipient name"
                              value={rrName} onChange={(e) => setRrName(e.target.value)} />
                          </div>
                          <input className={inputCls} placeholder="Note (optional)"
                            value={rrNote} onChange={(e) => setRrNote(e.target.value)} />
                          <div className="flex gap-2">
                            <Button variant="primary" size="sm" loading={busyId === d.id}
                              onClick={() => onReRefer(d)}>Re-refer onward</Button>
                            <Button variant="ghost" size="sm"
                              onClick={() => { setReReferFor(null); setRrCode(''); setRrName(''); setRrNote(''); }}>Cancel</Button>
                          </div>
                        </div>
                      ) : (
                        <Button variant="ghost" size="sm"
                          onClick={() => { setReReferFor(d.id); setRrCode(''); setRrName(''); setRrNote(''); }}>
                          Re-refer to another department
                        </Button>
                      )}
                    </div>
                  )}

                  {/* ── Incoming actions ── */}
                  {tab === 'incoming' && (
                    <div className="mt-3 border-t border-gray-100 pt-3">
                      {declineFor === d.id ? (
                        <div className="space-y-2">
                          <textarea
                            className={inputCls} rows={2} placeholder="Reason for declining (required)…"
                            value={declineReason} onChange={(e) => setDeclineReason(e.target.value)}
                          />
                          <div className="flex gap-2">
                            <Button variant="danger" size="sm" loading={busyId === d.id}
                              onClick={() => onDecline(d)}>Confirm decline</Button>
                            <Button variant="ghost" size="sm"
                              onClick={() => { setDeclineFor(null); setDeclineReason(''); }}>Cancel</Button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex gap-2">
                          <Button variant="primary" size="sm" loading={busyId === d.id}
                            onClick={() => onAccept(d)}>Accept</Button>
                          <Button variant="ghost" size="sm"
                            onClick={() => { setDeclineFor(d.id); setDeclineReason(''); }}>Decline</Button>
                        </div>
                      )}
                    </div>
                  )}

                  {/* ── Returned actions (reassign) ── */}
                  {tab === 'returned' && (
                    <div className="mt-3 border-t border-gray-100 pt-3">
                      {reassignFor === d.id ? (
                        <div className="space-y-2">
                          <div className="grid sm:grid-cols-2 gap-2">
                            <input className={inputCls} placeholder="New recipient staff code"
                              value={reCode} onChange={(e) => setReCode(e.target.value)} />
                            <input className={inputCls} placeholder="New recipient name"
                              value={reName} onChange={(e) => setReName(e.target.value)} />
                          </div>
                          <input className={inputCls} placeholder="Note (optional)"
                            value={reNote} onChange={(e) => setReNote(e.target.value)} />
                          <div className="flex gap-2">
                            <Button variant="primary" size="sm" loading={busyId === d.id}
                              onClick={() => onReassign(d)}>Reassign</Button>
                            <Button variant="ghost" size="sm"
                              onClick={() => { setReassignFor(null); setReCode(''); setReName(''); setReNote(''); }}>
                              Cancel</Button>
                          </div>
                        </div>
                      ) : (
                        <Button variant="secondary" size="sm"
                          onClick={() => { setReassignFor(d.id); }}>Reassign…</Button>
                      )}
                    </div>
                  )}
                </Card.Body>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
