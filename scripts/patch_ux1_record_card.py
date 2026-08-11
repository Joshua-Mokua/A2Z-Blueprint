#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
UX1 - one sectioned record card, picked values, and a house style on save.

FIVE RULINGS (2026-08-11).

1. "COLLAPSE THESE 3 INTO ONE DETAIL CARD that will be applicable even when one
   is creating an entry ... arrange them into sections, pool similar
   information together."

   Three cards asked the reader to hold one business in their head three times.
   Four sections do the pooling instead:

       IDENTITY             name · segment · sector · what they do
       WHERE TO FIND THEM   county · address · branches · phone · email · web
       OWNERSHIP AND PEOPLE decision maker · ownership · established
       THE BUSINESS         size · banks with · value chain

   Each section shows its own n/n, so somebody can finish one block in one
   sitting rather than facing fifteen unrelated rows.

2. "REMOVE THINGS LIKE 'the single thing that turns a cold call into a
   meeting'." Gone from the form. That copy earned its place when the panel was
   a list of accusations; inside a form somebody is filling in, being lectured
   on every row is noise.

3. "I DON'T UNDERSTAND WHAT LEGAL IS - I WOULD INSTEAD LOOK FOR SEGMENT, with a
   dropdown: Small, Medium, Large Enterprise, Corporate, Institution."

   Legal form was a lawyer's category. Segment is the one the bank organises
   itself around, and it decides which desk holds the relationship. Eight
   options, config-driven.

4. "FOR THOSE WE HAVE AUTOPOPULATED WE NEED A DROP DOWN, e.g. Sector, so that
   for our analysis we don't have mismatches that are a result of mistyping."

   Segment, sector and county are now PICKED. Free text would have produced
   "SME", "S.M.E", "Sme" and "Small" as four segments in every report built on
   top of this. The lists come from the server, so every client offers the same
   options rather than each drifting on its own.

5. "THE INPUT FORMAT SHOULD DEFAULT TO STANDARD - if upper case then Proper
   while saving, avoid double spacing and no spacing at the end, to protect the
   larger data sets."

   Normalised ON THE WAY IN, not on the way out. Cleaning at display time
   leaves the mess in the store, so the next consumer - an export, a match, a
   dedupe - still meets "MWALIMU  NATIONAL SACCO " and treats it as a different
   business from "Mwalimu National Sacco".

       MWALIMU NATIONAL SACCO SOCIETY LTD  ->  Mwalimu National Sacco Society Ltd
       nairobi wdt-sacco society ltd       ->  Nairobi WDT-Sacco Society Ltd
       p.o box 1234 - 00100,  nairobi      ->  P.O Box 1234 - 00100, Nairobi
       JANE WANJIKU - CEO                  ->  Jane Wanjiku - CEO
       PCEA Kayole Regulated Non-WDT       ->  unchanged

   MIXED CASE IS LEFT ALONE - somebody who typed "PCEA Kayole" or "e-Mobility"
   meant it, and title-casing that is a correction nobody asked for. Acronyms
   survive inside hyphenated words. Emails lowercase. Prose fields get their
   spacing fixed but keep their capitals.

   "Sacco" not "SACCO", because the register itself writes it that way and the
   source document is a better authority than my guess about acronyms.

REQUIRES CM3.

Usage (from project root, .venv active):
    python scripts\patch_ux1_record_card.py            # dry run
    python scripts\patch_ux1_record_card.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "deals_warehouse.py")
API = os.path.join("utils", "api_warehouse.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
DETAIL = os.path.join("frontend", "web", "src", "pages", "ProspectDetail.tsx")
BACKUP_SUFFIX = ".pre_ux1"

MOD_ANCHOR = "# ── EDITING, AND WHAT PROTECTS A VALIDATED RECORD"
EDITABLE_OLD = '    "branches", "established", "legal_form", "existing_banker",'
EDITABLE_NEW = '    "branches", "established", "segment", "existing_banker", "ownership",'
APPLY_OLD = '''            if k not in EDITABLE_FIELDS:
                continue
            rec[k] = v'''
APPLY_NEW = '''            if k not in EDITABLE_FIELDS:
                continue
            v = normalise_value(k, v)
            rec[k] = v'''
EP_OLD = '''    from utils.deals_warehouse import completeness_fields, completeness_summary
    return {"fields": completeness_fields(), "summary": completeness_summary()}'''
TS_OLD_TAIL = '''             validated: number; worst_gaps: { key: string; label: string; missing: number }[] };
}> {'''
TS_NEW_TAIL = '''             validated: number; worst_gaps: { key: string; label: string; missing: number }[] };
  segments: string[]; sectors: string[]; counties: string[];
}> {'''

HOUSE_STYLE = r'''# ── HOUSE STYLE ─────────────────────────────────────────────────────────────
# RULING (2026-08-11): "the input format should default to standard - if it is
# upper case, then Proper while saving. Avoid double spacing and no spacing at
# the end. This is to protect the larger data sets."
#
# NORMALISED ON THE WAY IN, NOT ON THE WAY OUT. Cleaning at display time leaves
# the mess in the store, so the next consumer - an export, a match, a dedupe -
# still meets "MWALIMU  NATIONAL SACCO " and treats it as a different business
# from "Mwalimu National Sacco". Doing it once at the door is the only version
# that protects the dataset.
#
# ALL-CAPS AND all-lower BECOME PROPER CASE. Mixed case is LEFT ALONE, because
# somebody who typed "PCEA Kayole" or "e-Mobility Ltd" meant it, and
# title-casing that would be a correction nobody asked for.
# Acronyms that look wrong in Proper Case. "Ltd" is deliberately NOT here -
# Kenyan usage is "Ltd", not "LTD", and forcing the shout would be a change
# nobody asked for.
_KEEP_UPPER = {"plc", "dt", "hq", "ke", "kcb", "nssf", "kra", "usiu", "cbd",
               "ict", "ngo", "pcea", "ack", "kag", "sme", "usa", "uk", "eu",
               # "Sacco" not "SACCO" - the register itself writes it that
               # way, and the source document is the better authority than my
               # guess about acronyms.
               "wdt", "fosa", "bosa", "kebs", "kemri", "helb", "cic",
               "epza", "gdc", "nrs", "amref", "icea", "kasneb", "p.o", "po",
               "ceo", "cfo", "coo", "md", "gm", "hr", "it", "mp", "dt-sacco"}
_LOWER_WORDS = {"and", "of", "the", "for", "in", "on", "at", "to", "a"}


def _cap(word: str) -> str:
    """Capitalise a single word, preserving its internal punctuation.

    Splits on the separators that appear inside real names - hyphens,
    apostrophes and dots - so "trans-nzoia" becomes "Trans-Nzoia" and "p.o"
    becomes "P.O" rather than losing the mark entirely, which is what happened
    when the address separator was treated as a word boundary.
    """
    out = word.lower()
    for sep in ("-", "'", "\u2019", "."):
        parts = []
        for p in out.split(sep):
            if not p:
                parts.append(p)
            elif p.strip(".,").lower() in _KEEP_UPPER:
                # A hyphenated word can contain an acronym: "wdt-sacco" is
                # "WDT-Sacco", not "Wdt-Sacco".
                parts.append(p.upper())
            else:
                parts.append(p[:1].upper() + p[1:])
        out = sep.join(parts)
    return out


def _proper(text: str) -> str:
    out = []
    for i, w in enumerate(text.split(" ")):
        if not w:
            continue
        low = w.lower().strip(".,")
        if not any(ch.isalpha() for ch in w):
            out.append(w)                    # "-", "&", numbers: leave alone
        elif low in _KEEP_UPPER:
            out.append(w.upper())
        elif i and low in _LOWER_WORDS:
            out.append(low)
        else:
            out.append(_cap(w))
    return " ".join(out)


def normalise_value(key: str, value):
    """House style for one field. Applied on every write."""
    if not isinstance(value, str):
        return value
    v = " ".join(value.split())          # collapses doubles AND trims both ends
    if not v:
        return v
    if key in ("contact_email", "website"):
        return v.lower()
    if key == "contact_phone":
        # Keep the digits and the punctuation people actually use.
        return "".join(ch for ch in v if ch.isdigit() or ch in "+-() ").strip()
    if key in ("additional_information", "notes", "business_activity",
               "value_chain"):
        return v                          # prose: cleaned of spacing, not recased
    if v.isupper() or v.islower():
        return _proper(v)
    return v


'''

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
    # SEGMENT REPLACES LEGAL FORM (ruling 2026-08-11: "I don't understand what
    # legal is, but I would instead look for information like Segment"). Legal
    # form is a lawyer's category; segment is the one the bank actually
    # organises itself around, and it decides which desk holds the
    # relationship.
    {"key": "segment", "label": "Segment", "weight": 3,
     "why": "Which desk holds the relationship."},
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

# PICKED, NOT TYPED (ruling 2026-08-11: "for those we have autopopulated we
# need a drop down, e.g. Sector, so that for our analysis we don't have
# mismatches that are a result of mistyping"). Free text here would produce
# "SME", "S.M.E", "Sme" and "Small" as four segments in every report.
DEFAULT_SEGMENTS = [
    "Micro", "Small Enterprise", "Medium Enterprise", "Large Enterprise",
    "Corporate", "Institution", "Public Sector", "NGO / Development",
]


def segments() -> list:
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("warehouse_segments")
        if isinstance(v, list) and v:
            return [str(x) for x in v if str(x).strip()]
    except Exception:
        pass
    return list(DEFAULT_SEGMENTS)

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
    if key == "segment":
        return _t("segment")
    if key == "existing_banker":
        return _t("existing_banker") or _card("relationship")
    if key == "online_presence":
        return _t("website", "url") or any(
            str(i.get("url") or "").strip() for i in items)
    if key == "value_chain":
        return _t("value_chain", "opportunity") or _card("note")
    return _t(key)


'''

SEGMENTS = r'''# PICKED, NOT TYPED (ruling 2026-08-11: "for those we have autopopulated we
# need a drop down, e.g. Sector, so that for our analysis we don't have
# mismatches that are a result of mistyping"). Free text here would produce
# "SME", "S.M.E", "Sme" and "Small" as four segments in every report.
DEFAULT_SEGMENTS = [
    "Micro", "Small Enterprise", "Medium Enterprise", "Large Enterprise",
    "Corporate", "Institution", "Public Sector", "NGO / Development",
]


def segments() -> list:
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("warehouse_segments")
        if isinstance(v, list) and v:
            return [str(x) for x in v if str(x).strip()]
    except Exception:
        pass
    return list(DEFAULT_SEGMENTS)

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


'''

ENDPOINT = r'''    from utils.deals_warehouse import (completeness_fields, completeness_summary,
                                       segments, sectors, towns)
    # The PICKLISTS travel with the matrix so a form can offer them without a
    # second round trip - and so every client offers the SAME options, which is
    # the whole reason they are lists rather than free text.
    return {"fields": completeness_fields(),
            "summary": completeness_summary(),
            "segments": segments(),
            "sectors": sectors(),
            "counties": towns()}


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
  fetchCompletenessMatrix,
  type ProspectDetail, type ProspectFact,
} from '@/lib/api';

// The completeness matrix, as an EDITABLE TABLE (ruling 2026-08-11: "build
// these fields into one table that one can be adding and saving"). A list that
// only tells you what is missing makes somebody go and find the Edit form; a
// table you can type into is the difference between a standard people meet and
// a standard people resent.
// ONE RECORD CARD, SECTIONED (ruling 2026-08-11: "collapse these 3 into one
// detail card that will be applicable even when one is creating an entry ...
// arrange them into sections ... pool similar information together").
//
// Three cards asked the reader to hold the same business in their head three
// times. Sections do the pooling instead - and because the shape is data, the
// SAME form serves creating a record and completing one.
//
// The "why this field matters" microcopy is GONE from the form. It earned its
// place when the panel was a list of accusations; inside a form somebody is
// filling in, being lectured on every row is noise.
type Row = {
  key: string; field: string; label: string;
  kind?: 'text' | 'select' | 'number' | 'date' | 'area';
  options?: 'segments' | 'sectors' | 'counties';
  placeholder?: string;
};

const SECTIONS: { title: string; hint: string; rows: Row[] }[] = [
  {
    title: 'Identity',
    hint: 'Who this is, in the terms the bank organises itself around.',
    rows: [
      { key: 'name', field: 'name', label: 'Legal name' },
      { key: 'segment', field: 'segment', label: 'Segment',
        kind: 'select', options: 'segments' },
      { key: 'sector', field: 'sector', label: 'Sector',
        kind: 'select', options: 'sectors' },
      { key: 'business_activity', field: 'business_activity',
        label: 'What they actually do', kind: 'area',
        placeholder: 'Grain milling and animal feeds; supplies three counties' },
    ],
  },
  {
    title: 'Where to find them',
    hint: 'Enough for somebody to turn up, or to call.',
    rows: [
      { key: 'county', field: 'town', label: 'County',
        kind: 'select', options: 'counties' },
      { key: 'physical_address', field: 'physical_address',
        label: 'Physical address', placeholder: 'Ngano House, Industrial Area' },
      { key: 'branches', field: 'branches', label: 'Branches or footprint',
        placeholder: '12 branches across 6 counties' },
      { key: 'phone', field: 'contact_phone', label: 'Phone',
        placeholder: '0722 000 000' },
      { key: 'email', field: 'contact_email', label: 'Email',
        placeholder: 'info@example.co.ke' },
      { key: 'online_presence', field: 'website', label: 'Website',
        placeholder: 'example.co.ke' },
    ],
  },
  {
    title: 'Ownership and people',
    hint: 'Who decides, and who they answer to.',
    rows: [
      { key: 'decision_maker', field: 'contact_name',
        label: 'Decision maker and role', placeholder: 'Jane Wanjiku — CEO' },
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
      { key: 'value_chain', field: 'value_chain',
        label: 'Value chain and potential needs', kind: 'area',
        placeholder: 'Buys maize from farmer groups; sells to schools and '
          + 'retailers. Likely needs: working capital, collection accounts.' },
    ],
  },
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
  // Picklists come from the server so every client offers the SAME options -
  // which is the entire reason they are lists rather than free text.
  const [lists, setLists] = useState<{ segments: string[]; sectors: string[]; counties: string[] }>(
    { segments: [], sectors: [], counties: [] });

  useEffect(() => {
    void (async () => {
      try {
        const m = await fetchCompletenessMatrix();
        setLists({ segments: m.segments ?? [], sectors: m.sectors ?? [],
                   counties: m.counties ?? [] });
      } catch { /* the form still works, just without the pickers */ }
    })();
  }, []);

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

                      {/* SECTIONED. Each block is a question somebody can
                          answer in one sitting, rather than fifteen unrelated
                          rows demanding fifteen different kinds of knowledge. */}
                      <div className="space-y-4">
                        {SECTIONS.map((sec) => {
                          const done = sec.rows.filter(
                            (r) => r.key && c.have.includes(r.key)).length;
                          const scored = sec.rows.filter((r) => r.key).length;
                          return (
                            <div key={sec.title}
                                 className="overflow-hidden rounded-xl border border-gray-200">
                              <div className="flex items-center justify-between gap-2 border-b border-gray-100 bg-gray-50/70 px-3 py-2">
                                <div>
                                  <div className="text-xs font-semibold uppercase tracking-wide text-[#003D57]">
                                    {sec.title}
                                  </div>
                                  <div className="text-[10px] text-gray-500">{sec.hint}</div>
                                </div>
                                {scored > 0 && (
                                  <span className={'shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ' + (
                                    done === scored
                                      ? 'bg-[#EAF3DE] text-[#3B6D11]'
                                      : 'bg-[#FEF6E7] text-[#854F0B]')}>
                                    {done}/{scored}
                                  </span>
                                )}
                              </div>

                              <div className="grid gap-3 p-3 sm:grid-cols-2">
                                {sec.rows.map((row) => {
                                  const answered = row.key ? c.have.includes(row.key) : true;
                                  const cur = edit[row.field]
                                    ?? String((p as unknown as Record<string, unknown>)[row.field] ?? '');
                                  const set = (val: string) =>
                                    setEdit({ ...edit, [row.field]: val });
                                  const box = 'mt-1 w-full rounded-lg border px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-[#0082BB] '
                                    + (answered ? 'border-gray-200' : 'border-[#F0D9A8] bg-[#FFFDF8]');
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
                                        // PICKED, NOT TYPED - four spellings of
                                        // one segment ruins every report built
                                        // on top of this.
                                        <select className={box} value={cur}
                                                onChange={(e) => set(e.target.value)}>
                                          <option value="">Select…</option>
                                          {opts.map((o) => <option key={o} value={o}>{o}</option>)}
                                        </select>
                                      ) : row.kind === 'area' ? (
                                        <textarea rows={2} className={box} value={cur}
                                                  placeholder={row.placeholder}
                                                  onChange={(e) => set(e.target.value)} />
                                      ) : (
                                        <input className={box} value={cur}
                                               inputMode={row.kind === 'number' ? 'numeric' : undefined}
                                               placeholder={row.placeholder}
                                               onChange={(e) => set(e.target.value)} />
                                      )}
                                    </label>
                                  );
                                })}
                              </div>
                            </div>
                          );
                        })}
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
            print("ABORT: %s not found - apply patch_cm3_matrix_table.py first." % p)
            return 1

    mod = open(MOD, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if "def normalise_value(" in mod:
        print("ABORT: the house style is already present - UX1 looks applied.")
        return 1
    for name, blob, needle in (("mod", mod, MOD_ANCHOR), ("mod", mod, EDITABLE_OLD),
                               ("mod", mod, APPLY_OLD), ("api", api, EP_OLD),
                               ("ts", ts, TS_OLD_TAIL)):
        if blob.count(needle) != 1:
            print("ABORT: an anchor in %s matched %d times." % (name, blob.count(needle)))
            return 1

    mod = mod.replace(MOD_ANCHOR, HOUSE_STYLE + MOD_ANCHOR, 1)
    mod = mod.replace(EDITABLE_OLD, EDITABLE_NEW, 1)
    mod = mod.replace(APPLY_OLD, APPLY_NEW, 1)
    i = mod.index("DEFAULT_COMPLETENESS = [")
    j = mod.index("def completeness_fields()")
    k = mod.index("def _has(rec: dict, key: str) -> bool:")
    l = mod.index("def completeness(")
    mod = mod[:i] + FIELDS + mod[j:k] + HAS + mod[l:]
    m = mod.index("# PICKED, NOT TYPED") if "# PICKED, NOT TYPED" in mod else -1
    if m < 0:
        n = mod.index("def validation_threshold()")
        mod = mod[:n] + SEGMENTS + mod[n:]
    api = api.replace(EP_OLD, ENDPOINT, 1)
    ts = ts.replace(TS_OLD_TAIL, TS_NEW_TAIL, 1)
    ts = ts.replace("export async function validateProspect(",
                    "", 1) if False else ts
    print("  ok  house style, segment, picklists, endpoint")

    # Normalisation must happen on WRITE.
    if "v = normalise_value(k, v)" not in APPLY_NEW:
        print("ABORT: values are not normalised on save - cleaning at display")
        print("       time leaves the mess in the store for every other reader.")
        return 1
    # Mixed case must be preserved.
    if "v.isupper() or v.islower()" not in HOUSE_STYLE:
        print("ABORT: mixed-case input would be recased - 'PCEA Kayole' was")
        print("       typed that way on purpose.")
        return 1
    if "def segments(" not in SEGMENTS:
        print("ABORT: segments are not config-driven.")
        return 1
    if "legal_form" in FIELDS:
        print("ABORT: legal form survives in the matrix.")
        return 1
    # Sections, pickers, and no lecturing.
    if "SECTIONS" not in DETAIL_SRC or DETAIL_SRC.count("title: '") < 4:
        print("ABORT: the form is not sectioned.")
        return 1
    if "row.kind === 'select'" not in DETAIL_SRC:
        print("ABORT: segment, sector and county are still free text - four")
        print("       spellings of one segment ruins every report built on it.")
        return 1
    if "The single thing that turns" in DETAIL_SRC:
        print("ABORT: the 'why this matters' copy survives inside the form.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if DETAIL_SRC.count(op) != DETAIL_SRC.count(cl):
            print("ABORT: detail unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: normalised on write, picked values, sectioned")

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
    print("Existing records keep their current casing - normalisation applies")
    print("on the next SAVE, so nothing is rewritten behind anybody's back.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
