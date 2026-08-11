#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CH5 - Origin Channels made to look like the rest of the system.

RULING (2026-08-11): "may be what we need to do is the UI clean up like we did
for the manager queues, at least to bring colour and life to this page, and
analytics as well; let the contents cover the whole page not just the mid
section. I would like it to be uniform so that it does not seem like they are
two separate systems."

MATCHED TO MANAGER QUEUES, not invented afresh - which is the point:

    max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6    the exact shell
    px-4 py-2 border-b-2 border-brand-primary          the exact tab style
    brand-primary rather than a raw #0082BB            the switcher

Using brand tokens instead of hex matters beyond tidiness: a hard-coded colour
does not follow the BrandingProvider, so the page would stay Ecobank blue if the
palette ever changed and quietly become the odd one out.

A SUMMARY BAND above the tabs, so the page says something even before a single
deal is tagged - records, deals tagged, accounts won, and either committed spend
or expected volume depending on whether the channel has a budget. A page whose
only content is three variations of "nothing here" gives a reader no reason to
believe it will ever do anything.

THE EMPTY PIPELINE TAB NOW EXPLAINS ITSELF: it names the channel and says which
choice on the capture form will populate it. "No deals are tagged" states a
fact; it does not tell anyone what to do about it.

THE OLD EVENTS PAGE IS RETIRED. Its route still resolves - bookmarks keep
working - but renders Origin Channels. Two pages showing the same events with
different layouts is exactly how a product starts to feel like two systems,
which is what this ruling was about.

Verified: tsc --noEmit clean, vite build clean.

REQUIRES CH4.

Usage (from project root, .venv active):
    python scripts\patch_ch5_channels_ui.py            # dry run
    python scripts\patch_ch5_channels_ui.py --apply
"""
import os
import shutil
import sys

PAGE = os.path.join("frontend", "web", "src", "pages", "OriginChannels.tsx")
APP = os.path.join("frontend", "web", "src", "App.tsx")
EVENTS = os.path.join("frontend", "web", "src", "pages", "Events.tsx")
BACKUP_SUFFIX = ".pre_ch5"

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
    for p in (PAGE, APP):
        if not os.path.isfile(p):
            print("ABORT: %s not found - apply patch_ch3_channel_tabs.py first." % p)
            return 1

    cur = open(PAGE, encoding="utf-8").read()
    if "2xl:max-w-[1680px]" in cur:
        print("ABORT: the page is already widened - CH5 looks applied.")
        return 1

    # Must match the rest of the system, not invent a third style.
    if "max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6" not in PAGE_SRC:
        print("ABORT: the page shell does not match Manager Queues.")
        return 1
    if "border-brand-primary" not in PAGE_SRC or "bg-brand-primary" not in PAGE_SRC:
        print("ABORT: the page uses raw hex instead of brand tokens - it would")
        print("       not follow the BrandingProvider and would become the odd")
        print("       page out the moment the palette changed.")
        return 1
    if "Committed spend" not in PAGE_SRC or "Expected volume" not in PAGE_SRC:
        print("ABORT: the summary band does not adapt to whether the channel")
        print("       has a budget.")
        return 1
    if "import Events from" in APP_SRC:
        print("ABORT: App still imports the retired Events page.")
        return 1
    if "/pipeline/events" not in APP_SRC:
        print("ABORT: the old events route was dropped - bookmarks would 404.")
        return 1
    for name, blob in (("page", PAGE_SRC), ("app", APP_SRC)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    print("  ok  shell, tokens, adaptive band, route preserved")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((PAGE, PAGE_SRC), (APP, APP_SRC)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)
    if os.path.exists(EVENTS):
        shutil.copy2(EVENTS, EVENTS + BACKUP_SUFFIX)
        os.remove(EVENTS)
        print("REMOVED %s  (superseded; its route now renders Origin Channels)"
              % EVENTS)

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
