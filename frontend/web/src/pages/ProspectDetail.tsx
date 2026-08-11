// Prospect detail — everything known, before deciding whether to pursue.
//
// RULING (2026-08-11): "it will be premature to pursue something whose only
// detail you have is a name. I would prefer Details, which then open into a
// page containing the card with contacts, known directors, location, branches
// etc, then for sanity checking we can have an edit and additional
// information."
//
// So the shelf card offers DETAILS, not Pursue. Pursue lives here, after
// somebody has seen what they would be taking on.
//
// ADDING A FACT IS THE FASTEST THING ON THE PAGE. At 134 prospects the register
// gives names and addresses and nothing else, so the card fills up by hand or
// not at all — and if recording something takes four clicks, nobody does it
// twice.

import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { PageHeader } from '@/components/PageHeader';
import { useToast } from '@/components/Toast';
import {
  fetchProspect, addProspectFact, claimProspect, validateProspect, updateProspect,
  type ProspectDetail, type ProspectFact,
} from '@/lib/api';

const KINDS: { key: string; label: string }[] = [
  { key: 'contact', label: 'Contact' },
  { key: 'relationship', label: 'Director / officer' },
  { key: 'financial', label: 'Financial' },
  { key: 'association', label: 'Membership' },
  { key: 'filing', label: 'Filing' },
  { key: 'news', label: 'News' },
  { key: 'note', label: 'Note' },
];

function kes(n: number | null | undefined): string {
  const v = Number(n ?? 0);
  if (!v) return '—';
  return Math.round(v).toLocaleString();
}

export default function ProspectDetail() {
  const { prospectId = '' } = useParams();
  const nav = useNavigate();
  const { toast } = useToast();
  const [data, setData] = useState<ProspectDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    kind: 'contact', title: '', source: '', url: '', occurred_on: '', detail: '',
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchProspect(prospectId));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [prospectId, toast]);

  useEffect(() => { void load(); }, [load]);

  async function add() {
    if (!form.title.trim() || !form.source.trim()) {
      toast({ tone: 'danger', message: 'A fact needs what it says and where it came from.' });
      return;
    }
    setBusy(true);
    try {
      await addProspectFact(prospectId, form);
      toast({ tone: 'success', message: 'Added to the card.' });
      setForm({ ...form, title: '', url: '', detail: '' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not add.' });
    } finally {
      setBusy(false);
    }
  }

  const [editing, setEditing] = useState(false);
  const [edit, setEdit] = useState<Record<string, string>>({});

  async function saveEdit() {
    // The password is asked for ONLY on a validated record - the working set
    // exists to be filled in, and friction there stops the backfilling.
    let pw = '';
    if (c?.validated) {
      pw = window.prompt(
        'This is a VALIDATED record. Enter the warehouse password to change it.') || '';
      if (!pw) return;
    }
    setBusy(true);
    try {
      await updateProspect(prospectId, edit, pw);
      toast({ tone: 'success', message: 'Saved.' });
      setEditing(false);
      setEdit({});
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not save.' });
    } finally {
      setBusy(false);
    }
  }

  async function validate() {
    setBusy(true);
    try {
      await validateProspect(prospectId);
      toast({ tone: 'success', message: 'Validated — this is now a usable record.' });
      await load();
    } catch (e) {
      // The 400 names the specific gaps, which is more use than "incomplete".
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not validate.' });
    } finally {
      setBusy(false);
    }
  }

  async function pursue() {
    setBusy(true);
    try {
      const r = await claimProspect(prospectId);
      toast({
        tone: 'success',
        message: `Yours. ${r.referrer_name || 'Whoever listed it'} is credited as the referrer.`,
      });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not claim it.' });
      await load();
    } finally {
      setBusy(false);
    }
  }

  const p = data?.prospect;
  const facts: ProspectFact[] = data?.card?.items ?? [];
  const c = data?.completeness;
  const inp = 'mt-1 w-full h-9 px-2 rounded border border-gray-300 text-sm';

  return (
    <>
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'Pipeline Intelligence (PIS)' },
                      { label: 'Deals Warehouse' }, { label: p?.name ?? 'Prospect' }]}
        title={p?.name ?? 'Prospect'}
      />
      <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">
        {loading && <p className="py-10 text-center text-sm text-gray-400">Loading…</p>}
        {!loading && !p && (
          <p className="py-10 text-center text-sm text-gray-400">No such prospect.</p>
        )}

        {p && (
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="lg:col-span-1 space-y-4">
              <Card>
                <Card.Header>
                  <div className="flex items-center justify-between gap-2">
                    <h2 className="text-base font-semibold text-gray-900">The business</h2>
                    <span className={'rounded-full px-2.5 py-1 text-[11px] ' + (
                      p.status === 'available'
                        ? 'bg-[#E6F1FB] text-[#0C447C]'
                        : 'bg-[#EAF3DE] text-[#3B6D11]')}>
                      {p.status === 'available' ? 'unclaimed'
                        : p.claimed_by_name ? `with ${p.claimed_by_name}` : p.status}
                    </span>
                  </div>
                </Card.Header>
                <Card.Body>
                  <dl className="space-y-2 text-sm">
                    {[
                      ['Sector', p.sector || '—'],
                      ['Location', p.town || '—'],
                      ['Rough value', p.estimated_value ? `KES ${kes(p.estimated_value)}` : '—'],
                      ['Listed by', p.created_by_name || '—'],
                      ['Source', p.source_event || '—'],
                    ].map(([k, v]) => (
                      <div key={k} className="flex gap-3">
                        <dt className="w-28 shrink-0 text-xs text-gray-500">{k}</dt>
                        <dd className="text-gray-800">{v}</dd>
                      </div>
                    ))}
                  </dl>

                  {p.notes && (
                    <p className="mt-3 border-t border-gray-100 pt-3 text-xs text-gray-600">
                      {p.notes}
                    </p>
                  )}

                  <div className="mt-3 border-t border-gray-100 pt-3">
                    <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Contact
                    </div>
                    {p.contacts_visible ? (
                      <div className="mt-1 space-y-0.5 text-sm text-gray-800">
                        <div>{p.contact_name || '—'}</div>
                        <div>{p.contact_phone || '—'}</div>
                        <div>{p.contact_email || '—'}</div>
                      </div>
                    ) : (
                      // Opening a page is not a claim. Contacts stay hidden
                      // until somebody takes the prospect on.
                      <p className="mt-1 text-xs text-gray-400">
                        Shown once you pursue this — the shelf shows the
                        opportunity, not the person.
                      </p>
                    )}
                  </div>

                  {p.status === 'available' && (
                    <Button className="mt-4 w-full" disabled={busy}
                            onClick={() => void pursue()}>
                      {busy ? 'Claiming…' : 'Pursue this'}
                    </Button>
                  )}
                  {p.status !== 'available' && !p.mine && (
                    <p className="mt-4 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-500">
                      Already being pursued by {p.claimed_by_name || 'someone'}.
                    </p>
                  )}

                  <button type="button"
                          className="mt-3 w-full rounded-md border border-gray-200 py-1.5 text-center text-xs text-gray-600 hover:bg-gray-50"
                          onClick={() => { setEditing((v) => !v); setEdit({}); }}>
                    {editing ? 'Cancel edit' : (c?.validated ? 'Edit (password)' : 'Edit details')}
                  </button>

                  {editing && (
                    <div className="mt-3 space-y-2 rounded-lg border border-gray-200 bg-gray-50/60 p-3">
                      {([
                        ['name', 'Name'],
                        ['registration_no', 'Registration no.'],
                        ['contact_name', 'Decision maker and role'],
                        ['contact_phone', 'Phone'],
                        ['contact_email', 'Email'],
                        ['physical_address', 'Physical address'],
                        ['established', 'Year established'],
                        ['existing_banker', 'Banks with'],
                        ['website', 'Website'],
                        ['opportunity', 'Identified need'],
                      ] as const).map(([k, label]) => (
                        <label key={k} className="block text-[11px] text-gray-600">
                          {label}
                          <input
                            className="mt-0.5 h-8 w-full rounded border border-gray-300 px-2 text-xs"
                            value={edit[k] ?? String((p as unknown as Record<string, unknown>)[k] ?? '')}
                            onChange={(e) => setEdit({ ...edit, [k]: e.target.value })} />
                        </label>
                      ))}
                      <Button size="sm" className="w-full" disabled={busy}
                              onClick={() => void saveEdit()}>
                        {busy ? 'Saving…' : 'Save'}
                      </Button>
                    </div>
                  )}

                  <button type="button"
                          className="mt-3 w-full text-center text-xs text-gray-500 hover:text-gray-700"
                          onClick={() => nav('/pipeline/warehouse')}>
                    Back to the shelf
                  </button>
                </Card.Body>
              </Card>
            </div>

            <div className="lg:col-span-2 space-y-4">
              {/* WHAT IS STILL MISSING, and why each one matters. A score on
                  its own tells somebody they are incomplete without telling
                  them what to do about it. */}
              <Card>
                <Card.Header>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-base font-semibold text-gray-900">
                      Completeness
                    </h2>
                    <div className="flex items-center gap-3">
                      <span className={'text-sm font-semibold tabular-nums ' + (
                        c?.validated ? 'text-[#3B6D11]' : 'text-gray-700')}>
                        {c?.score ?? 0}%
                      </span>
                      {c?.validated ? (
                        <span className="rounded-full bg-[#EAF3DE] px-2.5 py-1 text-[11px] text-[#3B6D11]">
                          validated by {c.validated_by}
                        </span>
                      ) : (
                        <Button size="sm" disabled={busy || !c?.complete}
                                onClick={() => void validate()}>
                          {c?.complete ? 'Validate' : 'Validate'}
                        </Button>
                      )}
                    </div>
                  </div>
                </Card.Header>
                <Card.Body>
                  <div className="mb-3 h-2 overflow-hidden rounded-full bg-gray-100">
                    <div className={'h-full rounded-full ' + (
                      c?.validated ? 'bg-[#3B6D11]'
                        : (c?.score ?? 0) >= 70 ? 'bg-[#BED600]'
                          : (c?.score ?? 0) >= 40 ? 'bg-[#E0A02B]' : 'bg-gray-300')}
                         style={{ width: `${Math.max(3, c?.score ?? 0)}%` }} />
                  </div>

                  {c?.stale_validation && (
                    <p className="mb-3 rounded-lg border border-[#FAEEDA] bg-[#FEFAF3] px-3 py-2 text-xs text-[#854F0B]">
                      This record has changed since it was validated, so it is no
                      longer the record that was checked. Worth validating again.
                    </p>
                  )}

                  {c && c.missing.length === 0 && !c.validated && (
                    <p className="text-xs text-gray-600">
                      Every field is answered. Validating means you have looked
                      and you believe it — a record can be complete and wrong,
                      which is why this is not automatic.
                    </p>
                  )}

                  {c && c.missing.length > 0 && (
                    <>
                      <p className="mb-2 text-xs text-gray-500">
                        {c.answered} of {c.of} answered. Still needed:
                      </p>
                      <ul className="space-y-1.5">
                        {c.missing.map((m) => (
                          <li key={m.key} className="flex gap-2 text-xs">
                            <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[#E0A02B]" />
                            <span>
                              <span className="font-medium text-gray-800">{m.label}</span>
                              <span className="text-gray-500"> — {m.why}</span>
                            </span>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </Card.Body>
              </Card>

              <Card>
                <Card.Header>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-base font-semibold text-gray-900">
                      What we know
                    </h2>
                    <span className="text-xs text-gray-500">
                      {facts.length} {facts.length === 1 ? 'entry' : 'entries'}, newest first
                    </span>
                  </div>
                </Card.Header>
                <Card.Body>
                  {/* Adding is at the TOP and always open. The register gives a
                      name and an address and nothing else, so this card fills
                      up by hand or not at all - and a form hidden behind a
                      button gets used once. */}
                  <div className="mb-4 rounded-lg border border-gray-200 bg-gray-50/60 p-3">
                    <div className="grid gap-2 sm:grid-cols-4">
                      <label className="text-xs text-gray-600">
                        Kind
                        <select className={inp} value={form.kind}
                                onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                          {KINDS.map((k) => (
                            <option key={k.key} value={k.key}>{k.label}</option>
                          ))}
                        </select>
                      </label>
                      <label className="text-xs text-gray-600 sm:col-span-2">
                        What it says
                        <input className={inp} value={form.title}
                               placeholder="e.g. CEO: Jane Wanjiku · 0722 000 000"
                               onChange={(e) => setForm({ ...form, title: e.target.value })} />
                      </label>
                      <label className="text-xs text-gray-600">
                        Dated
                        <input type="date" className={inp} value={form.occurred_on}
                               onChange={(e) => setForm({ ...form, occurred_on: e.target.value })} />
                      </label>
                      <label className="text-xs text-gray-600 sm:col-span-2">
                        Where it came from
                        <input className={inp} value={form.source}
                               placeholder="their website · a call · Business Daily"
                               onChange={(e) => setForm({ ...form, source: e.target.value })} />
                      </label>
                      <label className="text-xs text-gray-600 sm:col-span-2">
                        Link (optional)
                        <input className={inp} value={form.url}
                               onChange={(e) => setForm({ ...form, url: e.target.value })} />
                      </label>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <span className="text-[11px] text-gray-500">
                        Anyone can add. Every entry records who added it and where
                        it came from.
                      </span>
                      <Button size="sm" disabled={busy} onClick={() => void add()}>
                        {busy ? 'Adding…' : 'Add to card'}
                      </Button>
                    </div>
                  </div>

                  {facts.length === 0 && (
                    <div className="py-8 text-center">
                      <p className="text-sm text-gray-500">Nothing recorded yet.</p>
                      <p className="mx-auto mt-2 max-w-md text-xs text-gray-400">
                        The register gives a name, a location and a postal
                        address. Everything else — who runs it, what it is worth,
                        who it banks with — gets added by whoever finds out.
                      </p>
                    </div>
                  )}

                  {facts.length > 0 && (
                    <div className="space-y-2">
                      {facts.map((f) => (
                        <div key={f.id}
                             className="rounded-lg border border-gray-200 p-3">
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div className="min-w-0">
                              <span className="mr-2 rounded-full bg-gray-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-gray-600">
                                {KINDS.find((k) => k.key === f.kind)?.label ?? f.kind}
                              </span>
                              <span className="text-sm font-medium text-gray-900">
                                {f.title}
                              </span>
                              {f.detail && (
                                <p className="mt-1 text-xs text-gray-600">{f.detail}</p>
                              )}
                            </div>
                            <span className="shrink-0 text-[11px] tabular-nums text-gray-400">
                              {f.occurred_on || 'undated'}
                            </span>
                          </div>
                          <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-gray-500">
                            <span>{f.source}</span>
                            {f.url && (
                              <a href={f.url} target="_blank" rel="noreferrer"
                                 className="text-brand-primary hover:underline">
                                open source
                              </a>
                            )}
                            <span className="text-gray-400">added by {f.added_by || '—'}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </Card.Body>
              </Card>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
