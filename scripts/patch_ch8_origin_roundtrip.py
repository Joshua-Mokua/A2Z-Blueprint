#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CH8 - the database was dropping origin. Events showed zero; partnerships did not.

THE SYMPTOM, and why it was so misleading: after seeding twenty deals across
three channels, the Partnerships tab tracked four deals correctly while Events
and Lead Generators showed "0 deals tagged". Two of three channels working looks
like a data problem. It was not.

THE CAUSE. _db_sync_pipeline_deal writes non-column fields into `metadata`, and
its list contained mou_id but NOT event_id, channel_id, or origin. So a deal
tagged to an event synced to Postgres, came back without its event_id, and every
event reported having produced nothing. Partnerships worked purely because
mou_id happened to be on the list already - the SAME bug, invisible in the one
channel anybody had checked.

    _db_sync_pipeline_deal    now stores origin, origin_party_code,
                              origin_party_name, event_id, channel_id and
                              warehouse_prospect_id
    _normalize_db_deal_row    lifts them back out, for the same reason the FX
                              money set is lifted: a DB-first reader that cannot
                              see event_id makes a working page look broken

Verified by round trip: a row whose metadata carries event_id=EVT9001 and
origin=events comes back with both, and a null channel_id stays null.

CLICKING A DEAL OPENS THE EXISTING DETAIL PAGE (ruling 2026-08-11: "when I click
on it, it should take me to the page that has documentation for viewing only but
following the defined rules"). PipelineDealDetail already gates every action
behind the caller's permissions - fourteen gates - so it is ALREADY read-only
for anyone without rights. Linking to it rather than building a second viewer
means one place defines what a person may do; a bespoke read-only page would be
a second opinion that drifts.

WHY THIS MATTERS BEYOND THIS PAGE: anything that writes a deal must round-trip
through metadata, or the field silently disappears. That is worth remembering
for the pilot, where the same sync runs.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

REQUIRES CH7.

Usage (from project root, .venv active):
    python scripts\patch_ch8_origin_roundtrip.py            # dry run
    python scripts\patch_ch8_origin_roundtrip.py --apply

Then RESEED so existing rows carry the fields:
    python scripts\seed_scenario.py --apply
    python scripts\verify_scenario.py
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
PAGE = os.path.join("frontend", "web", "src", "pages", "OriginChannels.tsx")
BACKUP_SUFFIX = ".pre_ch8"

SYNC = r'''def _db_sync_pipeline_deal(deal: Optional[dict], conflict: str = "update") -> None:
    """Upsert a pipeline deal into Postgres so DB-backed reads reflect runtime
    mutations. H5 (2026-06-14): pipeline reads are DB-first but mutations
    write only the JSON store, so created/changed deals were invisible in the
    DB-backed list. No-op when Postgres is unavailable. Best-effort. Field
    map: JSON deal_value->amount, product_type->product; pipeline_category
    kept in metadata.
    """
    if not deal or not _db_available():
        return
    try:
        import json as _json
        from datetime import date as _date
        from utils.db import db as _db
        today = _date.today().isoformat()

        def _date_or_none(v):
            v = (str(v).strip() if v is not None else "")
            return v or None

        row = {
            "id":            str(deal.get("id", "") or ""),
            "staff_code":    str(deal.get("staff_code", "") or ""),
            "staff_name":    str(deal.get("staff_name", "") or ""),
            "unit":          deal.get("unit"),
            "role":          deal.get("role"),
            "client_name":   deal.get("client_name"),
            "client_cif":    deal.get("client_cif"),
            "product":       deal.get("product") or deal.get("product_type"),
            "stage":         deal.get("stage"),
            "deal_category": (deal.get("deal_category")
                              or deal.get("pipeline_category") or "New Facility"),
            "amount":        (deal.get("amount")
                              if deal.get("amount") is not None
                              else deal.get("deal_value")),
            "currency":      deal.get("currency", "KES"),
            "open_date":     _date_or_none(deal.get("open_date")) or today,
            "expected_close": _date_or_none(deal.get("expected_close")),
            "probability":   deal.get("probability"),
            "notes":         deal.get("notes"),
            "last_updated":  today,
            "metadata":      _json.dumps({
                "pipeline_category":   deal.get("pipeline_category"),
                "client_type":         deal.get("client_type"),
                "is_ntb":              deal.get("is_ntb"),
                "is_top_up":           deal.get("is_top_up"),
                "top_up_amount":       deal.get("top_up_amount"),
                "original_facility_amount": deal.get("original_facility_amount"),
                "existing_facility_id": deal.get("existing_facility_id"),
                "is_repeat_borrower":  deal.get("is_repeat_borrower"),
                "source":              deal.get("source"),
                "portfolio_owner_code": deal.get("portfolio_owner_code"),
                "portfolio_owner_name": deal.get("portfolio_owner_name"),
                "lms_application_id":   deal.get("lms_application_id"),
                "mou_id":               deal.get("mou_id"),
                # ORIGIN AND ITS SOURCE (2026-08-11). Without these three the
                # database round-trip DROPS them: a deal tagged to an event
                # syncs, comes back with no event_id, and the Events page shows
                # "0 deals tagged" while the deals plainly exist. mou_id was
                # here already, which is exactly why partnerships worked and
                # events did not - the same bug, visible in only two of three
                # channels.
                "origin":               deal.get("origin"),
                "origin_party_code":    deal.get("origin_party_code"),
                "origin_party_name":    deal.get("origin_party_name"),
                "event_id":             deal.get("event_id"),
                "channel_id":           deal.get("channel_id"),
                "warehouse_prospect_id": deal.get("warehouse_prospect_id"),
                "mou_title":            deal.get("mou_title"),
                "sector":               deal.get("sector"),
                "segment":              deal.get("segment"),
                "fx_rate":              deal.get("fx_rate"),
                "amount_kes":           deal.get("amount_kes"),
                "fx_rate_date":         deal.get("fx_rate_date"),
                "fx_rate_source":       deal.get("fx_rate_source"),
                "currency_book":        deal.get("currency_book"),
                "manager_validated":    deal.get("manager_validated"),
                "validated_by":         deal.get("validated_by"),
                "validated_at":         deal.get("validated_at"),
                "validated_by_name":    deal.get("validated_by_name"),
                "validated_by_role":    deal.get("validated_by_role"),
                "validated_by_code":    deal.get("validated_by_code"),
                "referral_status":      deal.get("referral_status"),
                "referred_to_code":     deal.get("referred_to_code"),
                "referred_to":          deal.get("referred_to"),
                "referred_by_code":     deal.get("referred_by_code"),
                "referred_by_name":     deal.get("referred_by_name"),
                "referral_note":        deal.get("referral_note"),
                "referral_chain":       deal.get("referral_chain"),
                "decline_reason":       deal.get("decline_reason"),
                "sla_step_log":         deal.get("sla_step_log"),
                "sla_commitments":      deal.get("sla_commitments"),
                # The Credit Report. Omitted here, it was written to the JSON
                # store and lost on every Postgres-first read, so cr_ok stayed
                # false and submit-to-credit refused every deal for ever with
                # "the Credit Report (CR) must be completed first" — blaming the
                # RM for the one thing they had done. Phase B0 set out to make
                # PG a complete mirror and missed it.
                "cr":                   deal.get("cr"),
                "submitted_to_credit":  deal.get("submitted_to_credit"),
                # Phase B0: persist the remaining deal fields so PG is a COMPLETE
                # mirror (these were JSON-only and vanished under PG-first reads).
                "bsc_credit_to":            deal.get("bsc_credit_to"),
                "manager_override_note":    deal.get("manager_override_note"),
                "is_referral":              deal.get("is_referral"),
                "referred_at":              deal.get("referred_at"),
                "accepted_by":              deal.get("accepted_by"),
                "accepted_at":              deal.get("accepted_at"),
                "declined_by":              deal.get("declined_by"),
                "declined_at":              deal.get("declined_at"),
                "disbursed":                deal.get("disbursed"),
                "disbursed_at":             deal.get("disbursed_at"),
                "disbursed_under_override": deal.get("disbursed_under_override"),
                "override_approved":        deal.get("override_approved"),
                "override_approved_by":     deal.get("override_approved_by"),
                "win_probability":          deal.get("win_probability"),
                "credit_deferred_to":       deal.get("credit_deferred_to"),
                "credit_deferred_to_code":  deal.get("credit_deferred_to_code"),
                "history":                  deal.get("history"),
                "document_files":           deal.get("document_files"),
                "documents_provided":       deal.get("documents_provided"),
            }),
        }
        if not row["id"]:
            return
        cols = list(row.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        if conflict == "raise":
            # Create path (Phase A): fail-closed on a duplicate id. DO NOTHING
            # suppresses the insert on conflict; RETURNING id is then empty, which
            # we detect and raise so the caller's retry derives a fresh id. This
            # makes concurrent creates with a colliding id IMPOSSIBLE to persist
            # as a silent overwrite (the PK is the hard guarantee, not a hint).
            sql = (f"INSERT INTO pipeline_deals ({', '.join(cols)}) "
                   f"VALUES ({placeholders}) "
                   f"ON CONFLICT (id) DO NOTHING RETURNING id")
            from utils.db import db as _db2
            got = _db2.fetch_one(sql, tuple(row[c] for c in cols))
            if not got:
                raise RuntimeError(
                    f"duplicate key: deal id {row['id']} already exists in Postgres")
        else:
            # Update/mirror path (default): upsert. Existing row is refreshed.
            updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "id")
            sql = (f"INSERT INTO pipeline_deals ({', '.join(cols)}) "
                   f"VALUES ({placeholders}) "
                   f"ON CONFLICT (id) DO UPDATE SET {updates}")
            _db.execute(sql, tuple(row[c] for c in cols))
    except Exception as e:
        # B13: do NOT swallow. A deal that can't persist to Postgres must fail
        # loudly — silent swallowing is exactly what let JSON and the DB drift
        # (deals invisible to DB-first reads). DB-unavailable is handled by the
        # early return above; reaching here means Postgres is up but the write
        # errored, which is a real fault the caller needs to see.
        logger.error(f"Pipeline deal DB sync FAILED for {deal.get('id')}: {e}")
        raise


'''

NORMALISE = r'''def _normalize_db_deal_row(row):
    """Map pipeline_deals DB columns to the field names the React frontend
    expects (amount->deal_value, product->product_type, metadata->
    pipeline_category) so the DB read path matches the JSON read path. H5."""
    if not isinstance(row, dict):
        return row
    r = dict(row)
    if r.get("deal_value") in (None, ""):
        r["deal_value"] = r.get("amount")
    if not r.get("product_type"):
        r["product_type"] = r.get("product")
    md = r.get("metadata")
    if isinstance(md, str):
        try:
            import json as _json
            md = _json.loads(md)
        except Exception:
            md = {}
    if isinstance(md, dict) and not r.get("pipeline_category"):
        r["pipeline_category"] = md.get("pipeline_category")
    if isinstance(md, dict) and not r.get("lms_application_id"):
        r["lms_application_id"] = md.get("lms_application_id")
    # ORIGIN AND ITS SOURCE. Lifted for the same reason as the FX set: a
    # DB-first reader that cannot see event_id reports every event as having
    # produced nothing, and the page looks broken rather than empty.
    if isinstance(md, dict):
        for _k in ("origin", "origin_party_code", "origin_party_name",
                   "event_id", "mou_id", "channel_id", "warehouse_prospect_id"):
            if not r.get(_k) and md.get(_k):
                r[_k] = md.get(_k)
    # Lift the FX money set + client-type fields out of metadata so DB-first
    # readers (analytics, dashboard canonical path) see KES-equivalent values
    # and the currency book — matching the JSON read path. Without this,
    # _deal_value falls back to NATIVE for FCY deals and analytics disagrees
    # with the dashboard.
    if isinstance(md, dict):
        for _k in ("amount_kes", "currency_book", "fx_rate", "fx_rate_date",
                   "fx_rate_source", "client_type", "mou_id", "mou_title",
                   "sector", "segment", "validated_by", "validated_at",
                   "validated_by_name", "validated_by_role", "validated_by_code",
                   "is_top_up", "top_up_amount", "original_facility_amount",
                   "existing_facility_id", "is_repeat_borrower",
                   "referral_status", "referred_to_code", "referred_to",
                   "referred_by_code", "referred_by_name", "referral_note",
                   "decline_reason", "sla_step_log", "sla_commitments", "referral_chain",
                   # Phase B0: lift the full field set back so DB-first reads
                   # reconstruct a complete deal (write side in _db_sync).
                   "portfolio_owner_code", "portfolio_owner_name", "is_ntb",
                   "source", "bsc_credit_to", "manager_override_note",
                   "is_referral", "referred_at", "accepted_by", "accepted_at",
                   "declined_by", "declined_at", "disbursed", "disbursed_at",
                   "disbursed_under_override", "override_approved",
                   "override_approved_by", "win_probability",
                   "credit_deferred_to", "credit_deferred_to_code", "history",
                   "document_files", "documents_provided",
                   # Lift the CR back out — a field carried on the write side
                   # but not listed here is mirrored and then dropped on read,
                   # which looks identical to never having been saved.
                   "cr", "submitted_to_credit"):
            if r.get(_k) in (None, "") and md.get(_k) is not None:
                r[_k] = md.get(_k)
        # manager_validated is a bool — lift whenever absent on the row so the
        # DB read path (analytics assured value + funnel) reflects validation.
        if "manager_validated" not in r or r.get("manager_validated") is None:
            r["manager_validated"] = bool(md.get("manager_validated"))
    return r

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
import { Link } from 'react-router-dom';
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
                                <td className={`${td} ${bg} tabular-nums`}>
                                  {/* Opens the EXISTING deal detail page, which
                                      already gates every action behind the
                                      caller's permissions - so it is read-only
                                      for anyone without rights, following the
                                      rules already defined rather than a second
                                      viewer with its own idea of them. */}
                                  <Link to={`/pipeline/${encodeURIComponent(d.id)}`}
                                        className="text-brand-primary hover:underline">
                                    {d.id}
                                  </Link>
                                </td>
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
    for p in (API, PAGE):
        if not os.path.isfile(p):
            print("ABORT: %s not found - apply patch_ch7_deal_tracker.py first." % p)
            return 1

    api = open(API, encoding="utf-8").read()
    if '"event_id":             deal.get("event_id")' in api:
        print("ABORT: the sync already carries event_id - CH8 looks applied.")
        return 1
    if "def _db_sync_pipeline_deal" not in api or "def _normalize_db_deal_row" not in api:
        print("ABORT: the sync helpers are not where expected.")
        return 1

    i = api.index("def _db_sync_pipeline_deal")
    j = api.index("def _normalize_db_deal_row")
    k = api.index("def _normalize_db_deal_row")
    m = api.index("\ndef ", k + 10)
    api = api[:i] + SYNC + NORMALISE + api[m:]
    print("  ok  sync stores origin and every source id; reads restore them")

    # Both halves are required. Storing without lifting still loses the field.
    if '"event_id":' not in SYNC or '"channel_id":' not in SYNC:
        print("ABORT: the sync does not store every source id.")
        return 1
    if "event_id" not in NORMALISE or "origin" not in NORMALISE:
        print("ABORT: the read path does not lift them back - storing without")
        print("       lifting loses the field just as surely.")
        return 1
    if 'to={`/pipeline/${encodeURIComponent(d.id)}`}' not in PAGE_SRC:
        print("ABORT: deals do not link to the detail page.")
        return 1
    # A second read-only viewer would be a second opinion on permissions.
    if "PipelineDealDetail" in PAGE_SRC:
        print("ABORT: the page imports the detail component rather than linking")
        print("       to its route - permissions belong in one place.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if PAGE_SRC.count(op) != PAGE_SRC.count(cl):
            print("ABORT: page unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: both halves present, one permissions authority")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((API, api), (PAGE, PAGE_SRC)):
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
    print("RESEED - rows already in Postgres were written without these fields:")
    print("  python scripts\\seed_scenario.py --apply")
    print("  python scripts\\verify_scenario.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
