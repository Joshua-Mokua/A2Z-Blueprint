#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DW2 - the Deals Warehouse UI. The shelf becomes usable.

DW1 built the store and seven endpoints; none of it was reachable, and the
router was never even registered. This makes the shelf real.

STANDALONE, NOT A CHANNEL (ruling 2026-08-11: "the one that could be standalone
is the warehouse since it has a different logic behind it"). Events,
partnerships and lead generators are things the bank INVESTS IN and measures a
return on. The warehouse is a shelf of prospects nobody owns, with claim
mechanics and no budget - grouping it beside them would imply a return question
it cannot answer.

TWO TABS, and the second is the point:

    THE SHELF   grouped by sector, searchable, filterable by town. Cards show
                the opportunity - not the person.
    MINE        what I listed and what became of it, what I picked up, and what
                NOBODY HAS TAKEN in over a month.

Someone who lists prospects and never learns whether anyone took them will stop
listing them within a fortnight. "Mine" is what keeps the shelf stocked.

CONTACT DETAILS ARE HIDDEN until a prospect is claimed, and the create form says
so while you are typing them. A shared shelf of every prospect's phone number is
a data-protection problem rather than a sales tool - the same reasoning that
shaped the advice against bulk-harvesting company contacts.

ONLY A NAME IS REQUIRED, and the form says that too. A prospect jotted down at
an event with a name and nothing else is still worth having; demanding a full
taxonomy at capture is how a shelf ends up empty.

A FAILED CLAIM RELOADS THE SHELF. First claim wins, so a 409 means somebody got
there first - and the list the person is looking at is already out of date.
Showing them a stale shelf after telling them they lost the race would invite
them to try again on something else already gone.

ARCHIVING REQUIRES A REASON (server-enforced) and keeps the record. A prospect
somebody judged not worth pursuing is itself worth knowing next time the same
name comes up.

HELD BACK FROM THE PILOT (ruling 2026-08-11) - patch_dw1_warehouse and this
patcher both belong in NOT_FOR_RELEASE until the build is settled.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

REQUIRES DW1.

Usage (from project root, .venv active):
    python scripts\patch_dw2_warehouse_ui.py            # dry run
    python scripts\patch_dw2_warehouse_ui.py --apply
"""
import os
import shutil
import sys

PAGE = os.path.join("frontend", "web", "src", "pages", "Warehouse.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
APP = os.path.join("frontend", "web", "src", "App.tsx")
SB = os.path.join("frontend", "web", "src", "components", "Sidebar.tsx")
API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_dw2"

TS_ANCHOR = "export async function fetchChannels()"
WIRE_OLD = """from utils.api_branch_log import router as branch_log_router
app.include_router(branch_log_router)"""

TS_NEW = r'''// ── Deals Warehouse ───────────────────────────────────────────────────────
export interface WarehouseProspect {
  id: string; name: string; sector: string; town: string; status: string;
  estimated_value: number; source_event: string; notes: string;
  created_by_name: string; created_at: string;
  claimed_by_name: string; claimed_at: string; deal_id: string;
  mine: boolean; contacts_visible: boolean;
  contact_name?: string; contact_phone?: string; contact_email?: string;
}
export interface WarehouseMine {
  listed: WarehouseProspect[]; claimed: WarehouseProspect[];
  stale: WarehouseProspect[];
  counts: { listed: number; claimed: number; stale: number };
}
export async function fetchWarehouseTaxonomy(): Promise<{ sectors: string[]; towns: string[] }> {
  return getJson<{ sectors: string[]; towns: string[] }>('/warehouse/taxonomy');
}
export async function fetchWarehouseShelves(
  opts: { town?: string; sector?: string; q?: string } = {},
): Promise<{ shelves: Record<string, WarehouseProspect[]>; total: number }> {
  const qs = new URLSearchParams();
  if (opts.town) qs.set('town', opts.town);
  if (opts.sector) qs.set('sector', opts.sector);
  if (opts.q) qs.set('q', opts.q);
  const s = qs.toString();
  return getJson<{ shelves: Record<string, WarehouseProspect[]>; total: number }>(
    `/warehouse/shelves${s ? `?${s}` : ''}`);
}
export async function fetchWarehouseMine(): Promise<WarehouseMine> {
  return getJson<WarehouseMine>('/warehouse/mine');
}
export async function createProspect(
  body: Record<string, unknown>,
): Promise<{ prospect: WarehouseProspect }> {
  return postJson<{ prospect: WarehouseProspect }, Record<string, unknown>>(
    '/warehouse/prospects', body);
}
export async function claimProspect(
  id: string,
): Promise<{ prospect: WarehouseProspect; referrer_code: string; referrer_name: string }> {
  return postJson<{ prospect: WarehouseProspect; referrer_code: string; referrer_name: string },
                  Record<string, never>>(
    `/warehouse/prospects/${encodeURIComponent(id)}/claim`, {} as Record<string, never>);
}
export async function archiveProspect(
  id: string, reason: string,
): Promise<{ prospect: WarehouseProspect }> {
  return postJson<{ prospect: WarehouseProspect }, { reason: string }>(
    `/warehouse/prospects/${encodeURIComponent(id)}/archive`, { reason });
}
'''

WIRE = r'''from utils.api_branch_log import router as branch_log_router
app.include_router(branch_log_router)

# Deals Warehouse - the shared shelf. HELD BACK FROM THE PILOT (ruling
# 2026-08-11) until the build is settled; excluded in the release chain.
from utils.api_warehouse import router as warehouse_router
app.include_router(warehouse_router)'''

PAGE_SRC = r'''// Deals Warehouse — the shared shelf.
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
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { PageHeader } from '@/components/PageHeader';
import { useToast } from '@/components/Toast';
import {
  fetchWarehouseShelves, fetchWarehouseTaxonomy, fetchWarehouseMine,
  createProspect, claimProspect, archiveProspect,
  type WarehouseProspect, type WarehouseMine,
} from '@/lib/api';

function kes(n: number | null | undefined): string {
  const v = Number(n ?? 0);
  if (!v) return '—';
  return Math.round(v).toLocaleString();
}

export default function Warehouse() {
  const { toast } = useToast();
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

  async function take(p: WarehouseProspect) {
    setBusy(p.id);
    try {
      const r = await claimProspect(p.id);
      toast({
        tone: 'success',
        message: `${p.name} is yours. ${r.referrer_name || 'Whoever listed it'} is credited as the referrer.`,
      });
      await load();
    } catch (e) {
      // 409 means somebody got there first — the message names them.
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not claim it.' });
      await load();
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
                          {p.mine ? (
                            <Button size="sm" variant="ghost" disabled={busy === p.id}
                                    onClick={() => void drop(p)}>Archive</Button>
                          ) : (
                            <Button size="sm" disabled={busy === p.id}
                                    onClick={() => void take(p)}>
                              {busy === p.id ? 'Claiming…' : 'Pursue this'}
                            </Button>
                          )}
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

SIDEBAR = r'''import { displayName } from "../lib/names";
import { Link, useLocation } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useAuth } from '@/hooks/useAuth';
import { useRole } from '@/hooks/useRole';
import { isManager } from '@/lib/role';

interface NavItem {
  path: string;
  label: string;
  matchActive: (pathname: string) => boolean;
  visibleFor?: (isMgr: boolean, isAdmin: boolean, isCfgAdmin: boolean, isAdminOrMd: boolean, isCreditStaff: boolean) => boolean;
}
interface NavGroup { label: string; items: NavItem[]; }

const DEMO_HIDE = new Set<string>([]);

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Executive Intelligence',
    items: [
      { path: '/',              label: 'Dashboard',        matchActive: (p) => p === '/' },
      { path: '/perform',       label: 'Balanced Scorecard', matchActive: (p) => p === '/perform' },
      { path: '/cascade',       label: 'Target Cascade',   matchActive: (p) => p === '/cascade' || p.startsWith('/cascade/'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/initiatives',   label: 'Initiatives',      matchActive: (p) => p === '/initiatives' || p.startsWith('/initiatives/') },
      { path: '/profitability', label: 'Profitability',    matchActive: (p) => p === '/profitability' },
      { path: '/sla',           label: 'SLA Monitor',      matchActive: (p) => p.startsWith('/sla'), visibleFor: (m, a) => m || a },
    ],
  },
  {
    label: 'Pipeline Intelligence (PIS)',
    items: [
      { path: '/pipeline',        label: 'A2Z Sales Pro',        matchActive: (p) => p === '/pipeline' || (p.startsWith('/pipeline/') && !p.startsWith('/pipeline/queues') && !p.startsWith('/pipeline/events') && !p.startsWith('/pipeline/channels') && !p.startsWith('/pipeline/warehouse')) },
      { path: '/analytics',       label: 'Sales Pro Analytics',  matchActive: (p) => p.startsWith('/analytics') },
      { path: '/pipeline/queues', label: 'Manager Queues',       matchActive: (p) => p.startsWith('/pipeline/queues'), visibleFor: (m) => m },
      { path: '/pipeline/channels', label: 'Origin Channels',    matchActive: (p) => p.startsWith('/pipeline/channels') || p.startsWith('/pipeline/events') },
      // Standalone, NOT a channel: a shelf with claim mechanics and no budget,
      // so grouping it with the invested channels would imply a return question
      // it cannot answer.
      { path: '/pipeline/warehouse', label: 'Deals Warehouse',    matchActive: (p) => p.startsWith('/pipeline/warehouse') },
      { path: '/referrals',       label: 'A2Z Sales Referral Analytics', matchActive: (p) => p.startsWith('/referrals') },
      { path: '/branch-log',      label: 'Daily Log',     matchActive: (p) => p.startsWith('/branch-log') },
      { path: '/portfolio',       label: 'Portfolio',            matchActive: (p) => p.startsWith('/portfolio') },
    ],
  },
  {
    label: 'Credit Intelligence (CIS)',
    items: [
      { path: '/lms',                 label: 'Credit Analysis',     matchActive: (p) => p === '/lms' || p.startsWith('/lms/'), visibleFor: (_m, _a, _c, _md, credit) => credit },
      { path: '/committee/convening', label: 'Committee Convening', matchActive: (p) => p.startsWith('/committee/convening'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/credit-admin',        label: 'Credit Admin',        matchActive: (p) => p === '/credit-admin' || p.startsWith('/credit-admin/'), visibleFor: (_m, _a, _c, _md, credit) => credit },
      { path: '/troops',              label: 'Trops Disbursement',  matchActive: (p) => p.startsWith('/troops'), visibleFor: (_m, _a, _c, _md, credit) => credit },
      { path: '/credit-analytics',    label: 'Credit Analytics',    matchActive: (p) => p.startsWith('/credit-analytics'), visibleFor: (_m, _a, _c, _md, credit) => credit },
    ],
  },
  {
    label: 'Reference & Admin',
    items: [
      { path: '/cbs',              label: 'Customer Lookup',     matchActive: (p) => p === '/cbs' || p.startsWith('/cbs/'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/admin/config',     label: 'Administration',      matchActive: (p) => (p.startsWith('/admin/') && !p.startsWith('/admin/cbs-debug')) || p.startsWith('/fx-rates'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/admin/cbs-debug', label: 'CBS / FlexCube Debug', matchActive: (p) => p.startsWith('/admin/cbs-debug'), visibleFor: (_m, isA) => isA },
    ],
  },
];

function initials(name?: string) {
  return (name ?? '?').trim().split(/\s+/).slice(0, 2).map((s) => s[0]?.toUpperCase() ?? '').join('');
}

interface SidebarProps { onNavigate?: () => void; }

export function Sidebar({ onNavigate }: SidebarProps) {
  const { pathname } = useLocation();
  const { branding } = useBranding();
  const { user } = useRole();
  const { logout } = useAuth();

  const isMgr      = isManager(user);
  const isAdmin    = user?.is_admin ?? false;
  const isCfgAdmin = isAdmin || ['admin', 'director', 'chief', 'managing'].some((t) => (user?.role ?? '').toLowerCase().includes(t));
  // First-rollout gate: admin or the MD/CEO only.
  const isAdminOrMd = isAdmin || ['managing director', 'chief executive'].some((t) => (user?.role ?? '').toLowerCase().includes(t));
  // Credit Intelligence modules belong to credit staff (analysts, credit admin,
  // treasury/disbursement, recovery) + admin/MD. Front-line RMs/branch see the
  // pipeline instead, and track their own cases there.
  const isCreditStaff = isAdminOrMd || /credit|analys|underwrit|recover|collection|treasur|disburs/i.test(user?.role ?? '');

  return (
    <aside className="sidebar">
      <div className="sb-brand">
        <img src="/img/ecobank-light.svg" alt="Ecobank" className="sb-logo" />
        <div className="sb-brand-text">
          <div className="sb-brand-name">{branding?.app_name ?? 'A2Z Blueprint'}</div>
          <div className="sb-brand-tag">MIS 360</div>
        </div>
      </div>

      <nav className="sb-nav">
        {NAV_GROUPS.map((group) => {
          const items = group.items.filter(
            (item) => !DEMO_HIDE.has(item.path) && (!item.visibleFor || item.visibleFor(isMgr, isAdmin, isCfgAdmin, isAdminOrMd, isCreditStaff)),
          );
          if (!items.length) return null;
          return (
            <div key={group.label}>
              <div className="sb-section-lbl">{group.label}</div>
              {items.map((item) => {
                const active = item.matchActive(pathname);
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    onClick={onNavigate}
                    className={`sb-item${active ? ' active' : ''}`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>

      <div className="sb-foot">
        <div className="sb-user">
          <div className="sb-av">{initials(user?.full_name ?? user?.username)}</div>
          <div className="sb-user-info">
            <div className="sb-user-name">{user?.full_name ? displayName(user.full_name, (user as any).display_name) : (user?.username ?? '—')}</div>
            <div className="sb-user-role">{user?.role ?? ''}</div>
          </div>
        </div>
        <button
          type="button"
          className="sb-logout"
          onClick={() => { logout(); onNavigate?.(); }}
        >
          Sign out
        </button>
        <Link to="/about" onClick={() => onNavigate?.()}
          className="mt-2 block text-center text-[11px] text-white/40 hover:text-white/70">
          © 2026 A2Z · About
        </Link>
      </div>
    </aside>
  );
}
'''


def main():
    apply = "--apply" in sys.argv
    for p in (APITS, APP, SB, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1
    if os.path.exists(PAGE):
        print("ABORT: %s already exists - DW2 looks applied." % PAGE)
        return 1
    if not os.path.isfile(os.path.join("utils", "api_warehouse.py")):
        print("ABORT: apply patch_dw1_warehouse.py first.")
        return 1

    ts = open(APITS, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()

    if "fetchWarehouseShelves" in ts:
        print("ABORT: the warehouse clients already exist.")
        return 1
    if ts.count(TS_ANCHOR) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(TS_ANCHOR))
        return 1
    ts = ts.replace(TS_ANCHOR, TS_NEW + TS_ANCHOR, 1)

    if "api_warehouse" not in api:
        if api.count(WIRE_OLD) != 1:
            print("ABORT: could not find the router registration block.")
            return 1
        api = api.replace(WIRE_OLD, WIRE, 1)
        print("  ok  warehouse router registered")
    else:
        print("  ok  warehouse router already registered")
    print("  ok  api.ts clients")

    # Contact details must not be on the open shelf.
    if "Contact shown once you claim it" not in PAGE_SRC:
        print("ABORT: the shelf does not hide contact details before a claim.")
        return 1
    # A lost race must refresh what the person is looking at.
    if PAGE_SRC.count("await load();") < 4:
        print("ABORT: a failed claim does not reload the shelf - the person")
        print("       would be looking at a list that is already out of date.")
        return 1
    if "Nobody has taken these" not in PAGE_SRC:
        print("ABORT: the stale list is missing - somebody who never learns")
        print("       what became of their prospects stops listing them.")
        return 1
    if "Deals Warehouse" not in SIDEBAR:
        print("ABORT: the sidebar entry is missing.")
        return 1
    for name, blob in (("page", PAGE_SRC), ("app", APP_SRC), ("sidebar", SIDEBAR)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    print("  ok  post-checks: contacts hidden, stale surfaced, race handled")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(PAGE, "w", encoding="utf-8", newline="").write(PAGE_SRC)
    print("CREATED %s" % PAGE)
    for path, content in ((APITS, ts), (API, api), (APP, APP_SRC), (SB, SIDEBAR)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("")
    print("Next: pushd frontend\\web && pnpm tsc --noEmit && popd, restart uvicorn.")
    print("REMINDER: add patch_dw2_warehouse_ui to NOT_FOR_RELEASE alongside")
    print("patch_dw1_warehouse - the warehouse is held back from the pilot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
