#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
WA1 - one record card, and analytics that report validated against total.

TWO RULINGS (2026-08-11).

1. "THOSE 2 TABLES SHOULD ALSO BE REMOVED and whatever information necessary
   goes to the one table we have built - the one they work on and save becomes
   the detail page."

   ProspectDetail is now ONE card. The separate business summary and the "what
   we know" card are gone; what they carried that mattered lives here:

       HEADER STRIP   name · validated-or-under-validation · claimed state ·
                      score · Pursue · Validate · provenance
       FOUR SECTIONS  Identity · Where to find them · Ownership and people ·
                      The business
       FREE TEXT      anything the fifteen do not cover
       SOURCES        findings, folded in rather than sitting in their own card

   The page was REWRITTEN rather than patched again. It had been spliced a
   dozen times and the last surgical edit broke its JSX - at that point another
   splice is a worse bet than a clean file.

2. "ANY ENTRY HAS TO GO THROUGH THE VALIDATION GATE EVEN IF IT ENTERS COMPLETE
   ... we are also to have proper analytics showing what we have validated,
   unvalidated, sectors, segments, towns and a lot more."

   Nothing is born validated, whatever its score - validation is somebody
   looking, not a number crossing a line. Everything lands under "Under
   validation" and moves across only when a person says so.

   The ANALYTICS tab cuts the warehouse by sector, segment, county and source -
   and EVERY CUT REPORTS VALIDATED AGAINST TOTAL. "Nairobi: 58" is not the
   useful figure; "58, of which 4 validated" is, because the second tells you
   whether the coverage is real or just imported. A dashboard showing only
   totals is how a warehouse comes to look bigger than it is.

   Plus completeness BANDS - so "how far off are we" has an answer that is not
   one average hiding both a validated record and an empty one - and WHAT TO
   BACKFILL NEXT: the field missing on the most records, which moves more
   prospects toward validation than any other.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

REQUIRES UX1.

Usage (from project root, .venv active):
    python scripts\patch_wa1_one_card_analytics.py            # dry run
    python scripts\patch_wa1_one_card_analytics.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "deals_warehouse.py")
API = os.path.join("utils", "api_warehouse.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
SHELF = os.path.join("frontend", "web", "src", "pages", "Warehouse.tsx")
DETAIL = os.path.join("frontend", "web", "src", "pages", "ProspectDetail.tsx")
BACKUP_SUFFIX = ".pre_wa1"

MOD_ANCHOR = "def completeness_summary() -> dict:"
API_ANCHOR = '@router.get("/mine")'
TS_ANCHOR = "export async function fetchCompletenessMatrix("

ANALYTICS = r'''def warehouse_analytics() -> dict:
    """What we hold, and how much of it anybody should trust.

    RULING (2026-08-11): "we are also to have proper analytics showing what we
    have validated, unvalidated, sectors, segments, towns and a lot more."

    EVERY CUT REPORTS BOTH NUMBERS. "Nairobi: 58" is not the useful figure -
    "Nairobi: 58, of which 4 validated" is, because the second one tells you
    whether the coverage is real or just imported. A dashboard that shows only
    totals is how a warehouse comes to look bigger than it is.
    """
    recs = all_prospects()
    live = [r for r in recs if r.get("status") != STATUS_ARCHIVED]

    def _cut(key, fallback="Unassigned"):
        out = {}
        for r in live:
            k = str(r.get(key) or "").strip() or fallback
            e = out.setdefault(k, {"label": k, "total": 0, "validated": 0,
                                   "ready": 0, "score_sum": 0})
            c = completeness(r)
            e["total"] += 1
            e["score_sum"] += c.get("score", 0)
            if c.get("validated"):
                e["validated"] += 1
            elif c.get("complete"):
                e["ready"] += 1
        for e in out.values():
            e["average_score"] = round(e["score_sum"] / e["total"]) if e["total"] else 0
            e.pop("score_sum", None)
        return sorted(out.values(), key=lambda x: -x["total"])

    scores = [completeness(r).get("score", 0) for r in live]
    validated = sum(1 for r in live if r.get("validated"))
    ready = sum(1 for r in live
                if not r.get("validated") and completeness(r).get("complete"))
    # Bands, so "how far off are we" has an answer that is not one average.
    bands = {"0-24": 0, "25-49": 0, "50-79": 0, "80-99": 0, "100": 0}
    for sc in scores:
        key = ("100" if sc >= 100 else "80-99" if sc >= 80
               else "50-79" if sc >= 50 else "25-49" if sc >= 25 else "0-24")
        bands[key] += 1

    return {
        "totals": {
            "prospects": len(live),
            "validated": validated,
            "ready_to_validate": ready,
            "under_validation": len(live) - validated,
            "average_score": round(sum(scores) / len(scores)) if scores else 0,
            "claimed": sum(1 for r in live if r.get("claimed_by_code")),
            "converted": sum(1 for r in live if r.get("deal_id")),
        },
        "by_sector": _cut("sector", "Unsorted"),
        "by_segment": _cut("segment", "Not set"),
        "by_county": _cut("town", "Countrywide"),
        "by_source": _cut("source_event", "Entered by hand"),
        "bands": [{"band": k, "count": v} for k, v in bands.items()],
        "gaps": completeness_summary().get("worst_gaps", []),
    }


'''

ENDPOINT = r'''@router.get("/analytics")
def warehouse_analytics_ep(user: dict = Depends(get_current_user)):
    """What the warehouse holds, cut by sector, segment, county and source -
    every cut reporting VALIDATED against TOTAL, because the total alone makes
    a warehouse look bigger than it is."""
    from utils.deals_warehouse import warehouse_analytics
    return warehouse_analytics()


'''

TS_NEW = r'''export interface WarehouseCut {
  label: string; total: number; validated: number; ready: number; average_score: number;
}
export interface WarehouseAnalytics {
  totals: { prospects: number; validated: number; ready_to_validate: number;
            under_validation: number; average_score: number; claimed: number;
            converted: number };
  by_sector: WarehouseCut[]; by_segment: WarehouseCut[];
  by_county: WarehouseCut[]; by_source: WarehouseCut[];
  bands: { band: string; count: number }[];
  gaps: { key: string; label: string; missing: number }[];
}
export async function fetchWarehouseAnalytics(): Promise<WarehouseAnalytics> {
  return getJson<WarehouseAnalytics>('/warehouse/analytics');
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
  const [tab, setTab] = useState<'validated' | 'working' | 'shelf' | 'mine' | 'analytics'>('validated');
  const [shelves, setShelves] = useState<Record<string, WarehouseProspect[]>>({});
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState({ validated: 0 });
  const [an, setAn] = useState<WarehouseAnalytics | null>(null);
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
        const r = await fetchWarehouseShelves({ town, q });
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
        setCounts({ validated: v });
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
                  <select value={town} onChange={(e) => setTown(e.target.value)}
                          className="rounded border border-gray-200 px-2 py-1 text-xs">
                    <option value="">Countrywide</option>
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
'''

DETAIL_SRC = r'''// The prospect record — ONE card.
//
// RULING (2026-08-11): "collapse these into one detail card that will be
// applicable even when one is creating an entry ... the one they work on and
// save becomes the detail page, that becomes our one table that is saved and
// when validated submitted to the validated side."
//
// Three cards asked a reader to hold the same business in their head three
// times. What the other two carried that mattered — status, provenance, the
// actions, and what anybody has found out — lives here: a header strip, four
// sections, and sources at the foot.
//
// EVERY ENTRY PASSES THE VALIDATION GATE. Nothing is born validated, however
// complete it arrives, because validation is somebody looking — not a score
// crossing a line.

import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/Button';
import { PageHeader } from '@/components/PageHeader';
import { useToast } from '@/components/Toast';
import {
  fetchProspect, addProspectFact, claimProspect, validateProspect,
  updateProspect, fetchCompletenessMatrix,
  type ProspectDetail as Detail, type ProspectFact,
} from '@/lib/api';

type Row = {
  key: string; field: string; label: string;
  kind?: 'text' | 'select' | 'number' | 'area';
  options?: 'segments' | 'sectors' | 'counties';
  placeholder?: string;
};

// Sections pool related questions, so a block can be finished in one sitting
// rather than facing fifteen rows that each demand a different kind of digging.
const SECTIONS: { title: string; hint: string; rows: Row[] }[] = [
  {
    title: 'Identity',
    hint: 'Who this is, in the terms the bank organises itself around.',
    rows: [
      { key: 'name', field: 'name', label: 'Legal name' },
      { key: 'segment', field: 'segment', label: 'Segment', kind: 'select', options: 'segments' },
      { key: 'sector', field: 'sector', label: 'Sector', kind: 'select', options: 'sectors' },
      { key: 'business_activity', field: 'business_activity', label: 'What they actually do',
        kind: 'area', placeholder: 'Grain milling and animal feeds; supplies three counties' },
    ],
  },
  {
    title: 'Where to find them',
    hint: 'Enough for somebody to turn up, or to call.',
    rows: [
      { key: 'county', field: 'town', label: 'County', kind: 'select', options: 'counties' },
      { key: 'physical_address', field: 'physical_address', label: 'Physical address',
        placeholder: 'Ngano House, Industrial Area' },
      { key: 'branches', field: 'branches', label: 'Branches or footprint',
        placeholder: '12 branches across 6 counties' },
      { key: 'phone', field: 'contact_phone', label: 'Phone', placeholder: '0722 000 000' },
      { key: 'email', field: 'contact_email', label: 'Email', placeholder: 'info@example.co.ke' },
      { key: 'online_presence', field: 'website', label: 'Website', placeholder: 'example.co.ke' },
    ],
  },
  {
    title: 'Ownership and people',
    hint: 'Who decides, and who they answer to.',
    rows: [
      { key: 'decision_maker', field: 'contact_name', label: 'Decision maker and role',
        placeholder: 'Jane Wanjiku — CEO' },
      { key: '', field: 'ownership', label: 'Ownership or affiliation',
        placeholder: 'Member-owned; affiliated to KUSCCO' },
      { key: 'established', field: 'established', label: 'Year established',
        kind: 'number', placeholder: '1974' },
    ],
  },
  {
    title: 'The business',
    hint: 'What decides whether this is worth anyone\u2019s time.',
    rows: [
      { key: 'size_indicator', field: 'estimated_value',
        label: 'Size (turnover, assets or members)', kind: 'number' },
      { key: 'existing_banker', field: 'existing_banker', label: 'Banks with now',
        placeholder: 'KCB, Co-operative Bank' },
      { key: 'value_chain', field: 'value_chain', label: 'Value chain and potential needs',
        kind: 'area',
        placeholder: 'Buys maize from farmer groups; sells to schools and retailers. '
          + 'Likely needs: working capital, collection accounts.' },
    ],
  },
];

const KINDS = [
  { key: 'contact', label: 'Contact' },
  { key: 'relationship', label: 'Director / officer' },
  { key: 'financial', label: 'Financial' },
  { key: 'association', label: 'Membership' },
  { key: 'filing', label: 'Filing' },
  { key: 'news', label: 'News' },
  { key: 'note', label: 'Note' },
];

export default function ProspectDetail() {
  const { prospectId = '' } = useParams();
  const nav = useNavigate();
  const { toast } = useToast();

  const [data, setData] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [lists, setLists] = useState<{ segments: string[]; sectors: string[]; counties: string[] }>(
    { segments: [], sectors: [], counties: [] });
  const [fact, setFact] = useState({
    kind: 'contact', title: '', source: '', url: '', occurred_on: '',
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

  useEffect(() => {
    void (async () => {
      try {
        const m = await fetchCompletenessMatrix();
        setLists({ segments: m.segments ?? [], sectors: m.sectors ?? [], counties: m.counties ?? [] });
      } catch { /* the form still works, just without the pickers */ }
    })();
  }, []);

  const p = data?.prospect;
  const c = data?.completeness;
  const facts: ProspectFact[] = data?.card?.items ?? [];

  async function save() {
    // The password is asked for ONLY on a validated record. The working set
    // exists to be filled in, and friction there stops the backfilling.
    let pw = '';
    if (c?.validated) {
      pw = window.prompt('This is a validated record. Enter the warehouse password to change it.') || '';
      if (!pw) return;
    }
    setBusy(true);
    try {
      await updateProspect(prospectId, edit, pw);
      toast({ tone: 'success', message: 'Saved.' });
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

  async function addFact() {
    if (!fact.title.trim() || !fact.source.trim()) {
      toast({ tone: 'danger', message: 'A source needs what it says and where it came from.' });
      return;
    }
    setBusy(true);
    try {
      await addProspectFact(prospectId, fact);
      setFact({ ...fact, title: '', url: '' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not add.' });
    } finally {
      setBusy(false);
    }
  }

  const box = 'mt-1 w-full rounded-lg border px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-[#0082BB] ';
  const small = 'h-8 w-full rounded-lg border border-gray-200 px-2 text-xs focus:outline-none focus:ring-1 focus:ring-[#0082BB]';

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
          <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-4 py-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-semibold text-gray-900">{p.name}</h2>
                  <span className={'rounded-full px-2.5 py-0.5 text-[11px] ' + (
                    c?.validated ? 'bg-[#EAF3DE] text-[#3B6D11]' : 'bg-[#FEF6E7] text-[#854F0B]')}>
                    {c?.validated ? `validated by ${c.validated_by}` : 'under validation'}
                  </span>
                  <span className={'rounded-full px-2.5 py-0.5 text-[11px] ' + (
                    p.status === 'available' ? 'bg-[#E6F1FB] text-[#0C447C]' : 'bg-gray-100 text-gray-600')}>
                    {p.status === 'available' ? 'unclaimed'
                      : p.claimed_by_name ? `with ${p.claimed_by_name}` : p.status}
                  </span>
                </div>
                <div className="mt-1 text-[11px] text-gray-500">
                  {p.source_event || 'Entered by hand'}
                  {p.created_at ? ` · ${String(p.created_at).slice(0, 10)}` : ''}
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="text-right">
                  <div className={'text-lg font-semibold tabular-nums ' + (
                    c?.validated ? 'text-[#3B6D11]' : 'text-gray-800')}>{c?.score ?? 0}%</div>
                  <div className="text-[10px] text-gray-400">
                    {c?.answered ?? 0}/{c?.of ?? 15} answered
                  </div>
                </div>
                {p.status === 'available' && (
                  <Button size="sm" variant="secondary" disabled={busy}
                          onClick={() => void pursue()}>Pursue</Button>
                )}
                {!c?.validated && (
                  <Button size="sm" disabled={busy || !c?.complete}
                          title={c?.complete ? '' : `${c?.threshold ?? 80}% needed first`}
                          onClick={() => void validate()}>Validate</Button>
                )}
              </div>
            </div>

            <div className="h-1.5 bg-gray-100">
              <div className={'h-full ' + (
                c?.validated ? 'bg-[#3B6D11]'
                  : (c?.score ?? 0) >= 80 ? 'bg-[#BED600]'
                    : (c?.score ?? 0) >= 40 ? 'bg-[#E0A02B]' : 'bg-gray-300')}
                   style={{ width: `${Math.max(2, c?.score ?? 0)}%` }} />
            </div>

            <div className="space-y-4 p-4">
              {c?.stale_validation && (
                <p className="rounded-lg border border-[#FAEEDA] bg-[#FEFAF3] px-3 py-2 text-xs text-[#854F0B]">
                  This record changed after it was validated, so it is no longer
                  the record that was checked. Worth validating again.
                </p>
              )}

              {SECTIONS.map((sec) => {
                const done = sec.rows.filter((r) => r.key && c?.have.includes(r.key)).length;
                const scored = sec.rows.filter((r) => r.key).length;
                return (
                  <div key={sec.title} className="overflow-hidden rounded-xl border border-gray-200">
                    <div className="flex items-center justify-between gap-2 border-b border-gray-100 bg-gray-50/70 px-3 py-2">
                      <div>
                        <div className="text-xs font-semibold uppercase tracking-wide text-[#003D57]">
                          {sec.title}
                        </div>
                        <div className="text-[10px] text-gray-500">{sec.hint}</div>
                      </div>
                      {scored > 0 && (
                        <span className={'shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ' + (
                          done === scored ? 'bg-[#EAF3DE] text-[#3B6D11]' : 'bg-[#FEF6E7] text-[#854F0B]')}>
                          {done}/{scored}
                        </span>
                      )}
                    </div>

                    <div className="grid gap-3 p-3 sm:grid-cols-2">
                      {sec.rows.map((row) => {
                        const answered = row.key ? Boolean(c?.have.includes(row.key)) : true;
                        const cur = edit[row.field]
                          ?? String((p as unknown as Record<string, unknown>)[row.field] ?? '');
                        const set = (v: string) => setEdit({ ...edit, [row.field]: v });
                        const cls = box + (answered ? 'border-gray-200' : 'border-[#F0D9A8] bg-[#FFFDF8]');
                        const opts = row.options === 'segments' ? lists.segments
                          : row.options === 'sectors' ? lists.sectors
                            : row.options === 'counties' ? lists.counties : [];
                        return (
                          <label key={row.field}
                                 className={'block text-[11px] text-gray-600 '
                                   + (row.kind === 'area' ? 'sm:col-span-2' : '')}>
                            <span className="flex items-center gap-1.5">
                              <span className={'h-1.5 w-1.5 rounded-full ' + (
                                answered ? 'bg-[#3B6D11]' : 'bg-[#E0A02B]')} />
                              {row.label}
                            </span>
                            {row.kind === 'select' ? (
                              <select className={cls} value={cur} onChange={(e) => set(e.target.value)}>
                                <option value="">Select…</option>
                                {opts.map((o) => <option key={o} value={o}>{o}</option>)}
                              </select>
                            ) : row.kind === 'area' ? (
                              <textarea rows={2} className={cls} value={cur}
                                        placeholder={row.placeholder}
                                        onChange={(e) => set(e.target.value)} />
                            ) : (
                              <input className={cls} value={cur} placeholder={row.placeholder}
                                     inputMode={row.kind === 'number' ? 'numeric' : undefined}
                                     onChange={(e) => set(e.target.value)} />
                            )}
                          </label>
                        );
                      })}
                    </div>
                  </div>
                );
              })}

              {/* Every warehouse eventually meets a business whose important
                  fact has no column, and a record with nowhere to put it loses
                  the fact. */}
              <label className="block text-[11px] text-gray-600">
                Anything else worth knowing
                <textarea rows={3}
                          className={box + 'border-gray-200'}
                          placeholder="Seasonality, known issues, group structure, anything the fields above do not cover…"
                          value={edit.additional_information
                            ?? String((p as unknown as Record<string, unknown>).additional_information ?? '')}
                          onChange={(e) => setEdit({ ...edit, additional_information: e.target.value })} />
              </label>

              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] text-gray-400">
                  {c?.validated
                    ? 'Validated — saving needs the warehouse password.'
                    : `Fill in what you know. ${c?.threshold ?? 80}% opens validation.`}
                </span>
                <Button size="sm" disabled={busy || Object.keys(edit).length === 0}
                        onClick={() => void save()}>
                  {busy ? 'Saving…' : 'Save'}
                </Button>
              </div>

              {/* SOURCES, folded in rather than sitting in a card of their own.
                  Each is a fact with a date and a place it came from - never a
                  copied article. */}
              <div className="overflow-hidden rounded-xl border border-gray-200">
                <div className="flex items-center justify-between gap-2 border-b border-gray-100 bg-gray-50/70 px-3 py-2">
                  <div className="text-xs font-semibold uppercase tracking-wide text-[#003D57]">
                    Sources and findings
                  </div>
                  <span className="text-[10px] text-gray-500">
                    {facts.length} {facts.length === 1 ? 'entry' : 'entries'}
                  </span>
                </div>

                <div className="space-y-2 p-3">
                  <div className="grid gap-2 sm:grid-cols-6">
                    <select className={small} value={fact.kind}
                            onChange={(e) => setFact({ ...fact, kind: e.target.value })}>
                      {KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
                    </select>
                    <input className={`${small} sm:col-span-2`} value={fact.title}
                           placeholder="What it says"
                           onChange={(e) => setFact({ ...fact, title: e.target.value })} />
                    <input className={small} value={fact.source}
                           placeholder="Where from"
                           onChange={(e) => setFact({ ...fact, source: e.target.value })} />
                    <input type="date" className={small} value={fact.occurred_on}
                           onChange={(e) => setFact({ ...fact, occurred_on: e.target.value })} />
                    <Button size="sm" disabled={busy} onClick={() => void addFact()}>Add</Button>
                  </div>

                  {facts.length === 0 ? (
                    <p className="py-3 text-center text-[11px] text-gray-400">
                      Nothing recorded yet. Whoever finds something out records it here.
                    </p>
                  ) : (
                    <ul className="divide-y divide-gray-100">
                      {facts.map((f) => (
                        <li key={f.id} className="flex flex-wrap items-baseline gap-2 py-1.5 text-xs">
                          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-gray-600">
                            {KINDS.find((k) => k.key === f.kind)?.label ?? f.kind}
                          </span>
                          <span className="font-medium text-gray-900">{f.title}</span>
                          <span className="text-[10px] text-gray-400">
                            {f.source}{f.occurred_on ? ` · ${f.occurred_on}` : ''}
                            {f.added_by ? ` · ${f.added_by}` : ''}
                          </span>
                          {f.url && (
                            <a href={f.url} target="_blank" rel="noreferrer"
                               className="text-[10px] text-brand-primary hover:underline">open</a>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

              <button type="button"
                      className="w-full text-center text-xs text-gray-500 hover:text-gray-700"
                      onClick={() => nav('/pipeline/warehouse')}>
                Back to the shelf
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
'''


def main():
    apply = "--apply" in sys.argv
    for p in (MOD, API, APITS, SHELF, DETAIL):
        if not os.path.isfile(p):
            print("ABORT: %s not found - apply patch_ux1_record_card.py first." % p)
            return 1

    mod = open(MOD, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if "def warehouse_analytics(" in mod:
        print("ABORT: warehouse_analytics already present - WA1 looks applied.")
        return 1
    if mod.count(MOD_ANCHOR) != 1 or api.count(API_ANCHOR) != 1 or ts.count(TS_ANCHOR) != 1:
        print("ABORT: anchors matched %d / %d / %d."
              % (mod.count(MOD_ANCHOR), api.count(API_ANCHOR), ts.count(TS_ANCHOR)))
        return 1

    mod = mod.replace(MOD_ANCHOR, ANALYTICS + MOD_ANCHOR, 1)
    api = api.replace(API_ANCHOR, ENDPOINT + API_ANCHOR, 1)
    ts = ts.replace(TS_ANCHOR, TS_NEW + TS_ANCHOR, 1)
    print("  ok  analytics, endpoint, client")

    # Every cut must carry validated, or the numbers flatter the warehouse.
    if '"validated": 0' not in ANALYTICS or '"total": 0' not in ANALYTICS:
        print("ABORT: a cut does not report validated against total - the")
        print("       total alone makes a warehouse look bigger than it is.")
        return 1
    if '"bands"' not in ANALYTICS:
        print("ABORT: no completeness bands - one average hides a validated")
        print("       record and an empty one in the same number.")
        return 1
    # One card, and the old ones gone.
    if "SECTIONS" not in DETAIL_SRC or "Sources and findings" not in DETAIL_SRC:
        print("ABORT: the detail page is not the single sectioned card.")
        return 1
    if DETAIL_SRC.count("<Card>") > 0:
        print("ABORT: separate Cards survive on the detail page - the ruling")
        print("       was to collapse them into one.")
        return 1
    if "'analytics'" not in SHELF_SRC:
        print("ABORT: the analytics tab is missing from the warehouse.")
        return 1
    for name, blob in (("shelf", SHELF_SRC), ("detail", DETAIL_SRC)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    print("  ok  post-checks: one card, validated-vs-total on every cut")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((MOD, mod), (API, api), (APITS, ts),
                          (SHELF, SHELF_SRC), (DETAIL, DETAIL_SRC)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    for path in (MOD, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("\nDeals Warehouse > Analytics for the cuts; Details on any prospect")
    print("for the single record card.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
