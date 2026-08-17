#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CH3 - the Pipeline and Analytics tabs. Completes the channels page.

RULING (2026-08-11): "we can have events listing now, then Events Pipeline,
Events Analytics where we can do analysis proper."

CH2 shipped Listing and Create. CH3 adds the other two, for EVERY channel rather
than only events - which is the point of having built one model.

    LISTING     what exists, who owns it, what it produced
    PIPELINE    where the tagged deals actually are, by stage
    ANALYTICS   does this channel pay for itself

ANALYTICS IS FETCHED ONLY WHEN ITS TAB IS OPENED. It reads every deal, and
paying that cost on a page most people open for the listing would be rude - the
same per-row discipline that the 504 taught this system.

EVERY FIGURE IS DERIVED FROM DEALS. The stored actual_* fields are deliberately
NOT mixed in: they are generated numbers, and a total combining generated with
derived is a number nobody can defend in a meeting.

TWO DISTINCTIONS THE ANALYTICS REFUSES TO BLUR:

  "NO CONVERSIONS YET" is not "EXPENSIVE". Records with leads but no closed
  accounts are excluded from the cost-per-account ranking rather than sorted
  last at infinity, and reported separately. Sharing a row position would imply
  a comparison that has not been earned.

  "NOTHING TAGGED" is not "FAILED". Records with no deals at all are listed
  under their own heading with the reason stated - it is usually a tagging gap,
  and it is worth asking before drawing conclusions.

Cost per account and return appear only where the channel supports ROI, so
partnerships - which carry expected volume and no budget - are never shown a
percentage computed against a budget nobody set.

Verified: tsc --noEmit clean, vite build clean.

REQUIRES CH2.

Usage (from project root, .venv active):
    python scripts\patch_ch3_channel_tabs.py            # dry run
    python scripts\patch_ch3_channel_tabs.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
PAGE = os.path.join("frontend", "web", "src", "pages", "OriginChannels.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
BACKUP_SUFFIX = ".pre_ch3"

API_ANCHOR = '@app.post("/api/channels/{key}/records", status_code=201)'
TS_ANCHOR = "export async function fetchChannels()"

ENDPOINT = r'''@app.get("/api/channels/{key}/analytics")
def channels_analytics(key: str, user: dict = Depends(get_current_user)):
    """Does this channel pay for itself, and which records carry it?

    Deals are read ONCE and bucketed. Every figure is derived from deals; the
    stored actual_* fields are not used, because they are generated numbers and
    mixing generated with derived in one total is how a report stops meaning
    anything.
    """
    from utils.origin_channels import channel, listing, CLOSED_WON
    c = channel(key)
    if not c:
        raise HTTPException(status_code=404, detail="No such channel.")

    field = {"events": "event_id", "partnership": "mou_id"}.get(key, "channel_id")
    deals = _acquire_scoped_deals(user)
    by_rec = {}
    for d in deals:
        rid = str(d.get(field) or "").strip()
        if rid:
            by_rec.setdefault(rid, []).append(d)

    def _val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    records = listing(key)
    total_spent = total_leads = total_accounts = 0.0
    total_value = 0.0
    by_owner = {}
    by_stage = {}
    rows = []
    for r in records:
        got = by_rec.get(r["id"], [])
        won = [d for d in got if str(d.get("stage") or "") == CLOSED_WON]
        spent = float(r.get("spent_kes") or r.get("budget_kes") or 0)
        val = round(sum(_val(d) for d in won), 2)
        total_spent += spent
        total_leads += len(got)
        total_accounts += len(won)
        total_value += val
        owner = r.get("owner") or "Unassigned"
        o = by_owner.setdefault(owner, {"owner": owner, "records": 0,
                                        "spent": 0.0, "leads": 0,
                                        "accounts": 0, "value": 0.0})
        o["records"] += 1
        o["spent"] += spent
        o["leads"] += len(got)
        o["accounts"] += len(won)
        o["value"] += val
        for d in got:
            st = str(d.get("stage") or "Unknown")
            by_stage[st] = by_stage.get(st, 0) + 1
        rows.append({"id": r["id"], "name": r["name"], "owner": owner,
                     "spent": spent, "leads": len(got), "accounts": len(won),
                     "value": val,
                     "cost_per_account": round(spent / len(won), 2) if won else None})

    for o in by_owner.values():
        o["spent"] = round(o["spent"], 2)
        o["value"] = round(o["value"], 2)

    # Ranked by cost per account, cheapest first - the question a head of unit
    # actually asks. Records with no accounts are EXCLUDED from the ranking
    # rather than sorted last at infinity: "no conversions yet" and "expensive"
    # are different findings and should not share a row position.
    ranked = sorted([r for r in rows if r["cost_per_account"] is not None],
                    key=lambda r: r["cost_per_account"])
    return {
        "channel": c,
        "totals": {
            "records": len(records),
            "spent": round(total_spent, 2),
            "leads": int(total_leads),
            "accounts": int(total_accounts),
            "value": round(total_value, 2),
            "conversion_pct": (round(total_accounts / total_leads * 100, 1)
                               if total_leads else None),
            "cost_per_account": (round(total_spent / total_accounts, 2)
                                 if total_accounts else None),
            "roi_pct": (round((total_value - total_spent) / total_spent * 100, 1)
                        if (c.get("supports_roi") and total_spent) else None),
            "supports_roi": bool(c.get("supports_roi")),
        },
        "by_owner": sorted(by_owner.values(), key=lambda o: -o["value"]),
        "by_stage": [{"stage": k, "count": v} for k, v in
                     sorted(by_stage.items(), key=lambda kv: -kv[1])],
        "best": ranked[:5],
        "no_conversions": [r for r in rows if r["cost_per_account"] is None
                           and r["leads"] > 0],
        "untagged": [r for r in rows if r["leads"] == 0],
    }


'''

TS_NEW = r'''export interface ChannelAnalytics {
  channel: OriginChannel;
  totals: {
    records: number; spent: number; leads: number; accounts: number;
    value: number; conversion_pct: number | null;
    cost_per_account: number | null; roi_pct: number | null;
    supports_roi: boolean;
  };
  by_owner: { owner: string; records: number; spent: number; leads: number;
              accounts: number; value: number }[];
  by_stage: { stage: string; count: number }[];
  best: { id: string; name: string; owner: string; spent: number;
          leads: number; accounts: number; value: number;
          cost_per_account: number | null }[];
  no_conversions: { id: string; name: string; leads: number }[];
  untagged: { id: string; name: string }[];
}
export async function fetchChannelAnalytics(key: string): Promise<ChannelAnalytics> {
  return getJson<ChannelAnalytics>(`/channels/${encodeURIComponent(key)}/analytics`);
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
  type OriginChannel, type ChannelRecord, type ChannelAnalytics,
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
    })();
    return () => { alive = false; };
  }, [tab, key]);

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
      <div className="mx-auto max-w-7xl p-6">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {channels.map((c) => (
            <button
              key={c.key}
              type="button"
              onClick={() => setKey(c.key)}
              className={'rounded-full px-3 py-1.5 text-xs font-medium ' + (
                c.key === key
                  ? 'bg-[#0082BB] text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200')}
            >
              {c.label}
            </button>
          ))}
        </div>

        {current?.note && (
          <p className="mb-3 text-xs text-gray-500">{current.note}</p>
        )}

        <div className="mb-4 flex gap-4 border-b border-gray-200">
          {(['listing', 'pipeline', 'analytics'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={'-mb-px border-b-2 px-1 pb-2 text-sm capitalize ' + (
                t === tab
                  ? 'border-[#0082BB] font-semibold text-[#0082BB]'
                  : 'border-transparent text-gray-500 hover:text-gray-700')}
            >
              {t}
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
                    <input className={inp} value={form.owner}
                           onChange={(e) => setForm({ ...form, owner: e.target.value })} />
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
                <p className="py-8 text-center text-sm text-gray-400">
                  No deals are tagged to this channel yet.
                </p>
              )}
              {an && an.by_stage.length > 0 && (
                <div className="space-y-2">
                  {an.by_stage.map((s2) => {
                    const top = an.by_stage[0]?.count || 1;
                    return (
                      <div key={s2.stage} className="flex items-center gap-3">
                        <div className="w-52 shrink-0 truncate text-xs text-gray-600"
                             title={s2.stage}>{s2.stage}</div>
                        <div className="h-5 flex-1 overflow-hidden rounded bg-gray-100">
                          <div className="h-full rounded bg-[#0082BB]"
                               style={{ width: `${Math.max(4, (s2.count / top) * 100)}%` }} />
                        </div>
                        <div className="w-10 shrink-0 text-right text-xs tabular-nums text-gray-700">
                          {s2.count}
                        </div>
                      </div>
                    );
                  })}
                </div>
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
            print("ABORT: %s not found - apply patch_ch2_channels_page.py first." % p)
            return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if "/api/channels/{key}/analytics" in api:
        print("ABORT: the analytics endpoint already exists - CH3 looks applied.")
        return 1
    if API_ANCHOR not in api:
        print("ABORT: apply patch_ch2_channels_page.py first.")
        return 1
    if ts.count(TS_ANCHOR) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(TS_ANCHOR))
        return 1

    api = api.replace(API_ANCHOR, ENDPOINT + API_ANCHOR, 1)
    ts = ts.replace(TS_ANCHOR, TS_NEW + TS_ANCHOR, 1)
    print("  ok  analytics endpoint and client")

    # Deals must be read once.
    if ENDPOINT.count("_acquire_scoped_deals") != 1:
        print("ABORT: deals are read %d times in analytics."
              % ENDPOINT.count("_acquire_scoped_deals"))
        return 1
    # "No conversions" must not be ranked as if it were expensive.
    if 'r["cost_per_account"] is not None' not in ENDPOINT:
        print("ABORT: records with no accounts are being ranked - 'no")
        print("       conversions yet' and 'expensive' are different findings.")
        return 1
    if '"no_conversions"' not in ENDPOINT or '"untagged"' not in ENDPOINT:
        print("ABORT: the endpoint does not separate untagged from unconverted.")
        return 1
    # ROI stays honest.
    if 'c.get("supports_roi") and total_spent' not in ENDPOINT:
        print("ABORT: a channel with no budget would be shown a return.")
        return 1
    # Analytics must not load on the listing tab.
    if "if (tab === 'listing') return;" not in PAGE_SRC:
        print("ABORT: analytics would load on the listing tab, reading every")
        print("       deal for a page most people open for the listing.")
        return 1
    for t in ("'listing'", "'pipeline'", "'analytics'"):
        if t not in PAGE_SRC:
            print("ABORT: the page is missing the %s tab." % t)
            return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if PAGE_SRC.count(op) != PAGE_SRC.count(cl):
            print("ABORT: page unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: one read, honest ranking, lazy analytics")

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
    print("Origin Channels now has Listing / Pipeline / Analytics for all three.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
