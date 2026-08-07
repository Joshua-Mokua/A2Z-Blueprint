// Referrals inbox — Batch B frontend.
//
// Three views over the refer-existing-deal lifecycle:
//   • Incoming  — pending referrals addressed to me; Accept or Decline (reason).
//   • Returned  — referrals I made that were declined; Reassign to someone new.
//   • Following — referrals I made that are live (pending/accepted); read-only.
import { displayName } from "../lib/names";
import { useEffect, useState, useMemo } from 'react';
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
  type ReferralView, type OutgoingReferralAnalytics, type ReferralsByDepartment, type StaffMember,
  type TeamReferralsResponse,
} from '@/lib/api';

type Tab = 'overview' | 'incoming' | 'returned' | 'following' | 'team';

import { StaffPicker } from '@/components/StaffPicker';
import { Table, type Column } from '@/components/Table';

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

function ReferralOverview({ dept, team, navigate, formatKes, displayName }: {
  dept: ReferralsByDepartment | null;
  team: ReferralView[];
  navigate: (to: string) => void;
  formatKes: (n: number | undefined) => string;
  displayName: (s: string | undefined) => string;
}) {
  const [dir, setDir] = useState<'by_us' | 'to_us' | 'all'>('all');
  const [fMember, setFMember] = useState('');
  const [fProduct, setFProduct] = useState('');
  const [fStatus, setFStatus] = useState('');

  // "our" codes = the referrers within scope (from the analytics leaderboard)
  const ourCodes = useMemo(() => {
    const set = new Set<string>();
    (dept?.by_referrer ?? []).forEach((l) => { if (l.code) set.add(String(l.code)); });
    return set;
  }, [dept]);

  const byUs = useMemo(
    () => team.filter((d) => ourCodes.size === 0 || ourCodes.has(String(d.referred_by_code || ''))),
    [team, ourCodes]);
  const toUs = useMemo(
    () => team.filter((d) => ourCodes.size === 0 || ourCodes.has(String(d.referred_to_code || ''))),
    [team, ourCodes]);
  const dirRows = dir === 'by_us' ? byUs : dir === 'to_us' ? toUs : team;

  const memberOpts = Array.from(new Set(team.map((r) => r.referred_by_name).filter(Boolean))) as string[];
  const productOpts = Array.from(new Set(team.map((r) => r.product_type).filter(Boolean))) as string[];
  const statusOpts = Array.from(new Set(team.map((r) => r.referral_status).filter(Boolean))) as string[];

  const rows = dirRows.filter((r) =>
    (!fMember || r.referred_by_name === fMember)
    && (!fProduct || r.product_type === fProduct)
    && (!fStatus || r.referral_status === fStatus));

  const t = dept?.totals;

  const statusTone2 = (v?: string): BadgeTone =>
    v === 'accepted' ? 'success' : v === 'declined' ? 'warning' : v === 'pending' ? 'info' : 'neutral';

  const columns: Column<ReferralView>[] = [
    { key: 'client_name', header: 'Client', sortable: true, exportValue: (r) => r.client_name || r.id,
      render: (r) => (
        <div>
          <div className="font-medium text-gray-900">{r.client_name || r.id}</div>
          {r.product_type && <div className="text-xs text-gray-500 mt-0.5">{r.product_type}</div>}
        </div>
      ) },
    { key: 'referred_by_name', header: 'Referred by', sortable: true, exportValue: (r) => r.referred_by_name || '',
      render: (r) => (
        <div>
          <div className="text-sm text-gray-800">{displayName(r.referred_by_name)}</div>
          {r.referred_by_code && <div className="text-xs text-gray-400 mt-0.5 font-mono">{r.referred_by_code}</div>}
        </div>
      ) },
    { key: 'referred_to', header: 'To', sortable: true, exportValue: (r) => r.referred_to || '',
      render: (r) => <span className="text-sm text-gray-600">{displayName(r.referred_to)}</span> },
    { key: 'stage', header: 'Stage', sortable: true, exportValue: (r) => r.stage || '',
      render: (r) => <span className="text-sm text-gray-700">{r.stage || '—'}</span> },
    { key: 'referral_status', header: 'Status', sortable: true, exportValue: (r) => r.referral_status || '',
      render: (r) => (
        <span className="flex items-center gap-1">
          <Badge tone={statusTone2(r.referral_status)} size="sm">{r.referral_status || '—'}</Badge>
          {r.referral_tier && <Badge tone={r.referral_tier === 'S2B' ? 'success' : 'info'} size="sm">{r.referral_tier}</Badge>}
        </span>
      ) },
    { key: 'amount_kes', header: 'Value', align: 'right', sortable: true,
      sortAccessor: (r) => Number(r.amount_kes ?? r.deal_value) || 0,
      exportValue: (r) => String(r.amount_kes ?? r.deal_value ?? ''),
      render: (r) => <span className="font-medium text-gray-900 tabular-nums">{formatKes(r.amount_kes ?? r.deal_value)}</span> },
    { key: 'actions', header: '',
      render: (r) => (
        <Button variant="secondary" size="sm" onClick={(e) => { e.stopPropagation(); navigate(`/pipeline/${encodeURIComponent(r.id)}`); }}>View</Button>
      ) },
  ];

  const dirTabs: { key: 'by_us' | 'to_us' | 'all'; label: string; count: number }[] = [
    { key: 'by_us', label: 'Referred by us', count: byUs.length },
    { key: 'to_us', label: 'Referred to us', count: toUs.length },
    { key: 'all', label: 'All', count: team.length },
  ];

  const Filter = ({ label, val, set, opts }: { label: string; val: string; set: (v: string) => void; opts: string[] }) => (
    <select value={val} onChange={(e) => set(e.target.value)}
      className="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700">
      <option value="">{label}: All</option>
      {opts.map((o) => <option key={o} value={o}>{displayName(o)}</option>)}
    </select>
  );

  return (
    <div className="space-y-4">
      {/* compact stat strip */}
      {t && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Card><Card.Body className="py-3"><div className="text-xs text-gray-500">Referrals</div><div className="text-xl font-bold text-gray-900 tabular-nums">{t.total}</div><div className="text-[11px] text-gray-400">{t.pending} pending · {t.accepted} accepted</div></Card.Body></Card>
          <Card><Card.Body className="py-3"><div className="text-xs text-gray-500">Conversion</div><div className="text-xl font-bold text-emerald-700 tabular-nums">{t.conversion_rate}%</div><div className="text-[11px] text-gray-400">{t.won} won · {t.lost} lost</div></Card.Body></Card>
          <Card><Card.Body className="py-3"><div className="text-xs text-gray-500">Value influenced</div><div className="text-xl font-bold text-gray-900 tabular-nums">{formatKes(t.value_influenced)}</div></Card.Body></Card>
          <Card><Card.Body className="py-3"><div className="text-xs text-gray-500">Declined</div><div className="text-xl font-bold text-amber-700 tabular-nums">{t.declined}</div></Card.Body></Card>
        </div>
      )}

      {/* direction toggle */}
      <div className="inline-flex rounded-lg border border-gray-200 bg-white p-1">
        {dirTabs.map((d) => (
          <button key={d.key} onClick={() => setDir(d.key)}
            className={'px-4 py-1.5 rounded-md text-sm font-medium transition-colors ' + (dir === d.key ? 'bg-brand-primary text-white' : 'text-gray-600 hover:text-gray-900')}>
            {d.label}
            <span className={'ml-2 rounded-full px-1.5 py-0.5 text-xs ' + (dir === d.key ? 'bg-white/20' : 'bg-gray-100 text-gray-500')}>{d.count}</span>
          </button>
        ))}
      </div>

      {/* the referral table (referrer-inclusive data) */}
      <Card><Card.Body>
        <Table<ReferralView>
          columns={columns}
          rows={rows}
          rowKey={(r) => r.id}
          searchable
          searchPlaceholder="Search referrals by client, stage, referrer…"
          paginated
          pageSize={15}
          exportable
          exportFilename="referrals.csv"
          onRowClick={(r) => navigate(`/pipeline/${encodeURIComponent(r.id)}`)}
          empty={<span className="text-sm text-gray-500">No referrals in this view yet.</span>}
          toolbar={
            <div className="flex flex-wrap items-center gap-2">
              <Filter label="Referrer" val={fMember} set={setFMember} opts={memberOpts} />
              <Filter label="Product" val={fProduct} set={setFProduct} opts={productOpts} />
              <Filter label="Status" val={fStatus} set={setFStatus} opts={statusOpts} />
            </div>
          }
        />
      </Card.Body></Card>
    </div>
  );
}

export default function Referrals() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('overview');
  const [incoming, setIncoming] = useState<ReferralView[]>([]);
  const [returned, setReturned] = useState<ReferralView[]>([]);
  const [outgoing, setOutgoing] = useState<ReferralView[]>([]);
  const [analytics, setAnalytics] = useState<OutgoingReferralAnalytics | null>(null);
  const [dept, setDept] = useState<ReferralsByDepartment | null>(null);
  const [team, setTeam] = useState<ReferralView[]>([]);
  const [reReferFor, setReReferFor] = useState<string | null>(null);
  const [rrMember, setRrMember] = useState<StaffMember | null>(null);
  const [rrNote, setRrNote] = useState('');
  const [teamSummary, setTeamSummary] = useState<TeamReferralsResponse['summary'] | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [declineFor, setDeclineFor] = useState<string | null>(null);
  const [declineReason, setDeclineReason] = useState('');
  const [reassignFor, setReassignFor] = useState<string | null>(null);
  const [reMember, setReMember] = useState<StaffMember | null>(null);
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
    if (!reMember) {
      toast({ tone: 'warning', message: 'Pick a recipient from the list.' });
      return;
    }
    setBusyId(d.id);
    try {
      await reassignReferral(d.id, reMember.staff_code, reMember.name, reNote.trim());
      toast({ tone: 'success', message: `Reassigned to ${displayName(reMember.name)}.` });
      setReassignFor(null); setReMember(null); setReNote(''); loadAll();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Reassign failed.' });
    } finally { setBusyId(null); }
  }

  async function onReRefer(d: ReferralView) {
    if (!rrMember) { toast({ tone: 'danger', message: 'Pick a recipient from the list.' }); return; }
    setBusyId(d.id);
    try {
      await reReferReferral(d.id, rrMember.staff_code, rrMember.name, rrNote.trim() || undefined);
      toast({ tone: 'success', message: 'Re-referred onward.' });
      setReReferFor(null); setRrMember(null); setRrNote('');
      await loadAll();
    } catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Re-refer failed' }); }
    finally { setBusyId(null); }
  }

  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: 'overview', label: 'Overview', count: dept?.totals?.total ?? 0 },
    { key: 'incoming', label: 'Incoming', count: incoming.length },
    { key: 'returned', label: 'Returned', count: returned.length },
    { key: 'following', label: 'Following', count: outgoing.length },
    { key: 'team', label: 'Team', count: team.length },
  ];
  const active = tab === 'overview' ? []
    : tab === 'incoming' ? incoming
    : tab === 'returned' ? returned
    : tab === 'team' ? team
    : outgoing;

  function CreditJourney({ stage }: { stage?: ReferralView['credit_stage'] }) {
    if (!stage) return null;
    const steps = [
      { key: 'intake', label: 'Submitted' },
      { key: 'assessment', label: 'Assessment' },
      { key: 'decision', label: 'Decision' },
      { key: 'offer', label: 'Offer' },
      { key: 'credit_admin', label: 'Credit admin' },
      { key: 'disbursement', label: 'Cleared' },
      { key: 'disbursed', label: 'Disbursed' },
    ];
    if (stage.declined) {
      return (
        <div className="mt-2 border-t border-gray-100 pt-2">
          <div className="mb-1 text-xs font-medium text-gray-500">Credit journey</div>
          <span className="rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-700">Declined in credit</span>
        </div>
      );
    }
    const idx = steps.findIndex((s) => s.key === stage.key);
    return (
      <div className="mt-2 border-t border-gray-100 pt-2">
        <div className="mb-1.5 text-xs font-medium text-gray-500">Credit journey</div>
        <div className="flex flex-wrap items-center gap-1">
          {steps.map((s, i) => (
            <div key={s.key} className="flex items-center gap-1">
              <span className={'rounded px-1.5 py-0.5 text-xs ' + (i < idx ? 'bg-emerald-50 text-emerald-700' : i === idx ? 'bg-brand-primary text-white' : 'bg-gray-50 text-gray-400')}>{s.label}</span>
              {i < steps.length - 1 && <span className="text-gray-300 text-xs">→</span>}
            </div>
          ))}
        </div>
      </div>
    );
  }

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
        title="EKE Sales Referral"
        subtitle="Deals referred to you, returned to you, and the ones you're following."
        breadcrumbs={[{ label: 'EKE Pipeline Intelligence System (PIS)' }, { label: 'EKE Sales Referral' }]}
        actions={
          <Button variant="primary" size="sm" onClick={() => navigate('/pipeline/new?refer=1')}>
            New referral
          </Button>
        }
      />
      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">
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

        {tab === 'overview' && (
          <ReferralOverview dept={dept} team={team} navigate={navigate} formatKes={formatKes} displayName={displayName} />
        )}

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
                <div className="mb-2 flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-900">By department</span>
                  {dept.scope && <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">{dept.scope === 'branch' ? 'Your branch' : 'Bank-wide'}</span>}
                </div>
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
                      {al.referred_to ? ` → ${displayName(al.referred_to)}` : ''} — {al.message}
                    </li>
                  ))}
                </ul>
              </Card.Body></Card>
            )}

            {dept && dept.departments.length > 0 && (
              <Card><Card.Body>
                <div className="mb-2 flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-900">By department</span>
                  {dept.scope && <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">{dept.scope === 'branch' ? 'Your branch' : 'Bank-wide'}</span>}
                </div>
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

        {tab !== 'overview' && (loading ? (
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
                    <button type="button" onClick={() => navigate(`/pipeline/${d.id}`)}
                      className="text-left min-w-0 flex-1 group" title="Open the full case journey">
                      <DealMeta d={d} />
                      <span className="mt-1 inline-block text-[11px] text-brand-primary opacity-0 group-hover:opacity-100 transition-opacity">Open case journey →</span>
                    </button>
                    <div className="shrink-0 text-right text-xs text-gray-400">
                      {tab === 'incoming' && d.referred_by_name && (
                        <div>from <span className="text-gray-600">{displayName(d.referred_by_name)}</span></div>
                      )}
                      {tab === 'following' && d.referred_to && (
                        <div>to <span className="text-gray-600">{displayName(d.referred_to)}</span></div>
                      )}
                      {tab === 'team' && (
                        <div>
                          {d.referred_by_name && <div><span className="text-gray-600">{displayName(d.referred_by_name)}</span></div>}
                          {d.referred_to && <div className="mt-0.5">→ <span className="text-gray-600">{displayName(d.referred_to)}</span></div>}
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
                  <CreditJourney stage={d.credit_stage} />

                  {d.referral_status === 'accepted' && (
                    <div className="mt-3 border-t border-gray-100 pt-3">
                      {reReferFor === d.id ? (
                        <div className="space-y-2">
                          <StaffPicker value={rrMember} onChange={setRrMember} />
                          <input className={inputCls} placeholder="Note (optional)"
                            value={rrNote} onChange={(e) => setRrNote(e.target.value)} />
                          <div className="flex gap-2">
                            <Button variant="primary" size="sm" loading={busyId === d.id}
                              onClick={() => onReRefer(d)}>Re-refer onward</Button>
                            <Button variant="ghost" size="sm"
                              onClick={() => { setReReferFor(null); setRrMember(null); setRrNote(''); }}>Cancel</Button>
                          </div>
                        </div>
                      ) : (
                        <Button variant="ghost" size="sm"
                          onClick={() => { setReReferFor(d.id); setRrMember(null); setRrNote(''); }}>
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
                          <StaffPicker value={reMember} onChange={setReMember} />
                          <input className={inputCls} placeholder="Note (optional)"
                            value={reNote} onChange={(e) => setReNote(e.target.value)} />
                          <div className="flex gap-2">
                            <Button variant="primary" size="sm" loading={busyId === d.id}
                              onClick={() => onReassign(d)}>Reassign</Button>
                            <Button variant="ghost" size="sm"
                              onClick={() => { setReassignFor(null); setReMember(null); setReNote(''); }}>
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
        ))}
      </main>
    </div>
  );
}
