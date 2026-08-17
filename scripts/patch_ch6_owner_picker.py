#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CH6 - the owner is PICKED, not typed. Fixes a defect CH2 shipped.

CH2's create form asked the user to TYPE which unit owns a channel. The value
has to match a unit name exactly - "Director Consumer & Commercial Banking
(CCB)" - and anything else produces a record owned by a unit nobody has, which
is invisible to every unit view and to the "Mine" filter.

This is not hypothetical. The lead-generator seeder aborted the same morning for
exactly this reason: it named "Head of Consumer", which had stopped being a unit
hours earlier when it was re-parented under CCB. If a script written that day
could get the name wrong, a person typing it under time pressure certainly will.

    GET /api/channels/owners     the real units (with readable labels), the
                                 real branches, and the CALLER'S OWN unit and
                                 branch

THE COMMON CASE NEEDS NO CHOOSING: the form preselects the caller's own unit, so
recording something for your own department is one less decision.

NON-ADMINS SEE THEIR OWN OWNER, LOCKED. The server already refused a mismatched
owner with a 403; showing an open list and then rejecting the choice would be a
worse experience than not offering it. Admins keep the full list.

IT DEGRADES RATHER THAN BLOCKS. If the lookup fails the field falls back to a
text box saying so. Blocking creation because a dropdown would not load is worse
than allowing a typo that can be corrected.

Verified: tsc --noEmit clean, vite build clean.

REQUIRES CH5.

Usage (from project root, .venv active):
    python scripts\patch_ch6_owner_picker.py            # dry run
    python scripts\patch_ch6_owner_picker.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
PAGE = os.path.join("frontend", "web", "src", "pages", "OriginChannels.tsx")
BACKUP_SUFFIX = ".pre_ch6"

API_ANCHOR = '@app.get("/api/channels/{key}/records")'
TS_ANCHOR = "export async function fetchChannels()"

ENDPOINT = r'''@app.get("/api/channels/owners")
def channels_owners(user: dict = Depends(get_current_user)):
    """The units and branches a channel can belong to, plus the caller's own.

    EXISTS BECAUSE TYPING IS NOT AN OPTION. The owner must match a unit name
    EXACTLY - "Director Consumer & Commercial Banking (CCB)" - and a free-text
    box guarantees mismatches that make a record invisible to every unit view.
    The same class of failure aborted the lead-generator seeder when a
    hardcoded unit name went stale.

    `mine` tells the form what to preselect, so the common case - recording
    something for your own unit - needs no choosing at all.
    """
    units = branches = []
    try:
        from utils.org_validator import md_reporting_roles, unit_label
        units = [{"value": u, "label": unit_label(u)}
                 for u in sorted(md_reporting_roles() or [])]
    except Exception as exc:
        logger.warning("channel owners: units unavailable: %s", exc)
    try:
        from utils.config import load_org_config
        br = (load_org_config() or {}).get("branches") or []
        if isinstance(br, dict):
            br = list(br.values())
        branches = [{"value": str(b.get("name") or ""),
                     "label": str(b.get("name") or "")}
                    for b in br if isinstance(b, dict) and b.get("name")]
        branches.sort(key=lambda x: x["label"])
    except Exception as exc:
        logger.warning("channel owners: branches unavailable: %s", exc)

    mine_unit = mine_branch = ""
    try:
        from utils.core import UserManager as _UM
        from utils.org_validator import unit_for_role
        rec = (_UM().users or {}).get(str(user.get("username", "") or "")) or {}
        mine_unit = unit_for_role(str(rec.get("role") or "")) or ""
        mine_branch = str(rec.get("branch") or "")
    except Exception as exc:
        logger.debug("channel owners: caller scope: %s", exc)

    return {"units": units, "branches": branches,
            "mine": {"unit": mine_unit, "branch": mine_branch},
            "is_admin": bool(user.get("is_admin") or user.get("can_view_all"))}


'''

TS_NEW = r'''export interface ChannelOwners {
  units: { value: string; label: string }[];
  branches: { value: string; label: string }[];
  mine: { unit: string; branch: string };
  is_admin: boolean;
}
export async function fetchChannelOwners(): Promise<ChannelOwners> {
  return getJson<ChannelOwners>('/channels/owners');
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
  fetchChannelOwners,
  type OriginChannel, type ChannelRecord, type ChannelAnalytics,
  type ChannelOwners,
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
            print("ABORT: %s not found - apply patch_ch5_channels_ui.py first." % p)
            return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if "/api/channels/owners" in api:
        print("ABORT: the owners endpoint already exists - CH6 looks applied.")
        return 1
    if API_ANCHOR not in api:
        print("ABORT: apply patch_ch2_channels_page.py first.")
        return 1
    if ts.count(TS_ANCHOR) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(TS_ANCHOR))
        return 1

    api = api.replace(API_ANCHOR, ENDPOINT + API_ANCHOR, 1)
    ts = ts.replace(TS_ANCHOR, TS_NEW + TS_ANCHOR, 1)
    print("  ok  owners endpoint and client")

    # The whole point is that the owner is chosen from real values.
    if "<select className={inp} value={form.owner}" not in PAGE_SRC:
        print("ABORT: the owner is still a free-text field.")
        return 1
    # But a failed lookup must not block creation.
    if "Could not load the list" not in PAGE_SRC:
        print("ABORT: there is no fallback when the owner list cannot load -")
        print("       blocking creation because a dropdown failed is worse")
        print("       than allowing a correctable typo.")
        return 1
    if "md_reporting_roles" not in ENDPOINT or "unit_label" not in ENDPOINT:
        print("ABORT: units are not read from the hierarchy with readable labels.")
        return 1
    if '"mine"' not in ENDPOINT:
        print("ABORT: the endpoint does not return the caller's own unit, so")
        print("       the form cannot preselect the common case.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if PAGE_SRC.count(op) != PAGE_SRC.count(cl):
            print("ABORT: page unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: picked not typed, preselected, degrades safely")

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
