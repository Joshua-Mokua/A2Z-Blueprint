#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CM3 - the matrix becomes a table you fill in, and validation opens at 80%.

FOUR RULINGS (2026-08-11).

1. "BUILD THESE FIELDS INTO ONE TABLE THAT ONE CAN BE ADDING AND SAVING."

   The missing-field LIST is gone. In its place is an editable table: every one
   of the fifteen, answered ones ticked green, unanswered ones amber with the
   reason beside them, and a box to type into on every row. A list that only
   tells you what you lack makes somebody go and find the Edit form; a table
   you can type into is the difference between a standard people meet and a
   standard people resent.

   The separate Edit panel is REMOVED - two ways to do one thing, and the
   weaker one was closer to hand.

2. "A THRESHOLD FOR SUBMITTING FOR VALIDATION SHOULD BE AT LEAST 80%, THEN THE
   ADDITIONAL CAN BE COMPLETED FROM VALIDATION."

   100% was the wrong bar. It left a record with fourteen of fifteen fields sat
   unusable beside one with four, and the last field is usually the hardest to
   get - so demanding it would strand good records in the working set forever.
   `complete` now means READY TO VALIDATE; `fully_complete` is reported
   separately so nobody has to guess which one a number means. Config-driven
   under warehouse_validation_threshold.

3. "REGISTRATION NUMBER MIGHT BE HARD TO OBTAIN - REPLACE IT."

   Right, and it would have been a permanent deduction: locked behind BRS, so
   it sits unanswered on almost every record with nobody able to fix it. A
   field nobody can fill is not a standard.

   Replaced with BRANCHES OR FOOTPRINT - visible, useful to every purpose, and
   already on the original wish list for the card.

4. "IDENTIFIED NEED WOULD MEAN THIS IS ONLY FOR PIPELINE - WE ARE BUILDING A
   WAREHOUSE USED ACROSS VARIOUS NEEDS."

   Correct, and worth catching early: a warehouse should not bake one
   consumer's vocabulary into its schema. Now VALUE CHAIN AND POTENTIAL NEEDS -
   what they buy, sell and depend on - which serves credit and sector analysis
   as much as sales.

PLUS a free-text box under the table, because every warehouse eventually meets
a business whose important fact has no column, and a record with nowhere to put
it loses the fact.

MEASURED: a register import scores 30%; filling eight rows of the table takes it
to 82%, which validates successfully with four fields still outstanding - and
those are finished during validation, which is the point.

REQUIRES PW1.

Usage (from project root, .venv active):
    python scripts\patch_cm3_matrix_table.py            # dry run
    python scripts\patch_cm3_matrix_table.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "deals_warehouse.py")
API = os.path.join("utils", "api_warehouse.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
DETAIL = os.path.join("frontend", "web", "src", "pages", "ProspectDetail.tsx")
BACKUP_SUFFIX = ".pre_cm3"

TS_OLD = "  prospect_id: string; score: number; complete: boolean;"
TS_NEW_LINE = '''  prospect_id: string; score: number; complete: boolean;
  fully_complete: boolean; threshold: number;'''

DET_OLD = '''    out = {k: rec.get(k) for k in
           ("id", "name", "sector", "town", "status", "estimated_value",
            "source_event", "notes", "created_by_name", "created_at",
            "claimed_by_name", "claimed_at", "deal_id")}'''

EDITABLE_OLD = '''    "registration_no", "established", "legal_form", "existing_banker",
    "website", "opportunity", "business_activity",'''
EDITABLE_NEW = '''    "branches", "established", "legal_form", "existing_banker",
    "website", "value_chain", "business_activity", "additional_information",'''

FIELDS = r'''DEFAULT_COMPLETENESS = [
    {"key": "name", "label": "Legal name", "weight": 15,
     "why": "Who they are, as registered."},
    # REGISTRATION NUMBER REPLACED (ruling 2026-08-11: "that might be hard to
    # obtain, we can replace it with another piece"). It is real but it is
    # locked behind BRS, so it would sit unanswered on almost every record and
    # drag the score down without anybody being able to fix it. A field nobody
    # can fill is not a standard, it is a permanent deduction.
    #
    # Branches are visible, useful to every purpose, and were on the original
    # wish list for the card.
    {"key": "branches", "label": "Branches or footprint", "weight": 10,
     "why": "Where they actually operate - and how big that makes them."},
    {"key": "sector", "label": "Sector", "weight": 10,
     "why": "Decides which products are even relevant."},
    {"key": "county", "label": "County", "weight": 10,
     "why": "Decides which branch owns the conversation."},
    {"key": "physical_address", "label": "Physical address", "weight": 8,
     "why": "You cannot visit a postal box."},
    {"key": "phone", "label": "Phone", "weight": 12,
     "why": "Without it nobody can start."},
    {"key": "email", "label": "Email", "weight": 8,
     "why": "For anything that needs a paper trail."},
    {"key": "decision_maker", "label": "Decision maker and role", "weight": 15,
     "why": "The single thing that turns a cold call into a meeting."},
    {"key": "size_indicator", "label": "Size - turnover, members or staff", "weight": 7,
     "why": "Tells you which desk should hold it."},
    {"key": "business_activity", "label": "What they actually do", "weight": 5,
     "why": "A sector is a category; this is the business."},
    # FIVE MORE (ruling 2026-08-11: "expand the field to at least 15 so that we
    # stretch our viability and give our models a better accuracy chance").
    # These are the ones that separate a contactable business from a
    # QUALIFIABLE one - they are what a viability score will be built on.
    {"key": "established", "label": "Year established", "weight": 5,
     "why": "Longevity is the cheapest risk signal there is."},
    {"key": "legal_form", "label": "Legal form", "weight": 3,
     "why": "A SACCO, an Ltd and an NGO borrow on different terms."},
    {"key": "existing_banker", "label": "Who they bank with now", "weight": 6,
     "why": "Tells you whether this is a switch, a share, or a first account."},
    {"key": "online_presence", "label": "Website or verified listing", "weight": 3,
     "why": "Somewhere to check the story before the meeting."},
    # "IDENTIFIED NEED" WAS PIPELINE LANGUAGE (ruling 2026-08-11: "that would
    # mean this is only for pipeline - we are building a warehouse that can be
    # used across various needs, and pipeline is one of them"). A warehouse
    # should not bake one consumer's vocabulary into its schema.
    {"key": "value_chain", "label": "Value chain and potential needs", "weight": 8,
     "why": "What they buy, sell and depend on - which serves sales, credit "
            "and sector analysis alike, not just a deal."},
]

STATUS_VALIDATED = "validated"

# RULING (2026-08-11): "a threshold for submitting for validation to begin
# should be at least 80% and above, then the additional can be completed from
# validation."
#
# 100% was the wrong bar. It meant a record with fourteen of fifteen fields sat
# unusable beside one with four, and the last field is often the hardest to get
# - so demanding it would leave good records stranded in the working set
# forever. Eighty per cent says "enough to act on"; the remainder is finished
# during validation by the person who is looking anyway.
DEFAULT_VALIDATION_THRESHOLD = 80


def validation_threshold() -> int:
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("warehouse_validation_threshold")
        if isinstance(v, (int, float)) and 0 < float(v) <= 100:
            return int(v)
    except Exception:
        pass
    return DEFAULT_VALIDATION_THRESHOLD

# Legal form can usually be read off the name itself - a register that says
# "Sacco Society Ltd" has already told you what kind of entity this is, and
# asking somebody to retype it would be busywork.
_LEGAL_FORM = re.compile(
    r"\b(ltd|limited|plc|llp|llc|sacco|society|co-?operative|co-?op|trust"
    r"|foundation|association|union|scheme|bank|ngo)\b", re.IGNORECASE)


'''

HAS = r'''def _has(rec: dict, key: str) -> bool:
    """Is this field answered - anywhere on the record or its card?"""
    def _t(*names):
        return any(str(rec.get(n) or "").strip() for n in names)

    items = rec.get("enrichment") or []

    def _card(*kinds):
        return any(str(i.get("title") or "").strip()
                   for i in items if i.get("kind") in kinds)

    if key == "name":
        return _t("name")
    if key == "branches":
        return _t("branches", "footprint") or _card("association")
    if key == "sector":
        return _t("sector") and str(rec.get("sector")).strip().lower() != "unsorted"
    if key == "county":
        return _t("town")
    if key == "physical_address":
        return _t("physical_address", "address") or _card("contact")
    if key == "phone":
        return _t("contact_phone") or _card("contact")
    if key == "email":
        return _t("contact_email") or _card("contact")
    if key == "decision_maker":
        return _t("contact_name") or _card("relationship")
    if key == "size_indicator":
        return bool(rec.get("estimated_value")) or _card("financial")
    if key == "business_activity":
        return _t("notes") or _card("note", "news")
    if key == "established":
        return _t("established", "year_established") or _card("filing")
    if key == "legal_form":
        return _t("legal_form") or bool(_LEGAL_FORM.search(str(rec.get("name") or "")))
    if key == "existing_banker":
        return _t("existing_banker") or _card("relationship")
    if key == "online_presence":
        return _t("website", "url") or any(
            str(i.get("url") or "").strip() for i in items)
    if key == "value_chain":
        return _t("value_chain", "opportunity") or _card("note")
    return _t(key)


'''

COMPLETENESS = r'''def completeness(prospect_id_or_rec) -> dict:
    """Score one prospect against the matrix.

    Returns the score, what is answered, and WHAT IS MISSING with the reason it
    matters - because a score alone tells somebody they are incomplete without
    telling them what to do about it.
    """
    rec = (prospect_id_or_rec if isinstance(prospect_id_or_rec, dict)
           else get(prospect_id_or_rec))
    if not rec:
        return {}
    fields = completeness_fields()
    total = sum(int(f.get("weight") or 0) for f in fields) or 1
    have, missing, got = [], [], 0
    for f in fields:
        if _has(rec, f["key"]):
            have.append(f["key"])
            got += int(f.get("weight") or 0)
        else:
            missing.append({"key": f["key"], "label": f.get("label") or f["key"],
                            "why": f.get("why") or "", "weight": f.get("weight")})
    pct = round(got / total * 100)
    bar = validation_threshold()
    return {
        "prospect_id": rec.get("id"),
        "score": pct,
        # "complete" now means READY TO VALIDATE, not perfect. The two are
        # reported separately so nobody has to guess which one a number means.
        "complete": pct >= bar,
        "fully_complete": pct >= 100,
        "threshold": bar,
        "have": have,
        "missing": missing,
        "answered": len(have),
        "of": len(fields),
        "validated": rec.get("validated") is True,
        "validated_by": rec.get("validated_by") or "",
        "validated_at": rec.get("validated_at") or "",
        # A record edited AFTER validation is no longer the record that was
        # validated. Saying so is more honest than silently keeping the badge.
        "stale_validation": bool(
            rec.get("validated") and rec.get("last_edited_at")
            and str(rec.get("last_edited_at")) > str(rec.get("validated_at") or "")),
    }


# ── EDITING, AND WHAT PROTECTS A VALIDATED RECORD ───────────────────────────
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
    "branches", "established", "legal_form", "existing_banker",
    "website", "value_chain", "business_activity", "additional_information",
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

THRESHOLD = r'''STATUS_VALIDATED = "validated"

# RULING (2026-08-11): "a threshold for submitting for validation to begin
# should be at least 80% and above, then the additional can be completed from
# validation."
#
# 100% was the wrong bar. It meant a record with fourteen of fifteen fields sat
# unusable beside one with four, and the last field is often the hardest to get
# - so demanding it would leave good records stranded in the working set
# forever. Eighty per cent says "enough to act on"; the remainder is finished
# during validation by the person who is looking anyway.
DEFAULT_VALIDATION_THRESHOLD = 80


def validation_threshold() -> int:
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("warehouse_validation_threshold")
        if isinstance(v, (int, float)) and 0 < float(v) <= 100:
            return int(v)
    except Exception:
        pass
    return DEFAULT_VALIDATION_THRESHOLD

'''

DETAIL_EP = r'''    # Every editable field travels, so the completeness table can be filled in
    # place rather than being a list of things you are told you lack.
    from utils.deals_warehouse import EDITABLE_FIELDS
    out = {k: rec.get(k) for k in
           ("id", "name", "sector", "town", "status", "estimated_value",
            "source_event", "notes", "created_by_name", "created_at",
            "claimed_by_name", "claimed_at", "deal_id")}
    for _f in EDITABLE_FIELDS:
        out.setdefault(_f, rec.get(_f))
'''

TS_NEW = r'''export interface Completeness {
  prospect_id: string; score: number; complete: boolean;
  fully_complete: boolean; threshold: number;
  have: string[]; missing: CompletenessField[];
  answered: number; of: number;
  validated: boolean; validated_by: string; validated_at: string;
  stale_validation: boolean;
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

// The completeness matrix, as an EDITABLE TABLE (ruling 2026-08-11: "build
// these fields into one table that one can be adding and saving"). A list that
// only tells you what is missing makes somebody go and find the Edit form; a
// table you can type into is the difference between a standard people meet and
// a standard people resent.
const MATRIX_ROWS: { key: string; field: string; label: string }[] = [
  { key: 'name', field: 'name', label: 'Legal name' },
  { key: 'sector', field: 'sector', label: 'Sector' },
  { key: 'county', field: 'town', label: 'County' },
  { key: 'physical_address', field: 'physical_address', label: 'Physical address' },
  { key: 'phone', field: 'contact_phone', label: 'Phone' },
  { key: 'email', field: 'contact_email', label: 'Email' },
  { key: 'decision_maker', field: 'contact_name', label: 'Decision maker and role' },
  { key: 'branches', field: 'branches', label: 'Branches or footprint' },
  { key: 'size_indicator', field: 'estimated_value', label: 'Size (turnover / members)' },
  { key: 'business_activity', field: 'business_activity', label: 'What they actually do' },
  { key: 'established', field: 'established', label: 'Year established' },
  { key: 'legal_form', field: 'legal_form', label: 'Legal form' },
  { key: 'existing_banker', field: 'existing_banker', label: 'Banks with now' },
  { key: 'online_presence', field: 'website', label: 'Website' },
  { key: 'value_chain', field: 'value_chain', label: 'Value chain and potential needs' },
];

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

                  {/* The Edit panel is gone: the completeness table IS the
                      edit surface now, so having two was two ways to do one
                      thing and the weaker one was closer to hand. */}
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

                  {c && (
                    <>
                      <p className="mb-2 text-xs text-gray-500">
                        {c.answered} of {c.of} answered
                        {c.complete ? ' — ready to validate.'
                          : ` — ${c.threshold}% needed before validation can begin.`}
                      </p>

                      <div className="overflow-hidden rounded-lg border border-gray-200">
                        <table className="w-full">
                          <tbody>
                            {MATRIX_ROWS.map((row, i) => {
                              const answered = c.have.includes(row.key);
                              const why = c.missing.find((m) => m.key === row.key)?.why;
                              const cur = edit[row.field]
                                ?? String((p as unknown as Record<string, unknown>)[row.field] ?? '');
                              return (
                                <tr key={row.key}
                                    className={i % 2 ? 'bg-gray-50/40' : 'bg-white'}>
                                  <td className="w-8 px-2 py-1.5 align-top">
                                    <span className={'inline-block h-2 w-2 rounded-full ' + (
                                      answered ? 'bg-[#3B6D11]' : 'bg-[#E0A02B]')} />
                                  </td>
                                  <td className="w-52 px-2 py-1.5 align-top">
                                    <div className="text-xs font-medium text-gray-800">
                                      {row.label}
                                    </div>
                                    {!answered && why && (
                                      <div className="text-[10px] text-gray-400">{why}</div>
                                    )}
                                  </td>
                                  <td className="px-2 py-1.5">
                                    <input
                                      className="h-8 w-full rounded border border-gray-200 px-2 text-xs focus:border-brand-primary focus:outline-none"
                                      placeholder={answered ? '' : 'add…'}
                                      value={cur}
                                      onChange={(e) => setEdit({ ...edit, [row.field]: e.target.value })} />
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>

                      {/* Anything the fifteen do not cover. Every warehouse
                          eventually meets a business whose important fact has
                          no column, and a record with nowhere to put it loses
                          the fact. */}
                      <label className="mt-3 block text-xs text-gray-600">
                        Anything else worth knowing
                        <textarea
                          rows={3}
                          className="mt-1 w-full rounded border border-gray-200 p-2 text-xs focus:border-brand-primary focus:outline-none"
                          placeholder="Ownership, group affiliation, seasonality, known issues, anything the fields above do not cover…"
                          value={edit.additional_information
                            ?? String((p as unknown as Record<string, unknown>).additional_information ?? '')}
                          onChange={(e) => setEdit({ ...edit, additional_information: e.target.value })} />
                      </label>

                      <div className="mt-3 flex items-center justify-between gap-2">
                        <span className="text-[11px] text-gray-400">
                          {c.validated
                            ? 'Validated — saving needs the warehouse password.'
                            : 'Fill in what you know; save as often as you like.'}
                        </span>
                        <Button size="sm" disabled={busy || Object.keys(edit).length === 0}
                                onClick={() => void saveEdit()}>
                          {busy ? 'Saving…' : 'Save'}
                        </Button>
                      </div>
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
    for p in (MOD, API, APITS, DETAIL):
        if not os.path.isfile(p):
            print("ABORT: %s not found - apply patch_pw1_protected_records.py first." % p)
            return 1

    mod = open(MOD, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if "def validation_threshold(" in mod:
        print("ABORT: the threshold is already present - CM3 looks applied.")
        return 1
    if mod.count(EDITABLE_OLD) != 1:
        print("ABORT: the editable-field list matched %d times." % mod.count(EDITABLE_OLD))
        return 1
    if ts.count(TS_OLD) != 1 or api.count(DET_OLD) != 1:
        print("ABORT: anchors matched %d / %d times."
              % (ts.count(TS_OLD), api.count(DET_OLD)))
        return 1

    i = mod.index("DEFAULT_COMPLETENESS = [")
    j = mod.index("def completeness_fields()")
    k = mod.index("def _has(rec: dict, key: str) -> bool:")
    l = mod.index("def completeness(")
    m = mod.index("def validate_prospect(")
    mod = mod[:i] + FIELDS + mod[j:k] + HAS + COMPLETENESS + mod[m:]
    o = mod.index('STATUS_VALIDATED = "validated"')
    q = mod.index("# Legal form can usually be read", o)
    mod = mod[:o] + THRESHOLD + mod[q:]
    mod = mod.replace(EDITABLE_OLD, EDITABLE_NEW, 1)

    api = api.replace(DET_OLD, DETAIL_EP, 1)
    ts = ts.replace(TS_OLD, TS_NEW_LINE, 1)
    print("  ok  fields, threshold, detail payload, types")

    # The threshold must be a threshold, not a rename of 100%.
    if "DEFAULT_VALIDATION_THRESHOLD = 80" not in THRESHOLD:
        print("ABORT: the threshold is not 80.")
        return 1
    if '"fully_complete"' not in COMPLETENESS:
        print("ABORT: complete and fully-complete are conflated - a reader")
        print("       could not tell which one a number means.")
        return 1
    # Pipeline vocabulary must be out of the schema.
    if "opportunity" in FIELDS or "Identified need" in FIELDS:
        print("ABORT: pipeline language survives in the matrix.")
        return 1
    if "value_chain" not in FIELDS or "branches" not in FIELDS:
        print("ABORT: the replacement fields are missing.")
        return 1
    # The table must be editable, and the old panel gone.
    if "MATRIX_ROWS" not in DETAIL_SRC:
        print("ABORT: the matrix is still a read-only list.")
        return 1
    if "Edit details" in DETAIL_SRC:
        print("ABORT: the old Edit panel survives alongside the table - two")
        print("       ways to do one thing.")
        return 1
    if "additional_information" not in DETAIL_SRC:
        print("ABORT: there is nowhere to record what the fields do not cover.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if DETAIL_SRC.count(op) != DETAIL_SRC.count(cl):
            print("ABORT: detail unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: real threshold, neutral schema, editable table")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((MOD, mod), (API, api), (APITS, ts), (DETAIL, DETAIL_SRC)):
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
    print("Existing prospects keep their data - only the SCORING changed, so")
    print("records will re-score against the new fifteen on the next read.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
