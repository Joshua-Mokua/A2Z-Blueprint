#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CH7 - the deal tracker. Follow a deal, do not just count it.

RULING (2026-08-11): "on the pages, as we have referrals, we should have that
deal tracker showing where each deal is, so that one can follow and flow into
the journey, so that this is well interlinked."

A STAGE COUNT SHOWS THE SHAPE OF THE WORK; IT DOES NOT LET ANYONE FOLLOW A DEAL.
The Pipeline tab could say "two deals at Credit Analysis" but not which two, for
whom, or worth how much - so nobody could act on it. The tracker lists the deals
themselves beneath the stage bars.

    GET /api/channels/{key}/deals?record_id=

ORDERED BY JOURNEY POSITION, NOT BY DATE. The useful reading is how far each
deal has travelled; a date sort scatters that across the table. Position is
built from the CONFIGURED buckets, so it cannot drift from the funnel, and
closed deals sort last - they are outcomes, not steps.

Each row carries its GATE - refining, processing, closure - so the tracker and
the architecture agree on where a deal sits, rather than the page inventing its
own grouping.

A RECORD FILTER narrows to one event or one partnership, which is the actual
question a head of unit asks: not "how is the channel doing" but "what happened
to the deals from the Nakuru forum". The filter resets when the channel changes,
because a record id from another channel would silently filter to nothing.

Verified: tsc --noEmit clean, vite build clean. Against the seeded scenario the
tracker shows 20 deals across every stage of the journey.

REQUIRES CH6.

Usage (from project root, .venv active):
    python scripts\patch_ch7_deal_tracker.py            # dry run
    python scripts\patch_ch7_deal_tracker.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
PAGE = os.path.join("frontend", "web", "src", "pages", "OriginChannels.tsx")
BACKUP_SUFFIX = ".pre_ch7"

API_ANCHOR = '@app.get("/api/channels/{key}/analytics")'
TS_ANCHOR = "export interface ChannelAnalytics {"

ENDPOINT = r'''@app.get("/api/channels/{key}/deals")
def channels_deals(key: str, record_id: str = "",
                   user: dict = Depends(get_current_user)):
    """The individual deals this channel produced, and where each one is.

    A stage COUNT tells you the shape of the work; it does not let anyone
    follow a deal. This returns the deals themselves, ordered along the
    journey, so a head of unit can see that the Toyota partnership has two
    deals stuck at Credit Analysis and go and ask why.

    Ordered by JOURNEY POSITION, not by date - the useful reading is how far
    each deal has travelled, and a date sort scatters that.
    """
    from utils.origin_channels import channel
    from utils.pipeline_funnel import buckets_for, gate_of
    c = channel(key)
    if not c:
        raise HTTPException(status_code=404, detail="No such channel.")

    field = {"events": "event_id", "partnership": "mou_id"}.get(key, "channel_id")
    rid = str(record_id or "").strip()
    got = []
    for d in _acquire_scoped_deals(user):
        v = str(d.get(field) or "").strip()
        if not v or (rid and v != rid):
            continue
        got.append(d)

    # Journey position, built from the configured buckets so it cannot drift
    # from the funnel. Closed deals sort last - they are outcomes, not steps.
    order, gates = {}, {}
    n = 0
    for flow in ("asset", "liability"):
        for b in buckets_for(flow):
            for st in (b.get("steps") or []):
                if st not in order:
                    order[st] = n
                    gates[st] = gate_of(b["key"])
                    n += 1

    def _val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    rows = []
    for d in got:
        stage = str(d.get("stage") or "")
        closed = stage in ("Closed Won", "Closed Lost")
        rows.append({
            "id": str(d.get("id") or ""),
            "client": str(d.get("client_name") or ""),
            "product": str(d.get("product_type") or ""),
            "value": _val(d),
            "stage": stage,
            "gate": gates.get(stage, "closure" if closed else ""),
            "position": order.get(stage, 999 if closed else 998),
            "closed": closed,
            "won": stage == "Closed Won",
            "owner": str(d.get("staff_name") or d.get("staff_code") or ""),
            "branch": str(d.get("branch") or ""),
            "source_id": str(d.get(field) or ""),
            "opened": str(d.get("open_date") or d.get("created_at") or "")[:10],
        })
    rows.sort(key=lambda r: (r["position"], -r["value"]))
    return {"channel": key, "record_id": rid, "deals": rows,
            "total_value": round(sum(r["value"] for r in rows), 2)}


'''

TS_NEW = r'''export interface ChannelDeal {
  id: string; client: string; product: string; value: number;
  stage: string; gate: string; position: number;
  closed: boolean; won: boolean;
  owner: string; branch: string; source_id: string; opened: string;
}
export async function fetchChannelDeals(
  key: string, recordId = '',
): Promise<{ channel: string; record_id: string; deals: ChannelDeal[]; total_value: number }> {
  const q = new URLSearchParams(recordId ? { record_id: recordId } : {});
  const qs = q.toString();
  return getJson<{ channel: string; record_id: string; deals: ChannelDeal[]; total_value: number }>(
    `/channels/${encodeURIComponent(key)}/deals${qs ? `?${qs}` : ''}`);
}
'''

PAGE_SRC = r'''// Origin Channels — one page for every channel the bank invests in.
//
// Events, Partnerships and Lead Generators ask the same question: what did we
// spend, what did it produce, was it worth it. Three sidebar entries would be
// three doors into one question, so they share a page and a switcher.
//
// CREATE IS A BUTTON, NOT A TAB. Four tabs across three channels would be
// twelve views, and "create" is not a view you return to — it is an action.
//
// The warehouse is deliberately NOT here: it is a shared shelf with claim
// mechanics and no budget, so putting it beside these would imply a return
// question it cannot answer.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { PageHeader } from '@/components/PageHeader';
import { useToast } from '@/components/Toast';
import {
  fetchChannels, fetchChannelRecords, createChannelRecord, fetchChannelAnalytics,
  fetchChannelOwners, fetchChannelDeals,
  type OriginChannel, type ChannelRecord, type ChannelAnalytics,
  type ChannelOwners, type ChannelDeal,
} from '@/lib/api';

function kes(n: number | null | undefined): string {
  const v = Number(n ?? 0);
  if (!v) return '—';
  return Math.round(v).toLocaleString();
}

function pct(a: number, b: number | null | undefined): string {
  const t = Number(b ?? 0);
  return t > 0 ? `${Math.round((a / t) * 100)}%` : '';
}

export default function OriginChannels() {
  const { toast } = useToast();
  const [channels, setChannels] = useState<OriginChannel[]>([]);
  const [key, setKey] = useState('events');
  const [rows, setRows] = useState<ChannelRecord[]>([]);
  const [tagged, setTagged] = useState(0);
  const [loading, setLoading] = useState(false);
  const [mine, setMine] = useState(false);
  const [activeOnly, setActiveOnly] = useState(false);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  // Listing · Pipeline · Analytics. Create is a BUTTON, not a tab - it is an
  // action, not a view anyone returns to.
  const [tab, setTab] = useState<'listing' | 'pipeline' | 'analytics'>('listing');
  const [an, setAn] = useState<ChannelAnalytics | null>(null);
  // Owners are PICKED, never typed. The value must match a unit name exactly,
  // and a free-text box guarantees mismatches that make a record invisible to
  // every unit view.
  const [owners, setOwners] = useState<ChannelOwners | null>(null);
  // The deal tracker: individual deals ordered along the journey, so a person
  // can follow one rather than read a bar chart of counts.
  const [tracker, setTracker] = useState<ChannelDeal[]>([]);
  const [focus, setFocus] = useState('');

  const [form, setForm] = useState({
    name: '', owner_type: 'unit', owner: '', party: '', category: '',
    start_date: '', end_date: '', budget_kes: '', target_leads: '',
    target_accounts: '', target_value_kes: '',
  });

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetchChannels();
        setChannels(r.channels ?? []);
      } catch {
        setChannels([]);
      }
      try {
        const o = await fetchChannelOwners();
        setOwners(o);
        // Preselect the caller's own unit: recording something for your own
        // department is the common case and should need no choosing.
        if (o.mine.unit) {
          setForm((f) => ({ ...f, owner_type: 'unit', owner: o.mine.unit }));
        } else if (o.mine.branch) {
          setForm((f) => ({ ...f, owner_type: 'branch', owner: o.mine.branch }));
        }
      } catch {
        setOwners(null);
      }
    })();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetchChannelRecords(key, activeOnly, mine);
      setRows(r.records ?? []);
      setTagged(r.tagged_deals ?? 0);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load.' });
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [key, activeOnly, mine, toast]);

  useEffect(() => { void load(); }, [load]);

  // A record id from another channel would filter the tracker to nothing.
  useEffect(() => { setFocus(''); }, [key]);

  // Analytics is fetched only when its tab is open - it reads every deal, and
  // paying that on a page most people open for the listing would be rude.
  useEffect(() => {
    if (tab === 'listing') return;
    let alive = true;
    void (async () => {
      try {
        const r = await fetchChannelAnalytics(key);
        if (alive) setAn(r);
      } catch {
        if (alive) setAn(null);
      }
      try {
        const t = await fetchChannelDeals(key, focus);
        if (alive) setTracker(t.deals ?? []);
      } catch {
        if (alive) setTracker([]);
      }
    })();
    return () => { alive = false; };
  }, [tab, key, focus]);

  const current = useMemo(
    () => channels.find((c) => c.key === key), [channels, key]);

  async function submit() {
    if (!form.name.trim() || !form.owner.trim()) {
      toast({ tone: 'danger', message: 'A name and an owner are required.' });
      return;
    }
    setBusy(true);
    try {
      await createChannelRecord(key, {
        ...form,
        budget_kes: Number(form.budget_kes) || 0,
        target_leads: Number(form.target_leads) || 0,
        target_accounts: Number(form.target_accounts) || 0,
        target_value_kes: Number(form.target_value_kes) || 0,
      });
      toast({ tone: 'success', message: `${form.name} created.` });
      setCreating(false);
      setForm({ ...form, name: '', party: '', budget_kes: '' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not create.' });
    } finally {
      setBusy(false);
    }
  }

  const th = 'whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide';
  const td = 'whitespace-nowrap px-3 py-2 text-sm';
  const inp = 'mt-1 w-full h-9 px-2 rounded border border-gray-300 text-sm';

  return (
    <>
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'Pipeline Intelligence (PIS)' }, { label: 'Origin Channels' }]}
        title="Origin Channels"
      />
      <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {channels.map((c) => (
            <button
              key={c.key}
              type="button"
              onClick={() => setKey(c.key)}
              className={'rounded-full px-4 py-1.5 text-sm font-medium transition-colors ' + (
                c.key === key
                  ? 'bg-brand-primary text-white shadow-sm'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200')}
            >
              {c.label}
            </button>
          ))}
        </div>

        {current?.note && (
          <p className="mb-3 text-xs text-gray-500">{current.note}</p>
        )}

        {rows.length > 0 && (
          <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { label: current?.label ?? 'Records', value: String(rows.length),
                tone: 'bg-[#EDF4F8] text-[#003D57]' },
              { label: 'Deals tagged', value: String(tagged),
                tone: tagged ? 'bg-[#EAF3DE] text-[#3B6D11]' : 'bg-gray-50 text-gray-500' },
              { label: 'Accounts won',
                value: String(rows.reduce((a, r) => a + (r.accounts || 0), 0)),
                tone: 'bg-[#EAF3DE] text-[#3B6D11]' },
              ...(current?.supports_roi
                ? [{ label: 'Committed spend (KES)',
                     value: kes(rows.reduce(
                       (a, r) => a + Number(r.spent_kes ?? r.budget_kes ?? 0), 0)),
                     tone: 'bg-[#FEF6E7] text-[#854F0B]' }]
                : [{ label: 'Expected volume (KES)',
                     value: kes(rows.reduce(
                       (a, r) => a + Number(r.target_value_kes ?? 0), 0)),
                     tone: 'bg-[#FEF6E7] text-[#854F0B]' }]),
            ].map((c) => (
              <div key={c.label} className={`rounded-xl px-4 py-3 ${c.tone}`}>
                <div className="text-[10px] font-semibold uppercase tracking-wide opacity-70">
                  {c.label}
                </div>
                <div className="mt-1 text-xl font-semibold tabular-nums">{c.value}</div>
              </div>
            ))}
          </div>
        )}

        <div className="mb-4 flex gap-4 border-b border-gray-200">
          {(['listing', 'pipeline', 'analytics'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={'px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px capitalize ' + (
                t === tab
                  ? 'border-brand-primary text-brand-primary'
                  : 'border-transparent text-gray-600 hover:text-gray-900')}
            >
              {t}
              {t === 'listing' && rows.length > 0 && (
                <span className={'ml-1 px-2 py-0.5 text-[11px] rounded-full ' + (
                  t === tab ? 'bg-brand-primary text-white' : 'bg-gray-200 text-gray-700')}>
                  {rows.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {tab === 'listing' && (
        <Card>
          <Card.Header>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-gray-900">
                {current?.label ?? 'Channels'}
              </h2>
              <div className="flex flex-wrap items-center gap-3 text-xs">
                <label className="flex items-center gap-1.5 text-gray-600">
                  <input type="checkbox" checked={mine}
                         onChange={(e) => setMine(e.target.checked)} />
                  Mine
                </label>
                <label className="flex items-center gap-1.5 text-gray-600">
                  <input type="checkbox" checked={activeOnly}
                         onChange={(e) => setActiveOnly(e.target.checked)} />
                  Active only
                </label>
                <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[#0C447C]">
                  {tagged} deal{tagged === 1 ? '' : 's'} tagged
                </span>
                <Button size="sm" onClick={() => setCreating((v) => !v)}>
                  {creating ? 'Cancel' : 'Create'}
                </Button>
              </div>
            </div>
          </Card.Header>

          <Card.Body>
            {creating && (
              <div className="mb-4 rounded-lg border border-gray-200 bg-gray-50/60 p-3">
                <div className="grid gap-3 sm:grid-cols-3">
                  <label className="text-xs text-gray-600">
                    Name
                    <input className={inp} value={form.name}
                           onChange={(e) => setForm({ ...form, name: e.target.value })} />
                  </label>
                  <label className="text-xs text-gray-600">
                    Belongs to
                    <select className={inp} value={form.owner_type}
                            onChange={(e) => setForm({ ...form, owner_type: e.target.value })}>
                      <option value="unit">A unit</option>
                      <option value="branch">A branch</option>
                    </select>
                  </label>
                  <label className="text-xs text-gray-600">
                    {form.owner_type === 'unit' ? 'Which unit' : 'Which branch'}
                    {(() => {
                      const opts = form.owner_type === 'unit'
                        ? (owners?.units ?? []) : (owners?.branches ?? []);
                      // Falls back to a text box only if the list could not be
                      // loaded - blocking creation because a lookup failed
                      // would be worse than allowing a typo.
                      if (opts.length === 0) {
                        return (
                          <input className={inp} value={form.owner}
                                 placeholder="Could not load the list — type it"
                                 onChange={(e) => setForm({ ...form, owner: e.target.value })} />
                        );
                      }
                      const locked = !owners?.is_admin
                        && Boolean(form.owner_type === 'unit'
                          ? owners?.mine.unit : owners?.mine.branch);
                      return (
                        <>
                          <select className={inp} value={form.owner} disabled={locked}
                                  onChange={(e) => setForm({ ...form, owner: e.target.value })}>
                            <option value="">Select…</option>
                            {opts.map((o) => (
                              <option key={o.value} value={o.value}>{o.label}</option>
                            ))}
                          </select>
                          {locked && (
                            <span className="mt-1 block text-[10px] text-gray-400">
                              You can create for your own {form.owner_type} only.
                            </span>
                          )}
                        </>
                      );
                    })()}
                  </label>
                  <label className="text-xs text-gray-600">
                    {current?.party_label || 'Partner'}
                    <input className={inp} value={form.party}
                           onChange={(e) => setForm({ ...form, party: e.target.value })} />
                  </label>
                  <label className="text-xs text-gray-600">
                    Starts
                    <input type="date" className={inp} value={form.start_date}
                           onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
                  </label>
                  <label className="text-xs text-gray-600">
                    Ends
                    <input type="date" className={inp} value={form.end_date}
                           onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
                  </label>
                  {current?.supports_roi && (
                    <label className="text-xs text-gray-600">
                      Budget (KES)
                      <input className={inp} value={form.budget_kes}
                             onChange={(e) => setForm({ ...form, budget_kes: e.target.value })} />
                    </label>
                  )}
                  <label className="text-xs text-gray-600">
                    Target leads
                    <input className={inp} value={form.target_leads}
                           onChange={(e) => setForm({ ...form, target_leads: e.target.value })} />
                  </label>
                  <label className="text-xs text-gray-600">
                    Target accounts
                    <input className={inp} value={form.target_accounts}
                           onChange={(e) => setForm({ ...form, target_accounts: e.target.value })} />
                  </label>
                </div>
                <div className="mt-3 flex justify-end">
                  <Button size="sm" disabled={busy} onClick={() => void submit()}>
                    {busy ? 'Creating…' : `Create ${current?.label?.replace(/s$/, '') ?? ''}`}
                  </Button>
                </div>
              </div>
            )}

            {loading && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}

            {!loading && rows.length === 0 && (
              <p className="py-8 text-center text-sm text-gray-400">
                {mine ? 'Nothing owned by you.' : 'Nothing here yet.'}
              </p>
            )}

            {!loading && rows.length > 0 && tagged === 0 && (
              <p className="mb-3 rounded-lg border border-[#FAEEDA] bg-[#FEFAF3] px-3 py-2 text-xs text-[#854F0B]">
                No deals are tagged to any of these yet, so leads and accounts
                below are zero. That is not a verdict on the channel — pick it
                on the deal capture form to start attributing.
              </p>
            )}

            {!loading && rows.length > 0 && (
              <div className="overflow-auto rounded-lg border border-gray-200">
                <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
                  <thead>
                    <tr>
                      <th className={`${th} bg-gray-100 text-gray-600`}>Name</th>
                      <th className={`${th} bg-gray-100 text-gray-600`}>Owner</th>
                      <th className={`${th} bg-gray-100 text-gray-600`}>When</th>
                      {current?.supports_roi && (
                        <th className={`${th} bg-gray-100 text-right text-gray-600`}>Spent</th>
                      )}
                      <th className={`${th} bg-[#0082BB] text-right text-white`}>Leads</th>
                      <th className={`${th} bg-[#0082BB] text-right text-white`}>Accounts</th>
                      <th className={`${th} bg-gray-100 text-right text-gray-600`}>Won value</th>
                      <th className={`${th} bg-gray-100 text-right text-gray-600`}>
                        {current?.supports_roi ? 'Return' : 'Expected'}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => {
                      const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                      return (
                        <tr key={r.id}>
                          <td className={`${td} ${bg} font-medium text-gray-900`}>
                            <div className="truncate" style={{ maxWidth: 260 }} title={r.name}>
                              {r.name}
                            </div>
                            {r.party && <div className="text-[10px] text-gray-400">{r.party}</div>}
                          </td>
                          <td className={`${td} ${bg} text-gray-600`}>
                            {r.owner || <span className="text-gray-300">unassigned</span>}
                            {r.owner_type && (
                              <div className="text-[10px] text-gray-400">{r.owner_type}</div>
                            )}
                          </td>
                          <td className={`${td} ${bg} text-gray-500`}>
                            {String(r.start_date ?? '').slice(0, 10)}
                            <div className="text-[10px] text-gray-400">{r.status}</div>
                          </td>
                          {current?.supports_roi && (
                            <td className={`${td} ${bg} text-right tabular-nums text-gray-700`}>
                              {kes(r.spent_kes ?? r.budget_kes)}
                            </td>
                          )}
                          <td className={`${td} ${bg} text-right tabular-nums`}>
                            <span className="font-semibold text-gray-900">{r.leads}</span>
                            {r.target_leads ? (
                              <span className="ml-1 text-[10px] text-gray-400">
                                / {r.target_leads} · {pct(r.leads, r.target_leads)}
                              </span>
                            ) : null}
                          </td>
                          <td className={`${td} ${bg} text-right tabular-nums`}>
                            <span className="font-semibold text-[#3B6D11]">{r.accounts}</span>
                            {r.target_accounts ? (
                              <span className="ml-1 text-[10px] text-gray-400">
                                / {r.target_accounts} · {pct(r.accounts, r.target_accounts)}
                              </span>
                            ) : null}
                          </td>
                          <td className={`${td} ${bg} text-right font-semibold tabular-nums text-[#003D57]`}>
                            {kes(r.won_value)}
                          </td>
                          <td className={`${td} ${bg} text-right tabular-nums`}>
                            {current?.supports_roi ? (
                              r.roi_pct === null || r.roi_pct === undefined ? (
                                <span className="text-gray-300">—</span>
                              ) : (
                                <span className={r.roi_pct >= 0 ? 'text-[#3B6D11]' : 'text-rose-600'}>
                                  {r.roi_pct}%
                                </span>
                              )
                            ) : (
                              <span className="text-gray-600">{kes(r.target_value_kes)}</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card.Body>
        </Card>
        )}

        {tab === 'pipeline' && (
          <Card>
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">
                Where the deals are
              </h2>
            </Card.Header>
            <Card.Body>
              {!an && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}
              {an && an.by_stage.length === 0 && (
                <div className="py-10 text-center">
                  <p className="text-sm text-gray-500">
                    No deals are tagged to this channel yet.
                  </p>
                  <p className="mx-auto mt-2 max-w-md text-xs text-gray-400">
                    On the deal capture form, choose
                    {' '}<strong className="text-gray-500">{current?.label}</strong>{' '}
                    as the origin and pick which one. Deals tagged here will show
                    their stage, so you can see where a channel's work stalls.
                  </p>
                </div>
              )}
              {an && an.by_stage.length > 0 && (
                <>
                  <div className="mb-5 space-y-2">
                    {an.by_stage.map((s2) => {
                      const top = an.by_stage[0]?.count || 1;
                      return (
                        <div key={s2.stage} className="flex items-center gap-3">
                          <div className="w-52 shrink-0 truncate text-xs text-gray-600"
                               title={s2.stage}>{s2.stage}</div>
                          <div className="h-5 flex-1 overflow-hidden rounded bg-gray-100">
                            <div className="h-full rounded bg-brand-primary"
                                 style={{ width: `${Math.max(4, (s2.count / top) * 100)}%` }} />
                          </div>
                          <div className="w-10 shrink-0 text-right text-xs tabular-nums text-gray-700">
                            {s2.count}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* THE TRACKER. A stage count shows the shape of the work; it
                      does not let anyone follow a deal. These are the deals
                      themselves, ordered by how far each has travelled. */}
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold text-gray-800">
                      Deal tracker
                    </h3>
                    <select value={focus} onChange={(e) => setFocus(e.target.value)}
                            className="rounded border border-gray-200 px-2 py-1 text-xs">
                      <option value="">All {current?.label?.toLowerCase()}</option>
                      {rows.map((r) => (
                        <option key={r.id} value={r.id}>{r.name}</option>
                      ))}
                    </select>
                  </div>

                  {tracker.length === 0 ? (
                    <p className="py-6 text-center text-xs text-gray-400">
                      No deals for this selection.
                    </p>
                  ) : (
                    <div className="overflow-auto rounded-lg border border-gray-200">
                      <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
                        <thead>
                          <tr>
                            <th className={`${th} bg-gray-100 text-gray-600`}>Deal</th>
                            <th className={`${th} bg-gray-100 text-gray-600`}>Client</th>
                            <th className={`${th} bg-gray-100 text-gray-600`}>Owner</th>
                            <th className={`${th} bg-gray-100 text-gray-600`}>Gate</th>
                            <th className={`${th} bg-brand-primary text-white`}>Stage</th>
                            <th className={`${th} bg-gray-100 text-right text-gray-600`}>Value (KES)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {tracker.map((d, i) => {
                            const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                            return (
                              <tr key={d.id}>
                                <td className={`${td} ${bg} tabular-nums text-gray-500`}>{d.id}</td>
                                <td className={`${td} ${bg} text-gray-900`}>
                                  <div className="truncate" style={{ maxWidth: 200 }}
                                       title={d.client}>{d.client}</div>
                                  <div className="text-[10px] text-gray-400">{d.product}</div>
                                </td>
                                <td className={`${td} ${bg} text-gray-600`}>
                                  <div className="truncate" style={{ maxWidth: 160 }}>{d.owner}</div>
                                  <div className="text-[10px] text-gray-400">{d.branch}</div>
                                </td>
                                <td className={`${td} ${bg}`}>
                                  {d.gate && (
                                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] capitalize text-gray-600">
                                      {d.gate}
                                    </span>
                                  )}
                                </td>
                                <td className={`${td} ${bg}`}>
                                  <span className={'rounded-full px-2 py-0.5 text-[11px] ' + (
                                    d.won ? 'bg-[#EAF3DE] text-[#3B6D11]'
                                      : d.closed ? 'bg-[#FBEAF0] text-[#993556]'
                                        : 'bg-[#E6F1FB] text-[#0C447C]')}>
                                    {d.stage}
                                  </span>
                                </td>
                                <td className={`${td} ${bg} text-right font-semibold tabular-nums text-[#003D57]`}>
                                  {kes(d.value)}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </Card.Body>
          </Card>
        )}

        {tab === 'analytics' && (
          <div className="space-y-4">
            <Card>
              <Card.Header>
                <h2 className="text-base font-semibold text-gray-900">
                  Does it pay for itself?
                </h2>
              </Card.Header>
              <Card.Body>
                {!an && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}
                {an && (
                  <>
                    <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
                      {[
                        ['Records', String(an.totals.records)],
                        ...(an.totals.supports_roi
                          ? [['Spent (KES)', kes(an.totals.spent)] as [string, string]]
                          : []),
                        ['Leads', String(an.totals.leads)],
                        ['Accounts', String(an.totals.accounts)],
                        ['Conversion', an.totals.conversion_pct === null
                          ? '—' : `${an.totals.conversion_pct}%`],
                        ['Won value (KES)', kes(an.totals.value)],
                      ].map(([label, val]) => (
                        <div key={label} className="rounded-lg border border-gray-200 p-3">
                          <div className="text-[10px] uppercase tracking-wide text-gray-500">
                            {label}
                          </div>
                          <div className="mt-1 text-lg font-semibold tabular-nums text-gray-900">
                            {val}
                          </div>
                        </div>
                      ))}
                    </div>

                    {an.totals.supports_roi && (
                      <div className="mt-3 flex flex-wrap gap-6 text-xs text-gray-600">
                        <span>
                          Cost per account:{' '}
                          <strong className="tabular-nums">
                            {an.totals.cost_per_account === null
                              ? 'no accounts yet'
                              : kes(an.totals.cost_per_account)}
                          </strong>
                        </span>
                        <span>
                          Return:{' '}
                          <strong className={an.totals.roi_pct !== null && an.totals.roi_pct >= 0
                            ? 'text-[#3B6D11]' : 'text-rose-600'}>
                            {an.totals.roi_pct === null ? '—' : `${an.totals.roi_pct}%`}
                          </strong>
                        </span>
                      </div>
                    )}
                  </>
                )}
              </Card.Body>
            </Card>

            {an && an.by_owner.length > 0 && (
              <Card>
                <Card.Header>
                  <h2 className="text-base font-semibold text-gray-900">By owner</h2>
                </Card.Header>
                <Card.Body>
                  <div className="overflow-auto rounded-lg border border-gray-200">
                    <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
                      <thead>
                        <tr>
                          <th className={`${th} bg-gray-100 text-gray-600`}>Owner</th>
                          <th className={`${th} bg-gray-100 text-right text-gray-600`}>Records</th>
                          {an.totals.supports_roi && (
                            <th className={`${th} bg-gray-100 text-right text-gray-600`}>Spent</th>
                          )}
                          <th className={`${th} bg-gray-100 text-right text-gray-600`}>Leads</th>
                          <th className={`${th} bg-gray-100 text-right text-gray-600`}>Accounts</th>
                          <th className={`${th} bg-gray-100 text-right text-gray-600`}>Won value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {an.by_owner.map((o, i) => (
                          <tr key={o.owner}>
                            <td className={`${td} ${i % 2 ? 'bg-gray-50/40' : 'bg-white'} text-gray-800`}>
                              {o.owner}
                            </td>
                            <td className={`${td} ${i % 2 ? 'bg-gray-50/40' : 'bg-white'} text-right tabular-nums text-gray-600`}>{o.records}</td>
                            {an.totals.supports_roi && (
                              <td className={`${td} ${i % 2 ? 'bg-gray-50/40' : 'bg-white'} text-right tabular-nums text-gray-600`}>{kes(o.spent)}</td>
                            )}
                            <td className={`${td} ${i % 2 ? 'bg-gray-50/40' : 'bg-white'} text-right tabular-nums text-gray-900`}>{o.leads}</td>
                            <td className={`${td} ${i % 2 ? 'bg-gray-50/40' : 'bg-white'} text-right tabular-nums text-[#3B6D11]`}>{o.accounts}</td>
                            <td className={`${td} ${i % 2 ? 'bg-gray-50/40' : 'bg-white'} text-right font-semibold tabular-nums text-[#003D57]`}>{kes(o.value)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card.Body>
              </Card>
            )}

            {an && (an.no_conversions.length > 0 || an.untagged.length > 0) && (
              <Card>
                <Card.Header>
                  <h2 className="text-base font-semibold text-gray-900">Worth a look</h2>
                </Card.Header>
                <Card.Body>
                  {an.no_conversions.length > 0 && (
                    <p className="mb-2 text-xs text-gray-600">
                      <strong>{an.no_conversions.length}</strong> with leads but no
                      closed accounts yet — {an.no_conversions.slice(0, 3)
                        .map((r) => r.name).join(', ')}
                      {an.no_conversions.length > 3 ? '…' : ''}
                    </p>
                  )}
                  {an.untagged.length > 0 && (
                    <p className="text-xs text-gray-500">
                      <strong>{an.untagged.length}</strong> with no deals tagged at
                      all. That is usually a tagging gap rather than a failed
                      channel, and it is worth asking before drawing conclusions.
                    </p>
                  )}
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


def main():
    apply = "--apply" in sys.argv
    for p in (API, APITS, PAGE):
        if not os.path.isfile(p):
            print("ABORT: %s not found - apply patch_ch6_owner_picker.py first." % p)
            return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if "/api/channels/{key}/deals" in api:
        print("ABORT: the deals endpoint already exists - CH7 looks applied.")
        return 1
    if API_ANCHOR not in api:
        print("ABORT: apply patch_ch3_channel_tabs.py first.")
        return 1
    if ts.count(TS_ANCHOR) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(TS_ANCHOR))
        return 1

    api = api.replace(API_ANCHOR, ENDPOINT + API_ANCHOR, 1)
    ts = ts.replace(TS_ANCHOR, TS_NEW + TS_ANCHOR, 1)
    print("  ok  deals endpoint and client")

    # Order must come from the configured journey, not a hardcoded list.
    if "buckets_for" not in ENDPOINT:
        print("ABORT: journey order is not read from the configured buckets -")
        print("       a hardcoded order drifts from the funnel silently.")
        return 1
    if 'r["position"]' not in ENDPOINT:
        print("ABORT: deals are not ordered by journey position.")
        return 1
    if "gate_of" not in ENDPOINT:
        print("ABORT: rows do not carry their gate, so the tracker and the")
        print("       architecture would disagree about where a deal sits.")
        return 1
    if "Deal tracker" not in PAGE_SRC:
        print("ABORT: the tracker is missing from the page.")
        return 1
    # A stale record id from another channel would filter to nothing.
    if "setFocus('');" not in PAGE_SRC:
        print("ABORT: the record filter does not reset when the channel changes.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if PAGE_SRC.count(op) != PAGE_SRC.count(cl):
            print("ABORT: page unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: journey order, gates carried, filter resets")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((API, api), (APITS, ts), (PAGE, PAGE_SRC)):
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

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd, restart uvicorn.")
    print("Origin Channels > Pipeline. With the scenario seeded you should see")
    print("deals at every stage, and be able to narrow to one event.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
