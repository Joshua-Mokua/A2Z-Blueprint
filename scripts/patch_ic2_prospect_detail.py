#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
IC2 - Details, not Pursue. The prospect page that makes a decision possible.

RULING (2026-08-11): "it will be premature to pursue something whose only
detail you have is a name. I would prefer details, which then open into a page
containing the card - contacts, known directors, location, branches etc - then
for sanity checking we can have an edit and additional information."

THE SHELF CARD NOW OFFERS "DETAILS". Pursuing happens on the detail page, after
somebody has seen what they would be taking on. A "Pursue this" button next to a
bare name asks for a commitment nobody has the information to make.

THE PAGE
    LEFT    the business - sector, location, rough value, who listed it, the
            source register, and the contact block
    RIGHT   the information card: every recorded fact, newest first, each with
            its source, its date, who added it, and a link where there is one

CONTACTS STAY HIDDEN UNTIL IT IS CLAIMED, on this page too. Opening a page is
not a claim, and revealing them on a click would make the shelf's protection
decorative. The panel says why rather than just showing a blank.

ADDING A FACT IS THE FASTEST THING ON THE PAGE - the form is at the TOP and
always open, not behind a button. This matters more than it looks: the SASRA
register gives a name, a county and a postal address and NOTHING ELSE. 134
prospects will only ever gain directors, phone numbers and financials because
somebody records what they find. A form hidden behind a button gets used once.

The placeholder text does the teaching: "CEO: Jane Wanjiku · 0722 000 000", and
"their website · a call · Business Daily" for the source - so the first person
to use it can see what a good entry looks like.

The shelf's own claim handler is REMOVED rather than left unused - dead code
that still compiles is how two ways of doing one thing survive.

Verified: tsc --noEmit clean, vite build clean.

REQUIRES IC1 and DW2.

Usage (from project root, .venv active):
    python scripts\patch_ic2_prospect_detail.py            # dry run
    python scripts\patch_ic2_prospect_detail.py --apply
"""
import os
import shutil
import sys

PAGE = os.path.join("frontend", "web", "src", "pages", "ProspectDetail.tsx")
SHELF = os.path.join("frontend", "web", "src", "pages", "Warehouse.tsx")
APP = os.path.join("frontend", "web", "src", "App.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
BACKUP_SUFFIX = ".pre_ic2"

TS_ANCHOR = "export interface WarehouseMine {"

TS_NEW = r'''export interface ProspectFact {
  id: string; kind: string; title: string; detail: string;
  source: string; url: string; occurred_on: string;
  added_by: string; added_at: string;
}
export interface ProspectDetail {
  prospect: WarehouseProspect;
  card: { items: ProspectFact[]; counts: Record<string, number>; total: number };
}
export async function fetchProspect(id: string): Promise<ProspectDetail> {
  return getJson<ProspectDetail>(`/warehouse/prospects/${encodeURIComponent(id)}`);
}
export async function addProspectFact(
  id: string, body: Record<string, unknown>,
): Promise<{ item: ProspectFact }> {
  return postJson<{ item: ProspectFact }, Record<string, unknown>>(
    `/warehouse/prospects/${encodeURIComponent(id)}/enrichment`, body);
}
'''

PAGE_SRC = r'''// Prospect detail — everything known, before deciding whether to pursue.
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
  fetchProspect, addProspectFact, claimProspect,
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
                          className="mt-3 w-full text-center text-xs text-gray-500 hover:text-gray-700"
                          onClick={() => nav('/pipeline/warehouse')}>
                    Back to the shelf
                  </button>
                </Card.Body>
              </Card>
            </div>

            <div className="lg:col-span-2 space-y-4">
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
'''

SHELF_SRC = r'''// Deals Warehouse — the shared shelf.
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
import {
  fetchWarehouseShelves, fetchWarehouseTaxonomy, fetchWarehouseMine,
  createProspect, archiveProspect,
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
  const [tab, setTab] = useState<'shelf' | 'mine'>('shelf');
  const [shelves, setShelves] = useState<Record<string, WarehouseProspect[]>>({});
  const [total, setTotal] = useState(0);
  const [mine, setMine] = useState<WarehouseMine | null>(null);
  const [sectors, setSectors] = useState<string[]>([]);
  const [towns, setTowns] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState('');
  const [q, setQ] = useState('');
  const [town, setTown] = useState('');
  const [creating, setCreating] = useState(false);
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
      if (tab === 'shelf') {
        const r = await fetchWarehouseShelves({ town, q });
        setShelves(r.shelves ?? {});
        setTotal(r.total ?? 0);
      } else {
        setMine(await fetchWarehouseMine());
      }
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load.' });
    } finally {
      setLoading(false);
    }
  }, [tab, town, q, toast]);

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

  return (
    <>
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'Pipeline Intelligence (PIS)' }, { label: 'Deals Warehouse' }]}
        title="Deals Warehouse"
      />
      <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">
        <div className="mb-4 flex gap-4 border-b border-gray-200">
          {(['shelf', 'mine'] as const).map((t) => (
            <button
              key={t} type="button" onClick={() => setTab(t)}
              className={'px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ' + (
                t === tab
                  ? 'border-brand-primary text-brand-primary'
                  : 'border-transparent text-gray-600 hover:text-gray-900')}
            >
              {t === 'shelf' ? 'The shelf' : 'Mine'}
            </button>
          ))}
        </div>

        {tab === 'shelf' && (
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
                  <select value={town} onChange={(e) => setTown(e.target.value)}
                          className="rounded border border-gray-200 px-2 py-1 text-xs">
                    <option value="">Anywhere</option>
                    {towns.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[#0C447C]">
                    {total} available
                  </span>
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

              {!loading && total === 0 && (
                <div className="py-10 text-center">
                  <p className="text-sm text-gray-500">The shelf is empty.</p>
                  <p className="mx-auto mt-2 max-w-md text-xs text-gray-400">
                    A prospect you cannot pursue yourself is worth more here than
                    in a notebook. Anyone with capacity can pick it up, and you
                    are credited as the referrer when they do.
                  </p>
                </div>
              )}

              {!loading && Object.entries(shelves).map(([sector, items]) => (
                <div key={sector} className="mb-5">
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
                    {sector} <span className="ml-1 text-gray-400">({items.length})</span>
                  </h3>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {items.map((p) => (
                      <div key={p.id} className="rounded-lg border border-gray-200 p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-gray-900"
                                 title={p.name}>{p.name}</div>
                            <div className="mt-0.5 text-[11px] text-gray-500">
                              {p.town || 'Anywhere'}
                              {p.estimated_value ? ` · KES ${kes(p.estimated_value)}` : ''}
                            </div>
                          </div>
                          {p.mine && (
                            <span className="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-gray-500">
                              yours
                            </span>
                          )}
                        </div>

                        {p.notes && (
                          <p className="mt-2 text-xs text-gray-600">{p.notes}</p>
                        )}

                        {p.contacts_visible ? (
                          <p className="mt-2 text-[11px] text-gray-500">
                            {p.contact_name}{p.contact_phone ? ` · ${p.contact_phone}` : ''}
                          </p>
                        ) : (
                          <p className="mt-2 text-[11px] text-gray-400">
                            Contact shown once you claim it
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
                            <Button size="sm" variant="secondary"
                                    onClick={() => nav(`/pipeline/warehouse/${encodeURIComponent(p.id)}`)}>
                              Details
                            </Button>
                            {p.mine && (
                              <Button size="sm" variant="ghost" disabled={busy === p.id}
                                      onClick={() => void drop(p)}>Archive</Button>
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
'''

APP_SRC = r'''// a2z/web/src/App.tsx
//
// Standard #37 — React SPA Architecture.
// v10.495 amendment: BrandingProvider added between QueryClient and Auth.
// v10.496 amendment: ToastProvider added between Branding and Auth.
//                    /components route added (Showcase page).
// v10.500 Phase 1 Batch 3a:
//   - /login route added (public, no ProtectedRoute wrapper).
//   - /perform and /profitability now wrapped in ProtectedRoute.
//   - /components remains public per Batch 3a doctrine — design-system
//     showcase, must be reachable for frontend governance inspection.
//   - AuthProvider is now the real provider (no longer a stub).
// v10.500 Phase 1 Batch 3b:
//   - /change-password route added, wrapped in ProtectedRoute. The
//     route is reachable for both 'must_rotate' (forced rotation) and
//     'authenticated' (future voluntary rotation) auth states.
//     ProtectedRoute's path-aware must_rotate gate confines users with
//     must_rotate tokens to this route specifically.
// v10.510 Phase 4 Batch β1:
//   - /pipeline route added (protected, requireAuth).
//   - Pipeline route element is wrapped in PipelineProvider so the
//     deal list state lives only where it's consumed — not hoisted to
//     app-level. Keeps the G381-protected provider chain unchanged.
// v10.511 Phase 4 Batch β2:
//   - /pipeline/:dealId route added (protected, requireAuth).
//   - Detail page is page-local — no PipelineProvider wrap.
// v10.512 Phase 4 Batch β3:
//   - /pipeline/new route added BEFORE /pipeline/:dealId. RR6 ranks
//     static routes above dynamic ones automatically, but explicit
//     ordering documents intent for future maintainers.
// v10.513 Phase 4 Batch β4:
//   - /pipeline/queues route added (manager-only via page guard).
//   - AppShell layout route introduced wrapping all protected routes
//     EXCEPT /change-password. The shell renders the persistent
//     Sidebar; pages render via React Router 6's <Outlet />.
//   - /change-password deliberately stays OUTSIDE AppShell — user
//     in must_rotate status would see a mocking sidebar of nav
//     links they can't use otherwise.
//   - /login and /components stay outside AppShell as before
//     (public, no auth needed).
//   - G381 byte-for-byte chain still unchanged:
//     QueryClient → Branding → Toast → Auth → Role → WebSocket → BrowserRouter
//
// CONTRACT NOTES (G381 - replaces phantom G46, G382 enforced from v10.496):
//
// Preserved byte-for-byte (G381 enforced):
//   - `import { QueryClient, QueryClientProvider } from '@tanstack/react-query'`
//   - `const queryClient = new QueryClient()`
//   - `<QueryClientProvider client={queryClient}>`
//   - `<AuthProvider><WebSocketProvider><BrowserRouter>` — chain order
//   - Existing route paths `/`, `/perform`, `/profitability`, `/components`,
//     `/login`, `/change-password`, `/pipeline`, `/pipeline/new`,
//     `/pipeline/:dealId`

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { BrandingProvider } from './providers/BrandingProvider';
import { AuthProvider } from './providers/AuthProvider';
import { RoleProvider } from './providers/RoleProvider';
import { WebSocketProvider } from './providers/WebSocketProvider';
import { PipelineProvider } from './providers/PipelineProvider';
import { ToastProvider } from './components/Toast';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AppShell } from './components/AppShell';
import About from './pages/About';
import { Dashboard } from './pages/Dashboard';
import { Perform } from './pages/Perform';
import { Profitability } from './pages/Profitability';
import { Showcase } from './pages/Showcase';
import { Login } from './pages/Login';
import { ChangePassword } from './pages/ChangePassword';
import { Pipeline } from './pages/Pipeline';
import { Analytics } from './pages/Analytics';
import { CreditAnalytics } from './pages/CreditAnalytics';
import { PipelineDealDetail } from './pages/PipelineDealDetail';
import { PipelineCreate } from './pages/PipelineCreate';
import { PipelineManagerQueues } from './pages/PipelineManagerQueues';
import OriginChannels from './pages/OriginChannels';
import Warehouse from './pages/Warehouse';
import ProspectDetail from './pages/ProspectDetail';
import { Lms } from './pages/Lms';
import { LmsApplicationDetail } from './pages/LmsApplicationDetail';
import { CreditAdmin } from './pages/CreditAdmin';
import { CreditAdminCaseDetail } from './pages/CreditAdminCaseDetail';
import { Troops } from './pages/Troops';
import { Cbs } from './pages/Cbs';
import { CbsCustomerDetail } from './pages/CbsCustomerDetail';
import { Cascade } from './pages/Cascade';
import { Initiatives } from './pages/Initiatives';
import { FxRates } from './pages/FxRates';
import AdminConfig from './pages/AdminConfig';
import DailyLogAdmin from './pages/DailyLogAdmin';
import RolesAdmin from './pages/RolesAdmin';
import HierarchyAdmin from './pages/HierarchyAdmin';
import BranchLog from './pages/BranchLog';
import Portfolio from './pages/Portfolio';
import CommitteeAdmin from './pages/CommitteeAdmin';
import { CommitteeConvening } from './pages/CommitteeConvening';
import StaffAdmin from './pages/StaffAdmin';
import CbsDebug from './pages/CbsDebug';
import Referrals from './pages/Referrals';
import Sla from './pages/Sla';
import { InitiativeDetail } from './pages/InitiativeDetail';

const queryClient = new QueryClient();

function App() {
    return <QueryClientProvider client={queryClient}>
        <BrandingProvider>
        <ToastProvider>
        <AuthProvider><RoleProvider><WebSocketProvider><BrowserRouter>
            <Routes>
                {/* Public — login surface */}
                <Route path="/login" element={<Login />} />

                {/* Public — design-system showcase (Batch 3a) */}
                <Route path="/components" element={<Showcase />} />

                {/* Protected (no shell) — password rotation must be
                    standalone so must_rotate users don't see a sidebar
                    of nav links they can't use until rotation completes. */}
                <Route path="/change-password" element={
                    <ProtectedRoute requireAuth><ChangePassword /></ProtectedRoute>
                } />

                {/* Protected (with shell) — all operational surfaces
                    share the AppShell layout with persistent Sidebar.
                    Pages render via <Outlet /> inside AppShell. */}
                <Route element={
                    <ProtectedRoute requireAuth>
                        <AppShell />
                    </ProtectedRoute>
                }>
                    {/* Dashboard at root */}
                    <Route path="/" element={<Dashboard />} />

                    {/* BSC + Profitability */}
                    <Route path="/perform" element={<Perform />} />
                    <Route path="/about" element={<About />} />
                    <Route path="/profitability" element={<Profitability />} />

                    {/* Pipeline list — wrapped in PipelineProvider for the
                        cascade-scoped deal list state. */}
                    <Route path="/pipeline" element={
                        <PipelineProvider>
                            <Pipeline />
                        </PipelineProvider>
                    } />

                    {/* Pipeline subroutes — order: static before dynamic.
                        RR6 ranks these automatically but explicit ordering
                        documents intent. */}
                    <Route path="/pipeline/new"     element={<PipelineCreate />} />
                    <Route path="/pipeline/queues"  element={<PipelineManagerQueues />} />
                    {/* The old Events page is superseded by Origin Channels -
                        one page for all three. The route is kept so bookmarks
                        still work, but it renders the new page: two pages
                        showing the same events, with different layouts, is how
                        a product starts to feel like two systems. */}
                    <Route path="/pipeline/events"  element={<OriginChannels />} />
                    <Route path="/pipeline/channels" element={<OriginChannels />} />
                    <Route path="/pipeline/warehouse" element={<Warehouse />} />
                    <Route path="/pipeline/warehouse/:prospectId" element={<ProspectDetail />} />
                    <Route path="/pipeline/:dealId" element={<PipelineDealDetail />} />
                    <Route path="/analytics" element={<Analytics />} />
                    <Route path="/credit-analytics" element={<CreditAnalytics />} />

                    {/* LMS subroutes — β5. Same static-before-dynamic ordering. */}
                    <Route path="/lms"         element={<Lms />} />
                    <Route path="/lms/:appId"  element={<LmsApplicationDetail />} />
                    <Route path="/committee/convening" element={<CommitteeConvening />} />

                    {/* Credit Admin subroutes — β6. */}
                    <Route path="/credit-admin"          element={<CreditAdmin />} />
                    <Route path="/credit-admin/:caseId"  element={<CreditAdminCaseDetail />} />
                    <Route path="/troops"                element={<Troops />} />

                    {/* CBS Customer Lookup — γ2. */}
                    <Route path="/cbs"         element={<Cbs />} />
                    <Route path="/cbs/:cif"    element={<CbsCustomerDetail />} />

                    {/* Target Cascade — γ3 (read-only). */}
                    <Route path="/cascade"     element={<Cascade />} />

                    {/* FX rates admin — P4-1c. Table visible to all; editor admin-gated (server enforces). */}
                    <Route path="/fx-rates"    element={<FxRates />} />

                    {/* Admin → Configuration — P4 Batch 1b. CEO/MD/Director; server enforces. */}
                    <Route path="/admin/config" element={<AdminConfig />} />
                    <Route path="/admin/daily-log" element={<DailyLogAdmin />} />
                    <Route path="/admin/roles" element={<RolesAdmin />} />
                    <Route path="/admin/hierarchy" element={<HierarchyAdmin />} />
                    <Route path="/branch-log" element={<BranchLog />} />
                    <Route path="/portfolio" element={<Portfolio />} />
                    <Route path="/admin/committees" element={<CommitteeAdmin />} />
                    <Route path="/admin/staff"      element={<StaffAdmin />} />
                    <Route path="/admin/cbs-debug" element={<CbsDebug />} />
                    <Route path="/referrals" element={<Referrals />} />
                    <Route path="/sla" element={<Sla />} />

                    {/* Strategic Initiatives — γ4 (read-only). */}
                    <Route path="/initiatives"                  element={<Initiatives />} />
                    <Route path="/initiatives/:initiativeId"    element={<InitiativeDetail />} />
                </Route>
            </Routes>
        </BrowserRouter></WebSocketProvider></RoleProvider></AuthProvider>
        </ToastProvider>
        </BrandingProvider>
    </QueryClientProvider>;
}

export default App;
'''


def main():
    apply = "--apply" in sys.argv
    for p in (SHELF, APP, APITS):
        if not os.path.isfile(p):
            print("ABORT: %s not found - apply patch_dw2_warehouse_ui.py first." % p)
            return 1
    if os.path.exists(PAGE):
        print("ABORT: %s already exists - IC2 looks applied." % PAGE)
        return 1

    ts = open(APITS, encoding="utf-8").read()
    if "fetchProspect" in ts:
        print("ABORT: the prospect clients already exist.")
        return 1
    if ts.count(TS_ANCHOR) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(TS_ANCHOR))
        return 1
    if "information_card" not in open(
            os.path.join("utils", "api_warehouse.py"), encoding="utf-8").read():
        print("ABORT: apply patch_ic1_information_card.py first - the detail")
        print("       endpoint it calls does not exist yet.")
        return 1

    ts = ts.replace(TS_ANCHOR, TS_NEW + TS_ANCHOR, 1)
    print("  ok  api.ts - prospect detail clients")

    # The shelf must offer Details, and must NOT still claim directly.
    if "Details" not in SHELF_SRC:
        print("ABORT: the shelf card does not offer Details.")
        return 1
    if "claimProspect" in SHELF_SRC:
        print("ABORT: the shelf still claims directly - two ways to do one")
        print("       thing, and the one without context wins by being closer.")
        return 1
    if "Shown once you pursue this" not in PAGE_SRC:
        print("ABORT: the detail page does not gate contacts.")
        return 1
    # The add form must be open, not hidden.
    if "setCreating" in PAGE_SRC:
        print("ABORT: the add form appears to be behind a toggle - at 134")
        print("       prospects with no contacts, a hidden form is never used.")
        return 1
    if "/pipeline/warehouse/:prospectId" not in APP_SRC:
        print("ABORT: the detail route is not registered.")
        return 1
    for name, blob in (("detail", PAGE_SRC), ("shelf", SHELF_SRC), ("app", APP_SRC)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    print("  ok  post-checks: Details offered, contacts gated, form open")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(PAGE, "w", encoding="utf-8", newline="").write(PAGE_SRC)
    print("CREATED %s" % PAGE)
    for path, content in ((APITS, ts), (SHELF, SHELF_SRC), (APP, APP_SRC)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd")
    print("Deals Warehouse > Details on any prospect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
