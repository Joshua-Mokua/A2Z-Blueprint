#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CH2 - Origin Channels. ONE sidebar entry, three channels, one question.

RULING (2026-08-11): "we can have them as one ... I am avoiding a scenario where
we will have so many items on the sidebar. When one clicks they can select from
the three."

Events, Partnerships and Lead Generators all ask: what did we spend, what did it
produce, was it worth it. Three sidebar entries would be three doors into one
question. So one page, a three-way switcher, and the sidebar's "Events" entry
becomes "Origin Channels" - it does not grow.

CREATE IS A BUTTON, NOT A TAB - my one change to the proposed layout. Create ·
Listing · Pipeline · Analytics across three channels is twelve views, and
"create" is not a view anyone returns to; it is an action. The form opens in
place above the table and closes on success.

THE FORM ADAPTS TO THE CHANNEL. Budget only appears where the channel
`supports_roi`, because asking for a partnership's budget invites someone to
type one, and a made-up budget produces a made-up return. The party field is
labelled from config - "Partner" for events, "Generator" for lead generators.

OWNERSHIP IS ASKED PROPERLY: "Belongs to - a unit / a branch", then which one.
Your customer-dinner case is a first-class branch-owned event rather than
something squeezed into a department field.

WHO MAY CREATE: anyone, for their OWN unit or branch; admins for any. The check
is deliberately light - a sponsorship recorded against the wrong unit is a
correction, not a breach - but it stops a branch quietly booking spend against a
department's budget.

"MINE" narrows to what the caller owns. Everyone can still SEE every channel: a
sponsorship is bank money, and hiding it from other units helps nobody.

ATTRIBUTION IS COMPUTED ONCE over the caller's scoped deals and bucketed by
record id - not per record. Reading the deal store fifty times to render one
page is the per-row cost that produced a 504 on this system before.

"NOTHING TAGGED" IS NOT "THE CHANNEL FAILED", and the page says so rather than
letting fifty zero rows read as a verdict.

The warehouse deliberately stays OUT: it is a shared shelf with claim mechanics
and no budget, so placing it beside these would imply a return question it
cannot answer.

Verified: tsc --noEmit clean, vite build clean.

REQUIRES CH1 and EV2.

Usage (from project root, .venv active):
    python scripts\patch_ch2_channels_page.py            # dry run
    python scripts\patch_ch2_channels_page.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
PAGE = os.path.join("frontend", "web", "src", "pages", "OriginChannels.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
APP = os.path.join("frontend", "web", "src", "App.tsx")
SB = os.path.join("frontend", "web", "src", "components", "Sidebar.tsx")
BACKUP_SUFFIX = ".pre_ch2"

API_ANCHOR = '@app.get("/api/pipeline/events")'
TS_ANCHOR = "export interface PipelineEvent {"

ENDPOINTS = r'''@app.get("/api/channels")
def channels_list(user: dict = Depends(get_current_user)):
    """The configured channels, for the switcher."""
    from utils.origin_channels import channels
    return {"channels": channels()}


@app.get("/api/channels/{key}/records")
def channels_records(key: str, active_only: bool = False, mine: bool = False,
                     user: dict = Depends(get_current_user)):
    """Records for a channel, each with what the DEALS say it produced.

    Attribution is computed ONCE over the caller's scoped deals and bucketed by
    record id - not per record. Reading the deal store fifty times to render one
    page is the per-row cost that produced a 504 on this system before.

    `mine` narrows to the caller's own unit or branch. Everyone can SEE every
    channel - a sponsorship is bank money and hiding it helps nobody - but
    "mine" is what a head of unit actually opens the page for.
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

    my_unit = my_branch = ""
    if mine:
        try:
            from utils.org_validator import unit_for_role
            from utils.core import UserManager as _UM
            rec = (_UM().users or {}).get(str(user.get("username", "") or "")) or {}
            my_unit = unit_for_role(str(rec.get("role") or "")) or ""
            my_branch = str(rec.get("branch") or "")
        except Exception as exc:
            logger.debug("channel scope: %s", exc)

    rows = []
    for r in listing(key, bool(active_only)):
        if mine and my_unit and r["owner_type"] == "unit" and r["owner"] != my_unit:
            continue
        if mine and my_branch and r["owner_type"] == "branch" and r["owner"] != my_branch:
            continue
        got = by_rec.get(r["id"], [])
        won = [d for d in got if str(d.get("stage") or "") == CLOSED_WON]
        spent = r.get("spent_kes") or r.get("budget_kes") or 0
        won_value = round(sum(_val(d) for d in won), 2)
        roi = None
        if c.get("supports_roi") and spent:
            roi = round((won_value - spent) / spent * 100, 1)
        rows.append({**r, "leads": len(got), "accounts": len(won),
                     "won_value": won_value, "roi_pct": roi,
                     "supports_roi": bool(c.get("supports_roi"))})
    return {"channel": c, "records": rows,
            "tagged_deals": sum(len(v) for v in by_rec.values())}


@app.post("/api/channels/{key}/records", status_code=201)
def channels_create(key: str, payload: dict = Body(default_factory=dict),
                    user: dict = Depends(get_current_user)):
    """Create a channel record.

    Anyone may create one for THEIR OWN unit or branch; admins for any. The
    check is deliberately light - a sponsorship recorded against the wrong unit
    is a correction, not a breach - but it stops a branch quietly booking spend
    against a department's budget.
    """
    from utils.origin_channels import create
    from utils.core import UserManager as _UM
    rec = (_UM().users or {}).get(str(user.get("username", "") or "")) or {}
    code = str(rec.get("staff_code") or user.get("username") or "")
    ot = str(payload.get("owner_type") or "").strip().lower()
    owner = str(payload.get("owner") or "").strip()

    if not (user.get("is_admin") or user.get("can_view_all")):
        try:
            from utils.org_validator import unit_for_role
            mine_unit = unit_for_role(str(rec.get("role") or "")) or ""
            mine_branch = str(rec.get("branch") or "")
        except Exception:
            mine_unit = mine_branch = ""
        if ot == "unit" and mine_unit and owner != mine_unit:
            raise HTTPException(
                status_code=403,
                detail="You can only create this for %s." % mine_unit)
        if ot == "branch" and mine_branch and owner != mine_branch:
            raise HTTPException(
                status_code=403,
                detail="You can only create this for %s." % mine_branch)

    try:
        out = create(
            key, name=str(payload.get("name", "") or ""),
            owner_type=ot, owner=owner, created_by=code,
            party=str(payload.get("party", "") or ""),
            branch=str(payload.get("branch", "") or ""),
            category=str(payload.get("category", "") or ""),
            start_date=str(payload.get("start_date", "") or ""),
            end_date=str(payload.get("end_date", "") or ""),
            budget_kes=float(payload.get("budget_kes") or 0),
            target_leads=float(payload.get("target_leads") or 0),
            target_accounts=float(payload.get("target_accounts") or 0),
            target_value_kes=float(payload.get("target_value_kes") or 0),
            notes=str(payload.get("notes", "") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit("CHANNEL_CREATE", user, "%s %s %s" % (key, out["id"], out["name"]))
    return {"record": out}


'''

TS_NEW = r'''export interface OriginChannel {
  key: string; label: string; origin: string; store: string;
  supports_roi: boolean; party_label: string; note: string;
}
export interface ChannelRecord {
  id: string; channel: string; name: string; party: string;
  owner_type: string; owner: string; branch: string; category: string;
  start_date: string; end_date: string; status: string;
  budget_kes: number | null; spent_kes: number | null;
  target_leads: number | null; target_accounts: number | null;
  target_value_kes: number | null;
  leads: number; accounts: number; won_value: number;
  roi_pct: number | null; supports_roi: boolean;
}
export async function fetchChannels(): Promise<{ channels: OriginChannel[] }> {
  return getJson<{ channels: OriginChannel[] }>('/channels');
}
export async function fetchChannelRecords(
  key: string, activeOnly = false, mine = false,
): Promise<{ channel: OriginChannel; records: ChannelRecord[]; tagged_deals: number }> {
  const q = new URLSearchParams({ active_only: String(activeOnly), mine: String(mine) });
  return getJson<{ channel: OriginChannel; records: ChannelRecord[]; tagged_deals: number }>(
    `/channels/${encodeURIComponent(key)}/records?${q.toString()}`);
}
export async function createChannelRecord(
  key: string, body: Record<string, unknown>,
): Promise<{ record: ChannelRecord }> {
  return postJson<{ record: ChannelRecord }, Record<string, unknown>>(
    `/channels/${encodeURIComponent(key)}/records`, body);
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
  fetchChannels, fetchChannelRecords, createChannelRecord,
  type OriginChannel, type ChannelRecord,
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
import Events from './pages/Events';
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
                    <Route path="/pipeline/events"  element={<Events />} />
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
      { path: '/pipeline',        label: 'A2Z Sales Pro',        matchActive: (p) => p === '/pipeline' || (p.startsWith('/pipeline/') && !p.startsWith('/pipeline/queues') && !p.startsWith('/pipeline/events') && !p.startsWith('/pipeline/channels')) },
      { path: '/analytics',       label: 'Sales Pro Analytics',  matchActive: (p) => p.startsWith('/analytics') },
      { path: '/pipeline/queues', label: 'Manager Queues',       matchActive: (p) => p.startsWith('/pipeline/queues'), visibleFor: (m) => m },
      { path: '/pipeline/channels', label: 'Origin Channels',    matchActive: (p) => p.startsWith('/pipeline/channels') || p.startsWith('/pipeline/events') },
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
    for p in (API, APITS, APP, SB):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1
    if os.path.exists(PAGE):
        print("ABORT: %s already exists - CH2 looks applied." % PAGE)
        return 1
    if not os.path.isfile(os.path.join("utils", "origin_channels.py")):
        print("ABORT: apply patch_ch1_origin_channels.py first.")
        return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if '"/api/channels"' in api:
        print("ABORT: the channels endpoints already exist.")
        return 1
    if API_ANCHOR not in api:
        print("ABORT: apply patch_ev2_events_page.py first.")
        return 1
    if ts.count(TS_ANCHOR) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(TS_ANCHOR))
        return 1

    api = api.replace(API_ANCHOR, ENDPOINTS + API_ANCHOR, 1)
    ts = ts.replace(TS_ANCHOR, TS_NEW + TS_ANCHOR, 1)
    print("  ok  channel endpoints and clients")

    # Attribution must not be per record.
    if ENDPOINTS.count("_acquire_scoped_deals") != 1:
        print("ABORT: deals are read %d times - attribution must be computed"
              % ENDPOINTS.count("_acquire_scoped_deals"))
        print("       once and bucketed, not per record.")
        return 1
    if '== CLOSED_WON' not in ENDPOINTS:
        print("ABORT: accounts are counted before closure.")
        return 1
    if 'c.get("supports_roi") and spent' not in ENDPOINTS:
        print("ABORT: a channel with no budget would be shown a return.")
        return 1
    # Budget must not be asked for where it is meaningless.
    if "current?.supports_roi && (" not in PAGE_SRC:
        print("ABORT: the create form asks for a budget on every channel - a")
        print("       made-up partnership budget produces a made-up return.")
        return 1
    if "owner_type" not in PAGE_SRC:
        print("ABORT: the form does not ask whether the owner is a unit or a branch.")
        return 1
    # The sidebar must not grow.
    if SIDEBAR.count("Origin Channels") != 1 or "'Events'" in SIDEBAR:
        print("ABORT: the sidebar should have ONE Origin Channels entry and no")
        print("       separate Events entry.")
        return 1
    for name, blob in (("page", PAGE_SRC), ("app", APP_SRC), ("sidebar", SIDEBAR)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    print("  ok  post-checks: one read, closure-only, honest budget, one entry")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(PAGE, "w", encoding="utf-8", newline="").write(PAGE_SRC)
    print("CREATED %s" % PAGE)
    for path, content in ((API, api), (APITS, ts), (APP, APP_SRC), (SB, SIDEBAR)):
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
    print("Pipeline Intelligence > Origin Channels. The old /pipeline/events")
    print("route still works, so nothing bookmarked breaks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
