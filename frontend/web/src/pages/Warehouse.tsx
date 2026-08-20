// Deals Warehouse — the shared shelf.
//
// Not a channel. Events, partnerships and lead generators are things the bank
// INVESTS IN and measures a return on; the warehouse is a shelf of prospects
// nobody owns yet, with claim mechanics and no budget. That is why it sits on
// its own rather than beside them.
//
// THE SECOND TAB IS THE POINT. "The shelf" is what everyone expects; "Mine" is
// what makes the thing work — someone who lists prospects and never learns
// whether anyone took them will stop listing them within a fortnight.

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { PageHeader } from '@/components/PageHeader';
import { useToast } from '@/components/Toast';
import { useRole } from '@/hooks/useRole';
import {
  fetchWarehouseShelves, fetchWarehouseTaxonomy, fetchWarehouseMine,
  createProspect, archiveProspect, deleteProspect, fetchWarehouseAnalytics,
  type WarehouseAnalytics,
  type WarehouseProspect, type WarehouseMine,
} from '@/lib/api';

function kes(n: number | null | undefined): string {
  const v = Number(n ?? 0);
  if (!v) return '—';
  return Math.round(v).toLocaleString();
}

export default function Warehouse() {
  const { toast } = useToast();
  const nav = useNavigate();
  // FOUR TABS. "Validated" first, deliberately (ruling 2026-08-11: "so that
  // people can mostly choose from validated data instead of throwing people
  // into using data that would be misleading"). The default landing is the
  // set somebody has vouched for; incomplete records are still reachable, but
  // you have to choose them.
  // Validated is the RIGHT default once there is a validated set - people
  // should land on data somebody vouched for. But defaulting there on a fresh
  // warehouse shows an empty page and looks broken, so the first load moves to
  // "Under validation" when nothing has been validated yet.
  const [tab, setTab] = useState<'validated' | 'working' | 'shelf' | 'mine' | 'analytics'>('validated');
  const [landed, setLanded] = useState(false);
  const [shelves, setShelves] = useState<Record<string, WarehouseProspect[]>>({});
  const [total, setTotal] = useState(0);
  // ── A WINDOW ONTO THE SHELF ─────────────────────────────────────────────
  // The shelf holds 12,591 records and is aiming at a million. The page asks
  // for 200 at a time and moves through them; `matched` is what the FILTER
  // matches, which is the number an officer is actually asking about.
  const PAGE = 200;
  const [offset, setOffset] = useState(0);
  const [matched, setMatched] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [counts, setCounts] = useState({ validated: 0 });
  const [an, setAn] = useState<WarehouseAnalytics | null>(null);
  // PICK A SHELF, do not scroll to it. At 165 records - and 1,800 coming - an
  // ungrouped listing is a filing cabinet with the drawers taken out.
  const [sector, setSector] = useState('');
  const [subsector, setSubsector] = useState('');
  const [mine, setMine] = useState<WarehouseMine | null>(null);
  const [sectors, setSectors] = useState<string[]>([]);
  const [towns, setTowns] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState('');
  const [q, setQ] = useState('');
  const [town, setTown] = useState('');
  const [creating, setCreating] = useState(false);
  // Admin-only. A row that was never a business - a county name, a street -
  // should leave no trace; archiving it would fill the audit trail with noise.
  const { isAdmin } = useRole();
  const [form, setForm] = useState({
    name: '', sector: '', town: '', contact_name: '', contact_phone: '',
    contact_email: '', notes: '', source_event: '', estimated_value: '',
  });

  useEffect(() => {
    void (async () => {
      try {
        const t = await fetchWarehouseTaxonomy();
        setSectors(t.sectors ?? []);
        setTowns(t.towns ?? []);
      } catch { /* the form still works without the lists */ }
    })();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === 'analytics') {
        setAn(await fetchWarehouseAnalytics());
      } else if (tab !== 'mine') {
        const r = await fetchWarehouseShelves({ town, q, limit: PAGE, offset });
        const all = r.shelves ?? {};
        // Filtered client-side: the shelf endpoint already returns every
        // prospect with its score, and a second round trip to re-ask the same
        // question would be a per-row cost for nothing.
        const keep = (p: WarehouseProspect) => (
          tab === 'validated' ? p.validated === true
            : tab === 'working' ? p.validated !== true
              : true);
        const out: Record<string, WarehouseProspect[]> = {};
        let n = 0;
        let v = 0;
        Object.entries(all).forEach(([sector, items]) => {
          items.forEach((it) => { if (it.validated) v += 1; });
          const kept = items.filter(keep);
          if (kept.length) { out[sector] = kept; n += kept.length; }
        });
        setShelves(out);
        setTotal(n);
        setMatched(r.total ?? n);
        setHasMore(Boolean(r.has_more));
        setCounts({ validated: v });
        if (!landed) {
          setLanded(true);
          if (v === 0 && tab === 'validated') setTab('working');
        }
      } else {
        setMine(await fetchWarehouseMine());
      }
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load.' });
    } finally {
      setLoading(false);
    }
  }, [tab, town, q, toast, landed, offset]);
  // A NEW FILTER STARTS AT THE FIRST PAGE. Keeping the offset would land you
  // on page four of a search that has three, and the shelf would look empty.
  useEffect(() => { setOffset(0); }, [town, q, tab]);


  useEffect(() => { void load(); }, [load]);

  async function submit() {
    if (!form.name.trim()) {
      toast({ tone: 'danger', message: 'A prospect needs a name.' });
      return;
    }
    setBusy('create');
    try {
      await createProspect({ ...form, estimated_value: Number(form.estimated_value) || 0 });
      toast({ tone: 'success', message: `${form.name} is on the shelf.` });
      setCreating(false);
      setForm({ ...form, name: '', contact_name: '', contact_phone: '', notes: '' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not list it.' });
    } finally {
      setBusy('');
    }
  }

  // Claiming moved to the detail page (IC2): a person should see what
  // they are taking on before they take it.
  async function remove(p: WarehouseProspect) {
    if (!window.confirm(
      `Delete "${p.name}" entirely? Use this only for rows that were never a `
      + `business — a county name, a street, a fragment of a table. `
      + `Archive instead if it is a real business you have decided not to pursue.`)) {
      return;
    }
    // A VALIDATED record needs the password. Asking only when it is validated
    // keeps the working set frictionless, which is where the work happens.
    let pw = '';
    if (p.validated) {
      pw = window.prompt(
        `"${p.name}" is a VALIDATED record — somebody vouched for it and people `
        + `are being told to prefer it. Enter the warehouse password to delete it.`) || '';
      if (!pw) return;
    }
    setBusy(p.id);
    try {
      await deleteProspect(p.id, pw);
      toast({ tone: 'success', message: `${p.name} deleted.` });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not delete.' });
    } finally {
      setBusy('');
    }
  }

  async function drop(p: WarehouseProspect) {
    const reason = window.prompt(`Why is ${p.name} coming off the shelf?`);
    if (!reason || !reason.trim()) return;
    setBusy(p.id);
    try {
      await archiveProspect(p.id, reason.trim());
      toast({ tone: 'success', message: 'Archived — it stays on record.' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not archive.' });
    } finally {
      setBusy('');
    }
  }

  const inp = 'mt-1 w-full h-9 px-2 rounded border border-gray-300 text-sm';

  // Shelf keys are "Sector › Subsector", so both pickers come from the data
  // itself rather than a second config that could drift out of step with it.
  const shelfKeys = Object.keys(shelves);
  const sectorsOnShelf = Array.from(new Set(
    shelfKeys.map((k) => k.split(' \u203a ')[0]))).sort();
  const subsOnShelf = Array.from(new Set(
    shelfKeys
      .filter((k) => !sector || k.split(' \u203a ')[0] === sector)
      .map((k) => k.split(' \u203a ')[1])
      .filter(Boolean))).sort();
  const visible = Object.entries(shelves).filter(([k]) => {
    const parts = k.split(' \u203a ');
    return (!sector || parts[0] === sector) && (!subsector || parts[1] === subsector);
  });
  const shown = visible.reduce((a, [, v]) => a + v.length, 0);

  return (
    <>
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'Pipeline Intelligence (PIS)' }, { label: 'Deals Warehouse' }]}
        title="Deals Warehouse"
      />
      <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">
        <div className="mb-4 flex gap-4 border-b border-gray-200">
          {([
            ['validated', 'Validated'],
            ['working', 'Under validation'],
            ['shelf', 'All'],
            ['mine', 'Mine'],
            ['analytics', 'Analytics'],
          ] as const).map(([t, label]) => (
            <button
              key={t} type="button" onClick={() => setTab(t)}
              className={'px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ' + (
                t === tab
                  ? 'border-brand-primary text-brand-primary'
                  : 'border-transparent text-gray-600 hover:text-gray-900')}
            >
              {label}
              {t === 'validated' && counts.validated > 0 && (
                <span className={'ml-1 rounded-full px-2 py-0.5 text-[11px] ' + (
                  t === tab ? 'bg-brand-primary text-white' : 'bg-gray-200 text-gray-700')}>
                  {counts.validated}
                </span>
              )}
            </button>
          ))}
        </div>

        {tab === 'analytics' && (
          <div className="space-y-4">
            {!an && <p className="py-10 text-center text-sm text-gray-400">Loading…</p>}
            {an && (
              <>
                <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
                  {[
                    ['Prospects', String(an.totals.prospects), 'bg-[#EDF4F8] text-[#003D57]'],
                    ['Validated', String(an.totals.validated), 'bg-[#EAF3DE] text-[#3B6D11]'],
                    ['Ready to validate', String(an.totals.ready_to_validate), 'bg-[#FEF6E7] text-[#854F0B]'],
                    ['Under validation', String(an.totals.under_validation), 'bg-gray-50 text-gray-600'],
                    ['Average score', `${an.totals.average_score}%`, 'bg-[#EDF4F8] text-[#003D57]'],
                    ['Claimed', String(an.totals.claimed), 'bg-[#E6F1FB] text-[#0C447C]'],
                  ].map(([label, value, tone]) => (
                    <div key={label} className={`rounded-xl px-4 py-3 ${tone}`}>
                      <div className="text-[10px] font-semibold uppercase tracking-wide opacity-70">
                        {label}
                      </div>
                      <div className="mt-1 text-xl font-semibold tabular-nums">{value}</div>
                    </div>
                  ))}
                </div>

                {/* EVERY CUT SHOWS VALIDATED AGAINST TOTAL. "Nairobi: 58" is
                    not the useful figure; "58, of which 4 validated" is - the
                    second tells you whether the coverage is real. */}
                <div className="grid gap-4 lg:grid-cols-3">
                  {([
                    ['By sector', an.by_sector],
                    ['By segment', an.by_segment],
                    ['By county', an.by_county],
                  ] as const).map(([title, rows]) => (
                    <Card key={title}>
                      <Card.Header>
                        <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
                      </Card.Header>
                      <Card.Body>
                        {rows.length === 0 && (
                          <p className="py-4 text-center text-xs text-gray-400">Nothing yet.</p>
                        )}
                        <ul className="space-y-2">
                          {rows.slice(0, 10).map((r) => (
                            <li key={r.label}>
                              <div className="flex items-baseline justify-between gap-2 text-xs">
                                <span className="truncate text-gray-700" title={r.label}>
                                  {r.label}
                                </span>
                                <span className="shrink-0 tabular-nums text-gray-500">
                                  <strong className="text-[#3B6D11]">{r.validated}</strong>
                                  <span className="text-gray-400"> / {r.total}</span>
                                </span>
                              </div>
                              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-gray-100">
                                <div className="h-full rounded-full bg-[#3B6D11]"
                                     style={{ width: `${r.total ? (r.validated / r.total) * 100 : 0}%` }} />
                              </div>
                            </li>
                          ))}
                        </ul>
                      </Card.Body>
                    </Card>
                  ))}
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <Card>
                    <Card.Header>
                      <h2 className="text-sm font-semibold text-gray-900">How complete</h2>
                    </Card.Header>
                    <Card.Body>
                      <div className="space-y-2">
                        {an.bands.map((b) => {
                          const top = Math.max(...an.bands.map((x) => x.count), 1);
                          return (
                            <div key={b.band} className="flex items-center gap-3">
                              <span className="w-14 shrink-0 text-xs text-gray-600">{b.band}%</span>
                              <div className="h-4 flex-1 overflow-hidden rounded bg-gray-100">
                                <div className={'h-full rounded ' + (
                                  b.band === '100' ? 'bg-[#3B6D11]'
                                    : b.band === '80-99' ? 'bg-[#BED600]' : 'bg-[#E0A02B]')}
                                     style={{ width: `${Math.max(2, (b.count / top) * 100)}%` }} />
                              </div>
                              <span className="w-10 shrink-0 text-right text-xs tabular-nums text-gray-700">
                                {b.count}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </Card.Body>
                  </Card>

                  <Card>
                    <Card.Header>
                      <h2 className="text-sm font-semibold text-gray-900">What to backfill next</h2>
                    </Card.Header>
                    <Card.Body>
                      <p className="mb-2 text-xs text-gray-500">
                        The field missing on the most records — fixing this one
                        moves more prospects toward validation than any other.
                      </p>
                      <ul className="space-y-1.5">
                        {an.gaps.map((g) => (
                          <li key={g.key} className="flex items-baseline justify-between gap-2 text-xs">
                            <span className="text-gray-700">{g.label}</span>
                            <span className="tabular-nums text-[#854F0B]">
                              {g.missing} missing
                            </span>
                          </li>
                        ))}
                      </ul>
                    </Card.Body>
                  </Card>
                </div>
              </>
            )}
          </div>
        )}

        {tab !== 'mine' && tab !== 'analytics' && (
          <Card>
            <Card.Header>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-base font-semibold text-gray-900">
                  Prospects anyone can pursue
                </h2>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <input value={q} onChange={(e) => setQ(e.target.value)}
                         placeholder="Search…"
                         className="rounded border border-gray-200 px-2 py-1 text-xs" />
                  {/* PICK A SHELF, do not scroll to it. At 165 records - and
                      1,800 coming - an ungrouped listing is a filing cabinet
                      with the drawers taken out. */}
                  <select value={sector}
                          onChange={(e) => { setSector(e.target.value); setSubsector(''); }}
                          className="rounded border border-gray-200 px-2 py-1 text-xs">
                    <option value="">All sectors</option>
                    {sectorsOnShelf.map((x) => <option key={x} value={x}>{x}</option>)}
                  </select>
                  {subsOnShelf.length > 0 && (
                    <select value={subsector} onChange={(e) => setSubsector(e.target.value)}
                            className="rounded border border-gray-200 px-2 py-1 text-xs">
                      <option value="">All subsectors</option>
                      {subsOnShelf.map((x) => <option key={x} value={x}>{x}</option>)}
                    </select>
                  )}
                  <select value={town} onChange={(e) => setTown(e.target.value)}
                          className="rounded border border-gray-200 px-2 py-1 text-xs">
                    <option value="">Countrywide</option>
                    {towns.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                  {/* WHAT IS ON SCREEN, AND WHAT THE FILTER MATCHES. The
                      shelf holds more than a page, so a bare count would be a
                      lie - "200 available" when 12,591 match is worse than no
                      number at all. */}
                  <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[#0C447C]">
                    {matched > shown
                      ? `${offset + 1}\u2013${offset + shown} of ${matched}`
                      : sector || subsector
                        ? `${shown} of ${total}`
                        : `${total} available`}
                  </span>
                  {(offset > 0 || hasMore) && (
                    <span className="inline-flex items-center gap-1">
                      <button
                        type="button"
                        disabled={offset === 0 || loading}
                        onClick={() => setOffset(Math.max(0, offset - PAGE))}
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs
                                   text-gray-700 hover:bg-gray-50 disabled:opacity-40"
                      >
                        \u2190 Previous
                      </button>
                      <button
                        type="button"
                        disabled={!hasMore || loading}
                        onClick={() => setOffset(offset + PAGE)}
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs
                                   text-gray-700 hover:bg-gray-50 disabled:opacity-40"
                      >
                        Next \u2192
                      </button>
                    </span>
                  )}
                  <Button size="sm" onClick={() => setCreating((v) => !v)}>
                    {creating ? 'Cancel' : 'List a prospect'}
                  </Button>
                </div>
              </div>
            </Card.Header>
            <Card.Body>
              {creating && (
                <div className="mb-4 rounded-lg border border-gray-200 bg-gray-50/60 p-3">
                  <div className="grid gap-3 sm:grid-cols-3">
                    <label className="text-xs text-gray-600">
                      Name <span className="text-gray-400">(all that is required)</span>
                      <input className={inp} value={form.name}
                             onChange={(e) => setForm({ ...form, name: e.target.value })} />
                    </label>
                    <label className="text-xs text-gray-600">
                      Sector
                      <select className={inp} value={form.sector}
                              onChange={(e) => setForm({ ...form, sector: e.target.value })}>
                        <option value="">Unsorted</option>
                        {sectors.map((x) => <option key={x} value={x}>{x}</option>)}
                      </select>
                    </label>
                    <label className="text-xs text-gray-600">
                      Town
                      <select className={inp} value={form.town}
                              onChange={(e) => setForm({ ...form, town: e.target.value })}>
                        <option value="">Not specified</option>
                        {towns.map((x) => <option key={x} value={x}>{x}</option>)}
                      </select>
                    </label>
                    <label className="text-xs text-gray-600">
                      Contact
                      <input className={inp} value={form.contact_name}
                             onChange={(e) => setForm({ ...form, contact_name: e.target.value })} />
                    </label>
                    <label className="text-xs text-gray-600">
                      Phone
                      <input className={inp} value={form.contact_phone}
                             onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} />
                    </label>
                    <label className="text-xs text-gray-600">
                      Rough value (KES)
                      <input className={inp} value={form.estimated_value}
                             onChange={(e) => setForm({ ...form, estimated_value: e.target.value })} />
                    </label>
                    <label className="text-xs text-gray-600 sm:col-span-2">
                      What is the opportunity?
                      <input className={inp} value={form.notes}
                             onChange={(e) => setForm({ ...form, notes: e.target.value })} />
                    </label>
                    <label className="text-xs text-gray-600">
                      Where you met them
                      <input className={inp} value={form.source_event}
                             onChange={(e) => setForm({ ...form, source_event: e.target.value })} />
                    </label>
                  </div>
                  <p className="mt-2 text-[11px] text-gray-500">
                    Contact details stay hidden from everyone else until someone
                    claims it — the shelf shows the opportunity, not the person.
                  </p>
                  <div className="mt-3 flex justify-end">
                    <Button size="sm" disabled={busy === 'create'} onClick={() => void submit()}>
                      {busy === 'create' ? 'Listing…' : 'Put it on the shelf'}
                    </Button>
                  </div>
                </div>
              )}

              {loading && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}

              {!loading && total === 0 && tab === 'validated' && (
                <div className="py-10 text-center">
                  <p className="text-sm text-gray-500">Nothing validated yet.</p>
                  <p className="mx-auto mt-2 max-w-md text-xs text-gray-400">
                    Everything that arrives lands under <strong>Under validation</strong>,
                    whatever its score — validation is somebody looking, not a
                    number crossing a line. Open a record there, fill in what you
                    know, and validate it at {80}% or above.
                  </p>
                  <button type="button" onClick={() => setTab('working')}
                          className="mt-3 rounded-md bg-[#E0A02B] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#C98A1E]">
                    Go to Under validation
                  </button>
                </div>
              )}

              {!loading && total === 0 && tab !== 'validated' && (
                <div className="py-10 text-center">
                  <p className="text-sm text-gray-500">The shelf is empty.</p>
                  <p className="mx-auto mt-2 max-w-md text-xs text-gray-400">
                    A prospect you cannot pursue yourself is worth more here than
                    in a notebook. Anyone with capacity can pick it up, and you
                    are credited as the referrer when they do.
                  </p>
                </div>
              )}

              {!loading && visible.map(([shelfName, items]) => (
                <div key={shelfName} className="mb-5">
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
                    {shelfName} <span className="ml-1 text-gray-400">({items.length})</span>
                  </h3>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {items.map((p) => (
                      <div key={p.id}
                           className="rounded-lg border border-gray-200 bg-white p-3 shadow-sm transition-shadow hover:border-[#BED600] hover:shadow-md">
                        {/* LABELLED, bold label and normal value (ruling
                            2026-08-11) - a card of bare strings makes the
                            reader work out which is which. */}
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 space-y-0.5 text-xs">
                            <div className="truncate" title={p.name}>
                              <span className="font-semibold text-gray-500">Name: </span>
                              <span className="text-sm font-medium text-gray-900">{p.name}</span>
                            </div>
                            <div>
                              <span className="font-semibold text-gray-500">Location: </span>
                              <span className="text-gray-700">{p.town || 'Countrywide'}</span>
                            </div>
                            <div className="truncate">
                              <span className="font-semibold text-gray-500">Contact: </span>
                              <span className="text-gray-700">
                                {p.contact_phone || p.contact_email || 'not recorded yet'}
                              </span>
                            </div>
                            {p.estimated_value ? (
                              <div>
                                <span className="font-semibold text-gray-500">Value: </span>
                                <span className="text-gray-700">KES {kes(p.estimated_value)}</span>
                              </div>
                            ) : null}
                          </div>
                          {p.mine && (
                            <span className="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-gray-500">
                              yours
                            </span>
                          )}
                        </div>

                        {/* THE SCORE, on the card. A completeness standard
                            nobody sees while browsing is a standard nobody
                            backfills against. */}
                        <div className="mt-2">
                          <div className="flex items-center justify-between text-[10px]">
                            <span className={p.validated ? 'font-semibold text-[#3B6D11]' : 'text-gray-500'}>
                              {p.validated ? '✓ validated' : `${p.score ?? 0}% complete`}
                            </span>
                            {!p.validated && (p.missing_count ?? 0) > 0 && (
                              <span className="text-gray-400">
                                {p.missing_count} field{p.missing_count === 1 ? '' : 's'} missing
                              </span>
                            )}
                          </div>
                          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-gray-100">
                            <div className={'h-full rounded-full ' + (
                              p.validated ? 'bg-[#3B6D11]'
                                : (p.score ?? 0) >= 70 ? 'bg-[#BED600]'
                                  : (p.score ?? 0) >= 40 ? 'bg-[#E0A02B]' : 'bg-gray-300')}
                                 style={{ width: `${Math.max(3, p.score ?? 0)}%` }} />
                          </div>
                        </div>

                        {p.notes && (
                          <p className="mt-2 text-xs text-gray-600">{p.notes}</p>
                        )}

                        {p.contacts_visible && p.contact_name && (
                          <p className="mt-2 text-[11px] text-gray-500">
                            {p.contact_name}
                          </p>
                        )}

                        <div className="mt-3 flex items-center justify-between gap-2">
                          <span className="text-[10px] text-gray-400">
                            {p.created_by_name} · {String(p.created_at ?? '').slice(0, 10)}
                          </span>
                          <div className="flex gap-1">
                            {/* DETAILS, not Pursue. Ruling 2026-08-11: "it will
                                be premature to pursue something whose only
                                detail you have is a name." Pursuing happens on
                                the detail page, after somebody has seen what
                                they would be taking on. */}
                            {/* Warm, and clearly the primary action - it is
                                what a person should do before deciding. */}
                            <button type="button"
                                    onClick={() => nav(`/pipeline/warehouse/${encodeURIComponent(p.id)}`)}
                                    className="rounded-md bg-[#E0A02B] px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-[#C98A1E]">
                              Details
                            </button>
                            {p.mine && (
                              <Button size="sm" variant="ghost" disabled={busy === p.id}
                                      onClick={() => void drop(p)}>Archive</Button>
                            )}
                            {isAdmin && (
                              <button type="button" disabled={busy === p.id}
                                      onClick={() => void remove(p)}
                                      title="Delete entirely - for rows that were never a business"
                                      className="rounded-md px-2 py-1.5 text-xs text-rose-600 hover:bg-rose-50">
                                Delete
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </Card.Body>
          </Card>
        )}

        {tab === 'mine' && (
          <div className="space-y-4">
            <Card>
              <Card.Header>
                <h2 className="text-base font-semibold text-gray-900">What I listed</h2>
              </Card.Header>
              <Card.Body>
                {!mine && <p className="py-6 text-center text-sm text-gray-400">Loading…</p>}
                {mine && mine.listed.length === 0 && (
                  <p className="py-6 text-center text-sm text-gray-400">
                    You have not listed anything yet.
                  </p>
                )}
                {mine && mine.listed.length > 0 && (
                  <div className="space-y-2">
                    {mine.listed.map((p) => (
                      <div key={p.id}
                           className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 p-3">
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium text-gray-900">{p.name}</div>
                          <div className="text-[11px] text-gray-500">
                            {p.sector || 'Unsorted'}{p.town ? ` · ${p.town}` : ''}
                          </div>
                        </div>
                        <span className={'rounded-full px-2.5 py-1 text-[11px] ' + (
                          p.status === 'claimed' || p.status === 'converted'
                            ? 'bg-[#EAF3DE] text-[#3B6D11]'
                            : p.status === 'archived'
                              ? 'bg-gray-100 text-gray-500'
                              : 'bg-[#E6F1FB] text-[#0C447C]')}>
                          {p.status === 'available' ? 'waiting'
                            : p.claimed_by_name ? `taken by ${p.claimed_by_name}` : p.status}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </Card.Body>
            </Card>

            {mine && mine.stale.length > 0 && (
              <Card>
                <Card.Header>
                  <h2 className="text-base font-semibold text-gray-900">
                    Nobody has taken these
                  </h2>
                </Card.Header>
                <Card.Body>
                  <p className="mb-2 text-xs text-gray-500">
                    Listed over a month ago and still on the shelf. Worth chasing
                    differently, or archiving so the shelf stays worth reading.
                  </p>
                  <ul className="text-xs text-gray-700">
                    {mine.stale.map((p) => (
                      <li key={p.id} className="py-0.5">
                        {p.name}
                        <span className="ml-2 text-gray-400">
                          {String(p.created_at ?? '').slice(0, 10)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Card.Body>
              </Card>
            )}

            {mine && mine.claimed.length > 0 && (
              <Card>
                <Card.Header>
                  <h2 className="text-base font-semibold text-gray-900">What I picked up</h2>
                </Card.Header>
                <Card.Body>
                  <div className="space-y-2">
                    {mine.claimed.map((p) => (
                      <div key={p.id}
                           className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 p-3">
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium text-gray-900">{p.name}</div>
                          <div className="text-[11px] text-gray-500">
                            {p.contact_name}{p.contact_phone ? ` · ${p.contact_phone}` : ''}
                          </div>
                        </div>
                        <span className="text-[11px] text-gray-500">
                          from {p.created_by_name}
                        </span>
                      </div>
                    ))}
                  </div>
                </Card.Body>
              </Card>
            )}
          </div>
        )}
      </div>
    </>
  );
}
