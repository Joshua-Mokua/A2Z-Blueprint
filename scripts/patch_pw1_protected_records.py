#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
PW1 - edit freely while under validation; a password to touch a validated one.

RULING (2026-08-11): "one will only be able to edit items under validation. The
edit and delete on the validated, let them be restricted with a delete password
- for now set it as Pendo, but I will be seeing I control that from admin."

THE ASYMMETRY IS THE WHOLE DESIGN.

    UNDER VALIDATION   editing is OPEN. That set exists to be filled in, and a
                       password in front of backfilling would guarantee the
                       backfilling never happens.

    VALIDATED          editing AND deleting need the password. Somebody staked
                       their name on those details and people are being told to
                       prefer them, so changing one should be a deliberate act
                       rather than a stray click on a page they were browsing.

ADMIN RIGHTS SAY WHO MAY DELETE; THE PASSWORD SAYS THEY MEANT TO. An admin still
needs it on a validated record - the two answer different questions.

THE PASSWORD IS CONFIG, defaulting to "Pendo" as instructed, under
warehouse_protected_password - changeable from admin without a release. It is a
SPEED BUMP, not security: it stops an accident and does not pretend to stop
anybody determined. Worth being plain about that rather than implying otherwise.

EDITING A VALIDATED RECORD DOES NOT SILENTLY UN-VALIDATE IT. completeness()
already flags it stale, which tells the reader the truth - this changed after it
was checked - without throwing away the fact that somebody once checked it.
Quietly dropping the badge would lose that history.

Only EDITABLE_FIELDS can be written, so a crafted request cannot flip
`validated` or rewrite provenance through the edit route.

MEASURED: edit allowed under validation; after validating, edit and delete both
refused without the password and both allowed with it.

REQUIRES CM2.

Usage (from project root, .venv active):
    python scripts\patch_pw1_protected_records.py            # dry run
    python scripts\patch_pw1_protected_records.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "deals_warehouse.py")
API = os.path.join("utils", "api_warehouse.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
SHELF = os.path.join("frontend", "web", "src", "pages", "Warehouse.tsx")
DETAIL = os.path.join("frontend", "web", "src", "pages", "ProspectDetail.tsx")
BACKUP_SUFFIX = ".pre_pw1"

MOD_ANCHOR = "def validate_prospect(prospect_id: str, by_code: str, by_name: str) -> dict:"
TS_ANCHOR = "export async function validateProspect("

EDITING = r'''# ── EDITING, AND WHAT PROTECTS A VALIDATED RECORD ───────────────────────────
# RULING (2026-08-11): "one will only be able to edit items under validation.
# The edit and delete on the validated, let them be restricted with a delete
# password - for now set it as Pendo, but I will control that from admin."
#
# A VALIDATED RECORD IS THE USABLE SET. Somebody staked their name on it, and
# people are being told to prefer it - so changing one should take a deliberate
# act, not a stray click on a page somebody was browsing.
#
# UNDER VALIDATION, editing is open. That is the point of the working set: it
# exists to be filled in, and putting a password in front of backfilling would
# guarantee the backfilling never happens.
#
# THE PASSWORD IS CONFIG, not code. Defaulting to "Pendo" as instructed, and
# admin can change it without a release. It is a SPEED BUMP, not security: it
# stops an accident, and it is not pretending to stop anybody determined.
DEFAULT_PROTECTED_PASSWORD = "Pendo"

EDITABLE_FIELDS = (
    "name", "sector", "town", "physical_address", "contact_name",
    "contact_phone", "contact_email", "notes", "estimated_value",
    "registration_no", "established", "legal_form", "existing_banker",
    "website", "opportunity", "business_activity",
)


def protected_password() -> str:
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("warehouse_protected_password")
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception:
        pass
    return DEFAULT_PROTECTED_PASSWORD


def update_prospect(prospect_id: str, changes: dict, *, by_name: str = "",
                    password: str = "") -> dict:
    """Edit a prospect. A VALIDATED one needs the password.

    Editing a validated record does NOT silently un-validate it - completeness()
    already flags it stale, which tells the reader the truth (this changed after
    it was checked) without throwing away the fact that somebody once checked
    it. Quietly dropping the badge would lose that history.
    """
    pid = str(prospect_id or "").strip()
    with _lock:
        data = _read()
        rec = data.get(pid)
        if not rec:
            raise ValueError("That prospect no longer exists.")
        if rec.get("validated") and password != protected_password():
            raise PermissionError(
                "This is a validated record. Editing it needs the warehouse "
                "password - somebody vouched for these details.")

        applied = {}
        for k, v in (changes or {}).items():
            if k not in EDITABLE_FIELDS:
                continue
            rec[k] = v
            applied[k] = v
        if not applied:
            raise ValueError("Nothing to change.")
        if "name" in applied:
            rec["canonical_key"] = canonical_key(str(applied["name"]))
        rec["last_edited_at"] = datetime.now().isoformat(timespec="seconds")
        rec["last_edited_by"] = str(by_name or "")
        data[pid] = rec
        _write(data)
    return rec


'''

DELETE = r'''def delete(prospect_id: str, password: str = "") -> bool:
    """Remove a prospect entirely. ADMIN ONLY - the endpoint enforces that.

    RULING (2026-08-11): "for the admin I need to be able to delete an entry as
    a whole so that items like Mombasa that are not saccos I can delete."

    Distinct from archive() on purpose. ARCHIVE says "we looked at this and
    decided not to pursue it" and is worth keeping. DELETE says "this was never
    a business" - a county name, a street, a fragment of a table. Keeping those
    would leave the audit trail full of noise that teaches nobody anything.
    """
    pid = str(prospect_id or "").strip()
    with _lock:
        data = _read()
        if pid not in data:
            return False
        # A VALIDATED record needs the password even for an admin. Admin rights
        # say who MAY delete; the password says they meant to.
        if data[pid].get("validated") and password != protected_password():
            raise PermissionError(
                "This is a validated record. Deleting it needs the warehouse "
                "password.")
        del data[pid]
        _write(data)
    return True


'''

DELETE_EP = r'''@router.delete("/prospects/{prospect_id}")
def warehouse_delete(prospect_id: str, password: str = "",
                     user: dict = Depends(get_current_user)):
    """Delete a prospect outright. ADMIN ONLY.

    Archiving is for a business somebody judged not worth pursuing. Deletion is
    for a row that was never a business - a county name, a street, a fragment of
    a table that survived the import. Those do not belong in an audit trail.
    """
    from utils.deals_warehouse import delete, get
    if not _is_admin(user):
        raise HTTPException(status_code=403,
                            detail="Only an admin can delete a prospect. "
                                   "Archiving is available to whoever listed it.")
    rec = get(prospect_id)
    if not rec:
        raise HTTPException(status_code=404, detail="No such prospect.")
    try:
        # Admin rights say who MAY delete; the password says they meant to.
        delete(prospect_id, password=str(password or ""))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    audit_log("WAREHOUSE_DELETE", str(user.get("username", "") or ""),
              detail="%s %s" % (prospect_id, str(rec.get("name"))[:60]))
    return {"deleted": prospect_id}


'''

EDIT_EP = r'''@router.patch("/prospects/{prospect_id}")
def warehouse_update(prospect_id: str,
                     payload: dict = Body(default_factory=dict),
                     user: dict = Depends(get_current_user)):
    """Edit a prospect.

    OPEN while the record is under validation - that set exists to be filled
    in, and a password in front of backfilling would guarantee the backfilling
    never happens.

    PASSWORD-PROTECTED once validated. Somebody staked their name on those
    details and people are being told to prefer them, so changing one should be
    a deliberate act rather than a stray click.
    """
    from utils.deals_warehouse import update_prospect
    _code, name = _actor(user)
    changes = dict(payload or {})
    password = str(changes.pop("password", "") or "")
    try:
        rec = update_prospect(prospect_id, changes, by_name=name,
                              password=password)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_log("WAREHOUSE_EDIT", str(user.get("username", "") or ""),
              detail="%s: %s" % (prospect_id, ", ".join(sorted(changes))[:60]))
    return {"prospect": {k: rec.get(k) for k in
                         ("id", "name", "sector", "town", "contact_name",
                          "contact_phone", "contact_email", "notes",
                          "validated", "last_edited_at", "last_edited_by")}}


'''

TS_EDIT = r'''export async function updateProspect(
  id: string, changes: Record<string, unknown>, password = '',
): Promise<{ prospect: Record<string, unknown> }> {
  return postJson<{ prospect: Record<string, unknown> }, Record<string, unknown>>(
    `/warehouse/prospects/${encodeURIComponent(id)}`,
    password ? { ...changes, password } : changes, 'PATCH');
}
'''

TS_DELETE = r'''export async function deleteProspect(
  id: string, password = '',
): Promise<{ deleted: string }> {
  // Uses the existing postJson-with-method pattern rather than a new helper -
  // one way of issuing a DELETE is enough.
  const q = password ? `?password=${encodeURIComponent(password)}` : '';
  return postJson<{ deleted: string }, Record<string, never>>(
    `/warehouse/prospects/${encodeURIComponent(id)}${q}`,
    {} as Record<string, never>, 'DELETE');
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
  createProspect, archiveProspect, deleteProspect,
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
  const [tab, setTab] = useState<'validated' | 'working' | 'shelf' | 'mine'>('validated');
  const [shelves, setShelves] = useState<Record<string, WarehouseProspect[]>>({});
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState({ validated: 0 });
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
      if (tab !== 'mine') {
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

DETAIL_SRC = r'''// Prospect detail — everything known, before deciding whether to pursue.
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
'''


def main():
    apply = "--apply" in sys.argv
    for p in (MOD, API, APITS, SHELF, DETAIL):
        if not os.path.isfile(p):
            print("ABORT: %s not found - apply patch_cm2_matrix_ui.py first." % p)
            return 1

    mod = open(MOD, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if "def update_prospect(" in mod:
        print("ABORT: update_prospect already present - PW1 looks applied.")
        return 1
    if mod.count(MOD_ANCHOR) != 1:
        print("ABORT: validate anchor matched %d times." % mod.count(MOD_ANCHOR))
        return 1
    if ts.count(TS_ANCHOR) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(TS_ANCHOR))
        return 1

    mod = mod.replace(MOD_ANCHOR, EDITING + MOD_ANCHOR, 1)
    i = mod.index("def delete(prospect_id")
    j = mod.index("def archive(prospect_id")
    mod = mod[:i] + DELETE + mod[j:]

    k = api.index('@router.delete("/prospects/{prospect_id}")')
    l = api.index('@router.get("/completeness")')
    api = api[:k] + DELETE_EP + EDIT_EP + api[l:]

    ts = ts.replace(TS_ANCHOR, TS_EDIT + TS_ANCHOR, 1)
    m = ts.index("export async function deleteProspect(")
    n = ts.index("export async function archiveProspect(")
    ts = ts[:m] + TS_DELETE + ts[n:]
    print("  ok  editing, password gates, clients")

    # The asymmetry must be real, not decorative.
    if 'rec.get("validated") and password != protected_password()' not in EDITING:
        print("ABORT: a validated record can be edited without the password.")
        return 1
    if 'data[pid].get("validated") and password != protected_password()' not in DELETE:
        print("ABORT: a validated record can be deleted without the password.")
        return 1
    if "EDITABLE_FIELDS" not in EDITING:
        print("ABORT: the edit route writes arbitrary fields - a crafted")
        print("       request could flip `validated` or rewrite provenance.")
        return 1
    if "DEFAULT_PROTECTED_PASSWORD = \"Pendo\"" not in EDITING:
        print("ABORT: the default password is not the one that was asked for.")
        return 1
    if "warehouse_protected_password" not in EDITING:
        print("ABORT: the password is hardcoded - admin could not change it.")
        return 1
    # Friction only where it belongs.
    if "if (c?.validated)" not in DETAIL_SRC or "if (p.validated)" not in SHELF_SRC:
        print("ABORT: the password is being asked for unconditionally - that")
        print("       would put friction in front of backfilling.")
        return 1
    for name, blob in (("shelf", SHELF_SRC), ("detail", DETAIL_SRC)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    print("  ok  post-checks: asymmetric, field-limited, config-driven")

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

    print("")
    print("Password is 'Pendo'. To change it, set warehouse_protected_password")
    print("in pipeline settings - no release needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
